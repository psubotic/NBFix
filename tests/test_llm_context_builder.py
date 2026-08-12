import unittest

from nbsynth.ir.intermediate_representations import IntermediateRepresentations
from nbsynth.llm.context_builder import (
    build_cell_context,
    build_dependency_edges,
    build_full_notebook_context,
    build_subgraph_context,
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

    def test_redefinition_updates_last_definer(self):
        notebook_IR = make_notebook(
            {0: "x = 1", 1: "x = 2", 2: "y = x + 1"}
        )
        edges = build_dependency_edges(notebook_IR)
        # cell 2 uses x, which was last (re)defined in cell 1, not cell 0.
        self.assertEqual(edges[2], {1})


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


if __name__ == "__main__":
    unittest.main()
