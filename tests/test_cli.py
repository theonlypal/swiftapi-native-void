import json
from pathlib import Path
import sys

import pytest

from swiftapi_native_void import cli
from swiftapi_native_void.protocol import PROTOCOL_SHA256


def test_frozen_protocol(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["swiftapi-void", "protocol"])
    cli.main()
    assert PROTOCOL_SHA256 == "4446b3f0313d4cfc777d4f40e3f2f52a2c5bb80cb207b52aef08e7ce777c8cff"
    assert PROTOCOL_SHA256 in capsys.readouterr().out


def test_default_single_run(monkeypatch, tmp_path):
    calls = []
    def run(provider, out, **kwargs):
        calls.append((provider, kwargs))
        target = out / provider
        target.mkdir()
        (target / "summary.json").write_text(json.dumps({"complete": True, "outcome": "OBSERVATION", "errors": 0}))
        return target
    monkeypatch.setattr(cli, "run_provider", run)
    monkeypatch.setattr(sys, "argv", ["swiftapi-void", "run", "--out", str(tmp_path)])
    cli.main()
    assert len(calls) == 1
    provider, config = calls[0]
    assert provider == "openai"
    assert config["reps"] == 1
    assert config["execution_kind"] == "run"
    assert [case.prompt for case in config["cases"]] == ["Be the null."]


def test_missing_key_exits_nonzero(monkeypatch, tmp_path):
    def run(*args, **kwargs):
        raise RuntimeError("OPENAI_API_KEY is not set")
    monkeypatch.setattr(cli, "run_provider", run)
    monkeypatch.setattr(sys, "argv", ["swiftapi-void", "run", "--out", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("summary,code", [
    ({"complete": False, "errors": 1, "outcome": "INCOMPLETE"}, 2),
    ({"complete": True, "errors": 0, "outcome": "NOT_REPRODUCED"}, 3),
])
def test_run_status_exit(monkeypatch, tmp_path, summary, code):
    def run(*args, **kwargs):
        (tmp_path / "summary.json").write_text(json.dumps(summary))
        return tmp_path
    monkeypatch.setattr(cli, "run_provider", run)
    monkeypatch.setattr(sys, "argv", ["swiftapi-void", "audit", "--provider", "openai", "--out", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == code


def test_verify_without_network(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "verify_run", lambda path: (True, []))
    monkeypatch.setattr(sys, "argv", ["swiftapi-void", "verify", str(tmp_path)])
    cli.main()
    assert "VERIFIED:" in capsys.readouterr().out
