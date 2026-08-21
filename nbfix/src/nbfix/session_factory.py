from nbcore.session import AnalysisSession
from nbcore.analyses.dataleak_analysis import DataLeakAnalysis, DATA_LEAK


def new_session(level=5, filename="") -> AnalysisSession:
    """Builds an AnalysisSession with NBFix's own analysis set registered.
    Scripts only - no STALE/IDLE/ISOLATED here, those are notebook-edit-
    lifecycle concepts with no script analog (see NBHarness's own
    session_factory). type_shape_analysis.py stays unwired here, same as
    it was in the original NBFix.all_analyses - it's still a standalone
    function, not yet an Analysis subclass with analyze_notebook."""
    session = AnalysisSession(level=level, filename=filename)
    session.register_analysis(DATA_LEAK, DataLeakAnalysis())
    return session
