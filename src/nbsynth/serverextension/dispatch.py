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
