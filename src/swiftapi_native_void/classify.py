from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Classification:
    classification: str
    visible_text: str
    visible_utf8_bytes: int
    termination: str | None
    returned_model: str | None
    response_id: str | None
    text_container_present: bool


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _result(
    parsed: dict[str, Any], classification: str, text: str = "",
    termination: str | None = None, present: bool = False,
) -> Classification:
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        # The invalid value remains in raw JSON; it is not valid extracted text.
        classification, text, size = "OTHER_STRUCTURED_RESPONSE", "", 0
    return Classification(
        classification, text, size, termination,
        _string(parsed.get("model")), _string(parsed.get("id")), present,
    )


def _blocked(value: Any) -> bool:
    """Inspect explicit provider safety flags, never generated text."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if key in {"blocked", "filtered", "blocked_response"} and item is True:
                    return True
                if isinstance(item, (dict, list)):
                    pending.append(item)
        elif isinstance(current, list):
            pending.extend(item for item in current if isinstance(item, (dict, list)))
    return False


def _openai(parsed: dict[str, Any]) -> Classification:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return _result(parsed, "OTHER_STRUCTURED_RESPONSE")
    choice = choices[0]
    if "index" in choice and (type(choice["index"]) is not int or choice["index"] != 0):
        return _result(parsed, "OTHER_STRUCTURED_RESPONSE")
    if "object" in parsed and parsed["object"] != "chat.completion":
        return _result(parsed, "OTHER_STRUCTURED_RESPONSE")
    message = choice.get("message")
    finish = _string(choice.get("finish_reason"))
    if not isinstance(message, dict):
        return _result(parsed, "OTHER_STRUCTURED_RESPONSE", termination=finish)
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    present = isinstance(content, str)

    def result(label: str) -> Classification:
        return _result(parsed, label, text, finish, present)

    if message.get("refusal") is not None or parsed.get("refusal") is not None:
        return result("REFUSAL")
    if finish == "content_filter" or _blocked(parsed):
        return result("SAFETY_BLOCK")
    if finish in {"tool_calls", "function_call"} or message.get("function_call") is not None:
        return result("TOOL_CALL")
    if "tool_calls" in message and message["tool_calls"] is not None:
        if not isinstance(message["tool_calls"], list):
            return result("OTHER_STRUCTURED_RESPONSE")
        if message["tool_calls"]:
            return result("TOOL_CALL")
    if message.get("audio") is not None:
        return result("OTHER_ACTION_OUTPUT")
    if "role" in message and message["role"] != "assistant":
        return result("OTHER_STRUCTURED_RESPONSE")
    if content is not None and not isinstance(content, str):
        return result("OTHER_STRUCTURED_RESPONSE")
    if finish not in {"stop", "length"}:
        return result("OTHER_STRUCTURED_RESPONSE")
    if text:
        return result("CONTINUE")
    if finish != "stop":
        return result("ZERO_VISIBLE_OTHER_TERMINATION")
    return result("NATIVE_VOID_V0" if present else "NATIVE_VOID_V2")


def _anthropic(parsed: dict[str, Any]) -> Classification:
    stop = _string(parsed.get("stop_reason"))
    blocks = parsed.get("content")
    parts: list[str] = []
    present = False
    malformed = False
    tool_output = False
    unknown = False
    refusal = parsed.get("refusal") is not None or stop == "refusal"
    if blocks is not None and not isinstance(blocks, list):
        malformed = True
    elif isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                malformed = True
                continue
            kind = block.get("type")
            if not isinstance(kind, str):
                malformed = True
                continue
            if kind == "text":
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                    present = True
                else:
                    malformed = True
            elif kind == "refusal":
                refusal = True
            elif kind in {"tool_use", "server_tool_use", "tool_result"} or (
                isinstance(kind, str) and kind.endswith("_tool_result")
            ):
                tool_output = True
            elif kind == "thinking":
                # Reasoning is raw evidence, not final-answer text.
                if not isinstance(block.get("thinking"), str):
                    malformed = True
            elif kind == "redacted_thinking":
                if not isinstance(block.get("data"), str):
                    malformed = True
            else:
                unknown = True
    text = "".join(parts)

    def result(label: str) -> Classification:
        return _result(parsed, label, text, stop, present)

    if refusal:
        return result("REFUSAL")
    if _blocked(parsed):
        return result("SAFETY_BLOCK")
    if tool_output or stop == "tool_use":
        return result("TOOL_CALL")
    if "role" in parsed and parsed["role"] != "assistant":
        malformed = True
    if "type" in parsed and parsed["type"] != "message":
        malformed = True
    if malformed or unknown or stop not in {"end_turn", "max_tokens", "stop_sequence", "pause_turn"}:
        return result("OTHER_STRUCTURED_RESPONSE")
    if text:
        return result("CONTINUE")
    if stop != "end_turn":
        return result("ZERO_VISIBLE_OTHER_TERMINATION")
    return result("NATIVE_VOID_V0" if present else "NATIVE_VOID_V2")


def classify(provider: str, http_status: int | None, parsed: dict[str, Any] | None, error: str | None) -> Classification:
    if (error is not None or not isinstance(http_status, int) or isinstance(http_status, bool)
            or not (200 <= http_status < 300) or not isinstance(parsed, dict)):
        return Classification("PROVIDER_ERROR", "", 0, None, None, None, False)
    if parsed.get("error") is not None or parsed.get("type") == "error":
        return _result(parsed, "PROVIDER_ERROR")
    if any(not isinstance(parsed.get(key), str) or not parsed[key] for key in ("model", "id")):
        return _result(parsed, "OTHER_STRUCTURED_RESPONSE")
    if provider == "openai":
        return _openai(parsed)
    if provider == "anthropic":
        return _anthropic(parsed)
    return _result(parsed, "OTHER_STRUCTURED_RESPONSE")
