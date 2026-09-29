from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protocol import (
    ANTHROPIC_ENDPOINT,
    ANTHROPIC_MODEL,
    ANTHROPIC_VERSION,
    MAX_TOKENS,
    OPENAI_ENDPOINT,
    OPENAI_MODEL,
    PRIMARY_SYSTEM,
    TEMPERATURE,
)


@dataclass
class ProviderResult:
    provider: str
    requested_model: str
    endpoint: str
    request_obj: dict[str, Any]
    request_body: bytes
    http_status: int | None
    response_body: bytes
    parsed: dict[str, Any] | None
    error: str | None
    response_headers: dict[str, str] = field(default_factory=dict)
    request_id: str | None = None
    usage: dict[str, Any] | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_headers(headers: Any) -> dict[str, str]:
    allowed = {
        "x-request-id", "request-id", "date", "content-type",
        "openai-processing-ms", "openai-version", "anthropic-version",
        "retry-after", "cf-ray",
    }
    return {
        key.lower(): value for key, value in headers.items()
        if key.lower() in allowed
    } if headers is not None else {}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite JSON constant")


def _post_json(url: str, headers: dict[str, str], body_obj: dict[str, Any], timeout: int) -> tuple[int | None, bytes, dict[str, Any] | None, str | None, bytes, dict[str, str]]:
    body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    # No environment proxy, automatic transport retry, or cross-host redirect.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    response_headers: dict[str, str] = {}
    error = None
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()  # Capture the entity bytes before JSON parsing.
            status = resp.status
            response_headers = _safe_headers(resp.headers)
    except urllib.error.HTTPError as e:
        status = e.code
        response_headers = _safe_headers(e.headers)
        try:
            raw = e.read()
        except Exception:
            return status, b"", None, "HTTP body read failed", body, response_headers
        finally:
            e.close()
        error = f"HTTP {status}"
    except Exception as e:
        # Exception messages can contain secrets. Persist the exception type only.
        return None, b"", None, f"TransportError: {type(e).__name__}", body, response_headers

    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if not isinstance(parsed, dict):
            raise ValueError("response is not an object")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        return status, raw, None, error or "InvalidJSONResponse", body, response_headers
    return status, raw, parsed, error, body, response_headers


def build_request(provider: str, prompt: str) -> dict[str, Any]:
    """Return the published request, without adding optional API settings."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    if provider == "openai":
        return {
            "model": OPENAI_MODEL,
            "temperature": TEMPERATURE,
            "max_completion_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": PRIMARY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
    if provider == "anthropic":
        return {
            "model": ANTHROPIC_MODEL,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "system": PRIMARY_SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        }
    raise ValueError("unsupported provider")


def _credential(provider: str) -> str:
    variable = f"{provider.upper()}_API_KEY"
    key = os.environ.get(variable)
    if key and key.strip():
        return key.strip()
    key_file = os.environ.get(f"{variable}_FILE")
    if key_file:
        path = Path(key_file)
        if not path.is_absolute():
            raise RuntimeError(f"{variable}_FILE must be an absolute path")
        try:
            key = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise RuntimeError(f"Could not read {variable}_FILE") from None
        if key:
            return key
    raise RuntimeError(f"Set {variable} or {variable}_FILE")


def _call(provider: str, prompt: str, timeout: int) -> ProviderResult:
    key = _credential(provider)
    obj = build_request(provider, prompt)
    if provider == "openai":
        endpoint, model = OPENAI_ENDPOINT, OPENAI_MODEL
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    else:
        endpoint, model = ANTHROPIC_ENDPOINT, ANTHROPIC_MODEL
        headers = {
            "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
    status, raw, parsed, error, body, response_headers = _post_json(endpoint, headers, obj, timeout)
    usage = parsed.get("usage") if isinstance(parsed, dict) else None
    return ProviderResult(
        provider, model, endpoint, obj, body, status, raw, parsed, error,
        response_headers,
        response_headers.get("x-request-id") or response_headers.get("request-id"),
        usage if isinstance(usage, dict) else None,
    )


def call_openai(prompt: str, timeout: int = 120) -> ProviderResult:
    return _call("openai", prompt, timeout)


def call_anthropic(prompt: str, timeout: int = 120) -> ProviderResult:
    return _call("anthropic", prompt, timeout)
