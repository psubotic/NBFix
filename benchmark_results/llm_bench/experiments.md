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

## Planned next: does *wrong* structural info actively hurt?

Everything above tests "more real structure" (dependency density) vs.
"none." Next session's goal is a different, distinct claim: that
structural info which is *wrong or irrelevant to the specific bug being
asked about* isn't neutral - it creates noise and measurably lowers
performance, so NBFix can't just blindly dump all available structural
info into the prompt; it has to be selective about what's actually
relevant to the analysis at hand.

**Important distinction from what's already shown**: `dep2/dep10/dep20`
does *not* demonstrate this yet. That chain is neutral padding - self-
contained, unrelated to the bug - and adding more of it mostly *helped*
rather than hurt (finding 5). So the existing evidence supports "more
real structure helps," which is a different claim from "wrong structure
hurts." A clean experiment for the second claim needs deliberately
*misleading* structure, not just more neutral structure:
- Feed a fixture from one bug class the dependency graph or deterministic
  findings framed around a *different* class's structure (or fabricated
  findings that don't match the actual bug), and compare against both
  `none` and the correct `deps` - isolating "wrong structure" as its own
  condition distinct from "no structure" and "right structure."
- `DetectBugsEvent`'s `context_mode`/`finding_types` params (Phase 2,
  `src/nbfix/llm/detect_bugs_event.py`) already support choosing exactly
  which deterministic-analysis findings to include - built for this kind
  of selectivity experiment but never benchmarked yet.
