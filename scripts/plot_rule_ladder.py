#!/usr/bin/env python3
"""Render the current release protocol decision-rule ladder figure from deterministic output."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


COLORS = {
    "supported": "#2C7A58",
    "contradicted": "#A84B3C",
    "inconclusive": "#BE7A19",
    "not_assessable": "#68727D",
}
STATE_ORDER = ["supported", "contradicted", "inconclusive", "not_assessable"]
RULE_LABELS = {
    "B0_mean_effect": "B0\nmean",
    "B1_ci_only": "B1\nCI",
    "B2_ci_direction": "B2\nCI+dir",
    "full_protocol": "Full\nprotocol",
}
RULE_ORDER = list(RULE_LABELS)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def state_lookup(rows: list[dict[str, str]], scenario: str, rule: str) -> dict[str, float]:
    return {row["state"]: float(row["rate"]) for row in rows if row["scenario"] == scenario and row["rule"] == rule}


def stacked(axis: plt.Axes, values: dict[str, float], x: float) -> None:
    bottom = 0.0
    for state in STATE_ORDER:
        height = values.get(state, 0.0) * 100.0
        if height:
            axis.bar(x, height, width=.68, bottom=bottom, color=COLORS[state], edgecolor="white", linewidth=.42)
        bottom += height


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows(args.simulation_dir / "rule_ladder_state_rates.csv")

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.4, "axes.linewidth": .75})
    figure, axes = plt.subplots(2, 2, figsize=(7.15, 4.45), constrained_layout=True)
    panels = [
        ("iid_null", "a  IID null, compatible interval"),
        ("ar1_autocorrelation_null", "b  AR(1) null, IID interval incompatible"),
        ("calibration_missing_bias", "c  Biased physical claim, calibration missing"),
        ("iid_5_percent", "d  IID 5% effect, compatible interval"),
    ]
    for axis, (scenario, title) in zip(axes.flat, panels):
        for position, rule in enumerate(RULE_ORDER):
            stacked(axis, state_lookup(rows, scenario, rule), position)
        axis.set_title(title, fontsize=9.2)
        axis.set_ylim(0, 100)
        axis.set_xticks(range(len(RULE_ORDER)), [RULE_LABELS[rule] for rule in RULE_ORDER])
        axis.grid(axis="y", color="#D9E0E6", linewidth=.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0, 0].set_ylabel("Classification probability (%)")
    axes[1, 0].set_ylabel("Classification probability (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[state]) for state in STATE_ORDER]
    figure.legend(
        handles,
        ["Statistical support", "Contradicted", "Inconclusive", "Not assessable"],
        ncol=4,
        loc="lower center",
        frameon=False,
        bbox_to_anchor=(.5, -.055),
        fontsize=7.8,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, bbox_inches="tight")
    figure.savefig(args.output.with_suffix(".png"), dpi=400, bbox_inches="tight")


if __name__ == "__main__":
    main()
