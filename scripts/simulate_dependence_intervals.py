#!/usr/bin/env python3
"""Compare dependence-aware interval estimators in synthetic AR(1) planning data.

The simulation deliberately separates an oracle control (reported by the current
script) from practicable estimators that do not receive the generator's rho or
variance.  It is a planning study, not a fitted description of GPU telemetry.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import norm, t


Z95 = float(norm.ppf(0.95))


def stationary_ar1(rng: np.random.Generator, count: int, n: int, rho: float, sd: float) -> np.ndarray:
    innovation_sd = sd * math.sqrt(1.0 - rho**2)
    values = np.empty((count, n))
    values[:, 0] = rng.normal(0.0, sd, size=count)
    for column in range(1, n):
        values[:, column] = rho * values[:, column - 1] + rng.normal(0.0, innovation_sd, size=count)
    return values


def iid_bounds(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = values.shape[1]
    mean = values.mean(axis=1)
    se = values.std(axis=1, ddof=1) / math.sqrt(n)
    critical = float(t.ppf(0.95, n - 1))
    return mean - critical * se, mean + critical * se


def ar1_estimated_bounds(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normal bounds using a Yule--Walker rho estimate and sample marginal SD."""
    n = values.shape[1]
    mean = values.mean(axis=1)
    centered = values - mean[:, None]
    denominator = np.sum(centered[:, :-1] ** 2, axis=1)
    rho = np.divide(
        np.sum(centered[:, 1:] * centered[:, :-1], axis=1),
        denominator,
        out=np.zeros(values.shape[0]),
        where=denominator > 1e-12,
    )
    rho = np.clip(rho, -0.95, 0.95)
    marginal_sd = values.std(axis=1, ddof=1)
    lags = np.arange(1, n)
    multiplier = 1.0 + 2.0 * np.sum(
        (1.0 - lags / n)[None, :] * rho[:, None] ** lags[None, :], axis=1
    )
    se = marginal_sd * np.sqrt(np.maximum(multiplier, 1e-12) / n)
    return mean - Z95 * se, mean + Z95 * se


