"""
Authors and validates the llm_bench benchmark fixtures (Phase 1 of the LLM
research-track plan). Not part of the installed package - a one-off/
repeatable authoring script, kept in the repo so the fixtures are
regeneratable and so the ground-truth derivation is documented in code,
not just asserted in a doc.

Ground-truth principle (see llm_bench/README.md): a fixture's "bug" must be
an objective, checkable property of actually running the code - a specific
exception (type + cell + line), not the fixture author's opinion about
intent. This script enforces that: every buggy fixture is exec()'d cell by
cell in a fresh namespace, the actual raised exception (type, message,
cell, line) is captured from the traceback, and .expected.json is written
from that observation - not from what the author intended to happen. Every
clean fixture is exec()'d the same way and must complete with no exception.

Cell-count note: the first version of these fixtures averaged 2.31 cells
each (min 1, max 3) - a real problem, not just a small-sample-size one.
The whole point of feeding an LLM a dependency graph is to save it from
cross-cell reasoning it can't hold in its head - in a 2-3 cell notebook
every cell is already visible in the prompt regardless of context mode, so
the graph has nothing to add. Every fixture below is padded with
DISTRACTOR_CELLS (plausible, deliberately inert filler) placed before and
after the actual bug cells. The bug cells' relative order and content are
unchanged from the original design; only their position within the larger
notebook shifts, and each bug's `path` is remapped accordingly.

Five size tiers, sharing the same underlying bug definitions (_BUGS below)
so "the same bug" is genuinely comparable across sizes rather than
independently-written examples that happen to share a category:
- llm_bench_micro/ - the bare bug cells, zero padding (~1-3 cells) - the
  original, pre-padding design; kept as the bottom of the size range
  rather than deleted, since it's a real, useful data point once there's
  a size axis to plot against.
- llm_bench/ - ~13-15 cells ("mini"), all 16 fixtures (3 buggy + 1 clean
  per class) - the original padded tier.
- llm_bench_medium/ - ~30 cells, 3 buggy examples per class (12 total).
- llm_bench_large/ - ~50 cells, 3 buggy examples per class (12 total).
- llm_bench_xlarge/ - ~100 cells, 3 buggy examples per class (12 total) -
  top of the range, closer to a real analysis notebook's size.

Only llm_bench/ ("mini") carries clean1 notebooks - added there
specifically to measure false-positive rate, not repeated at every size
since that's a separate question from "does cell count change the
deps-vs-none trend," which is what micro/medium/large exist to test with
the other 3 buggy examples per class.

Dependency-count axis, orthogonal to the size tiers above: computing the
real dependency-edge count for the size-tier fixtures (via
context_builder.build_dependency_edges) turned up that it's ~0-1 edges
everywhere regardless of cell count - DISTRACTOR_CELLS is deliberately
self-contained (no cell reads another distractor's name), so padding a
fixture with more distractors adds cells without adding any real
dependency structure. That means the size tiers vary notebook *length*
while leaving dependency *complexity* essentially flat - two genuinely
different axes that happened to be conflated. The three llm_bench_depN/
tiers isolate the second axis instead: cell count held fixed at 30
(matching medium), while build_dependency_chain injects a controlled
number of genuine dependency edges (2/10/20) via a distractor block that
*does* form a real read-chain, replacing the usual independent filler.
See _author_dep_tier.

Run with: python tests/resources/llm_bench/_author_fixtures.py
"""
import json
import os
import sys
import traceback

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
_RESOURCES_DIR = os.path.dirname(BENCH_DIR)
BENCH_MICRO_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_micro")
BENCH_MEDIUM_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_medium")
BENCH_LARGE_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_large")
BENCH_XLARGE_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_xlarge")
BENCH_DEP2_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_dep2")
BENCH_DEP10_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_dep10")
BENCH_DEP20_DIR = os.path.join(_RESOURCES_DIR, "llm_bench_dep20")

