#!/usr/bin/env python3
"""Regenerate the canonical manifest from Git-tracked source and input files."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def sha256(path: Path) -> str:
    payload = path.read_bytes()
    try:
        payload = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    except UnicodeDecodeError:
        pass
    return hashlib.sha256(payload).hexdigest()


def tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    )
    paths = [ROOT / item for item in result.stdout.splitlines() if item and item != MANIFEST.name]
    if not all(path.is_file() for path in paths):
        raise RuntimeError("Git returned a non-file manifest entry.")
    return paths


def main() -> None:
    records = sorted(
        (path.relative_to(ROOT).as_posix(), sha256(path)) for path in tracked_paths()
    )
    lines = [
        "# SHA-256 manifest for the shipped source and input payload.",
        "# UTF-8 text files are hashed after LF line-ending canonicalization so the",
        "# verification result is stable across Windows and POSIX checkouts.",
        "# Generated files under results/ and templates/generated/ are intentionally excluded.",
        *[f"{digest}  {relative}" for relative, digest in records],
        "",
    ]
    MANIFEST.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote {len(records)} canonical hashes to {MANIFEST.name}")


if __name__ == "__main__":
    main()
