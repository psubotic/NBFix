from ..events import Event
from .config import default_client
from .context_builder import (
    build_cell_context,
    build_full_notebook_context,
    build_subgraph_context,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .result_mapping import map_findings_to_result

_CONTEXT_BUILDERS = {
    "cell": build_cell_context,
    "subgraph": build_subgraph_context,
}


class DetectBugsEvent(Event):
    """
    Runs LLM-assisted bug detection over the notebook, grounded in the
    structural context context_builder.py derives from it. Not part of
    core events.py - see the "Critical design point" note in the plan for
    why: importing this module (directly or via `client`) pulls in
    `openai`, which core code must never do implicitly.
    """

    def __init__(self, scope: str, cell_index: int = None, client=None):
        self.scope = scope
        self.cell_index = cell_index
        self.client = client or default_client()

    def execute(self, nbfix):
        if self.scope == "full":
            context = build_full_notebook_context(nbfix.notebook_IR)
        elif self.scope in _CONTEXT_BUILDERS:
            if self.cell_index is None:
                raise ValueError(f"cell_index is required for scope={self.scope!r}")
            context = _CONTEXT_BUILDERS[self.scope](nbfix.notebook_IR, self.cell_index)
        else:
            raise ValueError(f"Unknown scope: {self.scope!r}")

        findings_json = self.client.chat_json(SYSTEM_PROMPT, build_user_prompt(context))
        return map_findings_to_result(findings_json, nbfix.notebook_IR)
