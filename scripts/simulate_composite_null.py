#!/usr/bin/env python3
"""Evaluate CI-plus-direction decisions across the declared composite null.

The simulator treats a claim as material only when the true effect is strictly
above the 2 percentage-point SESOI. It reports the zero point and the boundary
separately. B0 is retained as a deliberately naive point-estimate comparator,
not as a competing assurance method.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import t


def draw(rng: np.random.Generator, distribution: str, size: tuple[int, int], sd: float) -> np.ndarray:
    count, n = size
    if distribution == "iid_normal":
        return rng.normal(0.0, sd, size=size)
    if distribution == "iid_t3":
        return rng.standard_t(3, size=size) * (sd / math.sqrt(3.0))
    if distribution == "heteroscedastic":
        scales = np.where(np.arange(n) % 2 == 0, 0.55 * sd, 1.30 * sd)
        return rng.normal(0.0, scales, size=size)
    if distribution == "stationary_ar1":
        rho, innovation_sd = 0.65, sd * math.sqrt(1.0 - 0.65**2)
        values = np.empty(size)
        values[:, 0] = rng.normal(0.0, sd, size=count)
        for index in range(1, n):
            values[:, index] = rho * values[:, index - 1] + rng.normal(0.0, innovation_sd, size=count)
        return values
    raise ValueError(distribution)


def row(values: np.ndarray, effect: float, sesoi: float, direction: float, scenario: str, method: str) -> dict[str, object]:
    n = values.shape[1]
    mean = values.mean(axis=1)
    se = values.std(axis=1, ddof=1) / math.sqrt(n)
    critical = float(t.ppf(0.95, n - 1))
    lower, upper = mean - critical * se, mean + critical * se
    b0 = mean > sesoi
    b1 = lower > sesoi
    guard = (values > 0.0).mean(axis=1) >= direction
    b2 = b1 & guard
    material = effect > sesoi
    return {
        "scenario": scenario, "interval_method": method, "n_blocks": n,
        "true_effect_percent": effect, "sesoi_percent": sesoi,
        "direction_fraction": direction,
        "b0_naive_point_estimate_rate": float(np.mean(b0)),
        "b1_ci_only_support_rate": float(np.mean(b1)),
        "full_ci_direction_support_rate": float(np.mean(b2)),
        "ci_contradicted_rate": float(np.mean(upper < sesoi)),
        "direction_guard_pass_rate": float(np.mean(guard)),
        "ci_support_guard_fail_rate": float(np.mean(b1 & ~guard)),
        "composite_null_false_support_full": float(np.mean(b2)) if not material else 0.0,
        "material_effect_support_rate_full": float(np.mean(b2)) if material else 0.0,
        "iterations": values.shape[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--n-blocks", type=int, default=10)
    parser.add_argument("--sd-percent", type=float, default=5.0)
    parser.add_argument("--sesoi-percent", type=float, default=2.0)
    parser.add_argument("--direction-fraction", type=float, default=0.80)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    # IID normal is the compatible main operating-characteristic reference.
    for index, effect in enumerate((0.0, 0.5, 1.0, 1.5, 2.0, 2.1, 2.5, 5.0)):
        values = draw(np.random.default_rng(args.seed + index), "iid_normal", (args.iterations, args.n_blocks), args.sd_percent) + effect
        rows.append(row(values, effect, args.sesoi_percent, args.direction_fraction, "iid_normal", "iid one-sided t"))
    # Non-IID rows deliberately report naive iid-rule behavior only. The protocol
    # would mark them inconclusive unless a predeclared compatible interval passes.
    for index, scenario in enumerate(("iid_t3", "heteroscedastic", "stationary_ar1"), start=100):
        for effect in (0.0, 2.0, 5.0):
            values = draw(np.random.default_rng(args.seed + index + int(effect * 10)), scenario, (args.iterations, args.n_blocks), args.sd_percent) + effect
            rows.append(row(values, effect, args.sesoi_percent, args.direction_fraction, scenario, "naive iid one-sided t; incompatible by design"))
    output = args.output_dir / "composite_null_operating_characteristics.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    iid_null = [item for item in rows if item["scenario"] == "iid_normal" and item["true_effect_percent"] <= args.sesoi_percent]
    metadata = {
        "scope": "Synthetic decision-rule operating characteristics, not fitted telemetry or a physical-meter study.",
        "composite_null": f"true effect <= {args.sesoi_percent} percentage points",
        "interpretation": "For compatible IID normal data, the maximum Full-rule false-support rate across the evaluated composite-null grid is the relevant planning quantity; the true-zero point is reported separately.",
        "naive_comparator": "B0 is a sample-mean threshold retained to illustrate why a point estimate alone is not an assurance comparator.",
        "max_full_false_support_evaluated_iid_grid": max(item["composite_null_false_support_full"] for item in iid_null),
        "zero_effect_full_false_support": next(item["composite_null_false_support_full"] for item in iid_null if item["true_effect_percent"] == 0.0),
        "boundary_full_false_support": next(item["composite_null_false_support_full"] for item in iid_null if item["true_effect_percent"] == args.sesoi_percent),
        "non_iid_interpretation": "T3, heteroscedastic and AR(1) rows are stress demonstrations of naive iid inference. A conformant protocol record must instead use an assessed, dependence-compatible interval.",
    }
    (args.output_dir / "composite_null_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
