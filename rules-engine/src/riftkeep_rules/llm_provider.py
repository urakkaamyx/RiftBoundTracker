from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class JsonLlmProvider(Protocol):
    def complete_json(
        self, *, system: str, user: str, temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None, schema_name: str = "response",
    ) -> dict[str, Any]: ...


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.S)


def _strip_json_fence(content: str) -> str:
    """Some local models wrap JSON output in a markdown code fence despite being asked for a bare
    JSON object and despite response_format: json_object - not every llama.cpp server build
    enforces that as hard grammar. Stripping a fence is purely defensive: it never changes the
    parsed result for content that was already bare JSON, and validate_*_payload still rejects
    anything that isn't a legitimately-shaped contract either way."""
    m = _JSON_FENCE_RE.match(content)
    return m.group(1) if m else content


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
    # A hard backstop independent of the JSON schema: schema-constrained grammar decoding
    # guarantees valid *shape* but does not bound string *length* (maxLength support varies by
    # llama.cpp server build) - confirmed directly that a runaway generation can otherwise run to
    # thousands of tokens well past what any contract field allows, for several minutes, before
    # validate_*_payload ever gets a chance to reject the (by-then oversized) result as invalid.
    max_tokens: int = 1500

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

    def complete_json(
        self, *, system: str, user: str, temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None, schema_name: str = "response",
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        # A real schema gets grammar-constrained decoding (the server can only emit tokens that
        # produce valid-shaped JSON) instead of just a "please return JSON" hint - confirmed
        # directly that "json_object" mode alone lets a small local model wrap its answer in a
        # markdown fence or invent its own unrelated shape despite being asked not to.
        response_format = (
            {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": json_schema}}
            if json_schema is not None
            else {"type": "json_object"}
        )
        body = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "response_format": response_format,
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
            result = json.loads(_strip_json_fence(str(content)))
        if not isinstance(result, dict):
            raise ValueError("LLM response JSON must be an object")
        return result


def provider_from_env() -> "OpenAICompatibleLocalProvider | None":
    """Build the loopback LLM provider from environment configuration, if any is set.

    Ask Rules' AI interpretation/explanation layers are optional by design (M10/M11 - see
    KNOWN_LIMITATIONS_1.0.md's "Optional LLM presentation layers"): deterministic adjudication,
    proof verification, and citations never depend on this. Absent config just means those two
    layers stay inert and every caller already falls back to the plain deterministic answer, so
    there's nothing unsafe about defaulting to None here.
    """
    base_url = os.environ.get("RIFTKEEP_LLM_BASE_URL", "").strip()
    if not base_url:
        return None
    model = os.environ.get("RIFTKEEP_LLM_MODEL", "riftkeep-ask-rules").strip()
    try:
        return OpenAICompatibleLocalProvider(base_url=base_url, model=model)
    except ValueError:
        return None
