#!/usr/bin/env python3
"""Reproduce the public computational checks and synthetic controls.

The script needs no accelerator, private host, model checkpoint, or network
connection after package installation.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
CONFIGS = ROOT / "configs"
CLAIMS = ROOT / "claims"
RESULTS = ROOT / "results"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=SCRIPTS)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_rate(path: Path, scenario: str, rule: str, state: str) -> float:
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["scenario"] == scenario and row["rule"] == rule and row["state"] == state:
                return float(row["rate"])
    raise KeyError((scenario, rule, state))


def h3_row(path: Path, scenario: str) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["scenario"] == scenario:
                return row
    raise KeyError(scenario)


def state_by_id(classifications: list[dict[str, object]], claim_id: str) -> str:
    for item in classifications:
        if item["claim_id"] == claim_id:
            return str(item["state"])
    raise KeyError(claim_id)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    run("-m", "unittest", "-v", "test_engine.py")
    run("test_mutations.py")
    run("-m", "coverage", "erase")
    run("-m", "coverage", "run", "--branch", "test_engine.py")
    run("-m", "coverage", "run", "--branch", "--append", "test_mutations.py")
    run(
        "-m", "coverage", "json", "-o", str(RESULTS / "engine_branch_coverage.json"),
        "engine.py",
    )
    for label, expected_tokens in (("telemetry_case_a", "256"), ("telemetry_case_b", "512")):
        run(
            "analyze_telemetry.py",
            "--input-dir", str(DATA / label),
            "--output-dir", str(RESULTS / label),
            "--expected-completion-tokens", expected_tokens,
        )
    run(
        "evaluate_claims.py",
        "--claims-dir", str(CLAIMS),
        "--registry", str(CONFIGS / "required_gates.json"),
        "--output", str(RESULTS / "claim_classifications.json"),
    )
    run("simulate_rule_ladder.py", "--output-dir", str(RESULTS / "simulation"))
    run("simulate_model_based_ar1.py", "--output-dir", str(RESULTS / "h3_oracle"))
    run("simulate_dependence_intervals.py", "--output-dir", str(RESULTS / "dependence"))
    run(
        "plot_rule_ladder.py",
        "--simulation-dir", str(RESULTS / "simulation"),
        "--output", str(RESULTS / "figure2_protocol_ladder.pdf"),
    )
    run(
        "plot_design_audit.py",
        "--scheduled", str(DATA / "derived" / "scheduled_matrix" / "format_matrix_eight_cell_contrasts.csv"),
        "--balanced", str(DATA / "derived" / "balanced_confirmation" / "interleaved_confirmation_contrasts.csv"),
        "--output", str(RESULTS / "figure3_execution_design_audit.pdf"),
    )
    classifications = read_json(RESULTS / "claim_classifications.json")["classifications"]
    mutation = read_json(ROOT / "results" / "input_mutations.json")
    coverage = read_json(RESULTS / "engine_branch_coverage.json")
    rates = RESULTS / "simulation" / "rule_ladder_state_rates.csv"
    h3_null = h3_row(RESULTS / "h3_oracle" / "model_based_ar1_summary.csv", "ar1_model_based_null")
    h3_effect = h3_row(RESULTS / "h3_oracle" / "model_based_ar1_summary.csv", "ar1_model_based_5_percent")
    audit = {
        "telemetry_case_a_state": state_by_id(classifications, "telemetry-case-a"),
        "telemetry_case_b_state": state_by_id(classifications, "telemetry-case-b"),
        "simulation_case_state": state_by_id(classifications, "simulation-rule-ladder"),
        "dependence_control_state": state_by_id(classifications, "dependence-positive-control"),
        "input_mutations": mutation["mutations"],
        "input_mutation_unsafe_promotions": sum(
            count for state, count in mutation["state_counts"].items() if state in {
                "supported_under_declared_boundary", "contradicted_under_declared_boundary"
            }
        ),
        "engine_branch_coverage_percent": coverage["totals"]["percent_branches_covered"],
        "null_false_support_full": lookup_rate(rates, "iid_null", "full_protocol", "supported"),
        "boundary_false_support_full": lookup_rate(rates, "iid_exact_sesoi_2_percent", "full_protocol", "supported"),
        "ar1_null_false_support_naive_b2": lookup_rate(rates, "ar1_autocorrelation_null", "B2_ci_direction", "supported"),
        "ar1_null_full_inconclusive": lookup_rate(rates, "ar1_autocorrelation_null", "full_protocol", "inconclusive"),
        "h3_null_lower_coverage": float(h3_null["one_sided_lower_95_coverage"]),
        "h3_effect_lower_coverage": float(h3_effect["one_sided_lower_95_coverage"]),
        "h3_effect_supported_rate": float(h3_effect["power_supported_rate"]),
    }
    expected = {
        "telemetry_case_a_state": "not_assessable_with_available_evidence",
        "telemetry_case_b_state": "not_assessable_with_available_evidence",
        "simulation_case_state": "supported_under_declared_boundary",
        "dependence_control_state": "supported_under_declared_boundary",
        "input_mutations": 24,
        "input_mutation_unsafe_promotions": 0,
        "engine_branch_coverage_percent": 89.47368421052632,
        "null_false_support_full": 0.00206,
        "boundary_false_support_full": 0.04924,
        "ar1_null_false_support_naive_b2": 0.08019,
        "ar1_null_full_inconclusive": 1.0,
        "h3_null_lower_coverage": 0.95013,
        "h3_effect_lower_coverage": 0.95015,
        "h3_effect_supported_rate": 0.81001,
    }
    if audit != expected:
        raise RuntimeError(f"Reproduction check failed: observed={audit}, expected={expected}")
    (RESULTS / "reproduction_report.json").write_text(
        json.dumps({"status": "pass", "observed": audit, "expected": expected}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "observed": audit}, indent=2))


if __name__ == "__main__":
    main()
