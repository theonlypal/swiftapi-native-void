import json
from pathlib import Path

import pytest

from swiftapi_native_void import audit
from swiftapi_native_void.hashing import sha256_json, write_json
from swiftapi_native_void.protocol import ANTHROPIC_ENDPOINT, OPENAI_ENDPOINT, core_cases
from swiftapi_native_void.providers import ProviderResult, build_request


def load(path):
    return json.loads(path.read_text())


def fake_result(provider, prompt, index, *, status=200, content=None, error=None):
    request = build_request(provider, prompt)
    text = ("" if prompt in {c.prompt for c in core_cases()[:3]} else "Hello.") if content is None else content
    if provider == "openai":
        parsed = {"id": f"response-{index}", "model": "gpt-5.2-2025-12-11",
                  "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                  "usage": {"completion_tokens": 3}}
    else:
        parsed = {"id": f"response-{index}", "model": request["model"], "type": "message", "role": "assistant",
                  "content": [] if text == "" else [{"type": "text", "text": text}], "stop_reason": "end_turn",
                  "usage": {"output_tokens": 3}}
    if status != 200:
        parsed = {"error": {"type": "invalid_request_error", "message": "insufficient credit balance"}}
    raw = json.dumps(parsed).encode()
    return ProviderResult(provider, request["model"], OPENAI_ENDPOINT if provider == "openai" else ANTHROPIC_ENDPOINT,
                          request, audit._request_bytes(provider, prompt), status, raw, parsed, error,
                          {"request-id": f"request-{index}"}, f"request-{index}")


@pytest.fixture
def install_fake(monkeypatch, tmp_path):
    def install(provider="openai", *, status=200, content=None, error=None):
        calls = []
        monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-credential")

        def fake(prompt, timeout):
            runs = [p for p in tmp_path.iterdir() if p.is_dir()]
            assert len(runs) == 1
            root = runs[0]
            assert (root / "FREEZE.json").exists()
            manifest = load(root / "manifest.json")
            slot = manifest["schedule"][len(calls)]
            assert (root / "raw" / f"{slot['attempt_id']}.request.json").read_bytes() == audit._request_bytes(provider, prompt)
            calls.append(prompt)
            return fake_result(provider, prompt, len(calls), status=status, content=content, error=error)

        monkeypatch.setattr(audit, f"call_{provider}", fake)
        return calls
    return install


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_run_sealed_recomputed_observation(tmp_path, install_fake, provider):
    calls = install_fake(provider)
    run = audit.run_provider(provider, tmp_path, reps=1, cases=[core_cases()[2]], execution_kind="run")
    assert calls == ["Be the null."]
    assert audit.verify_run(run) == (True, [])
    summary = load(run / "summary.json")
    assert summary["outcome"] == "OBSERVATION"
    assert summary["void_arm_native_voids"] == 1
    assert summary["complete"] is True
    assert summary["expected_attempts"] == summary["attempted_count"] == 1


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_full_confirmatory_contract(tmp_path, install_fake, provider):
    calls = install_fake(provider)
    run = audit.run_provider(provider, tmp_path)
    assert len(calls) == 150
    assert audit.verify_run(run) == (True, [])
    summary = load(run / "summary.json")
    assert summary["outcome"] == "REPRODUCED"
    assert summary["void_arm_native_voids"] == 90
    assert summary["control_visible"] == 60


def test_short_audit_not_confirmatory(tmp_path, install_fake):
    install_fake()
    run = audit.run_provider("openai", tmp_path, reps=1)
    assert audit.verify_run(run) == (True, [])
    assert load(run / "summary.json")["outcome"] == "OBSERVED_MATCH"


def test_nonmatching_result_is_retained(tmp_path, install_fake):
    install_fake(content="Not empty")
    run = audit.run_provider("openai", tmp_path, reps=1)
    assert audit.verify_run(run) == (True, [])
    assert load(run / "summary.json")["outcome"] == "NOT_REPRODUCED"


def test_credit_failure_aborts_once_and_integrity_passes(tmp_path, install_fake):
    calls = install_fake("anthropic", status=400, error="HTTP 400")
    run = audit.run_provider("anthropic", tmp_path)
    assert len(calls) == 1
    assert audit.verify_run(run) == (True, [])
    summary = load(run / "summary.json")
    assert summary["outcome"] == "INCOMPLETE"
    assert summary["classification_counts"] == {"PROVIDER_ERROR": 1}
    assert len(summary["unexecuted_attempt_ids"]) == 149
    assert summary["void_arm_native_voids"] == 0


def test_missing_key_stops_before_any_attempt(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.setattr(audit, "call_openai", lambda *args: pytest.fail("must not call"))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        audit.run_provider("openai", tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_file_only_credentials_supported_without_disclosure(monkeypatch, tmp_path, install_fake, provider):
    calls = install_fake(provider)
    key_name = f"{provider.upper()}_API_KEY"
    monkeypatch.delenv(key_name, raising=False)
    key_file = tmp_path / "synthetic.key"
    key_file.write_text("file-only-synthetic-secret\n")
    monkeypatch.setenv(f"{key_name}_FILE", str(key_file))
    run = audit.run_provider(provider, tmp_path, reps=1, cases=[core_cases()[2]], execution_kind="run")
    assert len(calls) == 1
    assert audit.verify_run(run) == (True, [])
    assert all(b"file-only-synthetic-secret" not in p.read_bytes() for p in run.rglob("*") if p.is_file())


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("path_kind", ["relative", "missing"])
def test_invalid_credential_file_stops_before_run(monkeypatch, tmp_path, provider, path_kind):
    key_name = f"{provider.upper()}_API_KEY"
    monkeypatch.delenv(key_name, raising=False)
    monkeypatch.setenv(f"{key_name}_FILE", "relative.key" if path_kind == "relative" else str(tmp_path / "absent.key"))
    monkeypatch.setattr(audit, f"call_{provider}", lambda *args: pytest.fail("must not call"))
    with pytest.raises(RuntimeError, match=f"{key_name}_FILE"):
        audit.run_provider(provider, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("classification", ["OTHER_STRUCTURED_RESPONSE", "OTHER_ACTION_OUTPUT"])
def test_unexpected_provider_structure_aborts_and_retains(monkeypatch, tmp_path, classification):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    calls = []
    def unexpected(prompt, timeout):
        calls.append(1)
        result = fake_result("openai", prompt, len(calls))
        if classification == "OTHER_STRUCTURED_RESPONSE":
            result.parsed["choices"] = []
        else:
            result.parsed["choices"][0]["message"]["audio"] = {"data": "synthetic"}
        result.response_body = json.dumps(result.parsed).encode()
        return result
    monkeypatch.setattr(audit, "call_openai", unexpected)
    run = audit.run_provider("openai", tmp_path)
    assert calls == [1]
    assert audit.verify_run(run) == (True, [])
    summary = load(run / "summary.json")
    assert summary["outcome"] == "INCOMPLETE"
    assert summary["classification_counts"] == {classification: 1}
    assert len(summary["unexecuted_attempt_ids"]) == 149


def test_local_exception_retained_without_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    calls = []
    def broken(*args):
        calls.append(1)
        raise RuntimeError("unexpected transport exception")
    monkeypatch.setattr(audit, "call_openai", broken)
    run = audit.run_provider("openai", tmp_path)
    assert len(calls) == 1
    assert audit.verify_run(run) == (True, [])
    assert load(run / "summary.json")["classification_counts"] == {"LOCAL_ERROR": 1}


@pytest.mark.parametrize("mutation", ["raw", "parsed", "request", "summary", "receipt", "missing", "extra", "nested_seal", "malformed"])
def test_tampering_detected_even_with_reseal(tmp_path, install_fake, mutation):
    install_fake()
    run = audit.run_provider("openai", tmp_path, reps=1)
    receipt = run / "receipts" / "void_1_r001.json"
    if mutation == "raw":
        (run / "raw" / "void_1_r001.response.body").write_bytes(b"{}")
    elif mutation == "parsed":
        write_json(run / "raw" / "void_1_r001.response.parsed.json", {})
    elif mutation == "request":
        write_json(run / "raw" / "void_1_r001.request.json", {})
    elif mutation == "summary":
        value = load(run / "summary.json")
        value["void_arm_native_voids"] = 99
        write_json(run / "summary.json", value)
    elif mutation == "receipt":
        value = load(receipt)
        del value["receipt_sha256"]
        value.update({"classification": "CONTINUE", "visible_text": "forged", "visible_utf8_bytes": 6})
        value["receipt_sha256"] = sha256_json(value)
        write_json(receipt, value)
    elif mutation == "missing":
        receipt.unlink()
    elif mutation == "extra":
        write_json(run / "extra.json", {})
    elif mutation == "nested_seal":
        write_json(run / "raw" / "SEAL.json", {})
    elif mutation == "malformed":
        receipt.write_bytes(b"not-json")
    audit._seal(run)
    ok, errors = audit.verify_run(run)
    assert not ok
    assert errors


def test_seal_detects_byte_change_without_reseal(tmp_path, install_fake):
    install_fake()
    run = audit.run_provider("openai", tmp_path, reps=1)
    path = run / "manifest.json"
    path.write_bytes(path.read_bytes() + b" ")
    ok, errors = audit.verify_run(run)
    assert not ok
    assert any("hash mismatch" in e for e in errors)


def test_graceful_missing_and_malformed(tmp_path):
    assert audit.verify_run(tmp_path)[0] is False
    write_json(tmp_path / "SEAL.json", {"format": "sha256-file-set-v1", "files": []})
    assert audit.verify_run(tmp_path)[0] is False


def test_duplicate_ids_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(audit, "call_openai", lambda prompt, timeout: fake_result("openai", prompt, 1))
    run = audit.run_provider("openai", tmp_path, reps=1)
    ok, errors = audit.verify_run(run)
    assert not ok
    assert any("duplicate" in e for e in errors)
