# LLM detection experiments: does structural context help?

Preliminary experiment log for the question behind `src/nbfix/llm/`: does
feeding an LLM NBFix's own dependency graph make it detect bugs better
(accuracy, latency, cost) than raw code alone? Covers the full run from
taxonomy design through 5 notebook-size tiers and 3 dependency-density
tiers. Numbers below are real, not illustrative - see
`benchmark_results/llm_bench/*.csv` for the raw per-run data and
`charts/` for the plots.

## Methodology

**Taxonomy** (`tests/resources/llm_bench/README.md`): 4 bug classes, each
chosen because none of NBFix's four deterministic analyses (Stale/Idle/
Isolated/Data-leak) would catch it - `cross_cell_semantic` (a variable's
type/shape changes across cells), `order_dependent` (only correct if run
in a different order than written), `cross_cell_logic` (an off-by-one
computed in a different cell than where it crashes), and `api_misuse`
(wrong library argument, single-cell - the deliberate **control class**,
where context should measurably *not* help).

**Ground truth is execution-verified, not asserted.** Early design review
caught that "this looks wrong" isn't a checkable property of code. Every
buggy fixture instead raises a specific, real exception (type + cell +
line), captured by actually `exec()`ing the fixture and recording what
happened - not what the author intended. See
`tests/resources/llm_bench/_author_fixtures.py`.

**5 size tiers**, 3 buggy examples per class per tier (12 fixtures/tier,
60 total), all sharing the same underlying bug definitions padded with
verified-inert distractor cells so "the same bug" is comparable across
sizes:

| tier   | cells | rationale |
|--------|-------|-----------|
| micro  | ~2.25 | bare bug cells, zero padding - the original design |
| mini   | ~13.7 | first "realistic" size; also the only tier with a clean (false-positive baseline) fixture per class |
| medium | 30    | |
| large  | 50    | |
| xlarge | 100   | closer to a real analysis notebook |

**Models**: `qwen2.5-coder` at 1.5b / 7b / 14b, run locally via Ollama -
chosen to see whether model *size* changes the answer, not just notebook
size.

**Context modes compared**: `none` (raw code only) vs `deps` (code + the
dependency graph NBFix's static analysis derives - "Cell X depends on
Cell Y").

**3 dependency-density tiers**, added after the size tiers revealed cell
count and dependency complexity aren't the same axis (see Finding 5
below): `dep2` / `dep10` / `dep20`, cell count held fixed at 30 (matching
`medium`) while a `build_dependency_chain` block (verified, real
read-dependency chain, not independent filler) pushes the actual
dependency-edge count - as measured by NBFix's own
`build_dependency_edges` - to ~2/10/20. Same 12 buggy fixtures per tier,
same 4 classes, same ground-truth methodology as the size tiers.

## Headline results (averaged across all 4 classes per tier)

| tier | model | ctx | F1 | latency (s) | tokens |
|---|---|---|---|---|---|
| micro | qwen14b | none/deps | .72 / .75 | 6.87 / 6.21 | 493 / 501 |
| mini | qwen14b | none/deps | .33 / .67 | 5.83 / 6.09 | 798 / 829 |
| medium | qwen14b | none/deps | .27 / .50 | 17.46 / 6.52 | 1323 / 1284 |
| large | qwen14b | none/deps | .46 / .67 | 10.85 / 6.36 | 1806 / 1811 |
| xlarge | qwen14b | none/deps | .42 / .53 | 16.50 / 8.72 | 3050 / 3063 |

(Full table for all 3 models × 5 tiers in `raw_cross_tier_summary.csv`
alongside this file; per-class breakdowns in the individual `*.csv` files
and `charts/*.png`.)

### 1. The biggest model benefits from `deps` on every single tier tested

qwen14b's F1 is higher with `deps` than `none` in **all 5 tiers**,
without exception - the most consistent result across everything tested.
The control class (`api_misuse`) correctly shows little to no difference
in every tier, which is the sanity check that makes the other classes'
results trustworthy rather than an artifact of the scoring itself.

### 2. Latency: `deps` gets increasingly faster than `none` as notebooks grow, for the two more capable models

qwen7b and qwen14b both show `deps` latency pulling further ahead of
`none` as cell count increases (qwen14b's gap: ~0.7s at micro → ~11s at
medium → ~8s at xlarge). Token counts move the same direction - `none`
tends to produce more output tokens, consistent with the model spending
extra tokens re-deriving cross-cell structure it wasn't handed directly.
This is the cleanest, least noisy result in the whole set - it's a token
count difference, not a strict pass/fail scoring judgment, so it's much
less sensitive to a single borderline case than the accuracy numbers are.

### 3. Smaller/weaker models don't show a reliable benefit

qwen1.5b's F1 hovers near zero in every tier regardless of context mode -
too weak to read a signal from at all. qwen7b is genuinely mixed (worse
with `deps` at mini/medium, better at micro/large/xlarge) rather than
showing a clean trend either way. Read together with (1), this suggests
using structural context well may need enough model capacity to act on
it, not just receive it - a plausible story, not yet a proven one at
n=3-per-class.

### 4. Cost scales with notebook size regardless of context mode, as expected

Token counts roughly track cell count (micro ~500 tokens → xlarge ~3000+)
in both context modes - `deps` isn't a free win on raw token cost, its
value is in the accuracy/latency numbers above, not in using dramatically
fewer tokens outright.

### 5. Cell count and dependency complexity turned out to be two different axes - and the second one is where the real signal is

Computing the actual dependency-edge count for the 5 size tiers (via
`build_dependency_edges`, not estimated) turned up something the size
tiers were never actually testing: **it stays flat at ~0.6 edges on
average regardless of cell count** - 2.25 cells or 100, doesn't matter.
`DISTRACTOR_CELLS` is deliberately self-contained (padding cells never
reference each other), so growing a fixture from micro to xlarge adds
*length*, not *dependency structure*. Worse: digging into why even the
core bug cells often show only 1 edge instead of the 2+ expected (e.g.
`cross_cell_semantic`'s `data = len(data)` reads the *previous* cell's
`data` before overwriting it, which should be a real edge) found a gap in
`def_use.py`'s `unbound_names` computation - it's a whole-cell
`used - bound` set difference with no tracking of *read-before-write*
order within a cell, so a name that's both read and reassigned in the
same cell silently cancels out of the dependency graph entirely. That's
a real gap in `context_builder.py`'s production dependency-graph code,
most visible on exactly the class (`cross_cell_semantic`) this whole
project is trying to help detect - not fixed here, flagged for later.

