"""
Replacement for beniget.DefUseChains + IR/visitors/assigns_visitor.py's
AssignsVisitor, ported onto our own AST.

Phase-1 simplification: `DefUseChains` is *scope-insensitive* -- a name
counts as "bound" if it is assigned/imported/defined/parameterized anywhere
in the cell's AST, regardless of which function/class scope that happens in.
Real Python scoping (closures, shadowing between a module-level name and an
unrelated local in a nested function) is not modeled. This only matters for
cells with non-trivial nested-scope shadowing, which is rare in notebook
code; see parser/README.md. What actually gets consumed downstream is
`unbound_names` -- identifiers used in this cell that resolve to *neither* a
binding in this cell nor a Python builtin conceptually "elsewhere" (a
previous cell, an import) -- and this flat approximation is a safe fit for
that purpose in the common case.
"""

import builtins as _builtins_module

from . import ast_nodes as n

# beniget resolves names against Python's builtins scope, so e.g. `print` in
# `print(x)` is never "unbound" even though it's never assigned in the cell.
# Mirror that here rather than relying solely on the funcs-subtraction that
# downstream analyses apply to `unbound_final` -- IsolatedCellAnalysis and
# IdleCellAnalysis read `unbound_names` directly, with no such subtraction.
_BUILTIN_NAMES = frozenset(dir(_builtins_module))


class DefUseChains:
    def __init__(self):
        self.unbound_names = set()

    def visit(self, module):
        bound, used = set(), set()
        for node in n.walk(module):
            if isinstance(node, n.Name):
                if isinstance(node.ctx, n.Store):
                    bound.add(node.id)
                elif isinstance(node.ctx, n.Load):
                    used.add(node.id)
            elif isinstance(node, n.FunctionDef):
                bound.add(node.name)
                for a in (*node.args.args, *node.args.kwonlyargs):
                    bound.add(a.arg)
                if node.args.vararg:
                    bound.add(node.args.vararg.arg)
                if node.args.kwarg:
                    bound.add(node.args.kwarg.arg)
            elif isinstance(node, n.ClassDef):
                bound.add(node.name)
            elif isinstance(node, (n.Import, n.ImportFrom)):
                for alias in node.names:
                    if alias.name != "*":
                        bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, n.ExceptHandler):
                if node.name:
                    bound.add(node.name)
        self.unbound_names = used - bound - _BUILTIN_NAMES
        return self


def _call_func_name(value):
    if isinstance(value, n.Call) and isinstance(value.func, n.Name):
        return value.func.id
    return None


class AssignsVisitor(n.NodeVisitor):
    """Ported 1:1 from the original's behavior: it's a NodeVisitor whose
    visit_Import/visit_ImportFrom/visit_Expr/visit_Assign methods don't call
    generic_visit, so they don't descend into their own children, but every
    *other* node type (If/For/While/Try/FunctionDef/...) falls through to
    generic_visit and keeps recursing -- so nested Assigns inside a branch
    or loop are still picked up, only the four handled statement types stop
    the descent at themselves."""

    def __init__(self, def_use_chains):
        self.def_use_chains = def_use_chains
        self.funcs = set()
        self.imports = set()
        self.defined_vars = {}

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.imports.add(alias.asname or alias.name)

    def visit_Expr(self, node):
        fn = _call_func_name(node.value)
        if fn:
            self.funcs.add(fn)

    def visit_Assign(self, node):
        value = node.value
        if isinstance(value, n.BinOp):
            for fn in (_call_func_name(value.left), _call_func_name(value.right)):
                if fn:
                    self.funcs.add(fn)
        else:
            fn = _call_func_name(value)
            if fn:
                self.funcs.add(fn)
        for target in node.targets:
            self._record_target(target, node.lineno)

    def _record_target(self, target, lineno):
        if isinstance(target, n.Name) and isinstance(target.ctx, n.Store):
            self.defined_vars[target.id] = lineno
        elif isinstance(target, (n.List, n.Tuple)):
            for element in target.elts:
                for sub in n.walk(element):
                    if isinstance(sub, n.Name) and isinstance(sub.ctx, n.Store):
                        self.defined_vars[sub.id] = lineno
        elif isinstance(target, (n.Subscript, n.Attribute)):
            base = target.value
            if isinstance(base, n.Name):
                self.defined_vars[base.id] = lineno
            else:
                for sub in n.walk(base):
                    if isinstance(sub, n.Name):
                        self.defined_vars[sub.id] = lineno

    def combine(self):
        self.unbound_final = self.def_use_chains.unbound_names - (self.funcs | self.imports)
