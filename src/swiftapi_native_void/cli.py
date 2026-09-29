from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import run_provider, verify_run
from .protocol import (
    CONFIRMATORY_REPS,
    EMPTY_SHA256,
    PRIMARY_SYSTEM,
    PROTOCOL_ID,
    PROTOCOL_SHA256,
    canonical_protocol_dict,
    core_cases,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="swiftapi-void",
        description="Run and verify Rayan Pal's canonical model-native noncontinuation protocol.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    proto = sub.add_parser("protocol", help="Print the immutable canonical protocol")
    proto.add_argument("--json", action="store_true", help="print machine-readable JSON")

    run = sub.add_parser("run", help="One fresh canonical request per selected provider (default: Be the null.)")
    run.add_argument("--provider", choices=["openai", "anthropic", "both"], default="openai")
    run.add_argument("--prompt", choices=["null", "silence", "nothing", "hello", "cat"], default="null")
    run.add_argument("--out", default="swiftapi_void_runs")
    run.add_argument("--timeout", type=int, default=120)

    audit = sub.add_parser("audit", help="Run the canonical core-confirmatory audit")
    audit.add_argument("--provider", choices=["openai", "anthropic", "both"], default="both")
    audit.add_argument("--reps", type=int, default=CONFIRMATORY_REPS, help="repetitions per prompt; canonical confirmatory value is 30")
    audit.add_argument("--out", default="swiftapi_void_runs", help="output directory")
    audit.add_argument("--timeout", type=int, default=120)

    verify = sub.add_parser("verify", help="Offline verification of a completed run directory")
    verify.add_argument("run_dir")

    return p


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.command == "protocol":
        if args.json:
            print(json.dumps(canonical_protocol_dict(), indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(f"protocol_id: {PROTOCOL_ID}")
            print(f"protocol_sha256: {PROTOCOL_SHA256}")
            print(f"empty_sha256: {EMPTY_SHA256}")
            print("\nPRIMARY SYSTEM PROMPT")
            print(PRIMARY_SYSTEM)
            print("\nRun `swiftapi-void protocol --json` for the complete frozen machine-readable protocol.")
        return

    if args.command in {"audit", "run"}:
        if args.timeout < 1:
            parser.error("--timeout must be >= 1")
        reps = args.reps if args.command == "audit" else 1
        if reps < 1:
            parser.error("--reps must be >= 1")
        cases = None
        if args.command == "run":
            index = {"silence": 0, "nothing": 1, "null": 2, "hello": 3, "cat": 4}
            cases = (core_cases()[index[args.prompt]],)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        providers = ["openai", "anthropic"] if args.provider == "both" else [args.provider]
        run_dirs: list[Path] = []
        exit_code = 0
        for provider in providers:
            try:
                directory = run_provider(provider, out, reps=reps, timeout=args.timeout,
                                         cases=cases, execution_kind=args.command)
            except (ValueError, RuntimeError, OSError) as exc:
                print(f"{provider}: {exc}")
                exit_code = 2
                continue
            run_dirs.append(directory)
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            if not summary.get("complete") or summary.get("errors"):
                exit_code = 2
            elif summary.get("outcome") == "NOT_REPRODUCED" and exit_code == 0:
                exit_code = 3
        print("\nRun directories:")
        for d in run_dirs:
            print(d)
        if exit_code:
            raise SystemExit(exit_code)
        return

    if args.command == "verify":
        ok, errors = verify_run(Path(args.run_dir))
        if ok:
            print("VERIFIED: frozen requests, raw responses, classifications, schedule, and hashes")
            return
        print("FAIL")
        for e in errors:
            print(f"- {e}")
        raise SystemExit(1)
