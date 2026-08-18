import unittest

from nbfix.analyses.type_shape_analysis import (
    _compute_type_tags,
    build_pruned_dependency_edges,
    detect_type_changes,
    label_stable_dependencies,
)
from nbfix.ir.intermediate_representations import IntermediateRepresentations


def make_notebook(cells: dict[int, str]) -> dict:
    return {
        cell_id: IntermediateRepresentations(code, cell_id)
        for cell_id, code in cells.items()
    }


class TestComputeTypeTags(unittest.TestCase):
    def test_resolves_a_name_to_name_chain_regardless_of_cell_order(self):
        """
        The actual bug this whole rewrite exists to fix: `_infer_tag`'s
        ast.Name lookup for `a = b` needs b's tag - the old single
        ID-ordered pass could only resolve that if b's own defining cell
        happened to come earlier in the notebook's text. Here the chain
        is authored *backwards* (c, the ultimate source, is cell 2; a,
        the far end of the chain, is cell 0) - a real fixpoint has to
        iterate to resolve it, a single pass can't.
        """
        notebook_IR = make_notebook({0: "a = b", 1: "b = c", 2: "c = [1, 2, 3]"})
        tags = _compute_type_tags(notebook_IR)
        self.assertEqual(tags["a"], [(0, "list")])
        self.assertEqual(tags["b"], [(1, "list")])
        self.assertEqual(tags["c"], [(2, "list")])

    def test_a_true_reference_cycle_stays_unclassified(self):
        notebook_IR = make_notebook({0: "a = b", 1: "b = a"})
        tags = _compute_type_tags(notebook_IR)
        self.assertEqual(tags["a"], [(0, None)])
        self.assertEqual(tags["b"], [(1, None)])


class TestDetectTypeChanges(unittest.TestCase):
    def test_flags_a_type_change(self):
        """
        Order-independent: both definer sites get flagged (no more
        privileged "before"/"after" direction - see detect_type_changes's
        docstring), one finding anchored at each.
        """
        notebook_IR = make_notebook({0: "data = [1, 2, 3]", 1: "data = len(data)"})
        result = detect_type_changes(notebook_IR)
        self.assertEqual(len(result.path_results), 2)
        flagged_cells = {pr.error_infos[0].cell_id for pr in result.path_results}
        self.assertEqual(flagged_cells, {0, 1})
        self.assertTrue(all(pr.error_infos[0].error_type == "TYPE_CHANGE" for pr in result.path_results))

    def test_no_finding_when_type_never_changes(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1"})
        result = detect_type_changes(notebook_IR)
        self.assertEqual(result.path_results, [])


class TestBuildPrunedDependencyEdges(unittest.TestCase):
    def test_prunes_a_forward_type_stable_chain(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1", 2: "z = y + 1"})
        edges = build_pruned_dependency_edges(notebook_IR)
        self.assertEqual(edges, {0: set(), 1: set(), 2: set()})

    def test_keeps_an_edge_whose_type_changes(self):
        notebook_IR = make_notebook({
            0: "data = [1, 2, 3]",
            1: "data = len(data)",
            2: "data.append(4)",
        })
        edges = build_pruned_dependency_edges(notebook_IR)
        self.assertEqual(edges[2], {0, 1})

    def test_never_prunes_a_backward_read_before_defined_edge(self):
        """
        The specific conflict found while wiring this to
        build_fixpoint_dependency_edges: a name can be perfectly
        type-stable (e.g. always a plain list, never reassigned) and
        still be the read-before-defined edge that makes an
        order_dependent bug - type stability says nothing about whether
        the definition has even happened yet. A backward edge (definer
        cell ID greater than the reader's) must survive pruning
        regardless of what the type-stability walk concludes.
        """
        notebook_IR = make_notebook({0: "y = x + 1", 1: "x = 1"})
        edges = build_pruned_dependency_edges(notebook_IR)
        self.assertEqual(edges[0], {1})


class TestLabelStableDependencies(unittest.TestCase):
    def test_labels_a_type_stable_forward_edge(self):
        notebook_IR = make_notebook({0: "x = 1", 1: "y = x + 1"})
        result = label_stable_dependencies(notebook_IR)
        self.assertEqual(len(result.path_results), 1)
        self.assertEqual(result.path_results[0].error_infos[0].error_type, "STABLE_DEPENDENCY")

    def test_does_not_label_an_edge_whose_type_changes(self):
        notebook_IR = make_notebook({
            0: "data = [1, 2, 3]",
            1: "data = len(data)",
            2: "data.append(4)",
        })
        result = label_stable_dependencies(notebook_IR)
        labeled_names = {e.label for pr in result.path_results for e in pr.error_infos}
        self.assertNotIn("data", labeled_names)

    def test_never_labels_a_backward_read_before_defined_edge_as_stable(self):
        notebook_IR = make_notebook({0: "y = x + 1", 1: "x = 1"})
        result = label_stable_dependencies(notebook_IR)
        self.assertEqual(result.path_results, [])


if __name__ == "__main__":
    unittest.main()
