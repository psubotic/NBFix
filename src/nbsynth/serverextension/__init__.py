from .handlers import setup_handlers


def _jupyter_server_extension_points():
    return [{"module": "nbsynth.serverextension"}]


def _load_jupyter_server_extension(server_app):
    """
    Registers the NBSynth API handler on the running Jupyter server.

    Parameters
    ----------
    server_app: jupyter_server.serverapp.ServerApp
        The Jupyter server instance.
    """
    setup_handlers(server_app.web_app)
    server_app.log.info("Registered nbsynth server extension")
