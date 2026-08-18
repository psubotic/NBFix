import unittest
from unittest.mock import MagicMock

import pytest

# Importing DetectBugsEvent transitively imports openai (via config.py ->
# client.py), even though tests inject a mock client - see client tests
# for why this guard exists.
pytest.importorskip("openai")

from nbfix.analyses.runner.analysis_results import ErrorInfo, PathResult, Result
from nbfix.ir.intermediate_representations import IntermediateRepresentations
from nbfix.llm.client import LLMClientError
from nbfix.llm.detect_bugs_event import DetectBugsEvent


def make_notebook(cells: dict[int, str]) -> dict:
    return {
        cell_id: IntermediateRepresentations(code, cell_id)
        for cell_id, code in cells.items()
    }


EMPTY_FINDINGS = {"findings": []}


class FakeNBFix:
    def __init__(self, notebook_IR, results=None, active_analyses=None):
        self.notebook_IR = notebook_IR
        self.results = results or {}
        self.active_analyses = active_analyses or []


class TestDetectBugsEvent(unittest.TestCase):
    def setUp(self):
        self.notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1"})
        self.nbfix = FakeNBFix(self.notebook_IR)

    def test_cell_scope_calls_client_and_maps_result(self):
        client = MagicMock()
        client.chat_json.return_value = {
            "findings": [
                {
                    "cell_ids": [1],
                    "line": 1,
                    "label": "y",
                    "severity": "warning",
                    "message": "unused",
                }
            ]
        }
        event = DetectBugsEvent("cell", cell_index=1, client=client)

        result = event.execute(self.nbfix)

        client.chat_json.assert_called_once()
        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("y = x + 1", user_prompt)
        self.assertNotIn("x = 1", user_prompt)  # cell scope: no neighbor code
        self.assertEqual(len(result.path_results), 1)
        self.assertEqual(result.path_results[0].error_infos[0].error_type, "LLM_WARNING")

    def test_subgraph_scope_includes_neighbor_code(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("subgraph", cell_index=1, client=client)

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("x = 1", user_prompt)
        self.assertIn("y = x + 1", user_prompt)

    def test_full_scope_ignores_cell_index(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client)

        result = event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("x = 1", user_prompt)
        self.assertIn("y = x + 1", user_prompt)
        self.assertEqual(result.path_results, [])

    def test_cell_scope_without_cell_index_raises(self):
        event = DetectBugsEvent("cell", client=MagicMock())
        with self.assertRaises(ValueError):
            event.execute(self.nbfix)

    def test_unknown_scope_raises(self):
        event = DetectBugsEvent("not_a_scope", cell_index=0, client=MagicMock())
        with self.assertRaises(ValueError):
            event.execute(self.nbfix)

    def test_llm_client_error_propagates(self):
        client = MagicMock()
        client.chat_json.side_effect = LLMClientError("endpoint unreachable")
        event = DetectBugsEvent("full", client=client)

        with self.assertRaises(LLMClientError):
            event.execute(self.nbfix)

    def test_context_mode_none_omits_dependency_graph(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client, context_mode="none")

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertNotIn("## Dependency graph", user_prompt)

    def test_context_mode_deps_is_default(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client)

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("## Dependency graph", user_prompt)

    def test_invalid_context_mode_raises(self):
        event = DetectBugsEvent("full", client=MagicMock(), context_mode="bogus")
        with self.assertRaises(ValueError):
            event.execute(self.nbfix)

    def test_finding_types_adds_findings_section(self):
        finding = ErrorInfo(1, 1, "y", "TERMINAL", "idle")
        results = {"Idle Cells Analysis": Result()}
        results["Idle Cells Analysis"].add_path_result(PathResult([1], [finding]))
        nbfix = FakeNBFix(self.notebook_IR, results=results)

        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client, finding_types={"Idle Cells Analysis"})

        event.execute(nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("## Static analysis findings", user_prompt)
        self.assertIn("idle", user_prompt)

    def test_no_finding_types_omits_findings_section(self):
        results = {"Idle Cells Analysis": Result()}
        results["Idle Cells Analysis"].add_path_result(
            PathResult([1], [ErrorInfo(1, 1, "y", "TERMINAL", "idle")])
        )
        nbfix = FakeNBFix(self.notebook_IR, results=results)

        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client)

        event.execute(nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertNotIn("## Static analysis findings", user_prompt)

    def test_execute_never_mutates_active_analyses(self):
        """
        Regression guard: DetectBugsEvent must never call
        nbfix.add_analyses()/run_analyses() itself, since add_analyses()
        fully replaces active_analyses rather than merging - doing that
        here would silently change what the live JupyterLab editor shows
        on the next run_cell/change_cell event.
        """
        nbfix = FakeNBFix(self.notebook_IR, active_analyses=["Idle Cells Analysis"])
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client, finding_types={"Idle Cells Analysis"})

        event.execute(nbfix)

        self.assertEqual(nbfix.active_analyses, ["Idle Cells Analysis"])

    def test_extra_findings_render_alongside_finding_types(self):
        registered = ErrorInfo(1, 1, "y", "TERMINAL", "idle")
        results = {"Idle Cells Analysis": Result()}
        results["Idle Cells Analysis"].add_path_result(PathResult([1], [registered]))
        nbfix = FakeNBFix(self.notebook_IR, results=results)

        extra = ErrorInfo(1, 1, "y", "TYPE_CHANGE", "'y' redefined from list to int")
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent(
            "full", client=client, finding_types={"Idle Cells Analysis"}, extra_findings=[extra],
        )

        event.execute(nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("idle", user_prompt)
        self.assertIn("redefined from list to int", user_prompt)

    def test_extra_findings_alone_render_without_finding_types(self):
        extra = ErrorInfo(1, 1, "y", "TYPE_CHANGE", "'y' redefined from list to int")
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client, extra_findings=[extra])

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("## Static analysis findings", user_prompt)
        self.assertIn("redefined from list to int", user_prompt)

    def test_no_extra_findings_omits_section_as_before(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client)

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertNotIn("## Static analysis findings", user_prompt)

    def test_dependency_edges_override_replaces_real_graph(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        # Real graph would render "Cell 1 depends on: Cell 0" - the
        # override below has no edges at all, so that line must not appear.
        event = DetectBugsEvent("full", client=client, dependency_edges={0: set(), 1: set()})

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("## Dependency graph", user_prompt)
        self.assertNotIn("Cell 1 depends on: Cell 0", user_prompt)
        self.assertIn("(no cross-cell dependencies detected)", user_prompt)

    def test_no_dependency_edges_override_uses_real_graph(self):
        client = MagicMock()
        client.chat_json.return_value = EMPTY_FINDINGS
        event = DetectBugsEvent("full", client=client)

        event.execute(self.nbfix)

        _, user_prompt = client.chat_json.call_args.args
        self.assertIn("## Dependency graph", user_prompt)


if __name__ == "__main__":
    unittest.main()
