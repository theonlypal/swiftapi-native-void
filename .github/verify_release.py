"""Verify the checkout against the immutable PyPI 0.1.0 distribution bytes.

Public download, no credentials or model inference:
    python .github/verify_release.py
Previously downloaded pypi-0.1.0.json and the two distribution archives:
    python .github/verify_release.py --artifacts /absolute/path/to/artifacts
Additionally verify a reproducible local build:
    python .github/verify_release.py --built dist

Only repository infrastructure (.github, examples, RELEASE.md, .gitignore) is
outside the original distribution comparison. Package, tests, scripts, and the
seven original root build/source files must match the published source bytes.
Archives are inspected in memory, never extracted or executed.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile


NAME = "swiftapi-native-void"
VERSION = "0.1.0"
PACKAGE = "swiftapi_native_void"
METADATA_NAME = "pypi-0.1.0.json"
METADATA_URL = "https://pypi.org/pypi/swiftapi-native-void/0.1.0/json"
EXPECTED = {
    "swiftapi_native_void-0.1.0-py3-none-any.whl": {
        "sha256": "44047fc7611b42d4a8660fda9617116c2ce211342e686aaa612708e7403b5a7c",
        "size": 19181,
        "packagetype": "bdist_wheel",
    },
    "swiftapi_native_void-0.1.0.tar.gz": {
        "sha256": "071e786bc058b000aea54029daca3afa601b9f5b6932db40b8d872d3b0d7bb50",
        "size": 23401,
        "packagetype": "sdist",
    },
}
ROOT_FILES = (
    "README.md", "PROTOCOL.md", "LICENSE", "pyproject.toml", "MANIFEST.in",
    "requirements-build.txt", ".env.example",
)
LIMIT = 2 * 1024 * 1024


class VerificationError(Exception):
    """A release assertion failed. Messages contain no credentials."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url: str, host: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    require(
        parsed.scheme == "https" and parsed.netloc == host
        and parsed.hostname == host and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment,
        "Unapproved public artifact URL",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "swiftapi-native-void-release-verifier/0.1.0"})
    with opener.open(request, timeout=60) as response:
        require(response.status == 200, "Public download did not return HTTP 200")
        data = response.read(LIMIT + 1)
    require(len(data) <= LIMIT, "Public artifact exceeds size limit")
    return data


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON metadata key")
        result[key] = value
    return result


def read_metadata(data: bytes) -> dict:
    metadata = json.loads(data.decode("utf-8"), object_pairs_hook=unique_json_object)
    require(isinstance(metadata, dict), "PyPI metadata must be an object")
    info = metadata.get("info")
    require(isinstance(info, dict), "Missing PyPI release identity")
    require(info.get("name") == NAME and info.get("version") == VERSION, "PyPI release identity mismatch")
    require(info.get("yanked") is False, "PyPI release is yanked or has no yanked status")
    rows = metadata.get("urls")
    require(isinstance(rows, list) and len(rows) == len(EXPECTED), "PyPI artifact count mismatch")
    entries = {}
    for row in rows:
        require(isinstance(row, dict), "Malformed PyPI artifact record")
        filename = row.get("filename")
        require(isinstance(filename, str) and filename in EXPECTED, "Unexpected PyPI artifact")
        require(filename not in entries, "Duplicate PyPI artifact")
        expected = EXPECTED[filename]
        require(row.get("packagetype") == expected["packagetype"], "PyPI artifact type mismatch")
        require(row.get("size") == expected["size"], "PyPI artifact size mismatch")
        digests = row.get("digests")
        require(isinstance(digests, dict) and digests.get("sha256") == expected["sha256"], "PyPI SHA-256 differs from pinned release")
        require(row.get("yanked") is False, "PyPI artifact is yanked or has no yanked status")
        require(isinstance(row.get("url"), str), "Missing public artifact URL")
        url = urllib.parse.urlsplit(row["url"])
        require(
            url.scheme == "https" and url.netloc == "files.pythonhosted.org"
            and not url.query and not url.fragment
            and PurePosixPath(url.path).name == filename,
            "Unapproved PyPI artifact location",
        )
        entries[filename] = row
    require(set(entries) == set(EXPECTED), "Incomplete PyPI artifact metadata")
    return entries


def verify_bytes(filename: str, data: bytes) -> None:
    expected = EXPECTED[filename]
    require(len(data) == expected["size"], f"Artifact byte size mismatch: {filename}")
    require(hashlib.sha256(data).hexdigest() == expected["sha256"], f"Artifact SHA-256 mismatch: {filename}")


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in name, "Unsafe archive member")
    return path


