#!/usr/bin/env python3
"""Verify the SHA-256 hashes for the shipped source and input payload."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def sha256(path: Path) -> str:
    """Hash source files reproducibly across LF and CRLF checkouts.

    The shipped payload is UTF-8 text. Git and ZIP tools may materialize its
    line endings differently on Windows, so text payloads are canonicalized to
    LF before hashing. A non-UTF-8 file remains byte-for-byte hashed.
    """
    payload = path.read_bytes()
    try:
        payload = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    except UnicodeDecodeError:
        pass
    return hashlib.sha256(payload).hexdigest()


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
