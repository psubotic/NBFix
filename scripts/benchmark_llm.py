#!/usr/bin/env python
"""
Benchmarking harness comparing LLM bug-detection configs (e.g. a small
local model vs. a large hosted one, with vs. without NBFix's structural
context) over a directory of eval notebooks.

Not part of the installed nbfix package - a dev-only research tool.
Requires `pip install -e ".[dev,llm]"` first.

Each notebook in --eval-dir may have an optional
"<notebook>.ipynb.expected.json" sidecar (same {cell_id, path, errors}
shape as tests/rtests.py's .out files) to enable precision/recall scoring;
without one, results are still recorded for manual review, just unscored.

Usage:
    python scripts/benchmark_llm.py \\
        --eval-dir path/to/notebooks \\
        --config small=qwen2.5-coder:14b@http://localhost:11434/v1 \\
        --config large=gpt-4o@https://api.openai.com/v1 \\
        --scope full \\
        --ablation \\
        --output results/
"""
import argparse
import dataclasses
import json
import os
import time
from dataclasses import dataclass

from nbfix.analyses.runner.analysis_results import Result
from nbfix.llm.client import LLMClient, LLMClientError
from nbfix.llm.context_builder import build_cell_context, build_subgraph_context, build_full_notebook_context
from nbfix.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from nbfix.llm.notebook_loading import load_notebook_resilient
from nbfix.llm.result_mapping import map_findings_to_result
from nbfix.resource_utils.utils import read_json

_SCOPED_CONTEXT_BUILDERS = {
    "cell": build_cell_context,
    "subgraph": build_subgraph_context,
}

# Same task/output-contract as prompts.SYSTEM_PROMPT, minus the dependency
# graph section - the ablation baseline for "does NBFix's structural
# context actually help". Deliberately kept local to this script rather
# than added to nbfix.llm.prompts: it isn't a real product mode, only a
# research comparison.
NO_CONTEXT_SYSTEM_PROMPT = """You are reviewing Python code from Jupyter notebook cells for bugs.

Identify concrete bugs: logic errors, incorrect variable usage, misuse of
functions/libraries, or bugs that only manifest from how cells interact
with each other. Do not report style preferences, missing docstrings, or
purely stylistic issues.

Respond with a single JSON object of exactly this shape and nothing else:

{
  "findings": [
    {
      "cell_ids": [<int>, ...],
      "line": <int>,
      "label": "<the specific identifier/token the bug concerns, or \\"\\" if none applies>",
      "severity": "critical" | "warning",
      "message": "<concise explanation of the bug>"
    }
  ]
}

"cell_ids" lists every cell involved in the bug, ordered so the LAST entry
is the cell the bug should be anchored/displayed on. "line" is a 1-indexed
line number within that anchor cell. If you find no bugs, respond with
{"findings": []}.
"""


def build_no_context_user_prompt(notebook_IR) -> str:
    sections = ["## Notebook cells"]
    for cell_id in sorted(notebook_IR):
        sections.append(f"### Cell {cell_id}\n```python\n{notebook_IR[cell_id].cell_code}\n```")
    cell_list = ", ".join(f"Cell {cid}" for cid in sorted(notebook_IR))
    sections.append(f"## Cells to check\nFocus your review on: {cell_list}")
    return "\n\n".join(sections)


def score_findings(
    actual: list[tuple[int, int]],
    expected: list[tuple[int, int]],
    line_tolerance: int = 2,
) -> dict:
    """
    Lenient precision/recall/F1 between two lists of (cell_id, line) pairs.

    A match requires the same cell_id and a line within line_tolerance -
    unlike rtests.py's exact-equality comparison (appropriate for
    deterministic analyses), LLM output isn't line-exact reproducible, so
    exact matching would understate quality.
    """
    remaining_actual = list(actual)
    true_positives = 0

    for exp_cell, exp_line in expected:
        match = next(
            (
                a for a in remaining_actual
                if a[0] == exp_cell and abs(a[1] - exp_line) <= line_tolerance
            ),
            None,
        )
        if match is not None:
            remaining_actual.remove(match)
            true_positives += 1

    false_positives = len(remaining_actual)
    false_negatives = len(expected) - true_positives

    precision = true_positives / len(actual) if actual else 0.0
    recall = true_positives / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


@dataclass
class ModelConfig:
    name: str
    model: str
    base_url: str


def parse_config(spec: str) -> ModelConfig:
    name, _, rest = spec.partition("=")
    model, _, base_url = rest.partition("@")
    if not name or not model or not base_url:
        raise ValueError(f"Invalid --config {spec!r}, expected NAME=MODEL@BASE_URL")
    return ModelConfig(name=name, model=model, base_url=base_url)


@dataclass
class RunResult:
    notebook: str
    config: str
    context_mode: str  # "with_context" | "no_context"
    wall_clock_s: float
    tokens: dict
    finding_count: int
    raw_findings: list
    score: dict = None
    error: str = None


def _build_prompts(notebook_IR, scope: str, with_context: bool) -> tuple[str, list[str]]:
    if not with_context:
        return NO_CONTEXT_SYSTEM_PROMPT, [build_no_context_user_prompt(notebook_IR)]

    if scope == "full":
        return SYSTEM_PROMPT, [build_user_prompt(build_full_notebook_context(notebook_IR))]

    builder_fn = _SCOPED_CONTEXT_BUILDERS[scope]
    # cell/subgraph scope is inherently per-cell in real usage (JupyterLab's
    # "check cell for bugs" / CLI --cell) - faithfully benchmarking it means
    # running it once per cell and merging results, not one whole-notebook call.
    prompts = [build_user_prompt(builder_fn(notebook_IR, cell_id)) for cell_id in sorted(notebook_IR)]
    return SYSTEM_PROMPT, prompts