def sdist_files(data: bytes) -> dict[str, bytes]:
    files = {}
    seen = set()
    prefix = f"{PACKAGE}-{VERSION}"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            path = safe_member(member.name)
            require(path.parts and path.parts[0] == prefix, "Source archive root mismatch")
            require(member.name not in seen, "Duplicate source archive member")
            seen.add(member.name)
            require(member.isdir() or member.isfile(), "Source archive contains a link or special file")
            if member.isfile():
                require(len(path.parts) > 1, "Malformed source archive file path")
                source = archive.extractfile(member)
                require(source is not None, "Unreadable source archive member")
                files[str(PurePosixPath(*path.parts[1:]))] = source.read()
    return files


def wheel_files(data: bytes) -> dict[str, bytes]:
    files = {}
    seen = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            safe_member(member.filename)
            require(member.filename not in seen, "Duplicate wheel member")
            seen.add(member.filename)
            require(not stat.S_ISLNK(member.external_attr >> 16), "Wheel contains a symbolic link")
            if not member.is_dir():
                files[member.filename] = archive.read(member)
    return files


def verify_identity(data: bytes, label: str) -> None:
    metadata = BytesParser().parsebytes(data)
    require(metadata.get_all("Name") == [NAME], f"{label} name mismatch")
    require(metadata.get_all("Version") == [VERSION], f"{label} version mismatch")


def checkout_python_files(root: Path) -> set[str]:
    files = set()
    for directory in ("src", "tests", "scripts"):
        start = root / directory
        require(start.is_dir() and not start.is_symlink(), f"Missing or linked source directory: {directory}")
        for current, directories, filenames in os.walk(start, followlinks=False):
            for name in directories:
                require(not (Path(current) / name).is_symlink(), f"Linked directory under {directory}")
            for name in filenames:
                path = Path(current) / name
                if path.suffix == ".py":
                    require(path.is_file() and not path.is_symlink(), f"Linked Python source under {directory}")
                    files.add(path.relative_to(root).as_posix())
    return files


def verify_source(root: Path, source: dict[str, bytes], wheel: dict[str, bytes]) -> tuple[int, int]:
    source_python = {
        name for name in source
        if name.endswith(".py") and PurePosixPath(name).parts[0] in {"src", "tests", "scripts"}
    }
    require(checkout_python_files(root) == source_python, "Checkout Python file set differs from published source (missing or extra files)")
    required = source_python | set(ROOT_FILES)
    for name in sorted(required):
        path = root / name
        require(name in source and path.is_file() and not path.is_symlink(), f"Missing or linked source file: {name}")
        require(path.read_bytes() == source[name], f"Checkout differs from published source: {name}")
    package_prefix = f"src/{PACKAGE}/"
    source_modules = {name[4:]: value for name, value in source.items() if name.startswith(package_prefix) and name.endswith(".py")}
    wheel_modules = {name: value for name, value in wheel.items() if name.endswith(".py")}
    require(source_modules == wheel_modules and bool(source_modules), "Wheel Python modules differ from source distribution")
    require("PKG-INFO" in source, "Missing source distribution package metadata")
    metadata_name = f"{PACKAGE}-{VERSION}.dist-info/METADATA"
    require(metadata_name in wheel, "Missing wheel package metadata")
    verify_identity(source["PKG-INFO"], "Source distribution")
    verify_identity(wheel[metadata_name], "Wheel")
    return len(required), len(source_modules)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifacts", type=Path, help="Use previously downloaded PyPI metadata and archives; no network")
    parser.add_argument("--built", type=Path, help="Also check rebuilt distributions against the published hashes")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[1]
        metadata = (args.artifacts / METADATA_NAME).read_bytes() if args.artifacts else download(METADATA_URL, "pypi.org")
        entries = read_metadata(metadata)
        artifacts = {}
        for name, row in entries.items():
            data = (args.artifacts / name).read_bytes() if args.artifacts else download(row["url"], "files.pythonhosted.org")
            verify_bytes(name, data)
            artifacts[name] = data
        source = sdist_files(artifacts[f"{PACKAGE}-{VERSION}.tar.gz"])
        wheel = wheel_files(artifacts[f"{PACKAGE}-{VERSION}-py3-none-any.whl"])
        source_count, module_count = verify_source(root, source, wheel)
        if args.built:
            built_names = {path.name for path in args.built.iterdir() if path.name.endswith((".whl", ".tar.gz"))}
            require(built_names == set(EXPECTED), "Rebuilt distribution file set mismatch")
            for name in EXPECTED:
                verify_bytes(name, (args.built / name).read_bytes())
        print(json.dumps({
            "status": "PASS", "name": NAME, "version": VERSION,
            "artifacts": {name: item["sha256"] for name, item in EXPECTED.items()},
            "source_files_verified": source_count, "package_modules_verified": module_count,
            "mode": "offline" if args.artifacts else "public-download",
            "rebuilt_artifacts_verified": args.built is not None,
        }, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        # Do not serialize exception reprs, network headers, or environment values.
        message = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
        print(json.dumps({"status": "FAIL", "error": message}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
