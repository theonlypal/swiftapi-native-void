from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

# Canonical primary embodiment system prompt from:
# Pal, R. (2026). Cross-Model Semantic Void Convergence Under Embodiment Prompting.
# DOI: 10.5281/zenodo.18976656
PRIMARY_SYSTEM: Final[str] = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express."
)

# Published extended prompt. It is preserved for provenance but NOT used by the
# default core-confirmatory audit because it explicitly mentions silence.
EXTENDED_SYSTEM: Final[str] = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express. "
    "If the concept is silent by nature, be silent."
)

CORE_VOID_PROMPTS: Final[tuple[str, ...]] = (
    "Be silence.",
    "Be nothing.",
    "Be the null.",
)

CORE_CONTROL_PROMPTS: Final[tuple[str, ...]] = (
    "Say hello.",
    "Be a cat.",
)

# Preserved because it appears in the published reproduction appendix and the
# later boundary battery. It is intentionally not part of the clean two-control
# core result used by the default audit.
BOUNDARY_CONTROL_PROMPT: Final[str] = "Be thunder."

OPENAI_MODEL: Final[str] = "gpt-5.2"
ANTHROPIC_MODEL: Final[str] = "claude-opus-4-6"
OPENAI_ENDPOINT: Final[str] = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_ENDPOINT: Final[str] = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION: Final[str] = "2023-06-01"
TEMPERATURE: Final[int] = 0
MAX_TOKENS: Final[int] = 100
CONFIRMATORY_REPS: Final[int] = 30

PROTOCOL_ID: Final[str] = "rayan-pal-cross-model-native-noncontinuation-v1"
SOURCE_DOI: Final[str] = "10.5281/zenodo.18976656"
MATRIX_DOI: Final[str] = "10.5281/zenodo.21696066"
MATRIX_RUNNER_COMMIT: Final[str] = "2dfe895bdafd35d23d6dab5f307ed560214a3843"
EMPTY_SHA256: Final[str] = hashlib.sha256(b"").hexdigest()


def canonical_protocol_dict() -> dict:
    return {
        "protocol_id": PROTOCOL_ID,
        "source_doi": SOURCE_DOI,
        "matrix_doi": MATRIX_DOI,
        "matrix_runner_commit": MATRIX_RUNNER_COMMIT,
        "primary_system": PRIMARY_SYSTEM,
        "core_void_prompts": list(CORE_VOID_PROMPTS),
        "core_control_prompts": list(CORE_CONTROL_PROMPTS),
        "boundary_control_prompt": BOUNDARY_CONTROL_PROMPT,
        "openai": {
            "endpoint": OPENAI_ENDPOINT,
            "model": OPENAI_MODEL,
            "temperature": TEMPERATURE,
            "max_completion_tokens": MAX_TOKENS,
            "stream": False,
            "tools": False,
            "fresh_single_turn": True,
        },
        "anthropic": {
            "endpoint": ANTHROPIC_ENDPOINT,
            "model": ANTHROPIC_MODEL,
            "anthropic_version": ANTHROPIC_VERSION,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "stream": False,
            "tools": False,
            "fresh_single_turn": True,
        },
        "confirmatory_reps_per_prompt": CONFIRMATORY_REPS,
        "native_void_definition": {
            "provider_success": True,
            "visible_utf8_bytes": 0,
            "openai_normal_stop": "stop",
            "anthropic_normal_stop": "end_turn",
        },
    }


def _canonical_json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


PROTOCOL_SHA256: Final[str] = hashlib.sha256(_canonical_json_bytes(canonical_protocol_dict())).hexdigest()


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    expected_class: str


def core_cases() -> tuple[PromptCase, ...]:
    voids = tuple(
        PromptCase(f"void_{i+1}", prompt, "native_void")
        for i, prompt in enumerate(CORE_VOID_PROMPTS)
    )
    controls = tuple(
        PromptCase(f"control_{i+1}", prompt, "nonempty")
        for i, prompt in enumerate(CORE_CONTROL_PROMPTS)
    )
    return voids + controls
