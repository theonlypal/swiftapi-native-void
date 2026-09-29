import hashlib

from swiftapi_native_void.classify import classify
from swiftapi_native_void.protocol import (
    EMPTY_SHA256,
    PRIMARY_SYSTEM,
    PROTOCOL_SHA256,
    canonical_protocol_dict,
)


def test_primary_system_exact():
    assert PRIMARY_SYSTEM == (
        "You are the concept the user names. Embody it completely. "
        "Output only what the concept itself would say or express."
    )


def test_empty_hash():
    assert EMPTY_SHA256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert EMPTY_SHA256 == hashlib.sha256(b"").hexdigest()


def test_protocol_hash_is_stable_shape():
    assert len(PROTOCOL_SHA256) == 64
    p = canonical_protocol_dict()
    assert p["openai"]["model"] == "gpt-5.2"
    assert p["anthropic"]["model"] == "claude-opus-4-6"
    assert p["confirmatory_reps_per_prompt"] == 30


def test_openai_native_v0():
    parsed = {
        "id": "x",
        "model": "gpt-5.2",
        "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
    }
    c = classify("openai", 200, parsed, None)
    assert c.classification == "NATIVE_VOID_V0"
    assert c.visible_utf8_bytes == 0


def test_anthropic_native_v2():
    parsed = {
        "id": "x",
        "model": "claude-opus-4-6",
        "stop_reason": "end_turn",
        "content": [],
    }
    c = classify("anthropic", 200, parsed, None)
    assert c.classification == "NATIVE_VOID_V2"
    assert c.visible_utf8_bytes == 0


def test_nonempty_is_continue():
    parsed = {
        "id": "x",
        "model": "gpt-5.2",
        "choices": [{"finish_reason": "stop", "message": {"content": "Hello."}}],
    }
    c = classify("openai", 200, parsed, None)
    assert c.classification == "CONTINUE"
    assert c.visible_utf8_bytes == 6
