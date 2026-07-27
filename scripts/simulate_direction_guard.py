#!/usr/bin/env python3
"""Plan the direction guard separately from the population confidence decision."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import t


def ar1(rng, count, n, rho, sd):
    values = np.empty((count, n))
    values[:, 0] = rng.normal(0.0, sd, size=count)
    innovation = sd * math.sqrt(1.0 - rho**2)
    for index in range(1, n):
        values[:, index] = rho * values[:, index - 1] + rng.normal(0.0, innovation, size=count)
    return values


def exact_ar1_se(n, rho, sd):
    multiplier = 1 + 2 * sum((1 - lag / n) * rho**lag for lag in range(1, n))
    return math.sqrt(sd**2 * multiplier / n)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for design_index, design in enumerate(("iid_normal", "ar1_oracle_interval")):
        for n_index, n in enumerate((10, 20, 35, 50, 150)):
            for effect_index, effect in enumerate((0.0, 2.0, 5.0)):
                rng = np.random.default_rng(args.seed + design_index * 1_000_000 + n_index * 1000 + effect_index)
                values = (
                    rng.normal(0.0, 5.0, size=(args.iterations, n))
                    if design == "iid_normal" else ar1(rng, args.iterations, n, 0.65, 5.0)
                ) + effect
                mean = values.mean(axis=1)
                if design == "iid_normal":
                    se = values.std(axis=1, ddof=1) / math.sqrt(n)
                    critical = float(t.ppf(0.95, n - 1))
                else:
                    se = exact_ar1_se(n, 0.65, 5.0)
                    critical = 1.6448536269514722
                lower = mean - critical * se
                ci_support = lower > 2.0
                guard = (values > 0.0).mean(axis=1) >= 0.80
                rows.append({
                    "design": design, "n_blocks": n, "true_effect_percent": effect,
                    "ci_support_rate": float(ci_support.mean()),
                    "direction_guard_pass_rate": float(guard.mean()),
                    "joint_support_rate": float((ci_support & guard).mean()),
                    "ci_support_guard_fail_rate": float((ci_support & ~guard).mean()),
                    "iterations": args.iterations,
                })
    output = args.output_dir / "direction_guard_operating_characteristics.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    metadata = {
        "rule_semantics": "The confidence bound addresses the population mean under the declared estimand. The 80% direction guard is a sample-level stability safeguard, not an alpha adjustment or a population sign claim.",
        "conflict_rule": "If a confidence interval supports a material effect but the direction guard fails, the engine returns Inconclusive; the guard alone never produces Contradicted.",
        "ar1_note": "The AR(1) rows use oracle known-generator variance solely to demonstrate a compatible path. They do not validate an autocorrelation estimator.",
    }
    (args.output_dir / "direction_guard_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
