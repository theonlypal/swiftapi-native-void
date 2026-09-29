import copy

import pytest

from swiftapi_native_void.classify import classify


def openai(content="", finish="stop"):
    return {"id": "r1", "model": "gpt-5.2", "choices": [{
        "index": 0, "finish_reason": finish,
        "message": {"role": "assistant", "content": content, "refusal": None},
    }]}


def anthropic(content=None, stop="end_turn"):
    return {"id": "r2", "model": "claude-opus-4-6", "role": "assistant",
            "type": "message", "stop_reason": stop, "content": content}


@pytest.mark.parametrize("content,expected", [("", "NATIVE_VOID_V0"), (None, "NATIVE_VOID_V2")])
def test_openai_distinguishes_null_and_empty(content, expected):
    result = classify("openai", 200, openai(content), None)
    assert result.classification == expected
    assert result.text_container_present is (content is not None)


def test_openai_absent_text_is_v2_not_v0():
    response = openai()
    del response["choices"][0]["message"]["content"]
    assert classify("openai", 200, response, None).classification == "NATIVE_VOID_V2"


@pytest.mark.parametrize("text", [" ", "\n", "\u200b", "…", "null", "\"\""])
def test_no_trimming_or_normalization(text):
    for provider, response in [("openai", openai(text)), ("anthropic", anthropic([{"type": "text", "text": text}]))]:
        before = copy.deepcopy(response)
        result = classify(provider, 200, response, None)
        assert result.classification == "CONTINUE"
        assert result.visible_text == text
        assert result.visible_utf8_bytes == len(text.encode("utf-8"))
        assert response == before


@pytest.mark.parametrize("content", [0, False, {}, [], [{"type": "text", "text": ""}]])
def test_openai_malformed_content_not_void(content):
    assert classify("openai", 200, openai(content), None).classification == "OTHER_STRUCTURED_RESPONSE"


@pytest.mark.parametrize("field,value,label", [
    ("refusal", "", "REFUSAL"), ("refusal", "Denied", "REFUSAL"),
    ("tool_calls", [{"type": "function"}], "TOOL_CALL"),
    ("tool_calls", {}, "OTHER_STRUCTURED_RESPONSE"),
    ("function_call", {}, "TOOL_CALL"), ("audio", {}, "OTHER_ACTION_OUTPUT"),
])
def test_action_or_refusal_precedes_empty(field, value, label):
    response = openai()
    response["choices"][0]["message"][field] = value
    assert classify("openai", 200, response, None).classification == label


@pytest.mark.parametrize("finish,label", [
    ("length", "ZERO_VISIBLE_OTHER_TERMINATION"), ("content_filter", "SAFETY_BLOCK"),
    ("tool_calls", "TOOL_CALL"), (None, "OTHER_STRUCTURED_RESPONSE"),
    ("new_reason", "OTHER_STRUCTURED_RESPONSE"),
])
def test_openai_stop_metadata(finish, label):
    assert classify("openai", 200, openai(finish=finish), None).classification == label


@pytest.mark.parametrize("content,label", [
    ([], "NATIVE_VOID_V2"), (None, "NATIVE_VOID_V2"),
    ([{"type": "text", "text": ""}], "NATIVE_VOID_V0"),
    ([{"type": "thinking", "thinking": "analysis"}], "NATIVE_VOID_V2"),
    ([{"type": "redacted_thinking", "data": "opaque"}], "NATIVE_VOID_V2"),
    ([{"type": "text", "text": None}], "OTHER_STRUCTURED_RESPONSE"),
    ([{"type": "thinking", "thinking": 42}], "OTHER_STRUCTURED_RESPONSE"),
    ([{"type": "text"}], "OTHER_STRUCTURED_RESPONSE"),
    ([{"type": "refusal"}], "REFUSAL"),
    ([{"type": "tool_use"}], "TOOL_CALL"),
    ([{"type": "web_search_tool_result"}], "TOOL_CALL"),
    ([{"type": "unknown"}], "OTHER_STRUCTURED_RESPONSE"),
    ([{"type": {}}], "OTHER_STRUCTURED_RESPONSE"),
    ([None], "OTHER_STRUCTURED_RESPONSE"), ({}, "OTHER_STRUCTURED_RESPONSE"),
])
def test_anthropic_container_types(content, label):
    assert classify("anthropic", 200, anthropic(content), None).classification == label


def test_anthropic_mixed_text_blocks_preserved():
    result = classify("anthropic", 200, anthropic([
        {"type": "thinking", "thinking": "not final output"},
        {"type": "text", "text": "A "}, {"type": "text", "text": "\nB"},
    ]), None)
    assert result.visible_text == "A \nB"
    assert result.visible_utf8_bytes == 4


@pytest.mark.parametrize("stop,label", [
    ("refusal", "REFUSAL"), ("tool_use", "TOOL_CALL"),
    ("max_tokens", "ZERO_VISIBLE_OTHER_TERMINATION"),
    ("stop_sequence", "ZERO_VISIBLE_OTHER_TERMINATION"),
    (None, "OTHER_STRUCTURED_RESPONSE"), ("unknown", "OTHER_STRUCTURED_RESPONSE"),
])
def test_anthropic_termination(stop, label):
    assert classify("anthropic", 200, anthropic([], stop), None).classification == label


@pytest.mark.parametrize("parsed", [None, [], "", 1, {"choices": []}, {"choices": [None]}, {"choices": {}}])
def test_malformed_envelopes_do_not_throw_or_void(parsed):
    assert "VOID" not in classify("openai", 200, parsed, None).classification


def test_explicit_error_and_safety_preempt_empty():
    response = openai()
    response["error"] = {"message": "upstream failure"}
    assert classify("openai", 200, response, None).classification == "PROVIDER_ERROR"
    response = openai()
    response["choices"][0]["content_filter_results"] = {"hate": {"filtered": True}}
    assert classify("openai", 200, response, None).classification == "SAFETY_BLOCK"


def test_lone_surrogate_is_not_void_or_unhandled_encoding_error():
    assert classify("openai", 200, openai("\ud800"), None).classification == "OTHER_STRUCTURED_RESPONSE"


@pytest.mark.parametrize("status,error", [(400, None), (429, None), (500, None), (None, "timeout"), (200, "transport")])
def test_infrastructure_never_void(status, error):
    assert classify("openai", status, openai(), error).classification == "PROVIDER_ERROR"
