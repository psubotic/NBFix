import unittest

from nbsynth.ir.intermediate_representations import IntermediateRepresentations
from nbsynth.llm.context_builder import build_subgraph_context
from nbsynth.llm.prompts import SYSTEM_PROMPT, build_user_prompt


class TestBuildUserPrompt(unittest.TestCase):
    def test_includes_cell_code_and_dependencies(self):
        notebook_IR = {
            0: IntermediateRepresentations("x = 1", 0),
            1: IntermediateRepresentations("y = x + 1", 1),
        }
        context = build_subgraph_context(notebook_IR, 1)
        prompt = build_user_prompt(context)

        self.assertIn("Cell 0", prompt)
        self.assertIn("x = 1", prompt)
        self.assertIn("Cell 1", prompt)
        self.assertIn("y = x + 1", prompt)
        self.assertIn("Cell 1 depends on: Cell 0", prompt)

    def test_no_dependencies_says_so(self):
        notebook_IR = {0: IntermediateRepresentations("x = 1", 0)}
        context = build_subgraph_context(notebook_IR, 0)
        prompt = build_user_prompt(context)
        self.assertIn("no cross-cell dependencies detected", prompt)

    def test_system_prompt_documents_findings_schema(self):
        self.assertIn('"findings"', SYSTEM_PROMPT)
        self.assertIn("severity", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
