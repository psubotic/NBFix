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
    """

    def __init__(self, scope: str, cell_index: int = None, client=None,
                 context_mode: str = "deps", finding_types=None):
        self.scope = scope
        self.cell_index = cell_index
        self.client = client or default_client()
        self.context_mode = context_mode
        self.finding_types = finding_types

    def execute(self, nbfix):
        if self.context_mode not in _VALID_CONTEXT_MODES:
            raise ValueError(f"Unknown context_mode: {self.context_mode!r}")

        deterministic_findings = (
            collect_deterministic_findings(nbfix.results, self.finding_types)
            if self.finding_types else None
        )

        if self.scope == "full":
            context = build_full_notebook_context(nbfix.notebook_IR, deterministic_findings)
        elif self.scope in _CONTEXT_BUILDERS:
            if self.cell_index is None:
                raise ValueError(f"cell_index is required for scope={self.scope!r}")
            context = _CONTEXT_BUILDERS[self.scope](nbfix.notebook_IR, self.cell_index, deterministic_findings)
        else:
            raise ValueError(f"Unknown scope: {self.scope!r}")

        user_prompt = build_user_prompt(context, include_dependency_graph=(self.context_mode != "none"))
        findings_json = self.client.chat_json(SYSTEM_PROMPT, user_prompt)
        return map_findings_to_result(findings_json, nbfix.notebook_IR)
