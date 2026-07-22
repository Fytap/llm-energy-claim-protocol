#!/usr/bin/env python3
"""Evaluate all public machine-readable claim objects with the gate registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import classify_claim_object, load_gate_registry, load_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims-dir", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registry = load_gate_registry(args.registry)
    results = []
    for claim_path in sorted(args.claims_dir.glob("*.json")):
        classification = classify_claim_object(load_json(claim_path), registry)
        item = classification.to_dict()
        item["source_file"] = claim_path.name
        results.append(item)
    if not results:
        raise RuntimeError("No claim objects found.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"release": "public", "classifications": results}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classifications": [{"id": item["claim_id"], "state": item["state"]} for item in results]}, indent=2))


if __name__ == "__main__":
    main()
