#!/usr/bin/env python3
"""Audit built distributions for public-safe file contents."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path


FORBIDDEN_PATH_PARTS = {
    ".git",
    ".taskconfig.md",
    ".venv",
    "__pycache__",
    "config.local.json",
    "data",
    "exports",
    "var",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
}

FORBIDDEN_CONTENT_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"/" "Users/",
        r"/" "Volumes/",
        r"sk-[A-Za-z0-9]",
        r"ghp_[A-Za-z0-9]",
        r"xox[baprs]-",
        r"AKIA[0-9A-Z]{16}",
    ]
]


def iter_archive_files(path: Path):
    if path.suffix == ".whl" or path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith("/"):
                    yield name, archive.read(name)
        return
    if path.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        yield member.name, extracted.read()
        return
    raise ValueError(f"unsupported distribution format: {path}")


def audit_path(name: str) -> list[str]:
    errors = []
    parts = set(Path(name).parts)
    lowered_parts = {part.lower() for part in parts}
    if FORBIDDEN_PATH_PARTS & lowered_parts:
        errors.append(f"forbidden path part in {name}")
    if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
        errors.append(f"forbidden file suffix in {name}")
    return errors


def audit_content(name: str, data: bytes) -> list[str]:
    if len(data) > 1_000_000:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    errors = []
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        if pattern.search(text):
            errors.append(f"forbidden content pattern {pattern.pattern!r} in {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", nargs="+", type=Path, help="sdist/wheel paths to audit")
    args = parser.parse_args(argv)

    errors: list[str] = []
    for dist_path in args.dist:
        if not dist_path.exists():
            errors.append(f"missing distribution: {dist_path}")
            continue
        for name, data in iter_archive_files(dist_path):
            errors.extend(audit_path(name))
            errors.extend(audit_content(name, data))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("distribution audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
