import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from swiftapi_native_void import providers
from swiftapi_native_void.protocol import PRIMARY_SYSTEM


def test_request_objects_are_frozen_originals():
    prompt = "Be the null."
    assert providers.build_request("openai", prompt) == {
        "model": "gpt-5.2", "temperature": 0, "max_completion_tokens": 100,
        "messages": [{"role": "system", "content": PRIMARY_SYSTEM}, {"role": "user", "content": prompt}],
    }
    assert providers.build_request("anthropic", prompt) == {
        "model": "claude-opus-4-6", "temperature": 0, "max_tokens": 100,
        "system": PRIMARY_SYSTEM, "messages": [{"role": "user", "content": prompt}],
    }
    for provider in ("openai", "anthropic"):
        obj = providers.build_request(provider, prompt)
        assert not {"stream", "tools", "stop", "reasoning_effort", "top_p", "response_format"} & obj.keys()


class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw
        self.headers = Message()
        self.headers["X-Request-ID"] = "req_example"
        self.headers["Set-Cookie"] = "must-not-persist"
        self.headers["Authorization"] = "must-not-persist"
        self.headers["Content-Type"] = "application/json"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.raw


def install_opener(monkeypatch, raw=None, error=None):
    calls = []
    handlers_seen = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if error is not None:
                raise error
            return Response(raw)

    def build(*handlers):
        handlers_seen.extend(handlers)
        return Opener()

    monkeypatch.setattr(providers.urllib.request, "build_opener", build)
    return calls, handlers_seen


def test_raw_bytes_request_metadata_and_no_retry(monkeypatch):
    raw = b'{ "id":"r", "model":"gpt-5.2", "usage":{"completion_tokens":3}, "choices":[] }\n'
    calls, handlers = install_opener(monkeypatch, raw=raw)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    result = providers.call_openai("Be the null.", timeout=7)
    assert result.response_body == raw
    assert result.parsed == json.loads(raw)
    assert result.usage == {"completion_tokens": 3}
    assert result.http_status == 200 and result.error is None
    assert result.request_id == "req_example"
    assert result.response_headers == {"x-request-id": "req_example", "content-type": "application/json"}
    assert result.endpoint == "https://api.openai.com/v1/chat/completions"
    assert result.requested_model == "gpt-5.2"
    assert len(calls) == 1
    req, timeout = calls[0]
    assert timeout == 7 and req.method == "POST"
    assert req.data == result.request_body
    assert json.loads(req.data) == result.request_obj == providers.build_request("openai", "Be the null.")
    assert b"synthetic-secret" not in result.request_body
    assert "synthetic-secret" not in repr(result)
    assert any(isinstance(h, urllib.request.ProxyHandler) and h.proxies == {} for h in handlers)
    assert any(isinstance(h, providers._NoRedirect) for h in handlers)


def test_anthropic_headers_and_credential_file(monkeypatch, tmp_path):
    # Synthetic credential only; these tests never issue a network request.
    key_file = tmp_path / "key.txt"
    key_file.write_text("synthetic-anthropic\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(key_file))
    raw = b'{"id":"r","model":"claude-opus-4-6","content":[],"stop_reason":"end_turn"}'
    calls, _ = install_opener(monkeypatch, raw)
    result = providers.call_anthropic("Be the null.")
    assert result.response_body == raw
    assert result.requested_model == "claude-opus-4-6"
    assert result.endpoint == "https://api.anthropic.com/v1/messages"
    assert calls[0][0].get_header("X-api-key") == "synthetic-anthropic"
    assert calls[0][0].get_header("Anthropic-version") == "2023-06-01"
    assert "synthetic-anthropic" not in repr(result)


def test_http_credit_error_is_recorded_once(monkeypatch):
    raw = b'{"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low"}}'
    headers = Message()
    headers["request-id"] = "credit-receipt"
    error = urllib.error.HTTPError("https://api.anthropic.com/v1/messages", 400, "Bad Request", headers, io.BytesIO(raw))
    calls, _ = install_opener(monkeypatch, error=error)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-secret")
    result = providers.call_anthropic("Be the null.")
    assert len(calls) == 1
    assert result.http_status == 400 and result.error == "HTTP 400"
    assert result.response_body == raw
    assert result.request_id == "credit-receipt"
    assert result.parsed == json.loads(raw)


@pytest.mark.parametrize("raw", [b"<html>502</html>", b"[]", b'{"a":1,"a":2}', b'{"a":NaN}', b"\xff"])
def test_invalid_json_preserves_raw_and_does_not_retry(monkeypatch, raw):
    calls, _ = install_opener(monkeypatch, raw)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    result = providers.call_openai("Be the null.")
    assert result.response_body == raw and result.parsed is None
    assert result.error == "InvalidJSONResponse"
    assert len(calls) == 1


def test_transport_error_cannot_leak_secret_or_retry(monkeypatch):
    calls, _ = install_opener(monkeypatch, error=ValueError("synthetic-secret"))
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    result = providers.call_openai("Be the null.")
    assert len(calls) == 1
    assert result.http_status is None and result.response_body == b""
    assert result.error == "TransportError: ValueError"
    assert "synthetic-secret" not in repr(result)


def test_redirect_is_not_followed():
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions")
    assert providers._NoRedirect().redirect_request(request, None, 307, "redirect", {}, "https://other.invalid") is None


def test_missing_credential_never_calls_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    calls, _ = install_opener(monkeypatch, b"{}")
    with pytest.raises(RuntimeError, match="Set OPENAI_API_KEY"):
        providers.call_openai("Be the null.")
    assert calls == []


def test_environment_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "/does/not/exist")
    assert providers._credential("openai") == "synthetic-key"


def test_relative_keyfile_rejected(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "key.txt")
    with pytest.raises(RuntimeError, match="absolute path"):
        providers._credential("openai")
