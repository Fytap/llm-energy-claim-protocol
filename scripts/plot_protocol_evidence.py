#!/usr/bin/env python3
"""Render colourblind-friendly Protocol 1.2.0 operating-characteristic panels."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# Okabe-Ito palette: distinguishable under common colour-vision deficiencies.
BLUE, ORANGE, VERMILLION, GREY = "#0072B2", "#E69F00", "#D55E00", "#666666"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def label_bars(axis, bars, fmt="{:.1f}%"):
    for bar in bars:
        height = bar.get_height()
        axis.text(
            bar.get_x() + bar.get_width() / 2, height + 1.4, fmt.format(height),
            ha="center", va="bottom", fontsize=7.2, color="#222222",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    composite = [
        row for row in csv_rows(args.results_dir / "composite_null_operating_characteristics.csv")
        if row["scenario"] == "iid_normal" and float(row["true_effect_percent"]) in {0.0, 1.0, 2.0, 5.0}
    ]
    upstream = csv_rows(args.results_dir / "upstream_attestation_error_stress.csv")
    direction = [
        row for row in csv_rows(args.results_dir / "direction_guard_operating_characteristics.csv")
        if row["true_effect_percent"] == "5.0"
    ]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.3, "axes.linewidth": .75})
    figure, axes = plt.subplot_mosaic(
        [["A", "A"], ["B", "C"]], figsize=(7.15, 5.0), constrained_layout=True
    )

    effects = np.array([float(row["true_effect_percent"]) for row in composite])
    x = np.arange(len(effects))
    b0 = np.array([float(row["b0_naive_point_estimate_rate"]) * 100 for row in composite])
    full = np.array([float(row["full_ci_direction_support_rate"]) * 100 for row in composite])
    bars0 = axes["A"].bar(x - .18, b0, .36, color=GREY, label="B0 point estimate")
    bars1 = axes["A"].bar(x + .18, full, .36, color=BLUE, label="CI + direction")
    label_bars(axes["A"], bars0); label_bars(axes["A"], bars1)
    axes["A"].axvline(2, color=VERMILLION, lw=1, ls="--")
    axes["A"].set_title("a  Composite-null planning")
    axes["A"].set_xticks(x, [f"{effect:g}" for effect in effects])
    axes["A"].set_xlabel("True effect (%)"); axes["A"].set_ylabel("Support probability (%)")
    axes["A"].set_ylim(0, 105); axes["A"].grid(axis="y", color="#D9E0E6", lw=.5)
    axes["A"].legend(fontsize=7.2, frameon=False, loc="upper left")

    rates = (1, 5, 10)
    fp = [
        100 * float(next(row["false_promotion_rate"] for row in upstream
                         if row["scenario"] == "invalid_critical_gate_upstream_false_pass"
                         and float(row["upstream_error_rate"]) == rate / 100))
        for rate in rates
    ]
    fr = [
        100 * float(next(row["abstention_or_false_rejection_rate"] for row in upstream
                         if row["scenario"] == "valid_critical_gate_upstream_false_nonpass"
                         and float(row["upstream_error_rate"]) == rate / 100))
        for rate in rates
    ]
    xpos = np.arange(len(rates))
    first = axes["B"].bar(xpos - .18, fp, .36, color=VERMILLION, label="False promotion")
    second = axes["B"].bar(xpos + .18, fr, .36, color=ORANGE, label="Abstention / false rejection")
    for bar in first:
        if bar.get_height() < 2:
            axes["B"].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + .32,
                           f"{bar.get_height():.1f}%", ha="center", va="bottom",
                           fontsize=6.7, color="#222222")
        else:
            axes["B"].text(bar.get_x() + bar.get_width() / 2, bar.get_height() - .55,
                           f"{bar.get_height():.1f}%", ha="center", va="top", rotation=90,
                           fontsize=6.7, color="white")
    for bar in second:
        if bar.get_height() < 2:
            axes["B"].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + .32,
                           f"{bar.get_height():.1f}%", ha="center", va="bottom",
                           fontsize=6.7, color="#222222")
        else:
            axes["B"].text(bar.get_x() + bar.get_width() / 2, bar.get_height() - .55,
                           f"{bar.get_height():.1f}%", ha="center", va="top", rotation=90,
                           fontsize=6.7, color="#222222")
    axes["B"].set_title("b  Upstream-error sensitivity")
    axes["B"].set_xticks(xpos, [str(rate) for rate in rates])
    axes["B"].set_xlabel("Upstream error assumption (%)"); axes["B"].set_ylim(0, 14)
    axes["B"].grid(axis="y", color="#D9E0E6", lw=.5); axes["B"].legend(fontsize=6.3, frameon=False, loc="upper left")

    for design, color, marker, label in (
        ("iid_normal", BLUE, "o", "IID t interval"),
        ("ar1_oracle_interval", ORANGE, "s", "AR(1) oracle interval"),
    ):
        rows = sorted((row for row in direction if row["design"] == design), key=lambda row: int(row["n_blocks"]))
        blocks = [int(row["n_blocks"]) for row in rows]
        xblocks = list(range(len(blocks)))
        support = [100 * float(row["joint_support_rate"]) for row in rows]
        axes["C"].plot(xblocks, support, color=color, marker=marker, lw=1.5, label=label)
        for block, value in zip(xblocks, support):
            axes["C"].text(block, value + 2.6, f"{value:.0f}", ha="center", fontsize=6.8)
    axes["C"].axhline(80, color=GREY, lw=1, ls="--")
    axes["C"].set_title("c  5% effect planning")
    axes["C"].set_xlabel("Blocks"); axes["C"].set_ylabel("Joint support (%)")
    axes["C"].set_ylim(0, 105); axes["C"].set_xticks(range(5), ("10", "20", "35", "50", "150"))
    axes["C"].grid(axis="y", color="#D9E0E6", lw=.5); axes["C"].legend(fontsize=6.4, frameon=False, loc="upper left")
    for axis in axes.values():
        axis.spines[["top", "right"]].set_visible(False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, bbox_inches="tight")
    figure.savefig(args.output.with_suffix(".png"), dpi=400, bbox_inches="tight")


if __name__ == "__main__":
    main()
