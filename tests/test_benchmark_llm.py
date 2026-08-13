import os
import sys
import unittest

import pytest

pytest.importorskip("openai")

# scripts/ isn't a package (it's a dev-only tool, not shipped/installed) -
# add it to sys.path so the scoring function can be imported for testing.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from benchmark_llm import parse_config, score_findings  # noqa: E402


class TestParseConfig(unittest.TestCase):
    def test_parses_name_model_base_url(self):
        config = parse_config("small=qwen2.5-coder:14b@http://localhost:11434/v1")
        self.assertEqual(config.name, "small")
        self.assertEqual(config.model, "qwen2.5-coder:14b")
        self.assertEqual(config.base_url, "http://localhost:11434/v1")

    def test_missing_parts_raises(self):
        with self.assertRaises(ValueError):
            parse_config("small=qwen2.5-coder:14b")  # no @base_url

        with self.assertRaises(ValueError):
            parse_config("qwen2.5-coder:14b@http://localhost:11434/v1")  # no name=


class TestScoreFindings(unittest.TestCase):
    def test_exact_match(self):
        score = score_findings([(0, 3)], [(0, 3)])
        self.assertEqual(score["true_positives"], 1)
        self.assertEqual(score["false_positives"], 0)
        self.assertEqual(score["false_negatives"], 0)
        self.assertEqual(score["precision"], 1.0)
        self.assertEqual(score["recall"], 1.0)
        self.assertEqual(score["f1"], 1.0)

    def test_within_line_tolerance_still_matches(self):
        score = score_findings([(0, 5)], [(0, 3)], line_tolerance=2)
        self.assertEqual(score["true_positives"], 1)

    def test_outside_line_tolerance_does_not_match(self):
        score = score_findings([(0, 6)], [(0, 3)], line_tolerance=2)
        self.assertEqual(score["true_positives"], 0)

    def test_different_cell_id_does_not_match_even_if_line_close(self):
        score = score_findings([(1, 3)], [(0, 3)])
        self.assertEqual(score["true_positives"], 0)

    def test_extra_actual_findings_are_false_positives(self):
        score = score_findings([(0, 1), (0, 2)], [(0, 1)])
        self.assertEqual(score["true_positives"], 1)
        self.assertEqual(score["false_positives"], 1)
        self.assertEqual(score["precision"], 0.5)
        self.assertEqual(score["recall"], 1.0)

    def test_missing_expected_findings_are_false_negatives(self):
        score = score_findings([(0, 1)], [(0, 1), (1, 5)])
        self.assertEqual(score["true_positives"], 1)
        self.assertEqual(score["false_negatives"], 1)
        self.assertEqual(score["recall"], 0.5)

    def test_no_double_counting_same_actual_finding_twice(self):
        # Two expected findings both near the same single actual finding -
        # it should only count as one true positive, not two.
        score = score_findings([(0, 3)], [(0, 2), (0, 4)])
        self.assertEqual(score["true_positives"], 1)
        self.assertEqual(score["false_negatives"], 1)

    def test_empty_actual_and_expected(self):
        score = score_findings([], [])
        self.assertEqual(score["precision"], 0.0)
        self.assertEqual(score["recall"], 0.0)
        self.assertEqual(score["f1"], 0.0)

    def test_empty_expected_with_actual_findings_zero_recall(self):
        score = score_findings([(0, 1)], [])
        self.assertEqual(score["recall"], 0.0)
        self.assertEqual(score["false_positives"], 1)


if __name__ == "__main__":
    unittest.main()
