from dataclasses import dataclass, field

from ..analyses.dependency_analysis import build_dependency_edges, _connected_component
from ..analyses.runner.analysis_results import ErrorInfo, Result


@dataclass
class CellContext:
    cell_id: int
    code: str


@dataclass
class BugDetectionContext:
    target_cell_ids: list[int]
    cells: list[CellContext]
    dependency_edges: dict[int, set[int]]
    deterministic_findings: list[ErrorInfo] = field(default_factory=list)


def collect_deterministic_findings(results: dict[str, Result], finding_types) -> list[ErrorInfo]:
    """
    Flattens the requested analyses' already-computed Result objects (as
    stored on NBFix.results) into a plain list of ErrorInfo.

    Pure function, no NBFix dependency - deliberately never triggers a
    fresh analysis run itself. Callers that need guaranteed-fresh findings
    (CLI, benchmark scripts) are responsible for running a batch analysis
    themselves before calling this - see DetectBugsEvent's docstring for
    why it must not do that automatically.
    """
    findings: list[ErrorInfo] = []
    for analysis_name in finding_types or []:
        result = results.get(analysis_name)
        if result is None:
            continue
        for path_result in result.path_results:
            findings.extend(path_result.error_infos)
    return findings


def _findings_for_cells(findings: list[ErrorInfo], cell_ids) -> list[ErrorInfo]:
    cell_id_set = set(cell_ids)
    return [f for f in findings if f.cell_id in cell_id_set]


def build_cell_context(notebook_IR, cell_id: int, deterministic_findings=None, dependency_edges=None) -> BugDetectionContext:
    """Just the target cell's code, plus its own dependency edges as
    structural summary - no neighbor code included.

    dependency_edges, if given, overrides the real build_dependency_edges
    output entirely - an escape hatch (mirrors DetectBugsEvent's
    extra_findings) for benchmarking an alternative edge set, e.g.
    analyses/type_shape_analysis.py's build_pruned_dependency_edges,
    without wiring a whole new context_mode into product code."""
    edges = dependency_edges if dependency_edges is not None else build_dependency_edges(notebook_IR)
    ir = notebook_IR[cell_id]
    return BugDetectionContext(
        target_cell_ids=[cell_id],
        cells=[CellContext(cell_id=cell_id, code=ir.cell_code)],
        dependency_edges={cell_id: edges.get(cell_id, set())},
        deterministic_findings=_findings_for_cells(deterministic_findings or [], [cell_id]),
    )


def build_subgraph_context(notebook_IR, cell_id: int, deterministic_findings=None, dependency_edges=None) -> BugDetectionContext:
    """Full code for every cell in the target cell's connected component
    (transitive dependencies and dependents), not just the target cell.
    dependency_edges: see build_cell_context's docstring."""
    edges = dependency_edges if dependency_edges is not None else build_dependency_edges(notebook_IR)
    component = sorted(_connected_component(edges, cell_id))
    return BugDetectionContext(
        target_cell_ids=[cell_id],
        cells=[
            CellContext(cell_id=cid, code=notebook_IR[cid].cell_code)
            for cid in component
        ],
        dependency_edges={cid: edges.get(cid, set()) for cid in component},
        deterministic_findings=_findings_for_cells(deterministic_findings or [], component),
    )


def build_full_notebook_context(notebook_IR, deterministic_findings=None, dependency_edges=None) -> BugDetectionContext:
    """Every cell's code and the full dependency graph.
    dependency_edges: see build_cell_context's docstring."""
    edges = dependency_edges if dependency_edges is not None else build_dependency_edges(notebook_IR)
    all_ids = sorted(notebook_IR)
    return BugDetectionContext(
        target_cell_ids=all_ids,
        cells=[
            CellContext(cell_id=cid, code=notebook_IR[cid].cell_code)
            for cid in all_ids
        ],
        dependency_edges=edges,
        deterministic_findings=_findings_for_cells(deterministic_findings or [], all_ids),
    )
