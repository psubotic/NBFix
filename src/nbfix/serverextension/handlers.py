import json

import tornado
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join

from ..constants import DATA_LEAK, IDLE, ISOLATED, STALE
from .dispatch import InvalidEventError, build_event
from .sessions import SessionStore

DEFAULT_ANALYSES = [DATA_LEAK, STALE, IDLE, ISOLATED]


class EventHandler(APIHandler):
    """
    Single endpoint that receives {event, notebook_id, params} and dispatches
    it to the matching Event on the NBFix session for that notebook.
    """

    @tornado.web.authenticated
    def post(self):
        body = self.get_json_body() or {}
        try:
            event_name = body["event"]
            notebook_id = body["notebook_id"]
        except KeyError as exc:
            self._respond_error(400, f"Missing required field: {exc}")
            return

        params = body.get("params") or {}
        sessions: SessionStore = self.settings["nbfix_sessions"]

        if event_name == "open_notebook":
            nbfix = sessions.get_or_create(notebook_id)
        else:
            nbfix = sessions.get(notebook_id)
            if nbfix is None:
                self._respond_error(404, f"No open session for notebook {notebook_id!r}")
                return

        try:
            event = build_event(event_name, params)
        except InvalidEventError as exc:
            self._respond_error(400, str(exc))
            return

        try:
            result = nbfix.execute_event(event)

            if event_name == "open_notebook":
                # Bootstrap the default set of active analyses so the first
                # response already carries diagnostics, mirroring what the
                # VS Code prototype did via a follow-up add_active_analyses call.
                analyses_event = build_event("add_active_analyses", {"active_analyses": DEFAULT_ANALYSES})
                result = nbfix.execute_event(analyses_event)
        except Exception as exc:
            # Catches failures that only surface at execution time rather
            # than at dispatch (e.g. an unreachable local LLM endpoint for
            # detect_bugs) - one event failing this way must not crash the
            # request with an unhandled-exception response.
            self._respond_error(500, f"Event execution failed: {exc}")
            return

        if event_name == "close_notebook":
            sessions.close(notebook_id)

        self._respond_success(result)

    def _respond_success(self, result):
        diagnostics = []
        # Result.dumps() returns '' (not '[]') when there are no findings -
        # json.loads('') would raise, so only attempt to parse when there's
        # actually something to parse. A clean "no findings" result is the
        # common case for detect_bugs (most checks won't find a bug), not
        # an edge case to special-case away.
        if result is not None and result.path_results:
            try:
                diagnostics = json.loads(result.dumps())
            except (ValueError, AttributeError):
                self._respond_error(500, "Failed to serialize analysis results")
                return
        self.finish(json.dumps({"status": "success", "diagnostics": diagnostics}))

    def _respond_error(self, status_code, message):
        self.set_status(status_code)
        self.finish(json.dumps({"status": "error", "message": message}))


def setup_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]
    web_app.settings.setdefault("nbfix_sessions", SessionStore())
    route_pattern = url_path_join(base_url, "nbfix", "api", "event")
    web_app.add_handlers(host_pattern, [(route_pattern, EventHandler)])
