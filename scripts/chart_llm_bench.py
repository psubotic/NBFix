#!/usr/bin/env python
"""
Generates latency, accuracy (F1), and total-tokens (a cost proxy - most
hosted APIs bill per token, and even for a local model it's the resource
cost regardless of dollars) comparison charts from scripts/benchmark_llm.py's
results, across the llm_bench size tiers (micro/mini/medium/large/xlarge -
see tests/resources/llm_bench/_author_fixtures.py's module docstring for
what each tier is). One PNG per (tier, metric).

Not part of the installed nbfix package - a dev-only research tool.
Requires matplotlib, which isn't a project dependency (this is the only
thing in the repo that needs it): pip install matplotlib.

Reads the flat per-run CSVs benchmark_llm.py writes (results.csv,
alongside results.jsonl) - saved persistently under
benchmark_results/llm_bench/ so charts can be regenerated later without
rerunning any LLM calls.

The "mini" tier's CSV includes clean1.ipynb runs (that tier is the only
one with a clean/false-positive-baseline fixture per class) - excluded
here so every tier compares on the same n=3 buggy-examples-per-class basis.

Usage (repeatable --tier NAME=PATH, any number/order of tiers):
    python scripts/chart_llm_bench.py \\
        --tier micro=benchmark_results/llm_bench/micro.csv \\
        --tier mini=benchmark_results/llm_bench/mini.csv \\
        --tier medium=benchmark_results/llm_bench/medium.csv \\
        --tier large=benchmark_results/llm_bench/large.csv \\
        --tier xlarge=benchmark_results/llm_bench/xlarge.csv \\
        --output-dir benchmark_results/llm_bench/charts
"""
import argparse
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODELS = ["qwen1.5b", "qwen7b", "qwen14b"]
CLASSES = ["api_misuse", "cross_cell_logic", "cross_cell_semantic", "order_dependent"]
# Preferred left-to-right order when multiple context configs are present
# for a tier - only those actually found in a given tier's data get
# plotted, so a 2-condition tier (none/deps) and a 3-condition one
# (none/deps/deps+isolated) both render correctly without extra config.
CONTEXT_CONFIG_ORDER = [
    "none", "deps", "deps+isolated", "deps+findings", "deps+types",
    "deps-pruned", "deps-labeled", "deps-fixpoint",
]
CONTEXT_COLORS = {
    "none": "#d97757", "deps": "#5b8dd6",
    "deps+isolated": "#6bb583", "deps+findings": "#b58ee6",
    "deps+types": "#e0b13c",
    "deps-pruned": "#7a5195", "deps-labeled": "#ef5675",
    "deps-fixpoint": "#2ca58d",
}
CLEAN_NOTEBOOK_EXCLUDE = {"clean1.ipynb"}


def load_results(path: str, exclude_notebooks=frozenset()) -> list[dict]:
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r["notebook"] not in exclude_notebooks]


def aggregate(rows: list[dict]) -> dict:
    """(config, bug_class, context_config) -> {"latency"/"f1"/"tokens": [floats]}."""
    groups = defaultdict(lambda: {"latency": [], "f1": [], "tokens": []})
    for r in rows:
        if r["error"]:
            continue
        key = (r["config"], r["bug_class"], r["context_config"])
        groups[key]["latency"].append(float(r["wall_clock_s"]))
        if r["f1"] not in (None, ""):
            groups[key]["f1"].append(float(r["f1"]))
        if r["total_tokens"] not in (None, ""):
            groups[key]["tokens"].append(float(r["total_tokens"]))
    return groups


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


_METRIC_LABELS = {
    "latency": "avg latency (s)",
    "f1": "avg F1",
    "tokens": "avg total tokens (cost proxy)",
}


def make_chart(groups: dict, metric: str, tier_label: str, output_path: str) -> None:
    contexts_present = {ctx for (_, _, ctx) in groups}
    contexts = [c for c in CONTEXT_CONFIG_ORDER if c in contexts_present]
    if not contexts:
        contexts = sorted(contexts_present)

    fig, axes = plt.subplots(1, len(MODELS), figsize=(15, 4.5), sharey=True)
    metric_label = _METRIC_LABELS[metric]
    fig.suptitle(f"{tier_label} tier — {metric_label}", fontsize=14)

    x = range(len(CLASSES))
    n = len(contexts)
    width = 0.8 / n

    for ax, model in zip(axes, MODELS):
        for i, ctx in enumerate(contexts):
            vals = [_avg(groups[(model, cls, ctx)][metric]) for cls in CLASSES]
            offset = (i - (n - 1) / 2) * width
            ax.bar(
                [xi + offset for xi in x], vals, width, label=ctx,
                color=CONTEXT_COLORS.get(ctx, "#999999"),
            )

        ax.set_title(model)
        ax.set_xticks(list(x))
        ax.set_xticklabels(CLASSES, rotation=30, ha="right", fontsize=8)
        if metric == "f1":
            ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel(metric_label)
    axes[0].legend(loc="upper right", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"wrote {output_path}")


def _parse_tier(spec: str) -> tuple[str, str]:
    name, _, path = spec.partition("=")
    if not name or not path:
        raise ValueError(f"Invalid --tier {spec!r}, expected NAME=PATH")
    return name, path


def main():
    parser = argparse.ArgumentParser(description="Chart llm_bench results across size tiers.")
    parser.add_argument(
        "--tier", action="append", required=True, dest="tiers",
        help="NAME=PATH to a tier's results CSV, repeatable.",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    for spec in args.tiers:
        tier_name, path = _parse_tier(spec)
        exclude = CLEAN_NOTEBOOK_EXCLUDE if tier_name == "mini" else frozenset()
        rows = load_results(path, exclude_notebooks=exclude)
        if not rows:
            print(f"skipping {tier_name}: no rows loaded")
            continue
        groups = aggregate(rows)
        for metric in ["latency", "f1", "tokens"]:
            out_path = os.path.join(args.output_dir, f"{tier_name}_{metric}.png")
            make_chart(groups, metric, tier_name, out_path)


if __name__ == "__main__":
    main()
