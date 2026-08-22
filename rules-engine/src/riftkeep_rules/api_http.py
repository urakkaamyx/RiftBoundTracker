from __future__ import annotations

import ipaddress
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .product_api import API_VERSION, ProductApiError, ProductApiService

MAX_BODY_BYTES = 65_536
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
STATIC_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


def _is_loopback_host(host: str) -> bool:
    value = (host or "").strip().lower()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


class HttpRuntimeMetrics:
    """Thread-safe bounded counters; never stores request paths or question text."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._requests = 0
        self._errors = 0
        self._active = 0
        self._max_active = 0
        self._status_counts: dict[int, int] = {}

    def begin(self) -> str:
        with self._lock:
            self._sequence += 1
            self._requests += 1
            self._active += 1
            self._max_active = max(self._max_active, self._active)
            return f"rk-{self._sequence:08d}"

    def finish(self, status: int | None) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            code = int(status or 500)
            self._status_counts[code] = self._status_counts.get(code, 0) + 1
            if code >= 400:
                self._errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests": self._requests,
                "errors": self._errors,
                "active": self._active,
                "maxConcurrent": self._max_active,
                "statusCounts": {str(k): v for k, v in sorted(self._status_counts.items())},
                "storesRequestContent": False,
            }


class ProductApiHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], service: ProductApiService):
        self.service = service
        self.runtime_metrics = HttpRuntimeMetrics()
        super().__init__(server_address, handler)


class ProductApiHandler(BaseHTTPRequestHandler):
    server_version = "RiftKeepRulesAPI/1"
    sys_version = ""

    @property
    def service(self) -> ProductApiService:
        return self.server.service  # type: ignore[attr-defined]

    @property
    def runtime_metrics(self) -> HttpRuntimeMetrics:
        return self.server.runtime_metrics  # type: ignore[attr-defined]

    def _begin_request(self) -> None:
        self._request_id = self.runtime_metrics.begin()
        self._response_status: int | None = None

    def _finish_request(self) -> None:
        self.runtime_metrics.finish(self._response_status)

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        # Product applications may wrap the server with their own logging. Avoid
        # leaking questions/paths to stderr by default.
        return

    def _json(self, status: int, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._response_status = int(status)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-RiftKeep-API-Version", API_VERSION)
        self.send_header("X-RiftKeep-Request-Id", getattr(self, "_request_id", "rk-untracked"))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, err: ProductApiError) -> None:
        self._json(err.status, err.to_dict())

    def _static(self, path: str) -> bool:
        """Serve the small audited M15 UI from an exact route allowlist.

        No path supplied by the request is joined onto the filesystem.  This keeps
        traversal/symlink behavior outside the product surface and makes the static
        contract independently auditable.
        """
        route = STATIC_ROUTES.get(path)
        if route is None:
            return False
        filename, content_type = route
        target = self.service.root / "web" / filename
        if not target.is_file():
            raise ProductApiError(404, "ui_asset_missing", "RiftKeep UI asset is unavailable.", {"path": path})
        raw = target.read_bytes()
        self._response_status = 200
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-RiftKeep-API-Version", API_VERSION)
        self.send_header("X-RiftKeep-Request-Id", getattr(self, "_request_id", "rk-untracked"))
        for key, value in STATIC_SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)
        return True

    def _segments(self) -> tuple[list[str], dict[str, list[str]]]:
        split = urlsplit(self.path)
        if len(split.path) > 2048 or len(split.query) > 4096:
            raise ProductApiError(414, "uri_too_long", "Request URI exceeds the supported length.")
        segments = [unquote(x) for x in split.path.split("/") if x]
        return segments, parse_qs(split.query, keep_blank_values=True, max_num_fields=64)

    @staticmethod
    def _reject_unknown_query(query: dict[str, list[str]], allowed: set[str]) -> None:
        unknown = sorted(set(query) - allowed)
        if unknown:
            raise ProductApiError(400, "unknown_query_parameters", "Request contains unsupported query parameters.", {"parameters": unknown})

    @staticmethod
    def _one(query: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
        vals = query.get(key)
        if not vals:
            return default
        if len(vals) != 1:
            raise ProductApiError(400, "duplicate_parameter", f"{key} may be supplied only once.", {"parameter": key})
        return vals[0]

    def _route_get(self) -> dict[str, Any]:
        seg, query = self._segments()
        if seg == ["v1", "ask"]:
            raise ProductApiError(405, "method_not_allowed", "Use POST for /v1/ask.", {"allowed": ["POST"]})
        if seg == ["v1", "status"]:
            self._reject_unknown_query(query, set())
            return self.service.status()
        if seg == ["v1", "sources"]:
            self._reject_unknown_query(query, set())
            return self.service.sources()
        if seg == ["v1", "search"]:
            self._reject_unknown_query(query, {"q", "kind", "limit", "offset"})
            q = self._one(query, "q")
            if q is None:
                raise ProductApiError(400, "missing_parameter", "q is required.", {"parameter": "q"})
            raw_kind = self._one(query, "kind")
            kinds = None if raw_kind is None or raw_kind == "" else [x.strip() for x in raw_kind.split(",") if x.strip()]
            return self.service.search(q, kinds=kinds, limit=self._one(query, "limit", "20"), offset=self._one(query, "offset", "0"))
        if len(seg) == 4 and seg[:2] == ["v1", "rules"]:
            self._reject_unknown_query(query, set())
            return self.service.get_rule(seg[3], family=seg[2])
        if len(seg) == 3 and seg[:2] == ["v1", "cards"]:
            self._reject_unknown_query(query, set())
            return self.service.get_card(seg[2])
        if len(seg) == 3 and seg[:2] == ["v1", "evidence"]:
            self._reject_unknown_query(query, set())
            return self.service.get_evidence(seg[2])
        if seg == ["v1", "changes"]:
            self._reject_unknown_query(query, {"family", "sourceId"})
            family = self._one(query, "family")
            if family is None:
                raise ProductApiError(400, "missing_parameter", "family is required.", {"parameter": "family"})
            return self.service.changes(family, source_id=self._one(query, "sourceId"))
        raise ProductApiError(404, "route_not_found", "API route was not found.", {"path": urlsplit(self.path).path})

    def _read_json_body(self) -> dict[str, Any]:
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise ProductApiError(415, "unsupported_media_type", "Content-Type must be application/json.")
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            raise ProductApiError(411, "content_length_required", "Content-Length is required.")
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise ProductApiError(400, "invalid_content_length", "Content-Length must be an integer.") from exc
        if length < 0:
            raise ProductApiError(400, "invalid_content_length", "Content-Length cannot be negative.")
        if length > MAX_BODY_BYTES:
            raise ProductApiError(413, "payload_too_large", "Request body exceeds the supported size.", {"maximumBytes": MAX_BODY_BYTES})
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductApiError(400, "invalid_json", "Request body must be valid UTF-8 JSON.") from exc
        if not isinstance(body, dict):
            raise ProductApiError(400, "invalid_json_shape", "Request body must be a JSON object.")
        return body

    def _route_post(self) -> dict[str, Any]:
        split = urlsplit(self.path)
        if split.path in STATIC_ROUTES:
            raise ProductApiError(405, "method_not_allowed", "Use GET for RiftKeep UI assets.", {"allowed": ["GET"]})
        seg, _query = self._segments()
        if seg != ["v1", "ask"]:
            known_get = (seg == ["v1", "status"] or seg == ["v1", "sources"] or seg == ["v1", "search"] or seg == ["v1", "changes"] or (len(seg) >= 2 and seg[:2] in (["v1", "rules"], ["v1", "cards"], ["v1", "evidence"])))
            if known_get:
                raise ProductApiError(405, "method_not_allowed", "Use GET for this API route.", {"allowed": ["GET"]})
            raise ProductApiError(404, "route_not_found", "API route was not found.", {"path": urlsplit(self.path).path})
        body = self._read_json_body()
        unknown = sorted(set(body) - {"question"})
        if unknown:
            raise ProductApiError(400, "unknown_fields", "Request body contains unsupported fields.", {"fields": unknown})
        if "question" not in body:
            raise ProductApiError(400, "missing_field", "question is required.", {"field": "question"})
        return self.service.ask(body["question"])

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        self._begin_request()
        try:
            try:
                split = urlsplit(self.path)
                if not split.query and self._static(split.path):
                    return
                self._json(200, self._route_get())
            except ProductApiError as err:
                self._error(err)
            except Exception:
                self._error(ProductApiError(500, "internal_error", "The request could not be completed."))
        finally:
            self._finish_request()

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        self._begin_request()
        try:
            try:
                self._json(200, self._route_post())
            except ProductApiError as err:
                self._error(err)
            except Exception:
                self._error(ProductApiError(500, "internal_error", "The request could not be completed."))
        finally:
            self._finish_request()

    def _method_not_allowed(self, allow: str) -> None:
        self._json(405, ProductApiError(405, "method_not_allowed", "HTTP method is not allowed for this API route.").to_dict(), headers={"Allow": allow})

    def _run_disallowed(self) -> None:
        self._begin_request()
        try:
            self._method_not_allowed("GET, POST")
        finally:
            self._finish_request()

    def do_PUT(self) -> None:  # noqa: N802
        self._run_disallowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._run_disallowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._run_disallowed()

    def do_HEAD(self) -> None:  # noqa: N802
        self._run_disallowed()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._run_disallowed()


def create_server(
    root: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    allow_remote: bool = False,
    service: ProductApiService | None = None,
) -> ProductApiHttpServer:
    if not allow_remote and not _is_loopback_host(host):
        raise ValueError("non-loopback API binding requires allow_remote=True")
    if int(port) < 0 or int(port) > 65535:
        raise ValueError("port must be between 0 and 65535")
    svc = service or ProductApiService(Path(root), require_current_authority=True)
    return ProductApiHttpServer((host, int(port)), ProductApiHandler, svc)


def serve(root: Path, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, allow_remote: bool = False) -> None:
    server = create_server(root, host=host, port=port, allow_remote=allow_remote)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def start_test_server(root: Path, *, service: ProductApiService | None = None) -> tuple[ProductApiHttpServer, threading.Thread]:
    server = create_server(root, host="127.0.0.1", port=0, service=service)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return server, thread
