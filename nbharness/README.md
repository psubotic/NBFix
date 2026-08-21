# NBHarness

Live, real-time notebook diagnostics - stale/idle/isolated cells and
data leakage, plus LLM-assisted stale-cell and API-call-sequence
detection. Flags problems as you edit and run cells; never repairs.

Built on `nbcore`. Ships a `jupyter_server` REST extension
(`serverextension/`) for live diagnostics in JupyterLab (see the
`jupyterlab-nbharness/` labextension), and its own `nbharness` CLI for
batch/one-shot scanning of a notebook file outside a live session.

See the top-level repo README for how this fits into the wider suite.