# Deliberately inert padding cells: each is fully self-contained (no cell
# reads a name another distractor cell defines), so any contiguous slice of
# this list can be dropped into a notebook without risk of a broken
# reference - verified by the same exec()-based validation as the real bug
# cells, not just assumed. Distinct variable names from every entry in
# _BUGS below (checked by hand) so a distractor can never accidentally mask
# or interact with a bug's own variables. 40 entries - enough headroom for
# the large (30-cell) tier's before+after slices, which need up to ~29.
DISTRACTOR_CELLS = [
    'config = {"retries": 3, "timeout": 30}',
    'log_lines = ["start", "init", "ready"]',
    'greeting = "hello world"',
    "counter_a = 5",
    "price_list = [9.99, 19.99, 4.5]",
    "total_price = sum([9.99, 19.99, 4.5])",
    'user_names = ["alice", "bob", "carol"]',
    'first_user = ["alice", "bob", "carol"][0]',
    "is_ready = True",
    'tags = set(["a", "b", "c"])  # bare set literals aren\'t parseable by NBFix yet, use set() instead',
    'session_id = "sess-001"',
    'metrics = {"cpu": 0.4, "mem": 0.7}',
    'cache = {"k1": 1}',
    "retry_count = 3",
    'buffer = ["hello"]',
    "lookup_table = {i: i * 2 for i in range(5)}",
    'status_message = "ready"',
    "error_codes = [400, 404, 500]",
    "default_timeout = 30.0",
    'version_string = "1.0.3"',
    "max_retries = 5",
    "batch_size_cfg = 32",
    'queue_names = ["ingest", "process", "export"]',
    "avg_score = sum([70, 85, 90]) / 3",
    "thresholds = [0.1, 0.5, 0.9]",
    'city_names = ["oslo", "kyoto", "lima"]',
    "is_valid_flag = len([1, 2, 3]) > 0",
    'backup_path = "/tmp/backup"',
    'region_codes = ["us-east", "eu-west", "ap-south"]',
    "sample_rate = 0.05",
    'header_fields = ["id", "name", "value"]',
    'color_palette = ["#fff", "#000", "#f00"]',
    'api_version = "v2"',
    "chunk_sizes = [64, 128, 256]",
    'default_headers = {"Content-Type": "application/json"}',
    "worker_count = 4",
    'feature_flags = {"beta": False, "dark_mode": True}',
    "min_value = -10",
    "max_value = 10",
    'label_map = {0: "no", 1: "yes"}',
    "retry_delay = 2.5",
    "is_debug = False",
    "page_size = 20",
    'shipping_zones = ["north", "south", "east", "west"]',
    "discount_rate = 0.15",
    "product_ids = [101, 102, 103]",
    "is_admin = False",
    'stock_levels = {"sku1": 12, "sku2": 0}',
    'env_name = "staging"',
    "build_number = 4521",
    "latency_samples = [12, 15, 11, 20]",
    "avg_latency = sum([12, 15, 11, 20]) / 4",
    "active_users = 342",
    "inactive_users = 58",
    "total_users = 400",
    'theme_name = "dark"',
    "font_sizes = [12, 14, 16, 18]",
    'locale_code = "en-US"',
    'currency_symbol = "$"',
    "exchange_rate = 1.09",
    'server_names = ["srv-a", "srv-b"]',
    "is_maintenance = False",
    "queue_depth = 7",
    'job_priority = "high"',
    'event_types = ["click", "view", "purchase"]',
    "sample_size = 100",
    "confidence_level = 0.95",
    "p_value = 0.03",
    'test_group = "B"',
    'control_group = "A"',
    "shard_count = 8",
    "replica_factor = 3",
    "is_primary = True",
    'node_ids = ["n1", "n2", "n3"]',
    "heartbeat_interval = 5",
    "last_sync_ts = 1700000000",
    'checksum = "a1b2c3"',
    "compression_ratio = 0.72",
    'index_names = ["idx_a", "idx_b"]',
    'partition_key = "region"',
    "row_count = 1500",
    "col_count = 12",
    "null_ratio = 0.02",
    'dtype_map = {"a": "int", "b": "str"}',
    'encoding = "utf-8"',
    'delimiter = ","',
    "has_header = True",
    "skip_rows = 0",
    "max_columns = 50",
    'output_format = "json"',
    "compress_output = False",
    'archive_name = "backup.tar.gz"',
    "checkpoint_freq = 100",
    "epoch_count = 10",
    "learning_rate = 0.001",
    "momentum = 0.9",
    "weight_decay = 0.0001",
    "dropout_rate = 0.3",
    "hidden_units = [64, 32, 16]",
    'activation_fn = "relu"',
    'optimizer_name = "adam"',
    'loss_fn = "cross_entropy"',
    "val_split = 0.2",
    "random_seed = 42",
    "num_workers = 2",
    "pin_memory = True",
    "shuffle_data = True",
    "early_stop_patience = 5",
    "best_score = 0.0",
    'model_name = "baseline"',
]


