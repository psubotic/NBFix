import logging

from ..ir.intermediate_representations import IntermediateRepresentations

logger = logging.getLogger(__name__)


def load_notebook_resilient(cells_json) -> dict[int, IntermediateRepresentations]:
    """
    Like resource_utils.utils.load_notebook, but a cell whose code hits a
    construct the parser doesn't support yet (NotImplementedError - see
    ast_transformer.py's docstring for the tracked list: comprehensions,
    lambda, walrus, f-strings, etc.) is skipped rather than aborting the
    whole notebook.

    Scoped deliberately to the LLM path (this module, scripts/benchmark_llm.py)
    - the core engine (analyzer.py's NBFix.load_notebook,
    resource_utils.utils.load_notebook, and everything that depends on
    open_notebook succeeding - the CLI's -a flow, the JupyterLab extension,
    DetectBugsEvent included, since it runs against an already-loaded
    nbfix.notebook_IR) is untouched and still fails fast on the same
    input. A best-effort partial view is useful for ad-hoc LLM checks and
    benchmarking over real-world notebooks that may use constructs NBFix
    hasn't caught up to yet; silently producing partial results for the
    analyses that assume every cell has a real AST/CFG/def-use chain would
    be a different, riskier trade-off this doesn't make.
    """
    notebook_IR: dict[int, IntermediateRepresentations] = {}
    if not cells_json:
        return notebook_IR

    for cell_id, cell in enumerate(cells_json):
        if cell["cell_type"] != "code" or not cell["source"]:
            continue

        source = cell["source"]
        if isinstance(source, list):
            source = "".join(source)

        try:
            notebook_IR[cell_id] = IntermediateRepresentations(source, cell_id)
        except Exception as exc:
            logger.warning("Skipping cell %d - failed to parse: %s", cell_id, exc)

    return notebook_IR
