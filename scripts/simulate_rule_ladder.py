#!/usr/bin/env python3
"""Compare statistical and validity gates in the current release decision-rule ladder.

The synthetic study separates four decisions that are often conflated: a sample
mean threshold (B0), a one-sided confidence-bound rule (B1), that rule plus a
direction guard (B2), and the full validity-first protocol. It is an operating-
characteristic study, not a fitted model of a GPU, meter, organization, or user.
current release explicitly exposes the failure of an iid t interval under declared non-iid
stresses and routes a claim to inconclusive unless its interval method is
compatible with the declared dependence and distributional assumptions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import t


STATES = ("supported", "contradicted", "inconclusive", "not_assessable")
RULES = ("B0_mean_effect", "B1_ci_only", "B2_ci_direction", "full_protocol")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def residuals(rng: np.random.Generator, scenario: str, iterations: int, n_blocks: int, sd: float) -> np.ndarray:
    """Generate declared robustness stresses; none is fitted to GPU telemetry."""
    base = rng.normal(0.0, sd, size=(iterations, n_blocks))
    if scenario.startswith("scheduled_drift_"):
        # A stress pattern only; it is not fitted to the serving records.
        return base + 0.50 * (np.arange(n_blocks) - (n_blocks - 1) / 2.0)
    if scenario.startswith("heavy_tail_"):
        # Student-t_3 has finite variance; rescale to the stated marginal SD.
        return rng.standard_t(df=3, size=(iterations, n_blocks)) * (sd / math.sqrt(3.0))
    if scenario.startswith("ar1_autocorrelation_"):
        # Start at the stationary marginal distribution. Initializing from an
        # innovation would understate early-block variance and bias this audit.
        rho = 0.65
        innovation_sd = sd * math.sqrt(1.0 - rho ** 2)
        correlated = np.empty((iterations, n_blocks))
        correlated[:, 0] = rng.normal(0.0, sd, size=iterations)
        for block in range(1, n_blocks):
            correlated[:, block] = rho * correlated[:, block - 1] + rng.normal(
                0.0, innovation_sd, size=iterations
            )
        return correlated
    if scenario.startswith("heteroscedastic_"):
        scales = np.where(np.arange(n_blocks) % 2 == 0, 0.55 * sd, 1.30 * sd)
        return rng.normal(0.0, scales, size=(iterations, n_blocks))
    if scenario == "mapping_phase_confound_null":
        # A two-period map/phase shift: an intentionally invalid design case.
        phase = np.where(np.arange(n_blocks) < n_blocks / 2, 2.7, -2.7)
        return base + phase
    return base


def ci_bounds(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = values.shape[1]
    mean = values.mean(axis=1)
    se = values.std(axis=1, ddof=1) / math.sqrt(n)
    critical = float(t.ppf(0.95, n - 1))
    return mean, mean - critical * se, mean + critical * se


def b0_mean_effect(values: np.ndarray, sesoi: float) -> np.ndarray:
    return np.where(values.mean(axis=1) > sesoi, "supported", "contradicted")


def b1_ci_only(values: np.ndarray, sesoi: float) -> np.ndarray:
    _, lower, upper = ci_bounds(values)
    state = np.full(values.shape[0], "inconclusive", dtype=object)
    state[upper < sesoi] = "contradicted"
    state[lower > sesoi] = "supported"
    return state


def b2_ci_direction(values: np.ndarray, sesoi: float, direction_fraction: float) -> np.ndarray:
    _, lower, upper = ci_bounds(values)
    favorable = (values > 0.0).mean(axis=1)
    state = np.full(values.shape[0], "inconclusive", dtype=object)
    state[upper < sesoi] = "contradicted"
    state[(lower > sesoi) & (favorable >= direction_fraction)] = "supported"
    return state


def full_protocol(
    values: np.ndarray,
    sesoi: float,
    direction_fraction: float,
    validity_pass: bool,
    inference_method_compatible: bool,
) -> np.ndarray:
    if not validity_pass:
        return np.full(values.shape[0], "not_assessable", dtype=object)
    if not inference_method_compatible:
        return np.full(values.shape[0], "inconclusive", dtype=object)
    return b2_ci_direction(values, sesoi, direction_fraction)


def loss_weights(profile: str, material_benefit: bool) -> dict[str, float]:
    """Two openly normative decision-loss profiles for sensitivity reporting."""
    if profile == "claim_protection":
        return (
            {"supported": 0.0, "contradicted": 5.0, "inconclusive": 1.0, "not_assessable": 1.5}
            if material_benefit
            else {"supported": 50.0, "contradicted": 0.0, "inconclusive": 1.0, "not_assessable": 1.5}
        )
    if profile == "measurement_limited":
        return (
            {"supported": 0.0, "contradicted": 2.0, "inconclusive": 0.5, "not_assessable": 0.75}
            if material_benefit
            else {"supported": 10.0, "contradicted": 0.0, "inconclusive": 0.5, "not_assessable": 0.75}
        )
    raise ValueError(profile)


def state_rows(scenario: str, true_effect: float, rule: str, states: np.ndarray, iterations: int) -> list[dict[str, object]]:
    return [
        {
            "scenario": scenario,
            "true_effect_percent": true_effect,
            "rule": rule,
            "state": state,
            "rate": float(np.mean(states == state)),
            "iterations": iterations,
        }
        for state in STATES
    ]


def summary_row(
    *,
    scenario: str,
    description: str,
    true_effect: float,
    observed_bias: float,
    validity_pass: bool,
    inference_method_compatible: bool,
    rule: str,
    states: np.ndarray,
    sesoi: float,
) -> dict[str, object]:
    material = true_effect > sesoi
    rate = {state: float(np.mean(states == state)) for state in STATES}
    protection = loss_weights("claim_protection", material)
    limited = loss_weights("measurement_limited", material)
    return {
        "scenario": scenario,
        "description": description,
        "true_effect_percent": true_effect,
        "observed_bias_percent": observed_bias,
        "required_validity_pass": validity_pass,
        "inference_method_compatible": inference_method_compatible,
        "rule": rule,
        "supported_rate": rate["supported"],
        "contradicted_rate": rate["contradicted"],
        "inconclusive_rate": rate["inconclusive"],
        "not_assessable_rate": rate["not_assessable"],
        "false_support_rate": rate["supported"] if not material else 0.0,
        "false_contradiction_rate": rate["contradicted"] if material else 0.0,
        "power_supported_rate": rate["supported"] if material else 0.0,
        "expected_loss_claim_protection": float(np.mean([protection[state] for state in states])),
        "expected_loss_measurement_limited": float(np.mean([limited[state] for state in states])),
        "relative_evidence_burden": 1.35 if rule == "full_protocol" and not validity_pass else 1.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--n-blocks", type=int, default=10)
    parser.add_argument("--block-sd-percent", type=float, default=5.0)
    parser.add_argument("--sesoi-percent", type=float, default=2.0)
    parser.add_argument("--direction-fraction", type=float, default=0.80)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = [
        ("iid_null", 0.0, 0.0, True, True, "Valid L1 telemetry; no material benefit."),
        (
            "iid_exact_sesoi_2_percent", 2.0, 0.0, True, True,
            "Valid L1 telemetry exactly at the declared 2% materiality boundary; support is counted as false support because the lower bound must exceed the boundary.",
        ),
        (
            "iid_below_sesoi_1_5_percent", 1.5, 0.0, True, True,
            "Valid L1 telemetry below the declared 2% materiality boundary.",
        ),
        (
            "iid_near_sesoi_2_5_percent", 2.5, 0.0, True, True,
            "Valid L1 telemetry; near-SESOI 2.5% material benefit.",
        ),
        ("iid_5_percent", 5.0, 0.0, True, True, "Valid L1 telemetry; true 5% material benefit."),
        (
            "calibration_missing_bias",
            0.0,
            3.0,
            False,
            True,
            "Physical-energy claim with a +3-point observed bias and no accepted calibration evidence.",
        ),
        (
            "scheduled_drift_5_percent",
            5.0,
            0.0,
            True,
            False,
            "Declared drift stress with an iid t interval intentionally left uncorrected; the current release interval-compatibility gate fails.",
        ),
        (
            "heavy_tail_null",
            0.0,
            0.0,
            True,
            False,
            "Student-t(3) null residual stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "heavy_tail_5_percent",
            5.0,
            0.0,
            True,
            False,
            "Student-t(3) 5% effect stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "ar1_autocorrelation_null",
            0.0,
            0.0,
            True,
            False,
            "Stationary AR(1)=0.65 null stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "ar1_autocorrelation_5_percent",
            5.0,
            0.0,
            True,
            False,
            "Stationary AR(1)=0.65 5% effect stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "heteroscedastic_null",
            0.0,
            0.0,
            True,
            False,
            "Alternating 0.55x/1.30x null variance stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "heteroscedastic_5_percent",
            5.0,
            0.0,
            True,
            False,
            "Alternating 0.55x/1.30x 5% effect stress with an iid t interval intentionally left uncorrected.",
        ),
        (
            "mapping_phase_confound_null",
            0.0,
            0.0,
            False,
            False,
            "Two-period mapping/phase confound under a null format effect; Full must not return a statistical state because design integrity fails.",
        ),
    ]

    all_state_rows: list[dict[str, object]] = []
    all_summary_rows: list[dict[str, object]] = []
    for index, (name, true_effect, observed_bias, validity_pass, inference_method_compatible, description) in enumerate(scenarios):
        rng = np.random.default_rng(args.seed + index)
        observed = true_effect + observed_bias + residuals(
            rng, name, args.iterations, args.n_blocks, args.block_sd_percent
        )
        decisions = {
            "B0_mean_effect": b0_mean_effect(observed, args.sesoi_percent),
            "B1_ci_only": b1_ci_only(observed, args.sesoi_percent),
            "B2_ci_direction": b2_ci_direction(observed, args.sesoi_percent, args.direction_fraction),
            "full_protocol": full_protocol(
                observed,
                args.sesoi_percent,
                args.direction_fraction,
                validity_pass,
                inference_method_compatible,
            ),
        }
        for rule, states in decisions.items():
            all_state_rows.extend(state_rows(name, true_effect, rule, states, args.iterations))
            all_summary_rows.append(
                summary_row(
                    scenario=name,
                    description=description,
                    true_effect=true_effect,
                    observed_bias=observed_bias,
                    validity_pass=validity_pass,
                    inference_method_compatible=inference_method_compatible,
                    rule=rule,
                    states=states,
                    sesoi=args.sesoi_percent,
                )
            )

    write_csv(args.output_dir / "rule_ladder_state_rates.csv", all_state_rows)
    write_csv(args.output_dir / "rule_ladder_summary.csv", all_summary_rows)

    # A planning curve makes the conservatism of a confidence-bound protocol
    # explicit.  It is not a post-hoc power claim for any hardware experiment.
    curve_rows: list[dict[str, object]] = []
    for n_blocks in (10, 20, 35, 50):
        for effect_index, true_effect in enumerate((-1.0, 0.0, 1.0, 1.5, 2.0, 2.1, 2.5, 3.0, 4.0, 5.0, 7.0)):
            rng = np.random.default_rng(args.seed + n_blocks * 10_000 + effect_index)
            observed = true_effect + residuals(
                rng, "iid_operating_curve", args.iterations, n_blocks, args.block_sd_percent
            )
            states = full_protocol(
                observed, args.sesoi_percent, args.direction_fraction, True, True
            )
            material = true_effect > args.sesoi_percent
            curve_rows.append({
                "scenario": "iid_operating_curve",
                "n_blocks": n_blocks,
                "true_effect_percent": true_effect,
                "sesoi_percent": args.sesoi_percent,
                "direction_fraction": args.direction_fraction,
                "supported_rate": float(np.mean(states == "supported")),
                "contradicted_rate": float(np.mean(states == "contradicted")),
                "inconclusive_rate": float(np.mean(states == "inconclusive")),
                "false_support_rate": float(np.mean(states == "supported")) if not material else 0.0,
                "false_contradiction_rate": float(np.mean(states == "contradicted")) if material else 0.0,
                "iterations": args.iterations,
            })
    write_csv(args.output_dir / "iid_operating_characteristic_curve.csv", curve_rows)

    # Joint SESOI/direction-guard sensitivity. These are planning calculations,
    # not universal threshold recommendations or multiplicity-adjusted inference.
    sensitivity_rows: list[dict[str, object]] = []
    for sesoi in (1.0, 2.0, 5.0):
        for direction in (0.50, 0.80, 0.90):
            rng = np.random.default_rng(args.seed + int(sesoi * 100) + int(direction * 1000))
            observed = 5.0 + residuals(rng, "iid_5_percent", args.iterations, args.n_blocks, args.block_sd_percent)
            states = full_protocol(observed, sesoi, direction, True, True)
            sensitivity_rows.append({
                "scenario": "iid_true_5_percent",
                "n_blocks": args.n_blocks,
                "sesoi_percent": sesoi,
                "direction_fraction": direction,
                "supported_rate": float(np.mean(states == "supported")),
                "contradicted_rate": float(np.mean(states == "contradicted")),
                "inconclusive_rate": float(np.mean(states == "inconclusive")),
                "not_assessable_rate": float(np.mean(states == "not_assessable")),
                "iterations": args.iterations,
            })
    write_csv(args.output_dir / "sesoi_direction_sensitivity.csv", sensitivity_rows)
    metadata = {
        "purpose": "Synthetic decision-rule-ladder evaluation, not a serving-system estimate or physical-meter validation.",
        "iterations": args.iterations,
        "seed": args.seed,
        "assumptions": {
            "n_blocks": args.n_blocks,
            "block_sd_percent": args.block_sd_percent,
            "sesoi_percent": args.sesoi_percent,
            "direction_fraction": args.direction_fraction,
            "one_sided_confidence_level": 0.95,
        },
        "rules": {
            "B0_mean_effect": "Support if sample mean exceeds SESOI; otherwise contradict.",
            "B1_ci_only": "Support if one-sided lower t bound exceeds SESOI; contradict if upper bound is below SESOI; otherwise inconclusive.",
            "B2_ci_direction": "B1 plus a minimum favorable-block fraction for support.",
            "full_protocol": "B2 after required validity dependencies and a dependence-compatible interval method pass; otherwise not assessable or inconclusive, respectively.",
        },
        "decision_definition": {
            "supported_truth": "A true effect strictly greater than the declared SESOI.",
            "boundary_case": "At exactly the SESOI, a supported label is counted as false support because the decision rule requires a lower confidence bound strictly above the benefit boundary.",
            "direction_guard": "The 80% guard is an openly normative sign-stability preference. It is not an alpha adjustment and is reported jointly with the confidence-bound rule.",
        },
        "loss_profiles": {
            "claim_protection": "Illustrative normalized loss: false support=50, false contradiction=5, inconclusive=1, not assessable=1.5.",
            "measurement_limited": "Illustrative normalized loss: false support=10, false contradiction=2, inconclusive=0.5, not assessable=0.75.",
        },
        "evidence_burden": "Relative burden is 1.00 for the synthetic L1 rule comparison and 1.35 only for the full protocol in the missing-calibration physical-claim stress. These are planning units, not observed prices.",
    }
    metadata["robustness_scenarios"] = {
        "heavy_tail": "Student-t(3) null and 5% effect residuals, marginally rescaled to the declared SD; an iid t interval is flagged incompatible.",
        "autocorrelation": "Stationary AR(1)=0.65 null and 5% effect residuals. The first block is drawn from the stationary marginal distribution; an iid t interval is flagged incompatible.",
        "heteroscedasticity": "Alternating 0.55x/1.30x null and 5% effect block SDs; an iid t interval is flagged incompatible.",
        "mapping_phase": "A two-period map/phase confound with a failed design-integrity dependency.",
        "threshold_grid": "Joint SESOI (1,2,5%) and direction guard (0.50,0.80,0.90) sensitivity at a true 5% effect.",
        "operating_curve": "IID operating-characteristic curves span effects below, at and above the SESOI and 10, 20, 35 and 50 blocks. They are planning calculations, not post-hoc power statements for the RTX records.",
    }
    (args.output_dir / "simulation_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
