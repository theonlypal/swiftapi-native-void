"""Build from an explicit source allowlist; normalize sdist metadata."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

EPOCH = 1790553600  # 2026-09-28 00:00:00 UTC


def main() -> None:
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="swiftapi-void-build-") as temp:
        stage = Path(temp) / "source"
        stage.mkdir()
        for name in ("pyproject.toml", "README.md", "PROTOCOL.md", "LICENSE",
                     "MANIFEST.in", ".env.example", "requirements-build.txt"):
            shutil.copyfile(root / name, stage / name)
        for name in ("src/swiftapi_native_void", "tests", "scripts"):
            for source in sorted((root / name).rglob("*.py")):
                target = stage / source.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        env = dict(os.environ, SOURCE_DATE_EPOCH=str(EPOCH), PYTHONHASHSEED="0")
        subprocess.run([sys.executable, "-m", "build", "--no-isolation",
                        "--sdist", "--wheel", "--outdir", str(output), str(stage)],
                       env=env, check=True)
    for archive in sorted(output.glob("*.tar.gz")):
        normalized = io.BytesIO()
        with tarfile.open(archive, "r:gz") as original:
            with gzip.GzipFile(fileobj=normalized, mode="wb", filename="", mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as target:
                    for info in sorted(original.getmembers(), key=lambda item: item.name):
                        data = original.extractfile(info) if info.isfile() else None
                        info.mtime = EPOCH
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mode = 0o755 if info.isdir() else 0o644
                        info.pax_headers = {}
                        target.addfile(info, data)
        archive.write_bytes(normalized.getvalue())
    lines = []
    for file in sorted(output.iterdir()):
        if file.name.endswith((".whl", ".tar.gz")):
            lines.append(f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n")
    (output / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")
    print("".join(lines), end="")


if __name__ == "__main__":
    main()
