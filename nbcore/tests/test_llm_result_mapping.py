import json
import unittest

from nbcore.ir.intermediate_representations import IntermediateRepresentations
from nbcore.llm.result_mapping import map_findings_to_result


def make_notebook(cells: dict[int, str]) -> dict:
    return {
        cell_id: IntermediateRepresentations(code, cell_id)
        for cell_id, code in cells.items()
    }


class TestMapFindingsToResult(unittest.TestCase):
    def setUp(self):
        self.notebook_IR = make_notebook(
            {0: "x = 1", 1: "y = x + 1\nz = y + 1"}
        )

    def test_valid_single_cell_finding(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [1],
                    "line": 2,
                    "label": "z",
                    "severity": "warning",
                    "message": "z is computed but never used.",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(len(result.path_results), 1)
        path_result = result.path_results[0]
        self.assertEqual(path_result.path, [1])
        error = path_result.error_infos[0]
        self.assertEqual(error.cell_id, 1)
        self.assertEqual(error.line, 2)
        self.assertEqual(error.label, "z")
        self.assertEqual(error.error_type, "LLM_WARNING")
        self.assertEqual(error.error_message, "z is computed but never used.")

    def test_valid_multi_cell_finding_anchors_on_last_cell_id(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [0, 1],
                    "line": 1,
                    "label": "x",
                    "severity": "critical",
                    "message": "cross-cell issue.",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        error = result.path_results[0].error_infos[0]
        self.assertEqual(result.path_results[0].path, [0, 1])
        self.assertEqual(error.cell_id, 1)
        self.assertEqual(error.error_type, "LLM_CRITICAL")

    def test_dumps_produces_valid_json(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [1],
                    "line": 1,
                    "label": "y",
                    "severity": "warning",
                    "message": "example",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        parsed = json.loads(result.dumps())
        self.assertEqual(parsed[0]["cell_id"], 1)
        self.assertEqual(parsed[0]["errors"][0]["error_type"], "LLM_WARNING")

    def test_missing_findings_key_returns_empty_result(self):
        result = map_findings_to_result({"not_findings": []}, self.notebook_IR)
        self.assertEqual(result.path_results, [])

    def test_unknown_cell_id_is_dropped(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [99],
                    "line": 1,
                    "label": "",
                    "severity": "warning",
                    "message": "bad cell",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(result.path_results, [])

    def test_out_of_range_line_is_dropped(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [0],
                    "line": 50,
                    "label": "",
                    "severity": "warning",
                    "message": "bad line",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(result.path_results, [])

    def test_invalid_severity_is_dropped(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [0],
                    "line": 1,
                    "label": "",
                    "severity": "urgent",
                    "message": "bad severity",
                }
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(result.path_results, [])

    def test_missing_message_is_dropped(self):
        findings_json = {
            "findings": [
                {"cell_ids": [0], "line": 1, "label": "", "severity": "warning"}
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(result.path_results, [])

    def test_one_invalid_finding_does_not_drop_valid_ones(self):
        findings_json = {
            "findings": [
                {
                    "cell_ids": [0],
                    "line": 1,
                    "label": "x",
                    "severity": "warning",
                    "message": "valid finding",
                },
                {
                    "cell_ids": [99],
                    "line": 1,
                    "label": "",
                    "severity": "warning",
                    "message": "invalid - unknown cell",
                },
            ]
        }
        result = map_findings_to_result(findings_json, self.notebook_IR)
        self.assertEqual(len(result.path_results), 1)
        self.assertEqual(
            result.path_results[0].error_infos[0].error_message, "valid finding"
        )


if __name__ == "__main__":
    unittest.main()
