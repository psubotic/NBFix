import unittest

from nbfix.analyses.runner.analysis_results import ErrorInfo, PathResult, Result
from nbfix.ir.intermediate_representations import IntermediateRepresentations
from nbfix.llm.context_builder import (
    build_cell_context,
    build_dependency_edges,
    build_full_notebook_context,
    build_subgraph_context,
    collect_deterministic_findings,
)


def make_notebook(cells: dict[int, str]) -> dict:
    return {
        cell_id: IntermediateRepresentations(code, cell_id)
        for cell_id, code in cells.items()
    }


class TestBuildDependencyEdges(unittest.TestCase):
    def test_no_dependencies(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "z = 2"})
        edges = build_dependency_edges(notebook_IR)
        self.assertEqual(edges, {0: set(), 1: set()})

    def test_direct_dependency(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1"})
        edges = build_dependency_edges(notebook_IR)
        self.assertEqual(edges, {0: set(), 1: {0}})

    def test_multi_hop_chain(self):
        notebook_IR = make_notebook(
            {0: "x = 1", 1: "y = x + 1", 2: "z = y + 1"}
        )
        edges = build_dependency_edges(notebook_IR)
        self.assertEqual(edges, {0: set(), 1: {0}, 2: {1}})

    def test_redefinition_keeps_every_possible_definer(self):
        """
        build_dependency_edges is order-independent (see
        analyses/dependency_analysis.py's docstring) - it doesn't assume
        a single canonical "last definer in ID order" the way the old,
        now-removed single-pass implementation did. Both cell 0 and cell
        1 are legitimate candidate sources for the x cell 2 reads,
        depending on which execution order actually ran: a real user
        could run cell 0 then cell 2 without ever running cell 1.
        """
        notebook_IR = make_notebook(
            {0: "x = 1", 1: "x = 2", 2: "y = x + 1"}
        )
        edges = build_dependency_edges(notebook_IR)
        self.assertEqual(edges[2], {0, 1})

    def test_finds_a_backward_edge_the_old_id_ordered_pass_could_not(self):
        notebook_IR = make_notebook({0: "y = x + 1", 1: "x = 1"})
        edges = build_dependency_edges(notebook_IR)
        self.assertEqual(edges[0], {1})


class TestBuildCellContext(unittest.TestCase):
    def test_includes_only_target_cell_code(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1"})
        ctx = build_cell_context(notebook_IR, 1)
        self.assertEqual(ctx.target_cell_ids, [1])
        self.assertEqual(len(ctx.cells), 1)
        self.assertEqual(ctx.cells[0].cell_id, 1)
        self.assertEqual(ctx.cells[0].code, "y = x + 1")
        self.assertEqual(ctx.dependency_edges, {1: {0}})


class TestBuildSubgraphContext(unittest.TestCase):
    def test_transitive_closure_both_directions(self):
        notebook_IR = make_notebook(
            {
                0: "x = 1",
                1: "y = x + 1",
                2: "z = y + 1",
                3: "unrelated = 99",
            }
        )
        ctx = build_subgraph_context(notebook_IR, 1)
        included_ids = {c.cell_id for c in ctx.cells}
        # cell 1 depends on cell 0, and cell 2 depends on cell 1 - both
        # should be pulled in even though only cell 1 was requested.
        self.assertEqual(included_ids, {0, 1, 2})
        self.assertNotIn(3, included_ids)

    def test_isolated_cell_returns_only_itself(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "unrelated = 2"})
        ctx = build_subgraph_context(notebook_IR, 1)
        self.assertEqual({c.cell_id for c in ctx.cells}, {1})


class TestBuildFullNotebookContext(unittest.TestCase):
    def test_includes_all_cells(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1", 2: "z = 3"})
        ctx = build_full_notebook_context(notebook_IR)
        self.assertEqual({c.cell_id for c in ctx.cells}, {0, 1, 2})
        self.assertEqual(ctx.target_cell_ids, [0, 1, 2])
        self.assertEqual(ctx.dependency_edges, {0: set(), 1: {0}, 2: set()})


class TestCollectDeterministicFindings(unittest.TestCase):
    def test_flattens_requested_analysis_types(self):
        finding = ErrorInfo(1, 1, "x", "TERMINAL", "idle")
        results = {"Idle Cells Analysis": Result()}
        results["Idle Cells Analysis"].add_path_result(PathResult([1], [finding]))

        found = collect_deterministic_findings(results, {"Idle Cells Analysis"})
        self.assertEqual(found, [finding])

    def test_ignores_analysis_types_not_requested(self):
        finding = ErrorInfo(1, 1, "x", "TERMINAL", "idle")
        results = {"Idle Cells Analysis": Result()}
        results["Idle Cells Analysis"].add_path_result(PathResult([1], [finding]))

        found = collect_deterministic_findings(results, {"Stale Cells Analysis"})
        self.assertEqual(found, [])

    def test_missing_analysis_in_results_is_skipped_not_an_error(self):
        found = collect_deterministic_findings({}, {"Idle Cells Analysis"})
        self.assertEqual(found, [])

    def test_no_finding_types_returns_empty(self):
        results = {"Idle Cells Analysis": Result()}
        self.assertEqual(collect_deterministic_findings(results, None), [])


class TestDeterministicFindingsScoping(unittest.TestCase):
    def setUp(self):
        self.notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1", 2: "z = 99"})
        self.finding_0 = ErrorInfo(0, 1, "x", "TERMINAL", "idle at 0")
        self.finding_2 = ErrorInfo(2, 1, "z", "TERMINAL", "idle at 2")
        self.all_findings = [self.finding_0, self.finding_2]

    def test_cell_context_filters_to_target_cell_only(self):
        ctx = build_cell_context(self.notebook_IR, 0, deterministic_findings=self.all_findings)
        self.assertEqual(ctx.deterministic_findings, [self.finding_0])

    def test_subgraph_context_filters_to_component(self):
        # cell 2 is unrelated to cells 0/1's component.
        ctx = build_subgraph_context(self.notebook_IR, 1, deterministic_findings=self.all_findings)
        self.assertEqual(ctx.deterministic_findings, [self.finding_0])

    def test_full_notebook_context_includes_all(self):
        ctx = build_full_notebook_context(self.notebook_IR, deterministic_findings=self.all_findings)
        self.assertEqual(ctx.deterministic_findings, self.all_findings)

    def test_default_is_empty_list_not_none(self):
        ctx = build_cell_context(self.notebook_IR, 0)
        self.assertEqual(ctx.deterministic_findings, [])


if __name__ == "__main__":
    unittest.main()