def cell(source: str) -> dict:
    lines = source.splitlines(keepends=True)
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": lines}


def write_notebook(path: str, cells: list[str]) -> None:
    nb = {
        "cells": [cell(c) for c in cells],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(path, "w") as f:
        json.dump(nb, f, indent=1)


def execute_and_capture(cells: list[str]) -> dict:
    """
    Runs each cell's source in order in one shared namespace (simulating
    top-to-bottom notebook execution), stopping at the first exception.
    Returns {"crashed": bool, "cell_index": int, "line": int,
    "exc_type": str, "message": str} on crash, or {"crashed": False} if
    every cell ran cleanly.
    """
    namespace: dict = {}
    for idx, source in enumerate(cells):
        try:
            exec(compile(source, f"<cell {idx}>", "exec"), namespace)
        except Exception as exc:
            tb = traceback.extract_tb(sys.exc_info()[2])
            # Find the frame belonging to this cell's compiled code, not an
            # inner library frame - last frame whose filename is this cell.
            cell_frames = [f for f in tb if f.filename == f"<cell {idx}>"]
            line = cell_frames[-1].lineno if cell_frames else 1
            return {
                "crashed": True,
                "cell_index": idx,
                "line": line,
                "exc_type": type(exc).__name__,
                "message": str(exc),
            }
    return {"crashed": False}


def write_expected(path: str, buggy: bool, capture: dict, path_cells: list[int]) -> None:
    if not buggy:
        with open(path, "w") as f:
            json.dump([], f, indent=1)
        return
    assert capture["crashed"], f"expected a crash but none occurred: {path}"
    entry = {
        "cell_id": capture["cell_index"],
        "path": path_cells,
        "errors": [{
            "line": capture["line"],
            "label": capture["exc_type"],
            "error_type": "RUNTIME_ERROR",
            "message": capture["message"],
        }],
    }
    with open(path, "w") as f:
        json.dump([entry], f, indent=1)


def expand_with_distractors(core_cells: list[str], path_cells: list[int], before: int, after: int):
    """
    Pads core_cells with `before` distractor cells in front and `after`
    behind, both taken as a contiguous slice of DISTRACTOR_CELLS starting
    at 0 (never wrapping/skipping - keeps every slice a genuine prefix, so
    there's no risk of a distractor landing without whatever it'd need,
    even though in practice none of them need anything). Returns
    (full_cells, remapped_path_cells) - path_cells shifted by `before`
    since that's how far the core cells' positions moved.
    """
    assert before + after <= len(DISTRACTOR_CELLS), "not enough distractor cells for this fixture's padding"
    return expand_with_padding(core_cells, path_cells, DISTRACTOR_CELLS[:before], DISTRACTOR_CELLS[before:before + after])


def expand_with_padding(core_cells: list[str], path_cells: list[int], before_cells: list[str], after_cells: list[str]):
    """
    Same as expand_with_distractors, but takes explicit cell lists for the
    padding instead of counts sliced from DISTRACTOR_CELLS - used when the
    padding needs to be something other than fully-independent filler,
    e.g. build_dependency_chain's output, to control real dependency-edge
    count independent of total cell count.
    """
    full_cells = before_cells + core_cells + after_cells
    remapped_path = [i + len(before_cells) for i in path_cells]
    return full_cells, remapped_path


def build_dependency_chain(n_edges: int) -> list[str]:
    """
    Returns n_edges + 1 cells forming a genuine linear read-dependency
    chain - cell i reads cell i-1's variable and defines a new one, so
    build_dependency_edges() finds exactly n_edges edges (cell i -> cell
    i-1, for i in 1..n_edges). Uses a chain_var_N name prefix distinct
    from every _BUGS/DISTRACTOR_CELLS variable name, so it's always safe
    to combine with either. n_edges=0 returns a single inert seed cell.
    """
    cells = ["chain_var_0 = 1"]
    for i in range(1, n_edges + 1):
        cells.append(f"chain_var_{i} = chain_var_{i - 1} + 1")
    return cells


# ---------------------------------------------------------------------------
# Bug definitions, shared between size tiers: (bug_class, name) ->
# (core_cells, path_cells, buggy). path_cells is local to core_cells - the
# logical dependency chain ending at the crashing cell, only meaningful for
# buggy entries.
# ---------------------------------------------------------------------------

_BUGS: dict[tuple[str, str], tuple[list[str], list[int], bool]] = {
    # --- cross_cell_semantic: a variable's type/shape changes across cells ---
    ("cross_cell_semantic", "ex1"): ([
        "data = [1, 2, 3, 4, 5]",
        "data = len(data)  # reduced to a summary count",
        "data.append(6)",
    ], [0, 1, 2], True),
    ("cross_cell_semantic", "ex2"): ([
        'records = {"a": 1, "b": 2}',
        "records = list(records.values())  # flattened for downstream processing",
        'records["a"]',
    ], [0, 1, 2], True),
    ("cross_cell_semantic", "ex3"): ([
        "values = [10, 20, 30]",
        "values = sum(values)  # replaced with a running total",
        "values[0]",
    ], [0, 1, 2], True),
    ("cross_cell_semantic", "clean1"): ([
        "data = [1, 2, 3, 4, 5]",
        "data = data + [6]",
        "data.append(7)",
    ], [], False),

    # --- order_dependent: only correct if run in a different order than written ---
    ("order_dependent", "ex1"): ([
        "for item in dataset:\n    print(item * 2)",
        "dataset = [1, 2, 3]",
    ], [1, 0], True),
    ("order_dependent", "ex2"): ([
        "output = helper(5)",
        "def helper(x):\n    return x * 2",
    ], [1, 0], True),
    ("order_dependent", "ex3"): ([
        "filtered = [x for x in items if x > 7]",
        "items = [1, 5, 10, 15]",
    ], [1, 0], True),
    ("order_dependent", "clean1"): ([
        "dataset = [1, 2, 3]",
        "for item in dataset:\n    print(item * 2)",
    ], [], False),

    # --- api_misuse: wrong argument to a library call, single-cell (control class) ---
    ("api_misuse", "ex1"): ([
        "import numpy as np",
        "arr = np.arange(10)",
        "reshaped = arr.reshape(3, 4)",
    ], [2], True),
    ("api_misuse", "ex2"): ([
        "import numpy as np",
        "zeros = np.zeros(-5)",
    ], [1], True),
    ("api_misuse", "ex3"): ([
        'f = open("some_file.txt", mode="rw")',
    ], [0], True),
    ("api_misuse", "clean1"): ([
        "import numpy as np",
        "arr = np.arange(12)",
        "reshaped = arr.reshape(3, 4)",
    ], [], False),

    # --- cross_cell_logic: an off-by-one/boundary bug computed in a different cell ---
    ("cross_cell_logic", "ex1"): ([
        'items = ["a", "b", "c", "d", "e"]\nn = len(items)\nlast_index = n',
        "print(items[last_index])",
    ], [0, 1], True),
    ("cross_cell_logic", "ex2"): ([
        "target_count = 3\nextra = target_count + 1",
        "stack = [10, 20, 30]\nfor _ in range(extra):\n    stack.pop()",
    ], [0, 1], True),
    ("cross_cell_logic", "ex3"): ([
        "data = [5, 10, 15]\nsummary = [sum(data)]  # collapsed to a 1-element list",
        "for i in range(len(data)):\n    print(summary[i])",
    ], [0, 1], True),
    ("cross_cell_logic", "clean1"): ([
        'items = ["a", "b", "c", "d", "e"]\nn = len(items)\nlast_index = n - 1',
        "print(items[last_index])",
    ], [], False),
}

# (bug_class, name, before, after) - small tier, ~13-15 cells, all 16 bugs.
SMALL_PLACEMENTS = [
    ("cross_cell_semantic", "ex1", 5, 5),
    ("cross_cell_semantic", "ex2", 4, 6),
    ("cross_cell_semantic", "ex3", 6, 4),
    ("cross_cell_semantic", "clean1", 5, 5),
    ("order_dependent", "ex1", 6, 6),
    ("order_dependent", "ex2", 5, 7),
    ("order_dependent", "ex3", 7, 5),
    ("order_dependent", "clean1", 6, 6),
    ("api_misuse", "ex1", 5, 5),
    ("api_misuse", "ex2", 6, 6),
    ("api_misuse", "ex3", 7, 7),
    ("api_misuse", "clean1", 5, 5),
    ("cross_cell_logic", "ex1", 6, 6),
    ("cross_cell_logic", "ex2", 5, 7),
    ("cross_cell_logic", "ex3", 7, 5),
    ("cross_cell_logic", "clean1", 6, 6),
]

# (bug_class, name, before, after) - micro tier: the bare bug cells, zero
# padding. All 3 buggy examples per class, no clean1 (same rationale as
# medium/large below - llm_bench/'s clean fixtures already cover the
# false-positive baseline once).
MICRO_PLACEMENTS = [
    (bug_class, name, 0, 0)
    for (bug_class, name) in _BUGS
    if name != "clean1"
]

# (bug_class, name, before, after) - medium tier, ~30 cells, 3 buggy
# examples per class only. Exists to check whether the deps-vs-none trend
# holds at a size where the graph has much more potential value than at
# "mini" size, not to re-establish the false-positive baseline.
MEDIUM_PLACEMENTS = [
    ("cross_cell_semantic", "ex1", 14, 13),
    ("cross_cell_semantic", "ex2", 13, 14),
    ("cross_cell_semantic", "ex3", 15, 12),
    ("order_dependent", "ex1", 14, 14),
    ("order_dependent", "ex2", 13, 15),
    ("order_dependent", "ex3", 15, 13),
    ("api_misuse", "ex1", 14, 13),
    ("api_misuse", "ex2", 14, 14),
    ("api_misuse", "ex3", 15, 14),
    ("cross_cell_logic", "ex1", 14, 14),
    ("cross_cell_logic", "ex2", 13, 15),
    ("cross_cell_logic", "ex3", 15, 13),
]

# (bug_class, name, before, after) - large tier, ~50 cells, 3 buggy examples
# per class only. Checks whether the trend seen at mini/medium continues,
# plateaus, or reverses at a size closer to a real analysis notebook.
LARGE_PLACEMENTS = [
    ("cross_cell_semantic", "ex1", 24, 23),
    ("cross_cell_semantic", "ex2", 23, 24),
    ("cross_cell_semantic", "ex3", 25, 22),
    ("order_dependent", "ex1", 24, 24),
    ("order_dependent", "ex2", 23, 25),
    ("order_dependent", "ex3", 25, 23),
    ("api_misuse", "ex1", 24, 23),
    ("api_misuse", "ex2", 24, 24),
    ("api_misuse", "ex3", 25, 24),
    ("cross_cell_logic", "ex1", 24, 24),
    ("cross_cell_logic", "ex2", 23, 25),
    ("cross_cell_logic", "ex3", 25, 23),
]

# (bug_class, name, before, after) - xlarge tier, ~100 cells, 3 buggy
# examples per class only. Top of the size range for this preliminary
# experiment set - closer to a real analysis notebook's size than any
# tier below it.
XLARGE_PLACEMENTS = [
    ("cross_cell_semantic", "ex1", 49, 48),
    ("cross_cell_semantic", "ex2", 48, 49),
    ("cross_cell_semantic", "ex3", 50, 47),
    ("order_dependent", "ex1", 49, 49),
    ("order_dependent", "ex2", 48, 50),
    ("order_dependent", "ex3", 50, 48),
    ("api_misuse", "ex1", 49, 48),
    ("api_misuse", "ex2", 49, 49),
    ("api_misuse", "ex3", 50, 49),
    ("cross_cell_logic", "ex1", 49, 49),
    ("cross_cell_logic", "ex2", 48, 50),
    ("cross_cell_logic", "ex3", 50, 48),
]


def _author(bench_dir: str, placements: list[tuple[str, str, int, int]], name_suffix: str = "") -> list[tuple]:
    rows = []
    for bug_class, name, before, after in placements:
        core_cells, core_path, buggy = _BUGS[(bug_class, name)]
        fixture_name = name + name_suffix

        class_dir = os.path.join(bench_dir, bug_class)
        os.makedirs(class_dir, exist_ok=True)
        nb_path = os.path.join(class_dir, f"{fixture_name}.ipynb")
        expected_path = os.path.join(class_dir, f"{fixture_name}.ipynb.expected.json")

        cells, path_cells = expand_with_distractors(core_cells, core_path, before, after)

        write_notebook(nb_path, cells)
        capture = execute_and_capture(cells)
        write_expected(expected_path, buggy, capture, path_cells)

        if buggy:
            status = "OK" if capture["crashed"] else "FAIL: expected a crash, none occurred"
            detail = f"{capture.get('exc_type')} @ cell {capture.get('cell_index')} line {capture.get('line')}" if capture["crashed"] else ""
        else:
            status = "OK" if not capture["crashed"] else "FAIL: expected no crash, but one occurred"
            detail = f"{capture.get('exc_type')}: {capture.get('message')} @ cell {capture.get('cell_index')}" if capture["crashed"] else ""
        rows.append((bug_class, fixture_name, "buggy" if buggy else "clean", len(cells), status, detail))
    return rows


def _author_dep_tier(bench_dir: str, n_edges: int, target_cells: int = 30) -> list[tuple]:
    """
    Like _author, but for the dependency-count axis: cell count is held
    fixed at target_cells (matching the medium tier) while the number of
    real dependency edges is controlled directly via a build_dependency_chain
    padding cell block, instead of the usual independent DISTRACTOR_CELLS.
    Skips clean1 (same rationale as the micro/medium/large/xlarge tiers -
    llm_bench/'s clean fixtures already cover the false-positive baseline).
    """
    rows = []
    chain = build_dependency_chain(n_edges)
    for (bug_class, name), (core_cells, core_path, buggy) in _BUGS.items():
        if name == "clean1":
            continue
        after_count = target_cells - len(core_cells) - len(chain)
        assert after_count >= 0, (
            f"n_edges={n_edges} leaves no room for {bug_class}/{name} "
            f"(core={len(core_cells)}, chain={len(chain)}, target={target_cells})"
        )
        after_cells = DISTRACTOR_CELLS[:after_count]

        class_dir = os.path.join(bench_dir, bug_class)
        os.makedirs(class_dir, exist_ok=True)
        nb_path = os.path.join(class_dir, f"{name}.ipynb")
        expected_path = os.path.join(class_dir, f"{name}.ipynb.expected.json")

        cells, path_cells = expand_with_padding(core_cells, core_path, chain, after_cells)

        write_notebook(nb_path, cells)
        capture = execute_and_capture(cells)
        write_expected(expected_path, buggy, capture, path_cells)

        status = "OK" if capture["crashed"] else "FAIL: expected a crash, none occurred"
        detail = f"{capture.get('exc_type')} @ cell {capture.get('cell_index')} line {capture.get('line')}" if capture["crashed"] else ""
        rows.append((bug_class, name, "buggy", len(cells), status, detail))
    return rows


def _report(label: str, rows: list[tuple]) -> bool:
    print(f"\n=== {label} ===")
    print(f"{'class':<20}{'fixture':<12}{'kind':<8}{'cells':<7}{'status':<35}{'detail'}")
    any_fail = False
    total_cells = 0
    for bug_class, name, kind, n_cells, status, detail in rows:
        print(f"{bug_class:<20}{name:<12}{kind:<8}{n_cells:<7}{status:<35}{detail}")
        total_cells += n_cells
        if not status.startswith("OK"):
            any_fail = True
    if rows:
        print(f"{len(rows)} fixtures, avg cells: {total_cells / len(rows):.2f}")
    return any_fail


def main():
    micro_rows = _author(BENCH_MICRO_DIR, MICRO_PLACEMENTS)
    mini_rows = _author(BENCH_DIR, SMALL_PLACEMENTS)
    medium_rows = _author(BENCH_MEDIUM_DIR, MEDIUM_PLACEMENTS)
    large_rows = _author(BENCH_LARGE_DIR, LARGE_PLACEMENTS)
    xlarge_rows = _author(BENCH_XLARGE_DIR, XLARGE_PLACEMENTS)
    dep2_rows = _author_dep_tier(BENCH_DEP2_DIR, 2)
    dep10_rows = _author_dep_tier(BENCH_DEP10_DIR, 10)
    dep20_rows = _author_dep_tier(BENCH_DEP20_DIR, 20)

    all_tiers = [
        ("llm_bench_micro (micro tier)", micro_rows),
        ("llm_bench (mini tier)", mini_rows),
        ("llm_bench_medium (medium tier)", medium_rows),
        ("llm_bench_large (large tier)", large_rows),
        ("llm_bench_xlarge (xlarge tier)", xlarge_rows),
        ("llm_bench_dep2 (30 cells, ~2 dependency edges)", dep2_rows),
        ("llm_bench_dep10 (30 cells, ~10 dependency edges)", dep10_rows),
        ("llm_bench_dep20 (30 cells, ~20 dependency edges)", dep20_rows),
    ]

    failed = [_report(label, rows) for label, rows in all_tiers]

    if any(failed):
        print("\nSome fixtures did not validate as expected - see FAIL rows above.")
        sys.exit(1)
    total = sum(len(rows) for _, rows in all_tiers)
    print(f"\nAll {total} fixtures validated successfully.")


if __name__ == "__main__":
    main()
