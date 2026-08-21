import unittest

from nbcore.parser.ast_transformer import build_ast
from nbcore.parser.def_use import AssignsVisitor, DefUseChains
from nbcore.parser.lark_parser import parse_to_tree


def analyze(src):
    mod = build_ast(parse_to_tree(src))
    duc = DefUseChains().visit(mod)
    av = AssignsVisitor(duc)
    av.visit(mod)
    av.combine()
    return duc, av


class TestDefUse(unittest.TestCase):
    def test_unbound_names_and_funcs_and_imports(self):
        duc, av = analyze(
            "import pandas as pd\n"
            "from sklearn.model_selection import train_test_split\n"
            "df = pd.read_csv(unbound_path)\n"
            "X_train, X_test = train_test_split(df, y)\n"
            "print(X_train)\n"
            "z = w + 1\n"
        )
        # 'print' is a builtin, so unlike a real external dependency it's
        # never in unbound_names at all (matches beniget resolving builtins).
        self.assertEqual(duc.unbound_names, {"unbound_path", "y", "w"})
        self.assertEqual(av.funcs, {"train_test_split", "print"})
        self.assertEqual(av.imports, {"pd", "train_test_split"})
        self.assertEqual(av.defined_vars, {"df": 3, "X_train": 4, "X_test": 4, "z": 6})
        self.assertEqual(av.unbound_final, {"unbound_path", "w", "y"})

    def test_names_bound_inside_nested_blocks_are_not_unbound(self):
        duc, _ = analyze("if flag:\n    local = 1\nelse:\n    local = 2\nprint(local)\n")
        self.assertIn("flag", duc.unbound_names)
        self.assertNotIn("local", duc.unbound_names)

    def test_assign_nested_in_if_is_still_recorded(self):
        # AssignsVisitor must recurse into compound-statement bodies.
        _, av = analyze("if flag:\n    x = 1\n")
        self.assertEqual(av.defined_vars, {"x": 2})

    def test_function_params_are_bound_not_unbound(self):
        duc, _ = analyze("def f(a, b=1, *args, **kwargs):\n    return a + b + len(args)\n")
        self.assertEqual(duc.unbound_names, set())  # 'len' is a builtin

    def test_attribute_and_subscript_targets_record_base_name(self):
        _, av = analyze("x.y = 1\nz[0] = 2\n")
        self.assertEqual(av.defined_vars, {"x": 1, "z": 2})

    def test_comprehension_loop_variable_is_bound_not_unbound(self):
        # DefUseChains/AssignsVisitor walk the AST generically via _fields,
        # with no node-type allowlist - a comprehension's Store-context
        # target should be picked up as bound with zero special-casing
        # needed in def_use.py itself.
        duc, _ = analyze("y = [x * x for x in z]\n")
        self.assertIn("z", duc.unbound_names)
        self.assertNotIn("x", duc.unbound_names)


if __name__ == "__main__":
    unittest.main()
