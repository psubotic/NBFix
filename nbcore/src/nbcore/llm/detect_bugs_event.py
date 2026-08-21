from ..events import Event
from .config import default_client
from .context_builder import (
    build_cell_context,
    build_full_notebook_context,
    build_subgraph_context,
    collect_deterministic_findings,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .result_mapping import map_findings_to_result

_CONTEXT_BUILDERS = {
    "cell": build_cell_context,
    "subgraph": build_subgraph_context,
}

_VALID_CONTEXT_MODES = ("none", "deps")


class DetectBugsEvent(Event):
    """
    Runs LLM-assisted bug detection over the notebook, grounded in the
    structural context context_builder.py derives from it. Not part of
    core events.py - see the "Critical design point" note in the plan for
    why: importing this module (directly or via `client`) pulls in
    `openai`, which core code must never do implicitly.

    context_mode controls whether the dependency graph is included in the
    prompt: "deps" (default, today's original behavior) or "none" (the
    no-context ablation baseline). finding_types, if given, is an allowlist
    of analysis-name constants (see constants.py) whose findings - if
    already present in nbfix.results - get rendered as extra context.

    execute() deliberately never calls nbfix.add_analyses()/run_analyses()
    itself: NBFix.add_analyses() fully *replaces* active_analyses rather
    than merging, so doing that here would silently change what
    deterministic diagnostics the live JupyterLab editor shows on the next
    run_cell/change_cell event. finding_types is purely a filter over
    whatever nbfix.results already contains - callers that need
    guaranteed-fresh findings (CLI, benchmark scripts) must run a batch
    analysis themselves before constructing this event.

    extra_findings, if given, is a plain list[ErrorInfo] merged in
    alongside whatever finding_types produces - an escape hatch for
    findings from something that isn't (yet) a registered NBFix.all_analyses
    entry (e.g. a standalone prototype analysis under evaluation, see
    analyses/type_shape_analysis.py), without needing to fully wire it
    into constants.py/NBFix.all_analyses just to benchmark it.

    dependency_edges, if given, overrides context_builder's own
    build_dependency_edges output entirely - the same kind of escape
    hatch as extra_findings, but for the edges themselves rather than an
    additional findings section (e.g. analyses/type_shape_analysis.py's
    build_pruned_dependency_edges, which removes rather than adds).
    """

    def __init__(self, scope: str, cell_index: int = None, client=None,
                 context_mode: str = "deps", finding_types=None, extra_findings=None,
                 dependency_edges=None):
        self.scope = scope
        self.cell_index = cell_index
        self.client = client or default_client()
        self.context_mode = context_mode
        self.finding_types = finding_types
        self.extra_findings = extra_findings
        self.dependency_edges = dependency_edges

    def execute(self, nbfix):
        if self.context_mode not in _VALID_CONTEXT_MODES:
            raise ValueError(f"Unknown context_mode: {self.context_mode!r}")

        deterministic_findings = (
            collect_deterministic_findings(nbfix.results, self.finding_types)
            if self.finding_types else []
        )
        if self.extra_findings:
            deterministic_findings = deterministic_findings + list(self.extra_findings)
        deterministic_findings = deterministic_findings or None

        if self.scope == "full":
            context = build_full_notebook_context(
                nbfix.cells, deterministic_findings, dependency_edges=self.dependency_edges,
            )
        elif self.scope in _CONTEXT_BUILDERS:
            if self.cell_index is None:
                raise ValueError(f"cell_index is required for scope={self.scope!r}")
            context = _CONTEXT_BUILDERS[self.scope](
                nbfix.cells, self.cell_index, deterministic_findings, dependency_edges=self.dependency_edges,
            )
        else:
            raise ValueError(f"Unknown scope: {self.scope!r}")

        user_prompt = build_user_prompt(context, include_dependency_graph=(self.context_mode != "none"))
        findings_json = self.client.chat_json(SYSTEM_PROMPT, user_prompt)
        return map_findings_to_result(findings_json, nbfix.cells)
