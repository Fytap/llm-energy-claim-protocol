#!/usr/bin/env python3
"""Verify the SHA-256 hashes for the shipped source and input payload."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_manifest() -> list[tuple[str, Path]]:
    records: list[tuple[str, Path]] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        expected, relative = line.split("  ", maxsplit=1)
        candidate = (ROOT / relative).resolve()
        if ROOT not in candidate.parents or not candidate.is_file():
            raise RuntimeError(f"Invalid manifest path: {relative}")
        records.append((expected, candidate))
    if not records:
        raise RuntimeError("Manifest contains no records.")
    return records


def main() -> None:
    failures = []
    for expected, path in parse_manifest():
        observed = sha256(path)
        if not hmac.compare_digest(expected, observed):
            failures.append(path.relative_to(ROOT).as_posix())
    if failures:
        raise RuntimeError(f"SHA-256 verification failed: {', '.join(failures)}")
    print(f"Verified {len(parse_manifest())} source and input files against MANIFEST.sha256")


if __name__ == "__main__":
    main()
