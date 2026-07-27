#!/usr/bin/env python3
"""Stress-test the upstream-adjudication assumption of the local checker.

The engine can deterministically reject malformed or revoked local records. It
cannot detect a scientifically wrong but syntactically valid upstream attestation.
This simulation makes that residual risk explicit rather than treating the
provenance fields as an independent evidence validation.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    # One critical gate governs promotion. FPR means an invalid gate is attested
    # as pass; FNR means a valid gate is rejected/not attested.
    for index, error_rate in enumerate((0.01, 0.05, 0.10)):
        rng = np.random.default_rng(args.seed + index)
        false_promotion = rng.random(args.iterations) < error_rate
        rng = np.random.default_rng(args.seed + 100 + index)
        false_rejection = rng.random(args.iterations) < error_rate
        rows.extend([
            {
                "scenario": "invalid_critical_gate_upstream_false_pass",
                "upstream_error_rate": error_rate, "iterations": args.iterations,
                "local_provenance_checks_pass": True,
                "false_promotion_rate": float(false_promotion.mean()),
                "abstention_or_false_rejection_rate": 0.0,
                "interpretation": "Residual promotion risk if an upstream reviewer incorrectly attests an invalid critical gate as pass.",
            },
            {
                "scenario": "valid_critical_gate_upstream_false_nonpass",
                "upstream_error_rate": error_rate, "iterations": args.iterations,
                "local_provenance_checks_pass": True,
                "false_promotion_rate": 0.0,
                "abstention_or_false_rejection_rate": float(false_rejection.mean()),
                "interpretation": "Cost of conservative abstention if an upstream reviewer incorrectly rejects or omits a valid critical gate.",
            },
            {
                "scenario": "manifest_detectable_attack",
                "upstream_error_rate": error_rate, "iterations": args.iterations,
                "local_provenance_checks_pass": False,
                "false_promotion_rate": 0.0,
                "abstention_or_false_rejection_rate": 1.0,
                "interpretation": "Forged identifier, changed digest, stale/revoked record, self-review or wrong-role record is deterministically withheld when the local manifest is available.",
            },
        ])
    output = args.output_dir / "upstream_attestation_error_stress.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    metadata = {
        "scope": "Bernoulli sensitivity analysis, not an empirical estimate of reviewer error.",
        "key_limit": "Local provenance checks prevent only locally observable record failures. They cannot independently validate a scientifically wrong but well-formed attestation.",
        "decision_cost": "False promotion and abstention are reported separately because their relative loss must be set by the service owner and claim context.",
    }
    (args.output_dir / "upstream_attestation_error_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
