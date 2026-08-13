import unittest

import pytest

pytest.importorskip("openai")

from nbfix.llm.detect_bugs_event import DetectBugsEvent
from nbfix.serverextension.dispatch import InvalidEventError, build_event


class TestDetectBugsDispatch(unittest.TestCase):
    def test_full_scope(self):
        event = build_event("detect_bugs", {"scope": "full"})
        self.assertIsInstance(event, DetectBugsEvent)
        self.assertEqual(event.scope, "full")
        self.assertIsNone(event.cell_index)

    def test_defaults_to_full_scope(self):
        event = build_event("detect_bugs", {})
        self.assertEqual(event.scope, "full")

    def test_cell_scope_with_cell_index(self):
        event = build_event("detect_bugs", {"scope": "cell", "cell_index": 2})
        self.assertEqual(event.scope, "cell")
        self.assertEqual(event.cell_index, 2)

    def test_subgraph_scope_with_cell_index(self):
        event = build_event("detect_bugs", {"scope": "subgraph", "cell_index": 0})
        self.assertEqual(event.scope, "subgraph")
        self.assertEqual(event.cell_index, 0)

    def test_invalid_scope_raises(self):
        with self.assertRaises(InvalidEventError):
            build_event("detect_bugs", {"scope": "not_a_scope"})

    def test_cell_scope_without_cell_index_raises(self):
        with self.assertRaises(InvalidEventError):
            build_event("detect_bugs", {"scope": "cell"})

    def test_subgraph_scope_without_cell_index_raises(self):
        with self.assertRaises(InvalidEventError):
            build_event("detect_bugs", {"scope": "subgraph"})


if __name__ == "__main__":
    unittest.main()
