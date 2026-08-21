class Event:
    def execute(self, session):
        pass


class RunBatchEvent(Event):
    """Runs every active analysis once, in full detail, from start_cell -
    the batch/one-shot mode both NBHarness's CLI and NBFix's CLI use, as
    opposed to NBHarness's incremental per-edit events (see its own
    events.py)."""

    def __init__(self, start_cell):
        self.start_cell = start_cell

    def execute(self, session):
        return session.run_analyses(self.start_cell, detailed=True)
