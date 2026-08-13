import unittest

from nbfix.analyses.runner.analysis_results import ErrorInfo
from nbfix.ir.intermediate_representations import IntermediateRepresentations
from nbfix.llm.context_builder import build_subgraph_context
from nbfix.llm.prompts import SYSTEM_PROMPT, build_user_prompt


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

    def test_include_dependency_graph_false_omits_section(self):
        notebook_IR = {
            0: IntermediateRepresentations("x = 1", 0),
            1: IntermediateRepresentations("y = x + 1", 1),
        }
        context = build_subgraph_context(notebook_IR, 1)
        prompt = build_user_prompt(context, include_dependency_graph=False)
        self.assertNotIn("## Dependency graph", prompt)
        self.assertNotIn("depends on", prompt)

    def test_include_dependency_graph_true_is_default(self):
        notebook_IR = {0: IntermediateRepresentations("x = 1", 0)}
        context = build_subgraph_context(notebook_IR, 0)
        prompt = build_user_prompt(context)
        self.assertIn("## Dependency graph", prompt)

    def test_deterministic_findings_render_when_present(self):
        notebook_IR = {0: IntermediateRepresentations("x = 1", 0)}
        context = build_subgraph_context(notebook_IR, 0)
        context.deterministic_findings = [ErrorInfo(0, 1, "x", "TERMINAL", "idle cell")]
        prompt = build_user_prompt(context)
        self.assertIn("## Static analysis findings", prompt)
        self.assertIn("idle cell", prompt)

    def test_no_findings_section_when_empty(self):
        notebook_IR = {0: IntermediateRepresentations("x = 1", 0)}
        context = build_subgraph_context(notebook_IR, 0)
        prompt = build_user_prompt(context)
        self.assertNotIn("## Static analysis findings", prompt)


if __name__ == "__main__":
    unittest.main()
