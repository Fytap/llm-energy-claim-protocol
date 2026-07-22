#!/usr/bin/env python3
"""Synthetic positive control for an inference-compatible AR(1) interval.

This planning control is deliberately model matched: the stationary AR(1)
parameter and marginal standard deviation are fixed by the data generator, and
the interval uses the corresponding exact variance of the sample mean. It is
therefore a test of the protocol's compatible-inference path, not a validation
of an autocorrelation estimator, a meter, or GPU telemetry.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np


NORMAL_95 = NormalDist().inv_cdf(0.95)


def stationary_ar1(
    rng: np.random.Generator,
    iterations: int,
    n_blocks: int,
    rho: float,
    marginal_sd: float,
) -> np.ndarray:
    """Generate a stationary Gaussian AR(1) sequence with the declared SD."""
    innovation_sd = marginal_sd * math.sqrt(1.0 - rho**2)
    values = np.empty((iterations, n_blocks))
    values[:, 0] = rng.normal(0.0, marginal_sd, size=iterations)
    for index in range(1, n_blocks):
        values[:, index] = rho * values[:, index - 1] + rng.normal(
            0.0, innovation_sd, size=iterations
        )
    return values


def exact_mean_se(n_blocks: int, rho: float, marginal_sd: float) -> float:
    multiplier = 1.0 + 2.0 * sum(
        (1.0 - lag / n_blocks) * rho**lag for lag in range(1, n_blocks)
    )
    return math.sqrt((marginal_sd**2 / n_blocks) * multiplier)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--n-blocks", type=int, default=150)
    parser.add_argument("--rho", type=float, default=0.65)
    parser.add_argument("--marginal-sd-percent", type=float, default=5.0)
    parser.add_argument("--sesoi-percent", type=float, default=2.0)
    parser.add_argument("--direction-fraction", type=float, default=0.80)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    standard_error = exact_mean_se(args.n_blocks, args.rho, args.marginal_sd_percent)
    rows: list[dict[str, object]] = []
    for offset, true_effect in enumerate((0.0, 2.0, 5.0)):
        rng = np.random.default_rng(args.seed + offset)
        values = stationary_ar1(
            rng, args.iterations, args.n_blocks, args.rho, args.marginal_sd_percent
        ) + true_effect
        means = values.mean(axis=1)
        lower = means - NORMAL_95 * standard_error
        upper = means + NORMAL_95 * standard_error
        favorable = (values > 0.0).mean(axis=1) >= args.direction_fraction
        supported = (lower > args.sesoi_percent) & favorable
        contradicted = upper < args.sesoi_percent
        lower_coverage = float(np.mean(lower <= true_effect))
        upper_coverage = float(np.mean(upper >= true_effect))
        rows.append(
            {
                "scenario": (
                    "ar1_model_based_null" if true_effect == 0.0
                    else "ar1_model_based_exact_sesoi" if true_effect == args.sesoi_percent
                    else "ar1_model_based_5_percent"
                ),
                "true_effect_percent": true_effect,
                "iterations": args.iterations,
                "n_blocks": args.n_blocks,
                "rho": args.rho,
                "marginal_sd_percent": args.marginal_sd_percent,
                "sesoi_percent": args.sesoi_percent,
                "direction_fraction": args.direction_fraction,
                "interval_method": "predeclared AR(1) model-based exact-variance normal interval",
                "interval_information": "Oracle positive control: rho and marginal SD are fixed by the generator and supplied to the interval.",
                "exact_standard_error_percent": standard_error,
                "one_sided_lower_95_coverage": lower_coverage,
                "one_sided_upper_95_coverage": upper_coverage,
                "mean_one_sided_interval_width_percent": float(np.mean(upper - lower)),
                "supported_rate": float(np.mean(supported)),
                "contradicted_rate": float(np.mean(contradicted)),
                "inconclusive_rate": float(np.mean(~supported & ~contradicted)),
                "false_support_rate": float(np.mean(supported)) if true_effect <= args.sesoi_percent else 0.0,
                "false_contradiction_rate": float(np.mean(contradicted)) if true_effect > args.sesoi_percent else 0.0,
                "power_supported_rate": float(np.mean(supported)) if true_effect > args.sesoi_percent else 0.0,
            }
        )

    output = args.output_dir / "model_based_ar1_summary.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "scope": "Synthetic model-matched positive control; not a fitted GPU, meter or organizational model.",
        "seed": args.seed,
        "iterations": args.iterations,
        "n_blocks": args.n_blocks,
        "rho": args.rho,
        "marginal_sd_percent": args.marginal_sd_percent,
        "sesoi_percent": args.sesoi_percent,
        "direction_fraction": args.direction_fraction,
        "interval_method": "AR(1) model-based exact variance under the known generator",
    }
    (args.output_dir / "model_based_ar1_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
