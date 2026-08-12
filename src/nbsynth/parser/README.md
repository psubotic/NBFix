# NBSynth's own parser + IR

Replaces the analyzer's previous external dependencies -- `gast`/stdlib
`ast` (parsing), `beniget` (def-use chains), and `externals/simple_cfg`
(CFG construction) -- with a self-contained pipeline built on
[Lark](https://github.com/lark-parser/lark).

## Pipeline

```
source text
  -> lark_parser.py      (grammar/notebook_python.lark + Indenter postlex)
  -> ast_transformer.py  -> ast_nodes.py        (our own AST, P0 constructs)
  -> cfg_builder.py       -> cfg_nodes.py        (graph CFG, same node
                                                   shapes analyses already
                                                   expect: Node/
                                                   AssignmentNode/CondNode/
                                                   BBorBInode/...)
  -> def_use.py                                  (unbound-names + per-cell
                                                   assign/import/func
                                                   bookkeeping)
```

`IR/intermediate_representations.py` wires these into the same
`.AST`/`.CFG`/`.UDA` surface the four analyses (dataleak / stale / idle /
isolated) already consume, so none of their own logic needed to change --
only their imports moved from `simple_cfg`/`ast`/`gast` to this package.

## Implemented (grammar tiers P0, most of P1)

Assignments (plain/chained/tuple-unpack/augmented/annotated), attribute and
subscript access (including slicing), calls (positional/keyword/`*args`/
`**kwargs`), all binary/boolean/comparison/unary operators, `if`/`elif`/
`else`, `while`/`for` (with `else`), `try`/`except`/`else`/`finally`,
`with`, `import`/`from...import` (including relative), function and class
definitions (including decorators), `return`/`raise`/`break`/`continue`/
`pass`/`global`, list/tuple/dict literals, f-strings (see gap below).

## Same-cell function-call inlining: reduced scope, TODO to broaden

Implemented for a **reduced case only** (`CFGBuilder._inline_call` /
`_check_inline_eligible` in `cfg_builder.py`): a call to a locally-defined
function is inlined -- spliced into the caller's CFG with its parameters
and locals renamed uniquely per call site so they can't collide with the
caller's variables or with another call to the same function -- only when
*all* of the following hold:

- the function has plain positional parameters only: no defaults, no
  `*args`/`**kwargs`, no keyword-only params;
- the call passes plain positional arguments only, matching the parameter
  count exactly: no keywords, no `*`/`**` unpacking at the call site;
- the function's body contains no call to another locally-defined function
  (this is what rules out both recursion and nested inlining -- a body
  that calls itself, directly or via another local helper, is rejected);
- the result, if used, comes from a single `return <expr>` that is the
  function's very last statement (no early/multiple returns); if the
  result is discarded (a bare `f(...)` statement) the function may have no
  `return` at all.
- the call's result isn't tuple/multi-target-unpacked (`a, b = f(...)`).

**Any cell that calls a locally-defined function outside this envelope
fails to build its IR at all** -- `_check_inline_eligible` raises
`NotImplementedError` naming exactly which condition failed, the same
"reject loudly, don't silently mis-analyze" policy used everywhere else in
this package. **Broadening this (defaults/kwargs/`*args`/`**kwargs`,
multiple/early returns, nested calls to other local functions, recursion)
is a tracked TODO, not considered done.** Every call that doesn't resolve
to a locally-defined function at all (the overwhelming majority of
notebook code -- pandas/numpy/sklearn calls) is unaffected and still
treated as black-box (`BBorBInode`), as before.

## Deferred (tracked, not dropped)

- Comprehensions (list/set/dict/generator), `lambda`, ternary
  `x if y else z`, the walrus operator (`:=`), `async`/`await`, `del`/
  `assert`/`nonlocal`, dict/set unpacking (`**`/`*` inside a `{...}`
  literal), PEP 570 positional-only params (`/` marker), `match`
  statements. Hitting any of these raises `NotImplementedError` naming the
  construct (`ast_transformer.py`'s `__default__`), not a silent misparse.
- **f-strings are opaque literals**: `f"{x}"` round-trips as the literal
  text `"{x}"` -- the interpolated expression is not parsed, so a name used
  only inside an f-string won't be picked up by def-use analysis. The old
  pipeline did walk into these (gast's `JoinedStr`/`FormattedValue`).
- The `MUTATORS` rewrite (`lst.append(x)` treated like `lst += lst.append(x)`
  so mutation propagates taint onto the receiver) isn't implemented.
- Decorator call-arguments aren't preserved (the decorator name/attribute
  chain is; e.g. `@app.route("/x")`'s `"/x"` argument is dropped) since
  decorators aren't consumed by the CFG builder yet.

## Known simplifications (not gaps, but worth knowing about)

- `def_use.py`'s `DefUseChains` is **scope-insensitive**: a name is "bound"
  if it's assigned/imported/parameterized *anywhere* in the cell's AST,
  regardless of nested function/class scope. Real closures and
  shadowing-between-scopes aren't modeled. This only diverges from correct
  behavior for cells with non-trivial nested-scope shadowing, which is rare
  in notebook code.
- `try`/`except` control flow connects the `TryNode` itself to each
  handler (approximating "the body might raise") rather than simple_cfg's
  finer "any statement in the body can raise" edges. An
  under-approximation, not an over-approximation.
- Tuple-unpacking a call's return value (`a, b = f(...)`) creates one
  black-box-call node *per target*, matching simple_cfg's own (somewhat
  redundant) behavior for that pattern rather than a single shared call
  node.

## Tests

`framework/tests/test_parser_ast.py`, `test_cfg_builder.py`,
`test_cfg_inlining.py`, `test_def_use.py` exercise this package directly.
The full framework suite
(`framework/tests/test_*.py`) exercises it end-to-end through the four
analyses and passes in full -- see git history for the baseline comparison
against the old gast/beniget/simple_cfg pipeline.