def run_once(notebook_name, notebook_IR, config: ModelConfig, scope: str, with_context: bool, expected) -> RunResult:
    context_mode = "with_context" if with_context else "no_context"
    client = LLMClient(
        base_url=config.base_url,
        model=config.model,
        api_key=os.environ.get("OPENAI_API_KEY", "not-needed"),
    )
    system_prompt, user_prompts = _build_prompts(notebook_IR, scope, with_context)

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    combined_result = Result()
    start = time.monotonic()

    try:
        for user_prompt in user_prompts:
            findings_json, usage = client.chat_json_with_usage(system_prompt, user_prompt)
            for key in total_usage:
                if usage.get(key) is not None:
                    total_usage[key] += usage[key]
            combined_result.join_results(map_findings_to_result(findings_json, notebook_IR))
    except LLMClientError as exc:
        return RunResult(
            notebook=notebook_name, config=config.name, context_mode=context_mode,
            wall_clock_s=time.monotonic() - start, tokens=total_usage,
            finding_count=0, raw_findings=[], score=None, error=str(exc),
        )

    elapsed = time.monotonic() - start
    actual_pairs = [
        (path_result.path[-1], error_info.line)
        for path_result in combined_result.path_results
        for error_info in path_result.error_infos
    ]

    score = None
    if expected is not None:
        expected_pairs = [
            (entry["cell_id"], err["line"]) for entry in expected for err in entry["errors"]
        ]
        score = score_findings(actual_pairs, expected_pairs)

    raw_findings = json.loads(combined_result.dumps(True)) if combined_result.path_results else []

    return RunResult(
        notebook=notebook_name, config=config.name, context_mode=context_mode,
        wall_clock_s=elapsed, tokens=total_usage,
        finding_count=len(actual_pairs), raw_findings=raw_findings, score=score, error=None,
    )


def _discover_eval_notebooks(eval_dir: str):
    for name in sorted(os.listdir(eval_dir)):
        if name.endswith(".ipynb"):
            yield name


def _load_expected(eval_dir: str, notebook_name: str):
    path = os.path.join(eval_dir, notebook_name + ".expected.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _print_summary(results: list) -> None:
    groups: dict = {}
    for r in results:
        groups.setdefault((r.config, r.context_mode), []).append(r)

    print("\n=== Summary ===")
    print(f"{'config':<15}{'context':<14}{'runs':<6}{'avg_latency_s':<15}{'avg_tokens':<12}{'avg_precision':<15}{'avg_recall':<12}")
    for (config_name, context_mode), rs in groups.items():
        ok = [r for r in rs if r.error is None]
        avg_latency = sum(r.wall_clock_s for r in ok) / len(ok) if ok else 0.0
        avg_tokens = sum(r.tokens.get("total_tokens") or 0 for r in ok) / len(ok) if ok else 0.0
        scored = [r for r in ok if r.score is not None]
        avg_precision = sum(r.score["precision"] for r in scored) / len(scored) if scored else float("nan")
        avg_recall = sum(r.score["recall"] for r in scored) / len(scored) if scored else float("nan")
        print(
            f"{config_name:<15}{context_mode:<14}{len(rs):<6}{avg_latency:<15.2f}"
            f"{avg_tokens:<12.1f}{avg_precision:<15.2f}{avg_recall:<12.2f}"
        )


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLM bug-detection configs.")
    parser.add_argument("--eval-dir", required=True, help="Directory of .ipynb eval notebooks.")
    parser.add_argument(
        "--config", action="append", required=True, dest="configs",
        help="NAME=MODEL@BASE_URL, repeatable.",
    )
    parser.add_argument("--scope", choices=["cell", "subgraph", "full"], default="full")
    parser.add_argument(
        "--ablation", action="store_true",
        help="Also run a no-context baseline per config, for comparison.",
    )
    parser.add_argument("--output", default="benchmark_results", help="Output directory.")
    args = parser.parse_args()

    configs = [parse_config(c) for c in args.configs]
    os.makedirs(args.output, exist_ok=True)
    results_path = os.path.join(args.output, "results.jsonl")

    all_results = []
    with open(results_path, "w") as out_f:
        for notebook_name in _discover_eval_notebooks(args.eval_dir):
            try:
                notebook_json = read_json(os.path.join(args.eval_dir, notebook_name))
                # Cells the parser can't handle yet (see ast_transformer.py)
                # are skipped individually here, not the whole notebook -
                # this still guards against the file itself being
                # unreadable/corrupt JSON, a different failure than "one
                # cell uses an unsupported construct".
                notebook_IR = load_notebook_resilient(notebook_json["cells"])
            except Exception as exc:
                print(f"Skipping {notebook_name}: failed to load ({exc})")
                continue
            expected = _load_expected(args.eval_dir, notebook_name)

            for config in configs:
                for with_context in ([True, False] if args.ablation else [True]):
                    mode = "with_context" if with_context else "no_context"
                    print(f"Running {notebook_name} / {config.name} / {mode}...")
                    result = run_once(notebook_name, notebook_IR, config, args.scope, with_context, expected)
                    if result.error:
                        print(f"  error: {result.error}")
                    all_results.append(result)
                    out_f.write(json.dumps(dataclasses.asdict(result)) + "\n")
                    out_f.flush()

    _print_summary(all_results)
    print(f"\nFull results written to {results_path}")


if __name__ == "__main__":
    main()
