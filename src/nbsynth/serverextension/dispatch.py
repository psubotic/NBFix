from ..events import (
    AddActiveAnalysesEvent,
    AddCellEvent,
    ChangeCellCodeEvent,
    CloseNotebookEvent,
    OpenNotebookEvent,
    RemoveCellEvent,
    RunBatchEvent,
    RunCellEvent,
)


class InvalidEventError(ValueError):
    pass


def _build_detect_bugs_event(params):
    # Lazy import: nbsynth.llm.detect_bugs_event (via config.py -> client.py)
    # imports openai, which the base/jupyter packages must never depend on
    # at module load time. Only import it once this specific event is
    # actually requested, and turn "not installed" into the same
    # InvalidEventError every other bad-request case already produces.
    try:
        from ..llm.detect_bugs_event import DetectBugsEvent
    except ImportError as exc:
        raise InvalidEventError(
            "LLM bug detection is not installed - pip install nbsynth[llm]"
        ) from exc

    scope = params.get("scope", "full")
    if scope not in ("cell", "subgraph", "full"):
        raise InvalidEventError(f"Invalid scope: {scope!r}")

    cell_index = params.get("cell_index")
    if scope != "full" and cell_index is None:
        raise InvalidEventError(f"cell_index is required for scope={scope!r}")

    return DetectBugsEvent(scope, cell_index)


_EVENT_BUILDERS = {
    "open_notebook": lambda params: OpenNotebookEvent(params["notebook_json"]),
    "run_cell": lambda params: RunCellEvent(params["cell_index"]),
    "run_batch": lambda params: RunBatchEvent(params["start_cell"]),
    "add_active_analyses": lambda params: AddActiveAnalysesEvent(params["active_analyses"]),
    "add_cell": lambda params: AddCellEvent(params["position"], params["kind"], params["content"]),
    "remove_cell": lambda params: RemoveCellEvent(params["position"]),
    "change_cell": lambda params: ChangeCellCodeEvent(
        str(params["new_code"]), int(params["cell_index"]), bool(params["with_result"])
    ),
    "close_notebook": lambda params: CloseNotebookEvent(),
    "detect_bugs": _build_detect_bugs_event,
}


def build_event(event_name: str, params: dict):
    """
    Constructs an Event instance for the given event name and params.

    Raises InvalidEventError if the event name is unknown or the params
    don't match what that event requires.
    """
    try:
        builder = _EVENT_BUILDERS[event_name]
    except KeyError:
        raise InvalidEventError(f"Unknown event: {event_name!r}")

    try:
        return builder(params or {})
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidEventError(f"Invalid parameters for event {event_name!r}: {exc}") from exc
