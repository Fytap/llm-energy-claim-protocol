#!/usr/bin/env python3
"""Render a legible execution and stress-test summary for Protocol v1.2.0."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


BLUE, TEAL, ORANGE, RED, GREY = "#0072B2", "#009E73", "#E69F00", "#D55E00", "#6C757D"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def value(row: dict[str, str], key: str) -> float:
    return float(row[key])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    quality = json.loads((args.results_dir / "quality_audit_summary.json").read_text(encoding="utf-8"))
    mutation = json.loads((args.results_dir / "program_mutation_score.json").read_text(encoding="utf-8"))
    fuzz = json.loads((args.results_dir / "property_fuzz.json").read_text(encoding="utf-8"))
    baseline = rows(args.results_dir / "jsonschema_comparison.csv")
    stress = rows(args.results_dir / "statistical_stress.csv")

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.linewidth": 0.8})
    figure, axes = plt.subplots(2, 2, figsize=(7.15, 5.3), constrained_layout=True)

    labels = ["Statements", "Branches", "Mutants", "Malformed\nrecords"]
    scores = [quality["statement_coverage_percent"], quality["branch_coverage_percent"], 100 * mutation["mutation_score"], 100 * (1 - fuzz["positive_malformed_records"] / fuzz["runs"])]
    bars = axes[0, 0].bar(np.arange(4), scores, color=[BLUE, TEAL, ORANGE, GREY], width=0.63)
    for bar, score in zip(bars, scores):
        axes[0, 0].text(bar.get_x() + bar.get_width() / 2, score + 2.1, f"{score:.1f}%", ha="center", va="bottom", fontsize=8)
    axes[0, 0].set_title("a  Executable structural checks")
    axes[0, 0].set_ylabel("Pass or coverage (%)")
    axes[0, 0].set_xticks(range(4), labels)
    axes[0, 0].set_ylim(0, 110)
    axes[0, 0].grid(axis="y", color="#D9E0E6", lw=0.6)

    baseline_names = [row["constructed_case"].replace("_", "\n") for row in baseline]
    accepted = np.array([row["json_schema_accepts"] == "true" for row in baseline], dtype=int)
    local_ok = np.array([
        row["protocol_overall_state"] == "locally_provenance_complete_evidence_not_independently_validated"
        for row in baseline
    ], dtype=int)
    x = np.arange(len(baseline))
    axes[0, 1].bar(x - 0.18, accepted, 0.36, label="JSON Schema", color=GREY)
    axes[0, 1].bar(x + 0.18, local_ok, 0.36, label="Registry engine", color=BLUE)
    axes[0, 1].set_title("b  Constructed structural baseline")
    axes[0, 1].set_ylabel("Accepted (1 = yes)")
    axes[0, 1].set_xticks(x, baseline_names, fontsize=6.7)
    axes[0, 1].set_ylim(0, 1.24)
    axes[0, 1].set_yticks([0, 1], ["No", "Yes"])
    axes[0, 1].legend(frameon=False, fontsize=7, loc="upper right")

    compatible = [row for row in stress if row["iid_interval_compatible"] == "True"]
    names = ["IID\nreduction", "Log-ratio\nvariation"]
    support = [100 * value(row, "supported_probability") for row in compatible]
    inconclusive = [100 * value(row, "inconclusive_probability") for row in compatible]
    x = np.arange(len(compatible))
    axes[1, 0].bar(x, support, color=BLUE, label="Supported")
    axes[1, 0].bar(x, inconclusive, bottom=support, color=ORANGE, label="Inconclusive")
    for index, score in enumerate(support):
        axes[1, 0].text(index, score / 2, f"{score:.1f}%", ha="center", va="center", color="white", fontsize=8)
    axes[1, 0].set_title("c  Estimand and denominator sensitivity")
    axes[1, 0].set_ylabel("Synthetic decision probability (%)")
    axes[1, 0].set_xticks(x, names)
    axes[1, 0].set_ylim(0, 100)
    axes[1, 0].legend(frameon=False, fontsize=7, loc="upper right")

    incompatible = [row for row in stress if row["iid_interval_compatible"] == "False"]
    labels = ["Hetero-\nscedastic", "Ordered\ndrift", "Change\npoint"]
    axes[1, 1].bar(np.arange(3), [100 * value(row, "inconclusive_probability") for row in incompatible], color=RED)
    axes[1, 1].set_title("d  Known mismatch is not promoted")
    axes[1, 1].set_ylabel("Inconclusive probability (%)")
    axes[1, 1].set_xticks(np.arange(3), labels)
    axes[1, 1].set_ylim(0, 110)
    for i in range(3):
        axes[1, 1].text(i, 102, "100%", ha="center", va="bottom", fontsize=8)

    for axis in axes.ravel():
        axis.spines[["top", "right"]].set_visible(False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, bbox_inches="tight")
    figure.savefig(args.output.with_suffix(".png"), dpi=400, bbox_inches="tight")


if __name__ == "__main__":
    main()
