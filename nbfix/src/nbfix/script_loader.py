import ast

from nbcore.ir.intermediate_representations import IntermediateRepresentations


def script_cells_from_source(script_code: str) -> dict[int, IntermediateRepresentations]:
    """Splits a script's top-level statements into pseudo-cells, keyed by
    their position among top-level statements - the same shape
    AnalysisSession.load() expects from a notebook (see
    nbharness.notebook_loader.notebook_cells_from_json), so every
    cell-based analysis (dependency graph, LLM context chunking,
    dataleak/type-shape) works on a script unchanged instead of treating
    the whole file as one opaque blob.

    Uses the stdlib ast module (not nbcore's own notebook-flavored
    parser) purely to find each top-level statement's line span - the
    actual IntermediateRepresentations for each pseudo-cell is still
    built by nbcore's own parser/CFG/def-use pipeline, same as any
    notebook cell.

    Known limitation: a comment/blank line between two top-level
    statements is attributed to whichever statement's line span it falls
    inside per ast's lineno/end_lineno, not preserved as its own unit -
    acceptable for analysis purposes, since comments carry no code
    semantics, but would need revisiting if this feeds a diff-based
    repair UI that should preserve the original file's exact formatting.
    """
    lines = script_code.splitlines()
    tree = ast.parse(script_code)

    cells: dict[int, IntermediateRepresentations] = {}
    for position, node in enumerate(tree.body):
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        chunk = "\n".join(lines[start - 1:end])
        cells[position] = IntermediateRepresentations(chunk, position)
    return cells
