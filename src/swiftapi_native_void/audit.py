from __future__ import annotations

import datetime as dt
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

from .classify import classify
from .hashing import sha256_bytes, sha256_json, sha256_text, write_json
from .protocol import (
    ANTHROPIC_ENDPOINT, ANTHROPIC_MODEL, CONFIRMATORY_REPS, EMPTY_SHA256,
    OPENAI_ENDPOINT, OPENAI_MODEL, PRIMARY_SYSTEM, PROTOCOL_ID,
    PROTOCOL_SHA256, SOURCE_DOI, PromptCase, canonical_protocol_dict, core_cases,
)
from .providers import ProviderResult, _credential, build_request, call_anthropic, call_openai

ProviderFn = Callable[[str, int], ProviderResult]
OPERATIONAL_ERRORS = {
    "PROVIDER_ERROR", "LOCAL_ERROR", "MALFORMED_RESPONSE",
    "OTHER_STRUCTURED_RESPONSE", "OTHER_ACTION_OUTPUT",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_fn(provider: str) -> ProviderFn:
    return {"openai": call_openai, "anthropic": call_anthropic}[provider]


def _request_bytes(provider: str, prompt: str) -> bytes:
    return json.dumps(build_request(provider, prompt), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _schedule(cases: Iterable[PromptCase], reps: int) -> list[dict]:
    return [
        {"attempt_id": f"{case.case_id}_r{rep:03d}", "case_id": case.case_id,
         "rep": rep, "user_prompt": case.prompt, "expected_reference_class": case.expected_class}
        for case in cases for rep in range(1, reps + 1)
    ]


def _parse(raw: bytes) -> dict | None:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("nonfinite JSON constant")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=invalid_constant)
        return value if isinstance(value, dict) else None
    except (ValueError, UnicodeError, RecursionError):
        return None


def _receipt(manifest: dict, slot: dict, transport: dict, request: bytes, raw: bytes) -> dict:
    parsed = _parse(raw)
    cls = classify(manifest["provider"], transport["http_status"], parsed, transport["provider_error"])
    record = {
        "attempt_id": slot["attempt_id"], "run_id": manifest["run_id"],
        "timestamp_utc": transport["timestamp_utc"], "provider": manifest["provider"],
        "requested_model": manifest["requested_model"], "returned_model": cls.returned_model,
        "endpoint": manifest["endpoint"], "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256, "case_id": slot["case_id"], "rep": slot["rep"],
        "expected_reference_class": slot["expected_reference_class"],
        "system_prompt": PRIMARY_SYSTEM, "system_prompt_sha256": sha256_text(PRIMARY_SYSTEM),
        "user_prompt": slot["user_prompt"], "user_prompt_sha256": sha256_text(slot["user_prompt"]),
        "request_body_sha256": sha256_bytes(request), "response_body_sha256": sha256_bytes(raw),
        "transport_sha256": sha256_json(transport), "http_status": transport["http_status"],
        "provider_error": transport["provider_error"], "local_error": transport["local_error"],
        "request_id": transport["request_id"], "response_headers": transport["response_headers"],
        "response_id": cls.response_id, "termination": cls.termination,
        "text_container_present": cls.text_container_present, "visible_text": cls.visible_text,
        "visible_utf8_bytes": cls.visible_utf8_bytes, "visible_output_sha256": sha256_text(cls.visible_text),
        "empty_output_sha256_reference": EMPTY_SHA256,
        "usage": parsed.get("usage") if parsed is not None else None,
        "classification": "LOCAL_ERROR" if transport["local_error"] else cls.classification,
    }
    record["receipt_sha256"] = sha256_json(record)
    return record


def summarize(receipts: list[dict]) -> dict:
    voids = [r for r in receipts if r["expected_reference_class"] == "native_void"]
    controls = [r for r in receipts if r["expected_reference_class"] == "nonempty"]
    native = lambda r: r["classification"] in {"NATIVE_VOID_V0", "NATIVE_VOID_V2"}
    return {
        "attempts": len(receipts), "attempted_count": len(receipts),
        "void_arm_attempts": len(voids), "void_arm_native_voids": sum(map(native, voids)),
        "control_attempts": len(controls), "control_native_voids": sum(map(native, controls)),
        "control_visible": sum(r["classification"] == "CONTINUE" for r in controls),
        "errors": sum(r["classification"] in OPERATIONAL_ERRORS for r in receipts),
        "classification_counts": dict(sorted(Counter(r["classification"] for r in receipts).items())),
        "all_receipt_hashes_present": all(bool(r.get("receipt_sha256")) for r in receipts),
    }


def _summary(manifest: dict, receipts: list[dict], finished_at: str) -> dict:
    result = summarize(receipts)
    expected = len(manifest["schedule"])
    complete = len(receipts) == expected and not result["errors"]
    matched = (complete and result["void_arm_attempts"] > 0 and result["control_attempts"] > 0
               and result["void_arm_native_voids"] == result["void_arm_attempts"]
               and result["control_visible"] == result["control_attempts"])
    confirmatory = (manifest["schedule"] == _schedule(core_cases(), CONFIRMATORY_REPS)
                    and manifest["execution_kind"] == "audit")
    outcome = ("INCOMPLETE" if not complete else "OBSERVATION" if manifest["execution_kind"] == "run"
               else "REPRODUCED" if matched and confirmatory else "OBSERVED_MATCH" if matched
               else "NOT_REPRODUCED")
    result.update({
        "run_id": manifest["run_id"], "provider": manifest["provider"], "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256, "execution_kind": manifest["execution_kind"],
        "expected_attempts": expected, "complete": complete, "outcome": outcome,
        "abort_attempt_id": receipts[-1]["attempt_id"] if result["errors"] else None,
        "unexecuted_attempt_ids": [s["attempt_id"] for s in manifest["schedule"][len(receipts):]],
        "finished_at": finished_at,
    })
    return result


def _seal(run_dir: Path) -> None:
    files = {p.relative_to(run_dir).as_posix(): sha256_bytes(p.read_bytes())
             for p in sorted(run_dir.rglob("*")) if p.is_file() and p != run_dir / "SEAL.json"}
    write_json(run_dir / "SEAL.json", {"format": "sha256-file-set-v1", "files": files})


def run_provider(provider: str, out_root: Path, reps: int = CONFIRMATORY_REPS, timeout: int = 120,
                 *, cases: Iterable[PromptCase] | None = None, execution_kind: str = "audit") -> Path:
    if provider not in {"openai", "anthropic"}:
        raise ValueError(f"unsupported provider: {provider}")
    if type(reps) is not int or reps < 1 or type(timeout) is not int or timeout < 1:
        raise ValueError("reps and timeout must be positive integers")
    if execution_kind not in {"run", "audit"}:
        raise ValueError("execution_kind must be run or audit")
    selected = tuple(core_cases() if cases is None else cases)
    allowed = {c.case_id: c for c in core_cases()}
    if not selected or any(allowed.get(c.case_id) != c for c in selected):
        raise ValueError("cases must be exact canonical core cases")
    if len({c.case_id for c in selected}) != len(selected):
        raise ValueError("duplicate cases")
    if execution_kind == "run" and (len(selected) != 1 or reps != 1):
        raise ValueError("run mode requires exactly one case and one repetition")
    # Same credential resolution as transport, before creating a run or spending.
    _credential(provider)

    run_id = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{provider}_{uuid.uuid4().hex[:8]}"
    run_dir = Path(out_root) / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=False)
    (run_dir / "receipts").mkdir()
    schedule = _schedule(selected, reps)
    manifest = {
        "format_version": 1, "run_id": run_id, "started_at": _utc_now(), "provider": provider,
        "requested_model": OPENAI_MODEL if provider == "openai" else ANTHROPIC_MODEL,
        "endpoint": OPENAI_ENDPOINT if provider == "openai" else ANTHROPIC_ENDPOINT,
        "protocol_id": PROTOCOL_ID, "protocol_sha256": PROTOCOL_SHA256, "source_doi": SOURCE_DOI,
        "reps_per_prompt": reps, "timeout_seconds": timeout, "execution_kind": execution_kind,
        "case_ids": [c.case_id for c in selected], "canonical_protocol": canonical_protocol_dict(),
        "schedule": schedule, "schedule_sha256": sha256_json(schedule),
        "automatic_retries": 0, "abort_policy": "first_operational_error",
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "FREEZE.json", {"manifest_sha256": sha256_bytes((run_dir / "manifest.json").read_bytes()),
                                        "schedule_sha256": sha256_json(schedule)})
    fn = _provider_fn(provider)
    receipts: list[dict] = []
    for slot in schedule:
        stem = run_dir / "raw" / slot["attempt_id"]
        request = _request_bytes(provider, slot["user_prompt"])
        Path(f"{stem}.request.json").write_bytes(request)
        transport = {"timestamp_utc": _utc_now(), "http_status": None, "provider_error": None,
                     "local_error": None, "response_headers": {}, "request_id": None}
        raw = b""
        try:
            result = fn(slot["user_prompt"], timeout)
            raw = result.response_body
            # Preserve the provider body before inspecting or classifying it.
            Path(f"{stem}.response.body").write_bytes(raw)
            transport.update({"http_status": result.http_status, "provider_error": result.error,
                              "response_headers": result.response_headers, "request_id": result.request_id})
            if (result.request_body != request or result.request_obj != build_request(provider, slot["user_prompt"])
                    or result.provider != provider or result.endpoint != manifest["endpoint"]
                    or result.requested_model != manifest["requested_model"]):
                transport["local_error"] = "provider request contract mismatch"
            if result.parsed != _parse(raw):
                transport["local_error"] = "provider parsed response does not match raw body"
        except Exception as exc:
            # Never retry or synthesize a model answer after a local error.
            transport["local_error"] = type(exc).__name__
            Path(f"{stem}.response.body").write_bytes(raw)
        parsed = _parse(raw)
        if parsed is not None:
            write_json(Path(f"{stem}.response.parsed.json"), parsed)
        write_json(Path(f"{stem}.transport.json"), transport)
        receipt = _receipt(manifest, slot, transport, request, raw)
        write_json(run_dir / "receipts" / f"{slot['attempt_id']}.json", receipt)
        receipts.append(receipt)
        print(f"[{provider}] {slot['attempt_id']} {receipt['classification']} "
              f"bytes={receipt['visible_utf8_bytes']} termination={receipt['termination']}")
        if receipt["classification"] in OPERATIONAL_ERRORS:
            break
    summary = _summary(manifest, receipts, _utc_now())
    write_json(run_dir / "summary.json", summary)
    _seal(run_dir)
    print_summary(summary)
    return run_dir


