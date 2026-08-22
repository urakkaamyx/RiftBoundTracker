from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class JsonLlmProvider(Protocol):
    def complete_json(self, *, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise RuntimeError(f"LLM endpoint redirect rejected by local-only policy: {code}")


@dataclass
class OpenAICompatibleLocalProvider:
    """Minimal provider for a loopback OpenAI-compatible chat endpoint.

    M10 is local-only and fail-closed. The base URL must resolve syntactically to
    localhost/loopback, redirects are rejected, and responses are size-bounded.
    No remote provider is permitted through this class.
    """

    base_url: str
    model: str
    api_key: str | None = None
    timeout: int = 90
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("local LLM base_url must use http or https")
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("M10 local-provider policy rejects non-loopback LLM endpoints")
        if not self.model.strip():
            raise ValueError("model must be non-empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_response_bytes < 1024:
            raise ValueError("max_response_bytes is unreasonably small")

    def complete_json(self, *, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json", "User-Agent": "RiftKeepRules/m10-local-interpretation"}
        key = self.api_key or os.environ.get("RIFTKEEP_LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        opener = build_opener(_RejectRedirects())
        with opener.open(req, timeout=self.timeout) as resp:
            raw = resp.read(self.max_response_bytes + 1)
        if len(raw) > self.max_response_bytes:
            raise ValueError("LLM response exceeded configured size limit")
        payload = json.loads(raw.decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            result = content
        else:
            result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("LLM response JSON must be an object")
        return result
