#!/usr/bin/env python3
"""Render a descriptive audit of early scheduled and later balanced records.

The two record sets were collected at different times and are deliberately not
joined into a causal estimate. This graphic makes differences in nominal effect
magnitudes visible without implying an execution-design causal effect.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ORDER = [
    "chat_c1", "chat_c8", "rag_c1", "rag_c8", "code_c1", "code_c8",
    "long_context_c1", "long_context_c8",
]
LABELS = [
    "Chat, c1", "Chat, c8", "RAG, c1", "RAG, c8", "Code, c1", "Code, c8",
    "Long context, c1", "Long context, c8",
]
EARLY = (
    ("qwen_awq4 vs BF16", "Early scheduled\nAWQ4 vs BF16", "#2a7f7a"),
    ("qwen_gptq4 vs BF16", "Early scheduled\nGPTQ4 vs BF16", "#b35d3e"),
)
LATER = (
    ("qwen_awq4", "AWQ4", "#2a7f7a"),
    ("qwen_gptq4", "GPTQ4", "#b35d3e"),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot_early(axis: plt.Axes, rows: list[dict[str, str]], comparison: str, title: str, color: str) -> None:
    by_cell = {row["cell"]: row for row in rows if row["comparison"] == comparison}
    subset = [by_cell[cell] for cell in ORDER]
    y = np.arange(len(subset))
    low = np.array([float(row["min_percent_change"]) for row in subset])
    high = np.array([float(row["max_percent_change"]) for row in subset])
    mean = np.array([float(row["mean_percent_change"]) for row in subset])
    axis.hlines(y, low, high, color="#909090", linewidth=1.05, zorder=2)
    axis.scatter(mean, y, s=28, marker="D", color=color, edgecolor="white", linewidth=.45, zorder=3)
    for index, row in enumerate(subset):
        repeats = [float(row[f"repeat_{repeat}_percent_change"]) for repeat in (1, 2, 3)]
        axis.scatter(repeats, [index - .12, index, index + .12], s=11, color="#4a4a4a", alpha=.63, zorder=4)
    axis.axvline(0, color="#4f4f4f", linestyle="--", linewidth=.7)
    axis.set_title(title, fontsize=8.7, pad=5, linespacing=1.10)
    axis.set_xlim(-15, 12)
    axis.set_xlabel("Change (%)", fontsize=8.6)
    axis.grid(axis="y", color="#e1e1e1", linewidth=.5, zorder=0)


def plot_later(axis: plt.Axes, rows: list[dict[str, str]]) -> None:
    display_rows = []
    for index, (target, label, color) in enumerate(LATER):
        full = next(row for row in rows if row["target"] == target and row["workload"] == "all_confirmed_cells")
        cells = [row for row in rows if row["target"] == target and row["workload"] != "all_confirmed_cells"]
        display_rows.append((index, label, color, full, cells))

    for y, label, color, full, cells in display_rows:
        low = float(full["p05_reduction_percent"])
        high = float(full["p95_reduction_percent"])
        mean = float(full["mean_reduction_percent"])
        cell_means = [float(row["mean_reduction_percent"]) for row in cells]
        # A dashed segment is a descriptive cell range, visibly distinct from
        # an inferential interval or the solid scheduled-repeat ranges at left.
        axis.hlines(y, low, high, color="#a7a7a7", linewidth=1.05, linestyle=(0, (2.0, 1.6)), zorder=2)
        axis.scatter(cell_means, [y] * len(cell_means), s=19, color="#4a4a4a", alpha=.58, zorder=3)
        axis.scatter(mean, y, s=36, marker="D", color=color, edgecolor="white", linewidth=.45, zorder=4)
    axis.axvline(0, color="#4f4f4f", linestyle="--", linewidth=.7)
    axis.set_yticks([0, 1], ["AWQ4", "GPTQ4"], fontsize=8.6)
    axis.invert_yaxis()
    axis.set_title("Later block-balanced\nrecords", fontsize=8.7, pad=5, linespacing=1.10)
    axis.set_xlim(-15, 12)
    axis.set_xlabel("Reduction (%)", fontsize=8.6)
    axis.grid(axis="y", color="#e1e1e1", linewidth=.5, zorder=0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", type=Path, required=True)
    parser.add_argument("--balanced", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    early_rows = read_csv(args.scheduled)
    later_rows = read_csv(args.balanced)
    figure, axes = plt.subplots(
        1, 3, figsize=(7.15, 4.48), sharey=False,
        gridspec_kw={"width_ratios": [1.18, 1.18, .98]}, constrained_layout=True,
    )
    for axis, (comparison, title, color) in zip(axes[:2], EARLY):
        plot_early(axis, early_rows, comparison, title, color)
        axis.set_yticks(np.arange(len(LABELS)), LABELS if axis is axes[0] else [], fontsize=7.9)
        axis.invert_yaxis()
    plot_later(axes[2], later_rows)
    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(axis="x", labelsize=7.8)
    axes[0].set_ylabel("Workload and concurrency cell", fontsize=8.6)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, bbox_inches="tight")
    plt.close(figure)


if __name__ == "__main__":
    main()