So a second experiment: `dep2`/`dep10`/`dep20` hold cells fixed at 30 and
vary *only* real dependency-edge count (2/10/20, verified). Averaged
across the 4 classes:

| tier | model | ctx | F1 | latency (s) |
|---|---|---|---|---|
| dep2  | qwen7b  | none/deps | .31 / .39 | 4.48 / 4.68 |
| dep10 | qwen7b  | none/deps | .36 / .47 | 4.22 / 3.22 |
| dep20 | qwen7b  | none/deps | .14 / .39 | 3.31 / 3.46 |
| dep2  | qwen14b | none/deps | .67 / .53 | 12.87 / 7.36 |
| dep10 | qwen14b | none/deps | .61 / .64 | 14.27 / 6.23 |
| dep20 | qwen14b | none/deps | .53 / .64 | 9.01 / 8.80 |

**qwen7b's `deps` advantage widens monotonically as dependency count
increases** - +.08 F1 at dep2, +.11 at dep10, +.25 at dep20. **qwen14b
shows the same monotonic trend even though it starts negative** - `deps`
is worse at dep2 (-.14), roughly even at dep10 (+.03), clearly better at
dep20 (+.11). Both models point the same direction: the more real
dependency structure a notebook has, the more `deps` context helps,
independent of how many cells it's spread across. This is the most
direct evidence yet for the conjecture that motivated this second
experiment - that structural context's value scales with actual
complexity, not with notebook length.

**Product implication**: if what an analysis needs varies by workload
and by analysis type (this project's original framing: NBFix's four
deterministic analyses already each target a different structural
property - staleness, idleness, isolation, leakage - so it would be
consistent for LLM-assisted detection to need different structural input
per bug class too), then the right design isn't "always include the
dependency graph" or "never include it" - it's **measuring the workload's
actual complexity and the analysis being asked for, then deciding what
structural information to hand the LLM.** Finding 6 below is about
whether that decision can be made cheaply enough to do live.

### 6. Computing the dependency graph itself costs microseconds, not milliseconds

Timed `build_dependency_edges` directly (high-resolution timer, 200
iterations per fixture to smooth out noise, all 100 fixtures across all 8
tiers - `dependency_compute_timing.csv`). Result: **0.0004ms at micro
(2.25 cells) to 0.0166ms at xlarge (100 cells)** - the whole range never
exceeds 17 microseconds. It scales with cell count, not edge count -
`dep2/dep10/dep20` (30 cells, 2/10/20 edges) all land at ~0.0045-0.0051ms,
indistinguishable from `medium` (30 cells, ~0.6 edges), which makes sense
given the algorithm is one linear pass over cells regardless of how many
edges it finds along the way.

Compared to a single LLM call (seconds, per every result table above),
this is roughly 5-6 orders of magnitude cheaper. Concretely: there's no
practical cost to computing the dependency graph *first*, inspecting its
complexity, and only then deciding whether/how much of it to hand the
model - the "measure, then decide" design in the product implication
above is essentially free to do on every request, not something that
would need to be cached or precomputed to stay fast.

**The return on that microsecond spend, in concrete terms**: pairing
finding 6's compute cost against finding 2's actual latency savings
(qwen14b, `deps` vs `none`, both real measurements) gives the ratio of
milliseconds of LLM latency saved per millisecond spent computing the
graph:

| tier | latency saved | compute cost | return |
|---|---|---|---|
| micro | 0.66s | 0.0004ms | ~1,500,000x |
| mini | -0.26s | 0.0021ms | **-123,000x (net loss)** |
| medium | 10.94s | 0.0045ms | ~2,430,000x |
| large | 4.49s | 0.0075ms | ~600,000x |
| xlarge | 7.78s | 0.0160ms | ~485,000x |
| dep2 | 5.51s | 0.0045ms | ~1,220,000x |
| dep10 | 8.04s | 0.0047ms | ~1,690,000x |
| dep20 | 0.21s | 0.0051ms | ~41,600x |

7 of 8 tiers return somewhere between 40,000x and 2.4 million x (median
~1.2 million x) - a microsecond spend buying back seconds of latency is
about as close to a free lunch as this kind of measurement gets. Worth
being honest about the one exception rather than only quoting the best
numbers: `mini`/qwen14b is a real net loss (`deps` was 0.26s *slower*
there), a reminder finding 2's latency benefit isn't universal even
though it's the dominant pattern - see finding 2's own caveats.

### 7. Adding real-but-irrelevant structural info makes every model slower, and one model consistently less accurate

Before building new fixtures for the "does wrong structure hurt"
question, checked how much of the existing fixture set is already a
natural version of that experiment: ran `IsolatedCellAnalysis` (the real
analysis, not a fabrication) against every size tier and found **85-98%
of cells in the mini-through-xlarge tiers register as isolated** -
because the padding/distractor cells are deliberately self-contained, so
they're genuinely isolated by that analysis's own definition. That's real
analysis output that's almost entirely about cells with nothing to do
with the seeded bug - a ready-made "irrelevant-but-true structure"
condition, no fabrication needed.