def hac_bartlett_bounds(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Newey--West/Bartlett normal bounds with an explicitly stored rule-of-thumb lag."""
    n = values.shape[1]
    lag = max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))
    mean = values.mean(axis=1)
    centered = values - mean[:, None]
    long_run_variance = np.mean(centered**2, axis=1)
    for offset in range(1, lag + 1):
        weight = 1.0 - offset / (lag + 1.0)
        gamma = np.mean(centered[:, offset:] * centered[:, :-offset], axis=1)
        long_run_variance += 2.0 * weight * gamma
    se = np.sqrt(np.maximum(long_run_variance, 1e-12) / n)
    return mean - Z95 * se, mean + Z95 * se


def moving_block_bootstrap_bounds(
    values: np.ndarray,
    rng: np.random.Generator,
    resamples: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Circular moving-block percentile bounds, chunked to bound memory use."""
    count, n = values.shape
    block_length = max(2, int(round(n ** (1.0 / 3.0))))
    blocks_needed = int(math.ceil(n / block_length))
    offsets = np.arange(block_length)
    lower = np.empty(count)
    upper = np.empty(count)
    chunk_size = 128
    for start in range(0, count, chunk_size):
        stop = min(count, start + chunk_size)
        chunk = values[start:stop]
        starts = rng.integers(0, n, size=(stop - start, resamples, blocks_needed))
        indices = (starts[..., None] + offsets[None, None, None, :]) % n
        indices = indices.reshape(stop - start, resamples, -1)[..., :n]
        samples = np.take_along_axis(chunk[:, None, :], indices, axis=2)
        means = samples.mean(axis=2)
        lower[start:stop] = np.quantile(means, 0.05, axis=1)
        upper[start:stop] = np.quantile(means, 0.95, axis=1)
    return lower, upper


def outcomes(
    lower: np.ndarray,
    upper: np.ndarray,
    values: np.ndarray,
    effect: float,
    sesoi: float,
    direction_fraction: float,
) -> dict[str, float]:
    favorable = np.mean(values > 0.0, axis=1) >= direction_fraction
    supported = (lower > sesoi) & favorable
    contradicted = upper < sesoi
    material = effect > sesoi
    return {
        "one_sided_lower_95_coverage": float(np.mean(lower <= effect)),
        "one_sided_upper_95_coverage": float(np.mean(upper >= effect)),
        "mean_one_sided_interval_width_percent": float(np.mean(upper - lower)),
        "supported_rate": float(np.mean(supported)),
        "contradicted_rate": float(np.mean(contradicted)),
        "inconclusive_rate": float(np.mean(~supported & ~contradicted)),
        "false_support_rate": float(np.mean(supported)) if not material else 0.0,
        "false_contradiction_rate": float(np.mean(contradicted)) if material else 0.0,
        "power_supported_rate": float(np.mean(supported)) if material else 0.0,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--bootstrap-iterations", type=int, default=2_000)
    parser.add_argument("--bootstrap-resamples", type=int, default=199)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--rho", type=float, default=0.65)
    parser.add_argument("--marginal-sd-percent", type=float, default=5.0)
    parser.add_argument("--sesoi-percent", type=float, default=2.0)
    parser.add_argument("--direction-fraction", type=float, default=0.80)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    method_specs = (
        ("iid_t_reference", iid_bounds, args.iterations),
        ("estimated_ar1_model", ar1_estimated_bounds, args.iterations),
        ("hac_bartlett", hac_bartlett_bounds, args.iterations),
        ("moving_block_bootstrap", None, args.bootstrap_iterations),
    )
    for n_index, n_blocks in enumerate((10, 35, 150)):
        for effect_index, effect in enumerate((0.0, 2.0, 5.0)):
            for method_index, (method, bound_function, iterations) in enumerate(method_specs):
                rng = np.random.default_rng(args.seed + n_index * 1_000 + effect_index * 100 + method_index)
                values = stationary_ar1(
                    rng, iterations, n_blocks, args.rho, args.marginal_sd_percent
                ) + effect
                if method == "moving_block_bootstrap":
                    lower, upper = moving_block_bootstrap_bounds(
                        values, rng, args.bootstrap_resamples
                    )
                else:
                    assert bound_function is not None
                    lower, upper = bound_function(values)
                row = {
                    "scenario": "stationary_ar1_unknown_dependence",
                    "interval_method": method,
                    "n_blocks": n_blocks,
                    "true_effect_percent": effect,
                    "rho_generator": args.rho,
                    "marginal_sd_percent": args.marginal_sd_percent,
                    "sesoi_percent": args.sesoi_percent,
                    "direction_fraction": args.direction_fraction,
                    "iterations": iterations,
                    "bootstrap_resamples": args.bootstrap_resamples if method == "moving_block_bootstrap" else 0,
                }
                row.update(outcomes(
                    lower, upper, values, effect, args.sesoi_percent, args.direction_fraction
                ))
                rows.append(row)
    write_csv(args.output_dir / "dependence_interval_operating_characteristics.csv", rows)
    metadata = {
        "scope": "Synthetic AR(1) planning comparison. No row is fitted to GPU telemetry or a physical meter.",
        "generator": {
            "stationary_initialization": True,
            "rho": args.rho,
            "marginal_sd_percent": args.marginal_sd_percent,
        },
        "methods": {
            "iid_t_reference": "Reference only; intentionally incompatible with AR(1) dependence and never a candidate for a supported dependent-data claim.",
            "estimated_ar1_model": "Yule--Walker rho and sample marginal SD; normal approximation. It does not receive generator parameters.",
            "hac_bartlett": "Bartlett/Newey--West long-run variance with a documented rule-of-thumb lag; normal approximation.",
            "moving_block_bootstrap": "Circular moving-block percentile interval; block length round(n^(1/3)); 199 bootstrap resamples by default.",
        },
        "interpretation": "The engine can receive a pass for dependence_compatible_interval only when the analyst prospectively documents why the interval matches the declared design and diagnostics. This simulation does not automate that judgment.",
    }
    (args.output_dir / "dependence_interval_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
