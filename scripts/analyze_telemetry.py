#!/usr/bin/env python3
"""Recompute descriptive within-NVML AWQ--GPTQ audit quantities.

Claim classification is intentionally not performed here. The evaluator classifies only
the machine-readable objects through ``evaluate_claims.py``, which
derives mandatory gates from the registered evidence profile. This script
reports the descriptive numerical audit values for the two telemetry cases.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import numpy as np
from scipy import stats



def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def integrate_window(times_s: np.ndarray, powers_w: np.ndarray, start_ns: int, end_ns: int, stride: int = 1) -> tuple[float, int]:
    start_s = start_ns / 1e9
    end_s = end_ns / 1e9
    mask = (times_s >= start_s) & (times_s <= end_s)
    selected_t = times_s[mask][::stride]
    selected_p = powers_w[mask][::stride]
    if len(selected_t) < 2:
        raise ValueError("fewer than two telemetry samples inside request window")
    # Anchor the interval boundaries by linear interpolation; the physical
    # quantity remains the recorded NVML series, not an external calibration.
    t = np.concatenate(([start_s], selected_t, [end_s]))
    p = np.concatenate((
        [np.interp(start_s, times_s, powers_w)],
        selected_p,
        [np.interp(end_s, times_s, powers_w)],
    ))
    order = np.argsort(t)
    t = t[order]
    p = p[order]
    dedup = np.concatenate(([True], np.diff(t) > 0))
    integrate = getattr(np, "trapezoid", np.trapz)
    energy_mwh = float(integrate(p[dedup], t[dedup]) / 3.6)
    return energy_mwh, int(len(selected_t))


def telemetry_window_audit(times_s: np.ndarray, start_ns: int, end_ns: int) -> dict[str, object]:
    """Describe continuous telemetry coverage without using a raw sample-count rule."""
    start_s = start_ns / 1e9
    end_s = end_ns / 1e9
    selected = times_s[(times_s >= start_s) & (times_s <= end_s)]
    if len(selected) < 2:
        return {"sample_count": int(len(selected)), "max_gap_s": float("inf"), "boundary_bracketed": False}
    before = np.any(times_s <= start_s)
    after = np.any(times_s >= end_s)
    return {
        "sample_count": int(len(selected)),
        "max_gap_s": float(np.max(np.diff(selected))),
        "boundary_bracketed": bool(before and after),
    }


def exact_sign_flip_p(values: list[float]) -> float:
    observed = abs(mean(values))
    all_means = [abs(sum(sign * value for sign, value in zip(signs, values)) / len(values)) for signs in itertools.product((-1, 1), repeat=len(values))]
    return sum(value >= observed - 1e-12 for value in all_means) / len(all_means)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--expected-completion-tokens", type=int, default=256)
    parser.add_argument("--minimum-continuous-duration-s", type=float, default=25.0)
    parser.add_argument("--maximum-telemetry-gap-s", type=float, default=0.25)
    parser.add_argument("--maximum-stride2-difference-percent", type=float, default=0.20)
    parser.add_argument("--benefit-threshold-percent", type=float, default=2.0)
    parser.add_argument("--minimum-direction-fraction", type=float, default=0.80)
    args = parser.parse_args()

    outcomes = read_rows(args.input_dir / "request_outcomes.csv")
    telemetry = read_rows(args.input_dir / "raw_nvml_50ms.csv")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sessions: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in outcomes:
        sessions[(int(row["block"]), row["format"])].append(row)

    streams: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    by_gpu: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in telemetry:
        by_gpu[int(row["gpu"])].append(row)
    for gpu, rows in by_gpu.items():
        streams[gpu] = (
            np.array([int(row["epoch_ns"]) / 1e9 for row in rows], dtype=float),
            np.array([int(row["power_mw"]) / 1000 for row in rows], dtype=float),
        )

    summary_rows: list[dict[str, object]] = []
    for (block, format_name), rows in sorted(sessions.items()):
        gpu = int(rows[0]["physical_gpu"])
        start_ns = int(rows[0]["session_start_ns"])
        end_ns = int(rows[0]["session_end_ns"])
        all_completion = [int(row["completion_tokens"]) for row in rows]
        all_prompt = [int(row["prompt_tokens"]) for row in rows]
        full_mwh, sample_count = integrate_window(*streams[gpu], start_ns, end_ns)
        stride2_mwh, _ = integrate_window(*streams[gpu], start_ns, end_ns, stride=2)
        window_audit = telemetry_window_audit(streams[gpu][0], start_ns, end_ns)
        downsample_pct = 100 * abs(stride2_mwh - full_mwh) / full_mwh
        duration_s = (end_ns - start_ns) / 1e9
        summary_rows.append(
            {
                "block": block,
                "format": format_name,
                "phase": int(rows[0]["phase"]),
                "physical_gpu": gpu,
                "dispatch_first": rows[0]["dispatch_first"],
                "requests": len(rows),
                "session_duration_s": duration_s,
                "sample_count": sample_count,
                "max_telemetry_gap_s": float(window_audit["max_gap_s"]),
                "boundary_bracketed": bool(window_audit["boundary_bracketed"]),
                "energy_mwh": full_mwh,
                "stride2_energy_mwh": stride2_mwh,
                "stride2_absolute_difference_percent": downsample_pct,
                "prompt_tokens": sum(all_prompt),
                "completion_tokens": sum(all_completion),
                "total_tokens": sum(all_prompt) + sum(all_completion),
                "mwh_per_completion_token": full_mwh / sum(all_completion),
                "mwh_per_total_token": full_mwh / (sum(all_prompt) + sum(all_completion)),
                "completion_tokens_per_joule": sum(all_completion) / (full_mwh * 3.6),
                "all_completion_tokens_equal_expected": all(token == args.expected_completion_tokens for token in all_completion),
                "all_finish_reason_length": all(row["finish_reason"] == "length" for row in rows),
            }
        )

    pairs: list[dict[str, object]] = []
    block_ids = sorted({int(row["block"]) for row in summary_rows})
    by_block = {block: {row["format"]: row for row in summary_rows if row["block"] == block} for block in block_ids}
    for block, formats in sorted(by_block.items()):
        awq = formats["AWQ"]
        gptq = formats["GPTQ"]
        awq_unit = float(awq["mwh_per_completion_token"])
        gptq_unit = float(gptq["mwh_per_completion_token"])
        log_ratio = math.log(gptq_unit / awq_unit)
        pairs.append(
            {
                "block": block,
                "phase": awq["phase"],
                "AWQ_gpu": awq["physical_gpu"],
                "GPTQ_gpu": gptq["physical_gpu"],
                "dispatch_first": awq["dispatch_first"],
                "AWQ_mwh_per_completion_token": awq_unit,
                "GPTQ_mwh_per_completion_token": gptq_unit,
                "GPTQ_relative_reduction_percent": 100 * (awq_unit - gptq_unit) / awq_unit,
                "log_GPTQ_over_AWQ": log_ratio,
            }
        )

    effects = np.array([float(row["GPTQ_relative_reduction_percent"]) for row in pairs])
    log_ratios = np.array([float(row["log_GPTQ_over_AWQ"]) for row in pairs])
    n = len(effects)
    t_critical = float(stats.t.ppf(0.975, n - 1))
    one_sided_t_critical = float(stats.t.ppf(0.95, n - 1))
    effect_se = float(np.std(effects, ddof=1) / math.sqrt(n))
    effect_ci = [float(np.mean(effects) - t_critical * effect_se), float(np.mean(effects) + t_critical * effect_se)]
    one_sided_effect_bounds = [
        float(np.mean(effects) - one_sided_t_critical * effect_se),
        float(np.mean(effects) + one_sided_t_critical * effect_se),
    ]
    log_se = float(np.std(log_ratios, ddof=1) / math.sqrt(n))
    log_ci = [float(np.mean(log_ratios) - t_critical * log_se), float(np.mean(log_ratios) + t_critical * log_se)]
    rng = np.random.default_rng(args.seed)
    bootstrap = rng.choice(effects, size=(args.bootstrap, n), replace=True).mean(axis=1)
    boot_ci = [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))]
    nominal_intervals = [
        float(np.quantile(effects, 0.05)),
        float(np.quantile(effects, 0.95)),
    ]

    all_sample_counts = [int(row["sample_count"]) for row in summary_rows]
    all_durations = [float(row["session_duration_s"]) for row in summary_rows]
    all_max_gaps = [float(row["max_telemetry_gap_s"]) for row in summary_rows]
    all_boundary_bracketed = [bool(row["boundary_bracketed"]) for row in summary_rows]
    stride_differences = [float(row["stride2_absolute_difference_percent"]) for row in summary_rows]
    all_fixed_tokens = all(bool(row["all_completion_tokens_equal_expected"]) for row in summary_rows)
    all_length = all(bool(row["all_finish_reason_length"]) for row in summary_rows)
    direction_fraction = float(np.mean(effects > 0))
    duration_pass = min(all_durations) >= args.minimum_continuous_duration_s
    gap_pass = max(all_max_gaps) <= args.maximum_telemetry_gap_s
    bracketing_pass = all(all_boundary_bracketed)
    stride_pass = float(np.quantile(stride_differences, 0.95)) <= args.maximum_stride2_difference_percent
    contradiction_to_benefit = one_sided_effect_bounds[1] < args.benefit_threshold_percent
    statistical_pass = (
        one_sided_effect_bounds[0] > args.benefit_threshold_percent
        and direction_fraction >= args.minimum_direction_fraction
    )

    analysis = {
        "input_dir": "artifact-supplied raw data (relative location declared by the caller)",
        "n_blocks": n,
        "n_request_records": len(outcomes),
        "unit": "NVML-derived mWh per completion token",
        "token_accounting": {
            "expected_completion_tokens": args.expected_completion_tokens,
            "all_completion_tokens_equal_expected": all_fixed_tokens,
            "all_finish_reason_length": all_length,
            "completion_tokens_total": int(sum(int(row["completion_tokens"]) for row in outcomes)),
            "prompt_tokens_total": int(sum(int(row["prompt_tokens"]) for row in outcomes)),
        },
        "telemetry": {
            "configured_interval_s": 0.05,
            "minimum_continuous_duration_s": args.minimum_continuous_duration_s,
            "session_duration_s_min": min(all_durations),
            "session_duration_s_median": median(all_durations),
            "session_duration_s_max": max(all_durations),
            "sample_count_min": min(all_sample_counts),
            "sample_count_median": median(all_sample_counts),
            "sample_count_max": max(all_sample_counts),
            "maximum_telemetry_gap_s": max(all_max_gaps),
            "all_window_boundaries_bracketed": bracketing_pass,
            "maximum_allowed_telemetry_gap_s": args.maximum_telemetry_gap_s,
            "stride2_absolute_difference_percent_median": median(stride_differences),
            "stride2_absolute_difference_percent_p95": float(np.quantile(stride_differences, 0.95)),
            "maximum_allowed_stride2_difference_percent": args.maximum_stride2_difference_percent,
        },
        "effect_GPTQ_relative_to_AWQ": {
            "mean_reduction_percent": float(np.mean(effects)),
            "primary_one_sided_t95_bounds_percent": one_sided_effect_bounds,
            "benefit_threshold_percent": args.benefit_threshold_percent,
            "two_sided_t95_percent": effect_ci,
            "empirical_5th_95th_percent": nominal_intervals,
            "percentile_bootstrap95_percent": boot_ci,
            "direction_fraction_positive": direction_fraction,
            "exact_two_sided_sign_flip_p": exact_sign_flip_p(effects.tolist()),
        },
        "log_ratio_sensitivity": {
            "mean_log_GPTQ_over_AWQ": float(np.mean(log_ratios)),
            "two_sided_t95_log_ratio": log_ci,
            "implied_reduction_percent_from_log_mean": float(100 * (1 - math.exp(np.mean(log_ratios)))),
            "implied_reduction_percent_from_log_interval": [
                float(100 * (1 - math.exp(log_ci[1]))),
                float(100 * (1 - math.exp(log_ci[0]))),
            ],
        },
        "historical_screen_flags": {
            "continuous_duration_pass": duration_pass,
            "telemetry_gap_pass": gap_pass,
            "endpoint_bracketing_pass": bracketing_pass,
            "integration_stability_pass": stride_pass,
            "pooled_historical_upper_bound_below_2_percent": contradiction_to_benefit,
            "pooled_historical_lower_bound_and_direction_pass": statistical_pass,
            "classification_note": "These numerical flags are not a claim classification. The current release registry-driven evaluator adds design-integrity, provenance and inference-compatibility dependencies before issuing any state.",
        },
        "interpretation": "This analysis integrates recorded NVML power only. It is not an external power calibration, useful-service assessment, hardware-population estimate, or carbon/lifecycle result.",
    }

    def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(args.output_dir / "session_energy_summary.csv", summary_rows)
    write_csv(args.output_dir / "block_contrasts.csv", pairs)
    (args.output_dir / "numerical_audit.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
