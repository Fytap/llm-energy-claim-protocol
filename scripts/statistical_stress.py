#!/usr/bin/env python3
"""Illustrative ratio, drift, change-point, and heteroscedastic stress analyses.

The scenarios are synthetic decision-rule diagnostics. They are not fitted to a
GPU, meter, workload, or reviewer population and do not validate a universal
SESOI, direction guard, or interval method.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import t

from decision_policy import NumericDecisionRule, NumericState


ROOT = Path(__file__).resolve().parents[1]
DRAW_COUNT = 100_000
ROOT_SEED = 20260721
RULE = NumericDecisionRule(sesoi_percent=2.0, direction_fraction=0.8)


def _interval_states(samples: np.ndarray, scale: str, compatible: bool) -> dict[str, float]:
    """Classify paired sample effects with an IID t interval; mark known mismatches invalid."""
    n = samples.shape[1]
    mean = samples.mean(axis=1)
    sd = samples.std(axis=1, ddof=1)
    se = sd / np.sqrt(n)
    quantile = t.ppf(0.95, df=n - 1)
    lower = mean - quantile * se
    upper = mean + quantile * se
    favorable = (samples > 0.0).sum(axis=1)
    if scale == "log_ratio":
        threshold = -np.log1p(-RULE.sesoi_percent / 100.0)
        lower_cmp = lower
        upper_cmp = upper
        direction = (samples > 0.0).sum(axis=1)
        support = (lower_cmp > threshold + RULE.tolerance) & (direction >= RULE.required_favorable_blocks(n))
        contradicted = upper_cmp < threshold - RULE.tolerance
    else:
        support = (lower > RULE.sesoi_percent + RULE.tolerance) & (favorable >= RULE.required_favorable_blocks(n))
        contradicted = upper < RULE.sesoi_percent - RULE.tolerance
    if not compatible:
        return {"supported": 0.0, "contradicted": 0.0, "inconclusive": 1.0}
    return {
        "supported": float(support.mean()),
        "contradicted": float((~support & contradicted).mean()),
        "inconclusive": float((~support & ~contradicted).mean()),
    }


def _row(name: str, true_effect: float, scale: str, compatible: bool, states: dict[str, float]) -> dict[str, object]:
    return {
        "scenario": name,
        "true_effect_percent": true_effect,
        "effect_scale": scale,
        "iid_interval_compatible": compatible,
        "draws": DRAW_COUNT,
        "supported_probability": states["supported"],
        "supported_mc_se": np.sqrt(states["supported"] * (1.0 - states["supported"]) / DRAW_COUNT),
        "contradicted_probability": states["contradicted"],
        "contradicted_mc_se": np.sqrt(states["contradicted"] * (1.0 - states["contradicted"]) / DRAW_COUNT),
        "inconclusive_probability": states["inconclusive"],
        "inconclusive_mc_se": np.sqrt(states["inconclusive"] * (1.0 - states["inconclusive"]) / DRAW_COUNT),
    }


def run(output_dir: Path) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(ROOT_SEED)
    n = 20
    rows: list[dict[str, object]] = []

    iid = rng.normal(loc=5.0, scale=5.0, size=(DRAW_COUNT, n))
    rows.append(_row("iid_percent_reduction", 5.0, "percent_reduction", True, _interval_states(iid, "percent_reduction", True)))

    # Log-ratio scenario with a lognormal baseline and scale-dependent paired noise.
    baseline = rng.lognormal(mean=np.log(100.0), sigma=0.45, size=(DRAW_COUNT, n))
    relative_noise = rng.normal(loc=0.0, scale=0.08 + 0.00015 * baseline, size=(DRAW_COUNT, n))
    treatment = baseline * 0.95 * np.exp(relative_noise)
    log_ratio = np.log(baseline / treatment)
    rows.append(_row("paired_log_ratio_with_denominator_variation", 5.0, "log_ratio", True, _interval_states(log_ratio, "log_ratio", True)))

    heteroscedastic = rng.normal(loc=5.0, scale=np.linspace(2.0, 9.0, n), size=(DRAW_COUNT, n))
    rows.append(_row("unbalanced_heteroscedastic_percent_reduction", 5.0, "percent_reduction", False, _interval_states(heteroscedastic, "percent_reduction", False)))

    drift = rng.normal(loc=5.0 + np.linspace(-3.0, 3.0, n), scale=5.0, size=(DRAW_COUNT, n))
    rows.append(_row("ordered_drift_percent_reduction", 5.0, "percent_reduction", False, _interval_states(drift, "percent_reduction", False)))

    change_point = rng.normal(loc=np.r_[np.repeat(8.0, n // 2), np.repeat(2.0, n - n // 2)], scale=5.0, size=(DRAW_COUNT, n))
    rows.append(_row("change_point_percent_reduction", 5.0, "percent_reduction", False, _interval_states(change_point, "percent_reduction", False)))

    with (output_dir / "statistical_stress.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "scope": "Synthetic stress scenarios; not fitted energy, meter, or service data.",
        "root_seed": ROOT_SEED,
        "draws": DRAW_COUNT,
        "rule": {"sesoi_percent": RULE.sesoi_percent, "direction_fraction": RULE.direction_fraction, "tolerance": RULE.tolerance},
        "interpretation": "Known drift, change-point, or heteroscedastic scenarios with an unadjusted IID interval are marked interval-incompatible and returned inconclusive rather than treated as valid support probabilities.",
    }
    (output_dir / "statistical_stress_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    run(ROOT / "results")
