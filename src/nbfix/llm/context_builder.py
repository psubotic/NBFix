from dataclasses import dataclass, field

from ..analyses.runner.analysis_results import ErrorInfo, Result


def build_dependency_edges(notebook_IR) -> dict[int, set[int]]:
    """
    Returns cell_id -> set of cell_ids it depends on.

    Walks cells in id order tracking a running "last cell to define this
    name" map; a cell depends on cell X if it reads a name whose most
    recent definition, at that point in the walk, was in cell X. There is
    no existing cross-cell def-use resolver in the codebase to reuse here -
    parser/def_use.py only computes intra-cell info.
    """
    last_definer: dict[str, int] = {}
    edges: dict[int, set[int]] = {}

    for cell_id in sorted(notebook_IR):
        ir = notebook_IR[cell_id]
        edges[cell_id] = {
            last_definer[name]
            for name in ir.UDA.unbound_final
            if name in last_definer
        }
        for name in ir.UDA.defined_vars:
            last_definer[name] = cell_id

    return edges


def _connected_component(edges: dict[int, set[int]], cell_id: int) -> set[int]:
    """Transitive closure over `edges`, following both directions (what
    cell_id depends on, and what depends on cell_id)."""
    reverse: dict[int, set[int]] = {}
    for cell, deps in edges.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(cell)

    seen = {cell_id}
    frontier = {cell_id}
    while frontier:
        next_frontier = set()
        for cell in frontier:
            for neighbor in edges.get(cell, set()) | reverse.get(cell, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
    return seen


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


def build_cell_context(notebook_IR, cell_id: int, deterministic_findings=None) -> BugDetectionContext:
    """Just the target cell's code, plus its own dependency edges as
    structural summary - no neighbor code included."""
    edges = build_dependency_edges(notebook_IR)
    ir = notebook_IR[cell_id]
    return BugDetectionContext(
        target_cell_ids=[cell_id],
        cells=[CellContext(cell_id=cell_id, code=ir.cell_code)],
        dependency_edges={cell_id: edges.get(cell_id, set())},
        deterministic_findings=_findings_for_cells(deterministic_findings or [], [cell_id]),
    )


def build_subgraph_context(notebook_IR, cell_id: int, deterministic_findings=None) -> BugDetectionContext:
    """Full code for every cell in the target cell's connected component
    (transitive dependencies and dependents), not just the target cell."""
    edges = build_dependency_edges(notebook_IR)
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


def build_full_notebook_context(notebook_IR, deterministic_findings=None) -> BugDetectionContext:
    """Every cell's code and the full dependency graph."""
    edges = build_dependency_edges(notebook_IR)
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
