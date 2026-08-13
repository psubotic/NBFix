# LLM detection/repair benchmark fixtures

Hand-written notebooks used to measure whether feeding an LLM NBFix's own
structural context (dependency graph, deterministic-analysis findings)
actually improves bug detection and repair - the research question behind
`src/nbfix/llm/`. See `src/nbfix/llm/README.md` for how these get used.

## Ground truth: objective, not opinion

Every buggy fixture's ground truth is **a specific exception (type + cell +
line) that actually occurs when the notebook is executed top to bottom** -
not a description of what the fixture author thinks is "wrong" about the
code. A fixture like "this loop silently processes one fewer item than
intended" has no property in the code itself that's checkable; only a
fixture that actually crashes (or an embedded assertion that actually
fails) gives an objective fact to score against.

Every fixture here was authored and validated by `_author_fixtures.py`,
which `exec()`s each cell in order in a fresh namespace and records the
*actual* observed outcome - the real exception type/message/cell/line for
buggy fixtures, confirmation of a clean run for clean ones - into the
matching `.expected.json` sidecar. Nothing in `.expected.json` is asserted
by hand; it's captured from a real run. Re-running
`python tests/resources/llm_bench/_author_fixtures.py` regenerates and
re-validates every fixture from the same cell definitions.

`.expected.json` shape (same as `tests/resources/rtests/*.out`):
```json
[{"cell_id": 2, "path": [0, 1, 2],
  "errors": [{"line": 1, "label": "AttributeError",
              "error_type": "RUNTIME_ERROR",
              "message": "'int' object has no attribute 'append'"}]}]
```
Clean fixtures get an explicit empty `[]`, not an absent file - so a
hallucinated finding on a clean notebook is scored as a false positive
rather than silently unscored.

## Taxonomy

Four classes, chosen because none of NBFix's four deterministic analyses
(Stale/Idle/Isolated/Data-leak) would catch them - this is deliberately the
class of bug `src/nbfix/llm/README.md` frames the LLM path as targeting.

### `cross_cell_semantic`

A variable's type/shape changes across a def-use edge in a way that breaks
a downstream cell - e.g. a list gets reassigned to a scalar summary, and a
later cell still calls a list method on it. The bug is invisible reading
either cell alone; you need both. 3 examples: list→int (`.append` on an
int), dict→list (subscript-by-string on a list), list→int again via a
different aggregation (`sum`) and a different downstream operation
(`__getitem__`).

### `order_dependent`

Only correct if cells execute in an order other than their textual/saved
position - a very common real Jupyter footgun (define a loop while
drafting, backfill setup cells above it, never reorder them on disk).
Distinct from STALE: STALE needs live run-history (`last_ran_code` vs
current) and produces zero findings on a freshly-loaded static file
(confirmed empirically earlier in this project); this bug is visible from
the saved file alone via position + the dependency graph, no execution
history required. 3 examples: a loop, a function call, and a comprehension,
each referencing a name only defined in a later cell.

### `api_misuse`

Wrong argument to a well-known library call, fully contained in one cell -
deliberately the **control class**. Since it's single-cell, feeding the
dependency graph or cross-cell findings should measurably *not* help
detect it; this is what makes the eventual with/without-context comparison
falsifiable rather than "more context can only help." 3 examples, all
verified against the real library's actual behavior rather than assumed:
`numpy.reshape` with a mismatched element count, `numpy.zeros` with a
negative dimension, `open()` with an invalid mode string.

### `cross_cell_logic`

An off-by-one/boundary bug where the wrong bound was computed in a
*different* cell than where it causes a crash. Reading the crashing cell
alone looks completely ordinary; the bug is entirely in how a bound was
computed elsewhere. 3 examples, deliberately different manifestations: a
direct off-by-one index, a pop-count that exceeds a stack's size, and a
loop bound that outlives a collection that was collapsed to a smaller size
in an earlier cell.

## Fixture set

3 buggy + 1 clean notebook per class = 16 total, one seeded bug per buggy
notebook. Clean notebooks are structurally similar to their class but
exist specifically to measure false-positive rate per context mode -
without them, a detector that flags everything would look perfect on
recall alone.

**Cell count**: ~13-15 cells per notebook (avg 13.69), not the 1-3 cells
the first version had. That first version was a real design mistake, not
just small-sample noise: the whole point of feeding an LLM a dependency
graph is to save it from cross-cell reasoning it can't hold in its head -
in a 2-3 cell notebook, every cell is already visible in the prompt
regardless of context mode, so the graph has nothing to add and a
none-vs-deps comparison can't show a real effect either way. The 1-2
actual bug cells in each fixture are now padded with `DISTRACTOR_CELLS`
(`_author_fixtures.py`) - plausible, deliberately inert filler cells
placed before and after the bug, verified (same exec()-based validation as
the bug cells themselves) to never interact with or mask it. This makes
each fixture a realistically-sized notebook the bug is embedded in, not
the whole notebook.