def print_summary(s: dict) -> None:
    print(f"\nSWIFTAPI NATIVE VOID: {s['outcome']}")
    print(f"protocol: {s['protocol_id']}")
    print(f"protocol_sha256: {s['protocol_sha256']}")
    print(f"provider: {s['provider']}")
    print(f"attempts: {s['attempted_count']}/{s['expected_attempts']}")
    print(f"void arm: {s['void_arm_native_voids']}/{s['void_arm_attempts']} native voids")
    print(f"controls: {s['control_visible']}/{s['control_attempts']} visible")
    print(f"errors: {s['errors']}")


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"not a JSON object: {path.name}")
    return value


def verify_run(run_dir: Path) -> tuple[bool, list[str]]:
    """Verify an unkeyed integrity seal and reconstruct results, not provider authentication."""
    try:
        return _verify_run(Path(run_dir))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        return False, [f"malformed or incomplete evidence: {type(exc).__name__}: {exc}"]


def _verify_run(run_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    paths = list(run_dir.rglob("*"))
    if run_dir.is_symlink() or any(p.is_symlink() for p in paths):
        return False, ["symlink in evidence"]
    seal = _read_object(run_dir / "SEAL.json")
    actual_files = {p.relative_to(run_dir).as_posix() for p in paths if p.is_file() and p != run_dir / "SEAL.json"}
    if seal.get("format") != "sha256-file-set-v1" or not isinstance(seal.get("files"), dict):
        return False, ["invalid SEAL.json"]
    if actual_files != set(seal["files"]):
        errors.append("sealed file set mismatch")
    for name in actual_files & set(seal["files"]):
        if sha256_bytes((run_dir / name).read_bytes()) != seal["files"][name]:
            errors.append(f"file hash mismatch: {name}")
    manifest = _read_object(run_dir / "manifest.json")
    freeze = _read_object(run_dir / "FREEZE.json")
    if freeze != {"manifest_sha256": sha256_bytes((run_dir / "manifest.json").read_bytes()),
                  "schedule_sha256": sha256_json(manifest["schedule"])}:
        errors.append("freeze mismatch")
    if (manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("protocol_sha256") != PROTOCOL_SHA256
            or manifest.get("canonical_protocol") != canonical_protocol_dict()
            or sha256_json(manifest.get("canonical_protocol")) != PROTOCOL_SHA256
            or manifest.get("source_doi") != SOURCE_DOI or manifest.get("format_version") != 1
            or manifest.get("automatic_retries") != 0 or manifest.get("abort_policy") != "first_operational_error"):
        errors.append("frozen protocol mismatch")
    provider = manifest["provider"]
    if provider not in {"openai", "anthropic"}:
        return False, errors + ["invalid provider"]
    if (manifest["requested_model"] != (OPENAI_MODEL if provider == "openai" else ANTHROPIC_MODEL)
            or manifest["endpoint"] != (OPENAI_ENDPOINT if provider == "openai" else ANTHROPIC_ENDPOINT)):
        errors.append("provider identity mismatch")
    reps = manifest["reps_per_prompt"]
    case_ids = manifest["case_ids"]
    allowed = {c.case_id: c for c in core_cases()}
    if (type(reps) is not int or reps < 1 or not isinstance(case_ids, list) or not case_ids
            or len(set(case_ids)) != len(case_ids) or any(c not in allowed for c in case_ids)
            or manifest["execution_kind"] not in {"run", "audit"}
            or type(manifest["timeout_seconds"]) is not int or manifest["timeout_seconds"] < 1):
        return False, errors + ["invalid schedule configuration"]
    schedule = _schedule([allowed[c] for c in case_ids], reps)
    if (manifest["schedule"] != schedule or manifest["schedule_sha256"] != sha256_json(schedule)
            or (manifest["execution_kind"] == "run" and len(schedule) != 1)):
        errors.append("schedule mismatch")
    receipt_paths = list((run_dir / "receipts").glob("*.json"))
    if not receipt_paths:
        return False, errors + ["no receipts"]
    receipts = []
    expected_files = {"manifest.json", "FREEZE.json", "summary.json"}
    response_ids: set[str] = set()
    request_ids: set[str] = set()
    aborted = False
    for slot in schedule:
        receipt_path = run_dir / "receipts" / f"{slot['attempt_id']}.json"
        if not receipt_path.exists():
            break
        if aborted:
            errors.append("attempt after operational abort")
        stem = f"raw/{slot['attempt_id']}"
        request = (run_dir / f"{stem}.request.json").read_bytes()
        raw = (run_dir / f"{stem}.response.body").read_bytes()
        transport = _read_object(run_dir / f"{stem}.transport.json")
        expected_files.update({f"{stem}.request.json", f"{stem}.response.body", f"{stem}.transport.json",
                               f"receipts/{slot['attempt_id']}.json"})
        if request != _request_bytes(provider, slot["user_prompt"]):
            errors.append(f"request mismatch: {slot['attempt_id']}")
        parsed = _parse(raw)
        if parsed is not None:
            expected_files.add(f"{stem}.response.parsed.json")
            if _read_object(run_dir / f"{stem}.response.parsed.json") != parsed:
                errors.append(f"raw/parsed mismatch: {slot['attempt_id']}")
        expected_receipt = _receipt(manifest, slot, transport, request, raw)
        receipt = _read_object(receipt_path)
        if receipt != expected_receipt:
            errors.append(f"receipt reconstruction mismatch: {slot['attempt_id']}")
        receipts.append(expected_receipt)
        for name, seen in (("response_id", response_ids), ("request_id", request_ids)):
            identifier = expected_receipt[name]
            if identifier is not None:
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    errors.append(f"invalid or duplicate {name}: {slot['attempt_id']}")
                seen.add(identifier)
        aborted = expected_receipt["classification"] in OPERATIONAL_ERRORS
    if len(receipts) != len(receipt_paths):
        errors.append("unexpected receipts or non-prefix schedule")
    if len(receipts) != len(schedule) and not aborted:
        errors.append("incomplete schedule without operational abort")
    if actual_files != expected_files:
        errors.append("missing or extraneous run files")
    summary = _read_object(run_dir / "summary.json")
    if summary != _summary(manifest, receipts, summary["finished_at"]):
        errors.append("summary reconstruction mismatch")
    return not errors, errors