Added a third context config, `deps+isolated` (dependency graph *plus*
`IsolatedCellAnalysis`'s real findings), and ran it against `dep2`/`dep10`/
`dep20` alongside the existing `none`/`deps` results:

| tier | model | deps F1 | deps+isolated F1 | deps latency | deps+isolated latency |
|---|---|---|---|---|---|
| dep2  | qwen7b  | .39 | **.26** | 4.68s | **11.29s** |
| dep10 | qwen7b  | .47 | **.18** | 3.22s | **8.25s** |
| dep20 | qwen7b  | .39 | **.14** | 3.46s | **6.00s** |
| dep2  | qwen14b | .53 | .69 | 7.36s | **32.11s** |
| dep10 | qwen14b | .64 | **.39** | 6.23s | **28.21s** |
| dep20 | qwen14b | .64 | **.59** | 8.80s | **16.17s** |

Two results, one very clean and one clean-ish:

- **Latency: unanimous.** `deps+isolated` is slower than `deps` alone in
  every single one of these 9 (model, tier) combinations - not just
  slower, often 2-4x slower (qwen14b/dep2: 7.36s -> 32.11s; one individual
  run in that cell hit 76s). Dumping in dozens of true-but-irrelevant
  findings doesn't just fail to help, it visibly costs the model
  reasoning time it wasn't costing before.
- **Accuracy: consistent for one model, mixed for the other.** qwen7b's
  F1 drops with `deps+isolated` at all three dependency levels - the
  cleanest accuracy result in this whole section. qwen14b is mixed
  (better at dep2, worse at dep10 and dep20) - 2 of 3 worse, not as clean
  as qwen7b but pointing the same direction overall. qwen1.5b's numbers
  are too close to zero everywhere to read.

Put together with finding 5 (real, *relevant* dependency structure helps,
increasingly so as density grows): the picture isn't "more structure is
better" or "more structure is worse," it's that **relevance matters more
than volume** - the same "give it more real analysis output" move that
helped when the structure was actually about the bug (finding 5) instead
measurably hurt when it was mostly about unrelated cells (finding 7).
That's the concrete evidence behind the "you can't blindly dump all
structural info in, you have to be selective" thesis this session's
`finding_types` mechanism was built for but hadn't been benchmarked
until now.

### 8. A purpose-built heuristic, aimed exactly at the gap it was designed for, still made things worse

Finding 7 showed *generic* real structure (isolated-cell findings, not about
the bug at all) costs accuracy and latency. The natural next question:
what about structure built specifically to close a known gap? `deps` (the
dependency graph) tells the model a cell *reads* a name another cell
*defines* - nothing about whether a reassignment along the way changed
what that name *means*. That's exactly `cross_cell_semantic`'s bug shape
(`data = [1,2,3]` ... `data = len(data)` ... downstream `data.append(...)`
crashes), and it's also exactly the shape `def_use.py`'s `unbound_names`
computation is structurally blind to (confirmed directly: `data =
len(data)` produces `unbound_final: set()`, a same-cell read-before-write
that a plain set-difference silently cancels out).

Built `src/nbfix/analyses/type_shape_analysis.py`: a small heuristic pass
that tags each name's coarse type/shape (`list`, `dict`, `int`, `DataFrame`,
etc.) across cells and flags a `TYPE_CHANGE` finding whenever a reassignment
changes an already-known tag - deliberately conservative (both sides must
be a recognized, non-unknown tag to fire, so it never guesses on code it
can't classify). Validated in isolation first, against the bare
(unpadded) bug fixtures: exactly 1 correct finding per `cross_cell_semantic`
example, 0 findings everywhere else, including every clean fixture - a
clean, false-positive-free signal on its own. Wired it into the benchmark
as a fourth context config, `deps+types` (`deps` plus this tagger's
findings via `DetectBugsEvent`'s new `extra_findings` param), and re-ran
`dep2`/`dep10`/`dep20`, scoped to `cross_cell_semantic` and
`order_dependent` per this session's narrowed focus:

| tier | class | model | deps F1 | deps+types F1 | deps latency | deps+types latency |
|---|---|---|---|---|---|---|
| dep2  | cross_cell_semantic | qwen7b  | **.89** | .00 | 5.2s | 5.5s |
| dep2  | cross_cell_semantic | qwen14b | .78 | .61 | 10.6s | **19.0s** |
| dep10 | cross_cell_semantic | qwen7b  | .67 | .56 | 3.4s | 6.2s |
| dep10 | cross_cell_semantic | qwen14b | .67 | .67 | 5.6s | **16.0s** |
| dep20 | cross_cell_semantic | qwen7b  | .33 | .00 | 3.0s | 4.4s |
| dep20 | cross_cell_semantic | qwen14b | **1.00** | .44 | 8.8s | **15.2s** |
| dep10 | order_dependent | qwen14b | .67 | .00 | 6.5s | **14.1s** |
| dep20 | order_dependent | qwen14b | .33 | .44 | 6.0s | **31.6s** |

(qwen1.5b omitted - both configs are near-zero noise for it on these two
classes at every tier, nothing to read.)

**Accuracy: worse on average for the class it was built for.** Averaged
across the three tiers, qwen14b's `cross_cell_semantic` F1 drops from .82
(`deps`) to .57 (`deps+types`); qwen7b's drops from .63 to .19 - a sharper
fall than finding 7's *generic* irrelevant structure produced. This is the
opposite of the hypothesis: giving the model exactly the fact it seemed to
be missing made detection worse, not better.

**Root cause, confirmed by reading the raw model output, not guessed**:
the ground truth in these fixtures is anchored at the *crash site* (the
downstream cell where the exception actually fires, e.g. cell 5's
`.append()` on what's now an int) - by Phase 1's own design principle,
verified via real `exec()`. Under plain `deps`, qwen7b on `dep2`'s
`cross_cell_semantic/ex1.ipynb` correctly names cell 5 (`path: [4, 5]`,
"Data is overwritten... before being used in function calls or accessed by
other cells") - a hit. Under `deps+types`, the *same model on the same
notebook* instead reports **cell 4** (the reassignment site) - `"'data' is
redefined from type list to int, which will affect all dependent cells"` -
a diagnosis that is arguably *more* correct (it names the actual root
cause) but is scored a miss, because cell_id must match exactly and the
line-tolerance scoring only forgives a few lines within the same cell, not
a different cell. On other fixtures (`dep20`'s ex2/ex3) the model reported
*both* the reassignment cell and the crash cell - recall stayed intact but
precision dropped, since the reassignment mention now counts as an extra,
unmatched finding. Handing the model the type-change fact didn't make it
worse at understanding the bug; it changed *where* the model chooses to
point, and the benchmark's symptom-site ground truth punishes that shift
either way it plays out (root-cause-only report, or a two-cell report).

**Latency: costlier again, most severely for the strongest model.**
`deps+types` is slower than `deps` in 7 of these 8 rows, and for qwen14b
specifically the ratio is often ~2x and once ~5x (`order_dependent`/dep20:
6.0s -> 31.6s) - matching finding 7's pattern that extra findings cost
reasoning time even though token counts barely move (checked: total_tokens
only rises by roughly 50-90 tokens per run across these conditions, nowhere
near enough to explain a 2-5x latency jump on its own).

This sharpens finding 7's conclusion rather than contradicting it: it's
not just that *irrelevant* structure hurts and *relevant* structure helps
(finding 5) - a structurally-targeted, empirically-validated-in-isolation
heuristic can *still* hurt, once the benchmark's own scoring convention
(crash-site, exact-cell-match) doesn't line up with what the added
information causes the model to report. The tagger itself isn't obviously
wrong - it's telling the model something true and directly relevant - but
"relevant and true" turned out not to be sufficient either. Whether that's
a fact about the tagger (maybe it should be phrased to point *forward*
toward likely downstream failures, not just name the reassignment) or a
fact about the scoring methodology (maybe root-cause and symptom-site
should both count as correct) is the open question this result raises,
not one it answers.

### 9. Acting *on* the dependency graph beats adding a fact next to it - but "how" still matters

Finding 8's diagnosis pointed at a specific mechanism: adding the
type-change fact as a *new* finding gave the model a place to anchor its
answer that competed with the crash site. That suggested a different
move entirely - instead of adding information, use the same type/shape
stability signal to act on the `deps` graph itself, two ways:

- **`deps-pruned`**: remove edges the tagger can positively confirm are
  type-stable throughout (same mechanism as finding 8's tagger, but
  wired through `DetectBugsEvent`'s new `dependency_edges` override
  instead of `extra_findings` - see `build_pruned_dependency_edges`).
  Conservative by construction: an edge is only removed once the tagger
  has *positive evidence* of stability; anything it can't classify stays.
- **`deps-labeled`**: keep the full, untouched graph, but attach a
  low-risk annotation to each confirmed-stable edge instead of removing
  it (`label_stable_dependencies`, fed in via `extra_findings` like
  finding 8's tagger) - leaving the weighting decision to the model
  rather than deciding it beforehand.

Getting either to do anything on these fixtures required one more piece:
the dep-tier fixtures' controlled edges are all `chain_var_i =
chain_var_{i-1} + 1` - a `BinOp`, which the tagger from finding 8 couldn't
see through (only literals and known calls), so every chain variable
tagged `None` (unclassifiable) and nothing was ever prunable. Extended
`_infer_tag` to propagate numeric/str/list types through `+`/`-`/`*`/`/`,
confirmed structurally before running any LLM calls: at `dep20`,
`cross_cell_semantic` goes from 21 raw edges to exactly 1 pruned edge -
the one edge that actually involves the type change - and `order_dependent`
(no type-change bug at all) prunes to 0, correctly recognizing its edges
were never bug-relevant to begin with.

| tier | class | model | deps F1 | pruned F1 | labeled F1 |
|---|---|---|---|---|---|
| dep2  | cross_cell_semantic | qwen7b  | .89 | .00 | **1.00** |
| dep2  | cross_cell_semantic | qwen14b | .78 | .33 | **1.00** |
| dep10 | cross_cell_semantic | qwen7b  | .67 | .56 | .00 |
| dep10 | cross_cell_semantic | qwen14b | .67 | .44 | .72 |
| dep20 | cross_cell_semantic | qwen7b  | .33 | **.67** | **.78** |
| dep20 | cross_cell_semantic | qwen14b | **1.00** | .56 | .33 |
| dep2  | order_dependent | qwen14b | .00 | **.67** | .00 |
| dep10 | order_dependent | qwen14b | .67 | .67 | .33 |
| dep20 | order_dependent | qwen14b | .33 | .33 | **.67** |

Averaged across the three tiers (qwen1.5b omitted - noise-level on both
classes at every tier, same as findings 7-8):

| class | model | deps | deps-pruned | deps-labeled |
|---|---|---|---|---|
| cross_cell_semantic | qwen7b  | .63 | .41 | .59 |
| cross_cell_semantic | qwen14b | .81 | .44 | .69 |
| order_dependent | qwen7b  | .04 | .00 | .22 |
| order_dependent | qwen14b | .33 | **.56** | .33 |

**Pruning is a clean win exactly where the graph was never useful, and a
loss where it was.** `order_dependent` never had a real type-change bug
for the tagger to preserve - `deps-pruned` strips its graph down to
whatever's left after removing the boring chain, and for qwen14b that
recovers real accuracy (.33 -> .56, driven mostly by dep2's .00 -> .67
jump, where plain `deps` had actively misled the model). `cross_cell_semantic`
is the opposite: the one edge the tagger keeps *is* the bug's edge, but
losing the surrounding "boring" chain structure still costs accuracy for
both models (qwen14b .81 -> .44, qwen7b .63 -> .41) - the chain scaffold
that finding 5 showed helps isn't only informative when it's about the
bug; something about having *more* graph, even type-stable graph, seems
to help the model orient, and pruning removes that along with the noise.

**Labeling is higher-variance, and for cross_cell_semantic on average, the
best-performing config of any tried so far** - .59-.69 average F1 for the
class it targets, ahead of `deps+types` (finding 8: .19-.57) and closer to
plain `deps` (.63-.81) than pruning ever gets, with two genuine 1.00s (both
models at dep2). But it isn't a clean win: qwen7b's `dep10` result
collapsed to .00, and qwen14b's `dep20` dropped from a perfect 1.00
(`deps` alone) to .33. Reading the raw output for both collapses turned up
two distinct causes, not one:

- **The label meant to reassure instead read as a warning.** At `dep10`,
  qwen7b's `cross_cell_semantic/ex3.ipynb` run flagged `chain_var_8` and
  `chain_var_2` - names `label_stable_dependencies` explicitly annotated
  as low-risk - as findings in their own right: *"Variable 'chain_var_8'
  is defined in a previous cell, but its value might have been altered or
  redefined elsewhere."* The model saw a list of "static analysis
  findings" entries and treated their presence as a risk signal
  regardless of what the text said - the same volume-over-content problem
  as finding 7's `deps+isolated`, now showing up even when every
  individual annotation is reassuring rather than alarming.
- **The same root-cause-vs-crash-site anchoring from finding 8, again.**
  At `dep20`, qwen14b's `ex1.ipynb`/`ex2.ipynb` runs both produced a
  *correct diagnosis in the message text* - `"Cell 23 attempts to append
  to 'data', but 'data' has already been reduced to an integer..."` -
  while anchoring the finding's `cell_ids` at the earlier reassignment
  cell (21/22) instead of the crash cell (23) the message itself names.
  Same scoring-methodology gap finding 8 surfaced, reappearing under a
  different context config - worth treating as a property of how these
  models respond to *any* explicit type-change signal (added or labeled),
  not something specific to `deps+types`.

**Latency: worse for both, including pruning - fewer edges is not
faster.** Averaged across tiers, `deps-pruned` costs more wall-clock than
plain `deps` for both models on both classes (e.g. qwen14b/
cross_cell_semantic: 8.3s -> 14.8s) despite the graph itself being
*smaller*, not larger. This rules out "extra content to read" as the
whole explanation for findings 7-8's latency costs - removing content
can cost time too, which points toward the graph shape itself (not just
its size) changing how much the model has to reason before answering,
consistent with finding 8's observation that token counts barely moved
while latency swung 2-5x.

**Put together with findings 5, 7, and 8**: none of "more structure,"
"less structure," or "the same structure plus a fact" is reliably better
- what moved the needle was *which* structure got removed or annotated
relative to where the model's benchmark-scored answer needs to land, and
that relationship isn't stable across model size, dependency density, or
even individual fixtures within the same class. The clearest actionable
result across all three of findings 7-9 is `deps-pruned` on
`order_dependent`/qwen14b - a case where the mechanism (strip a graph
that was actively misleading) matches the class (one the graph was never
built to help) cleanly enough to read as real, not noise.

### 10. A structurally more-correct graph doesn't average out to a more-accurate one

Finding 9's `deps-pruned`/`deps-labeled` both still built on `deps`'s
underlying graph, just filtered or annotated it. This finding instead
fixes a real defect in the graph itself. `context_builder.build_dependency_edges`
walks cells in a single pass in *cell-ID* order, so it can only ever
record an edge pointing backward to an already-visited definer - it
silently assumes cell ID order is execution order. The NBLyzer paper this
project is a continuation of explicitly rejects that assumption (Section 1:
cells "can be executed... in *any* given sequence"), and defines
dependency edges via fixpoint propagation of abstract state across the
notebook instead (Definition 3.1, "Cell Propagation Dependency Graph")
- discovered by asking whether one cell's post-state satisfies another's
pre-condition, regardless of which one has the lower cell number.

Built `analyses/dependency_analysis.py`'s `build_fixpoint_dependency_edges`,
reusing the *same* fixpoint engine `StaleCellAnalysis` already uses
(`Runner.inter_fixpoint_runner`) with a new abstract domain ("which names
are defined so far along this path") and an order-agnostic `phi_condition`
(plain set intersection, no ID comparison anywhere). Caught a real bug
while building it: seeding from a truly empty abstract state broke on
cells like `data = len(data)`, which compiles to a `Call` CFG node
followed by an `Assign` node - the fixpoint's "did the state change"
convergence check saw the no-op `Call` transform, concluded nothing
changed, and never even visited the `Assign` node. Fixed by pre-seeding
each cell's own defined names directly, the same way
`StaleCellAnalysis._prepare_init_as` already does for the cell it's
tracking - a detail this implementation had initially missed copying.

**Verified structurally before any LLM calls** (`tests/test_dependency_analysis.py`,
plus a direct diff against every dep2/dep10/dep20 fixture): the fixpoint
graph strictly preserves every edge `build_dependency_edges` finds (zero
missing edges anywhere), while additionally finding real edges the old
graph is structurally blind to - most importantly, `order_dependent`'s
"read before defined anywhere" edges (e.g. `cell 3 depends on cell 4`
when cell 3's read comes textually first). As a side effect, several
`cross_cell_semantic` fixtures also gained a legitimate second edge (the
crash cell now correctly shows dependence on *both* the original
definition and the later reassignment, not just the most recent one).

| tier | class | model | deps F1 | deps-fixpoint F1 |
|---|---|---|---|---|
| dep2  | cross_cell_semantic | qwen7b  | .89 | .22 |
| dep2  | cross_cell_semantic | qwen14b | .78 | **1.00** |
| dep10 | cross_cell_semantic | qwen7b  | .67 | .00 |
| dep10 | cross_cell_semantic | qwen14b | .67 | **1.00** |
| dep20 | cross_cell_semantic | qwen7b  | .33 | .67 |
| dep20 | cross_cell_semantic | qwen14b | **1.00** | .33 |
| dep2  | order_dependent | qwen14b | .00 | .33 |
| dep10 | order_dependent | qwen14b | **.67** | .33 |
| dep20 | order_dependent | qwen14b | .33 | .22 |

Averaged across tiers: `cross_cell_semantic` qwen7b .63 -> .30 (worse),
qwen14b .81 -> .78 (roughly tied); `order_dependent` qwen14b .33 -> .29
(roughly tied, despite the structural fix landing squarely on this
class). **A graph that is verifiably more complete and more correct than
before did not translate into a cleaner accuracy result** - it's exactly
as high-variance as findings 7-9's other conditions, with two genuine
1.00s (qwen14b/cross_cell_semantic, dep2 and dep10) sitting alongside a
matching set of real regressions (qwen7b/cross_cell_semantic at every
tier; qwen14b/cross_cell_semantic's dep20 drop from a perfect `deps`
score to .33).

Reading the raw output for that dep20 regression turned up the *exact
same* anchoring artifact from findings 8 and 9, now confirmed a fourth
time under yet another context config: `ex1.ipynb`'s message correctly
explains *"Overwriting the list `data` with an integer... will cause
issues"* but reports the finding at cell 22 (the reassignment) rather
than cell 23 (the crash site) the message itself implies. That this keeps
recurring regardless of *which* structural augmentation is in play -
extra findings, labels, or now a richer graph - is itself the more
durable result: it looks less like a property of any one context config
and more like a general property of how these models respond to *any*
prompt containing an explicit cross-cell relationship, independent of
whether that relationship is more accurate or less.

**Latency: worse again**, matching every other condition in findings
7-10 - `deps-fixpoint` costs more wall-clock than plain `deps` in most
(model, tier) pairs (e.g. qwen14b/order_dependent: 6.4s -> 11.0s on
average) despite near-identical token counts, reinforcing that these
latency costs track something about graph *shape*/complexity the model
has to reason through, not input size.

### 11. Revising finding 9 with fixpoint-sourced edges: labeling's `order_dependent` result flips from noise to the strongest single result in this whole investigation

Finding 9's `deps-pruned`/`deps-labeled` numbers were computed *before*
finding 10's fixpoint graph existed - both sourced their own edges from
`type_shape_analysis.py`'s own hand-rolled, ID-ordered `last_definer`
walk, the same order-blind approach `build_dependency_edges` has. Wiring
them to `build_fixpoint_dependency_edges` instead (so pruning/labeling
act on the more-complete graph, not the old one) surfaced an immediate
conflict, caught before running anything: a name can be perfectly
type-stable (never reassigned) and *still* be the read-before-defined
edge that makes an `order_dependent` bug - type stability and definition
timing are orthogonal, so the type-stability walk was pruning away (and
would have mislabeled as "low-risk") exactly the edge that matters most.
Fixed by treating any backward edge (definer cell ID greater than the
reader's - only possible because of finding 10's order-independence fix
in the first place) as automatically risky, regardless of what type
inference concludes - covered directly in `tests/test_type_shape_analysis.py`.

Re-ran `deps-pruned`/`deps-labeled` on `dep2`/`dep10`/`dep20` with the
fix in place and replaced (not appended to) finding 9's original rows,
since the underlying computation changed:

| tier | class | model | deps | deps-pruned (v2) | deps-labeled (v2) |
|---|---|---|---|---|---|
| dep2  | order_dependent | qwen7b | .13 | .00 | .33 |
| dep10 | order_dependent | qwen7b | .00 | .00 | **.67** |
| dep20 | order_dependent | qwen7b | .00 | .00 | **.89** |
| dep20 | cross_cell_semantic | qwen7b  | .33 | .89 | **1.00** |
| dep20 | cross_cell_semantic | qwen14b | 1.00 | .67 | **1.00** |

Averaged across tiers, `deps-labeled`/`order_dependent`/qwen7b goes from
finding 9's .22 to **.63** - a complete reversal, now clearly the best
config tried for that (class, model) pair by a wide margin (`deps` itself
only manages .04 there). `cross_cell_semantic` stays strong too:
qwen14b's `deps-labeled` average is .80, statistically tied with plain
`deps`'s .81 and the best of any augmentation tried across findings 7-10,
with two outright perfect scores at `dep20`. `deps-pruned` improved less
dramatically and stays net-negative on average, but no longer produces
the flat zero finding 9 originally found for `order_dependent` (dep2's
qwen14b: .00 -> .33, matching `deps-fixpoint`'s own recovery there).

Not a clean, uniform win even now - qwen14b's `deps-labeled` result for
`order_dependent` actually got *worse* on average (.33 -> .22), and
`cross_cell_semantic`/qwen7b/`dep10` swung the other way (.00, down from
finding 9's earlier .00 too - no change there, still weak). The variance
across individual (tier, model) cells remains real and unresolved. But
the qwen7b/`order_dependent` result is the single cleanest positive
number produced across findings 7-11: a large, consistent, mechanism-
explained improvement (the model finally gets to see the actual
read-before-defined relationship, correctly flagged as risky, instead of
either nothing or a misleadingly "safe" label) on exactly the class nothing
else in this investigation managed to help. It came from fixing a real
defect in how the structure was built, not from picking a different way
to present already-correct structure - a different kind of result than
findings 7-10's presentation experiments, and arguably a more durable one.

### 12. `cross_cell_semantic`, re-measured after fixing the type tagger and the edge-attribution bug: `deps` and `deps-labeled` cross over as density grows

Two real bugs got fixed between finding 11 and this one, both affecting
every number findings 8-11 reported for the type-tagger-derived configs:

- The type tagger's own tag inference (`_compute_type_tags`) walked
  cells in ID order, same wrong assumption as the old dependency graph -
  `_infer_tag`'s name-to-name lookups (`a = b`) could only resolve if
  `b`'s defining cell happened to come earlier in the notebook's text.
  Fixed with a small iterate-to-fixpoint pass over the whole notebook's
  Assign statements (not the heavy CFG/Runner machinery - type tagging
  only ever looks at one Assign's RHS, so a lighter, purpose-fit
  fixpoint fits the actual shape of the problem better than reusing
  DependencyAnalysis's CFG-level engine would).
- `build_fixpoint_dependency_edges` itself had a latent attribution bug,
  invisible at `_DIRECT_EDGE_DEPTH = 2` but real: without per-name
  provenance tracking in `DependencyAS`, a cell several hops downstream
  of a seed got attributed back to the *seed* for every name reachable
  along the path, not whichever cell actually defined it. Fixed by
  having `defined_vars` store *which cell* provided each name, not a
  placeholder. Confirmed empirically (not just reasoned through) that
  this makes the direct-edges computation genuinely insensitive to K:
  identical output at K=2 vs. K=6 across every fixture in the repo, a
  100-cell synthetic chain, and a genuine cross-cell cycle - architectural
  (every cell seeds its own 1-hop search), not a coincidence of small
  fixtures.

With both fixed, re-ran `cross_cell_semantic`/qwen14b - deliberately
narrowed to one class and one model, after this session's earlier broad
sweeps were judged too noisy to draw conclusions from - across all three
dependency-density tiers:

![F1 vs. dependency density](charts/dep_density_focus_f1.png)
![latency vs. dependency density](charts/dep_density_focus_latency.png)

| edges | none | deps | deps+types | deps-pruned | deps-labeled |
|---|---|---|---|---|---|
| 2  | .50 | .39 | .32 | .67 | **.80** |
| 10 | .44 | **1.00** | .22 | .67 | .67 |
| 20 | .56 | **.89** | .22 | .33 | .56 |

**`deps` and `deps-labeled` cross over as dependency density grows.** At
the lowest density (2 edges), plain `deps` is actually *worse* than
`none` (.39 vs .50) and `deps-labeled` is the clear best (.80). By 10
edges `deps` has climbed to a perfect 1.00 and `deps-labeled` has fallen
behind it (.67); at 20 edges the gap widens further in `deps`'s favor
(.89 vs .56). `deps-pruned` peaks in the middle (10 edges) rather than
at either extreme. `deps+types` is the one config that never wins
anywhere in this class - consistently at or below `none` regardless of
density, now that its own type-tag bug is fixed and this genuinely is
its best-case behavior, not an artifact of broken inference.

A plausible mechanism, not yet independently confirmed: at low density
there's little real graph for the model to reason about on its own, so
the labeler's commentary is one of the only informative signals in the
prompt and gets used; at high density the graph itself already carries
enough signal that the same commentary becomes one more thing to read
without displacing anything useful - consistent with finding 7's
volume-over-content theme, just now shown to depend on *how much real
graph there already is*, not only on how much extra text gets added on
top of a fixed graph.

**Latency reinforces the same crossover, doesn't just add noise to it.**
`deps-labeled` is cheap at 2 edges (13.3s, close to `deps`'s 12.2s) but
balloons at 20 edges (18.5s vs `deps`'s 10.1s) - so the accuracy
crossover at higher density comes with a matching latency cost, not a
wash. `deps-pruned` is the fastest condition at every density tested.

n=3 examples per tier, one run each, one model - a real, mechanism-
plausible pattern worth taking seriously because it reverses cleanly and
consistently across three tiers, but not yet enough repeated sampling to
rule out getting lucky on particular fixtures at either end.

## A different question: can an LLM replace a deterministic analysis outright?

Findings 1-12 all ask "does structural context help LLM bug detection."
This next one asks something different: for a bug class NBFix already
has a real, working, tested deterministic analysis for, how does an LLM
compare - not augmented by that analysis, but *instead of* it. Chose
`StaleCellAnalysis` since it's the analysis this session had already
debugged and understood deeply (the `MAX_LEVEL` fixpoint-depth fix
earlier this session), and because it's a clean, bounded case: one
notebook, one edit, one question ("which cells are now stale").

### 13. On a simple analysis, LLMs land on the same accuracy as a hand-built one - at 1,000-8,000x the latency, with a real, capability-dependent gap in whether they get there the "right" way

**Staleness needed a genuinely different fixture format.** Unlike the
other four llm_bench classes, staleness isn't a property of a static code
snapshot - it's a property of *execution history* (a cell ran, an
upstream cell it depends on was edited afterward but not yet re-run).
Built `tests/resources/llm_bench_stale/` (`_author_stale_fixtures.py`):
3 buggy notebooks + 1 clean negative control, each with an *original*
state and an *edit*. Ground truth isn't exec()-based like the other four
classes (staleness isn't something Python itself would ever raise on) -
it's the real `StaleCellAnalysis`'s own output, obtained by running the
literal production event sequence (`RunCellEvent`/`ChangeCellCodeEvent`,
not the `analyze_notebook()` shortcut the existing unit test uses) so
it's faithful to what a live session actually produces. Confirmed
empirically along the way: a cell's very first `RunCellEvent` compares
against an empty `last_ran_code`, which looks identical to a genuine
edit - harmless here only because every fixture does a full warm-up
pass first, and two other real gaps got surfaced and worked around
(f-string interpolation isn't tracked as a use of the interpolated name
at all; ternary expressions aren't parsed yet).

**First pass (`scripts/benchmark_stale_llm.py`, "passive" framing -
"which values are currently out of date"): one wrong pattern, but a
strikingly consistent one.**

| notebook | real analysis | qwen14b | Claude (subagent, no shared context) |
|---|---|---|---|
| clean1 | [] | [1] | [1] |
| ex1 | [2, 3] | [1, 2, 3] | [1, 2, 3] |
| ex2 | [2] | [1, 2, 3] | [1, 2, 3] |
| ex3 | [2, 3] | [1, 2, 3] | [1, 2, 3] |

Both models - one a small local 14B model, one a full Claude agent
session with zero shared context, spawned fresh specifically to avoid
contaminating the comparison - independently produced the *identical*
answer on every single fixture. Both always included the cell directly
reading the edited variable, which the real analysis's `k=2`
impact-level threshold deliberately excludes. That's not two models
being sloppy in the same random way; it's two independent systems
converging on the same, more literal definition of "stale."

**Why the threshold isn't arbitrary, worked out by hand**: the edited
cell gets *re-executed* as part of triggering the check (confirmed via
the real event sequence), so its new value is already in the kernel.
A cell reading that variable directly would compute correctly if run
next - it only *looks* stale because its currently-displayed value
predates the edit. Cells further downstream are different: they'd use
values still sitting in the kernel from *before*, because their own
immediate dependency hasn't been re-run yet. "Which values look old" and
"which cells would give a wrong answer if executed right now" are
different questions, and the real analysis answers the second one.

**Reframing the prompt around that operational question split the two
models apart.** `--prompt-variant operational` states the actual
mechanism explicitly (kernel memory, what re-executing does and doesn't
refresh) instead of leaving the "how many hops" threshold implicit.

| notebook | real analysis | qwen14b (operational) | Claude (operational, one subagent per notebook) |
|---|---|---|---|
| clean1 | [] | [1] (still wrong) | **[]** |
| ex1 | [2, 3] | [] (wrong, different direction) | **[2, 3]** |
| ex2 | [2] | [] (wrong) | **[2, 3]** (catches a real analysis blind spot, see below) |
| ex3 | [2, 3] | [1, 2] (still wrong) | **[2, 3]** |

qwen14b did not improve - it got *worse* and less consistent, sometimes
now under-reporting instead of over-reporting, and its own reasoning
text showed no sign of correctly chaining "does this cell's dependency
itself still need a re-run." Claude, given the identical explicit rule,
applied it correctly on every fixture, reconstructing the real
analysis's own 2-hop threshold from first principles rather than being
told the number. `ex2`'s "mismatch" is `ex2`'s already-documented real
analysis blind spot (`print(report)` is a call, not a bare Name
reference the analysis's Name-node detection catches) - Claude correctly
flagged it anyway, arguably beating its own ground truth there rather
than missing it.

**So "small models do just as well" is only true for the framing where
neither model actually reasons about the mechanism** - under the passive
framing they fail identically; under the operational framing, model
capability is the entire story. Worth being precise about which claim
the data actually supports.

**Latency, measured individually per notebook (not batched/averaged),
operational framing**:

![stale-cell detection latency](../stale/charts/stale_latency_comparison.png)

| notebook | real analysis | qwen14b | Claude (individual subagent call) |
|---|---|---|---|
| clean1 | 0.4ms | 3.53s | 2.81s |
| ex1 | 1.0ms | 1.45s | 4.57s |
| ex2 | 1.4ms | 1.67s | 5.61s |
| ex3 | 1.0ms | 1.96s | 4.18s |

The real analysis is 1,000-8,000x faster than either LLM path, every
single time, with no exceptions - sub-millisecond because it's a local
static analysis with no network round-trip, versus 1.4-5.6s per LLM
call regardless of which model or how it was framed. Notably, the
framing that got Claude to reason *correctly* (operational) also cost
roughly 3x the latency of the framing that got it to reason identically
to a much smaller model (passive) - correctness and speed pulled in
opposite directions here, not together.

**Bottom line**: for a bug class this simple and this well-served by an
existing deterministic analysis, an LLM - even a fairly small one, and
even a frontier one reasoning zero-shot with no tool access - can reach
the same accuracy the deterministic analysis defines as ground truth,
*if* prompted to ask the right operational question and *if* the model
is capable enough to actually chain that reasoning. What no amount of
prompting fixed was latency: three to four orders of magnitude slower,
consistently, regardless of model or framing. For anything needing
feedback at typing/editing speed - which is the whole reason
`StaleCellAnalysis` exists as a deterministic analysis in the first
place, per NBLyzer's own "within a second" design target - that gap is
disqualifying on its own, independent of whatever the accuracy
comparison shows.

## Known limitations - read the numbers with these in mind

- **The dep2/10/20 chain is a uniform, artificial structure** - a single
  linear `chain_var_i = chain_var_{i-1} + 1` read-chain, not the mixed
  fan-in/fan-out/branching dependency shapes a real notebook would have.
  It's a clean way to isolate "edge count" as a variable, but "20 edges
  in one straight chain" and "20 edges across a branchier real notebook"
  aren't guaranteed to behave the same way - worth treating finding 5's
  trend as real but not yet generalized past this specific chain shape.
- **n=3 buggy examples per class per tier, one run each.** LLM output is
  stochastic; a single fixture flipping right/wrong swings an average by
  33 percentage points. Nothing here should be read as a precise number,
  only as a direction worth taking seriously because it repeats across 5
  independent tiers.
- **One real anomaly on record**: qwen1.5b/`order_dependent`/`deps` at
  the medium tier logged a 41s average latency (vs ~2-6s everywhere else
  for that model) with roughly double the usual token count - looks like
  a small-model repetition/rambling failure mode, not a real result.
  Not investigated further; flagged here so it isn't mistaken for signal.
- **Fixtures are synthetic**, hand-authored with verified-inert filler
  cells around a seeded bug - not real-world notebooks. The taxonomy and
  ground-truth methodology are designed to generalize, but that's an
  assumption, not something these experiments test directly.
- **Line-level scoring has a tolerance/slack** (`result_mapping.py`'s
  `_LINE_OVERSHOOT_SLACK`, `score_findings`'s `line_tolerance`) added
  after the first run showed models often identify the right cell but
  misjudge the exact line on small cells - loosening this recovered a lot
  of real signal, but it's also a scoring-methodology choice worth being
  aware of, not a neutral given.
- **No cell-level slack, only line-level** - finding 8 surfaced the
  matching gap this leaves: a correct-but-differently-anchored answer
  (root cause cell vs. crash-site cell) scores as a full miss, with no
  partial credit and no way to distinguish "wrong" from "right diagnosis,
  different cell." `score_findings` only forgives line drift *within* the
  cell_id the ground truth names.

## Open questions for discussion

- Is the qwen14b accuracy result (finding 1) strong enough to act on, or
  does it need repeated sampling per fixture (not just more fixtures) to
  rule out "got lucky on 2 of 3" before treating it as real?
- Does finding 3 (context needs model capacity to pay off) hold up with a
  mid-size model between 7b and 14b, or other model families entirely -
  is this a `qwen2.5-coder`-specific pattern or a general one?
- Worth adding a repeated-runs axis (same fixture, same config, N
  samples) before adding more fixtures - which axis is more likely to
  change the conclusion?
- Given finding 2 held up cleanly and finding 1 is the most consistent
  accuracy result, is that enough to move forward into Phase 4
  (repair, with the same context-mode ablation) using `deps` as the
  default, or should the confirm/dismiss triage phase (deterministic
  findings as LLM input) come first as originally sequenced?
- Findings 5+6 together are arguably the most actionable pair here: `deps`'s
  value tracks dependency density rather than cell count (5), and checking
  that density costs microseconds (6) - so "measure the workload, then
  decide what structural info to hand the LLM" is cheap enough to do on
  every request, not just a nice idea. What's not yet decided: the actual
  policy (a hard edge-count threshold? per-bug-class thresholds, given the
  four deterministic analyses already target different structural
  properties? something continuous rather than a cutoff?) - and that
  still depends on the chain-shape caveat below holding up.
- Worth fixing the `unbound_names` read-before-write gap in `def_use.py`
  before running this experiment again - `cross_cell_semantic` fixtures
  specifically are undercounting their own real edges, which likely
  understates that class's results in every tier above, not just the
  dependency-axis ones.
- The chain shape caveat above is worth resolving before leaning on
  finding 5 too hard - does the same monotonic trend hold for a branchier
  synthetic structure (e.g. several short chains, or a fan-out from one
  cell into many readers) at the same edge counts?

## Planned next: does *actively misleading* structural info hurt even more?

Finding 7 closed most of this gap, but not all of it. There are now three
distinct claims in play, and it's worth keeping them separate:

1. "More real, *relevant* structure helps" - finding 5, real dependency
   density, shown.
2. "Real but *irrelevant* structure costs latency and, for at least one
   model, accuracy" - finding 7, `deps+isolated`'s mostly-filler-cell
   findings, shown.
3. "*Actively wrong/misleading* structure hurts more than irrelevant
   structure does" - not yet shown. `deps+isolated`'s findings are true
   (every cell it names really is isolated) and merely beside the point;
   they were never *false*. A fabricated or mismatched finding (e.g. "this
   cell depends on cell 4" when it doesn't, or another bug class's
   findings presented as if relevant) is a different, stronger claim than
   finding 7 tested.

Still-open experiment for (3): feed a fixture from one bug class the
dependency graph or deterministic findings framed around a *different*
class's structure (or fabricated findings that don't match the actual
bug), and compare against `none`, the correct `deps`, and finding 7's
`deps+isolated` - isolating "actively wrong" as its own condition,
distinct from "no structure," "right structure," and "true-but-
irrelevant structure." `DetectBugsEvent`'s `context_mode`/`finding_types`
params (Phase 2, `src/nbfix/llm/detect_bugs_event.py`) already support
choosing which real findings to include, as used for finding 7 - claim
(3) needs one more step, a way to inject a *fabricated* finding/edge that
doesn't come from a real analysis run at all, which doesn't exist yet.
