import unittest
from unittest.mock import MagicMock

import pytest

# Importing DetectBugsEvent transitively imports openai (via config.py ->
# client.py), even though tests inject a mock client - see client tests
# for why this guard exists.
pytest.importorskip("openai")

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
    def __init__(self, notebook_IR):
        self.notebook_IR = notebook_IR


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


if __name__ == "__main__":
    unittest.main()
