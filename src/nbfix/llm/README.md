# LLM-assisted bug detection

Grounds a locally-run (or hosted) LLM in NBFix's own structural analysis
(dependency graph, def-use info - see `context_builder.py`) so a small
model can perform closer to a large one, at a fraction of the cost, on
general bugs the four deterministic analyses (stale/idle/isolated/
data-leak) were never built to catch.

## Implemented

The full original 7-phase plan is done and wired into every surface:

- `context_builder.py` / `client.py` / `prompts.py` / `result_mapping.py` -
  foundation: builds cell/subgraph/full-notebook context, talks to any
  OpenAI-compatible endpoint (local Ollama or hosted), maps LLM JSON output
  back onto the existing `ErrorInfo`/`PathResult`/`Result` shapes with no
  changes needed to `analyses/runner/analysis_results.py`.
- `detect_bugs_event.py` - `DetectBugsEvent`, wired through the server
  extension (`serverextension/dispatch.py`'s `detect_bugs` event, lazily
  imported so `nbfix[jupyter]` without `[llm]` degrades cleanly), the CLI
  (`cli.py --detect-bugs`), and the JupyterLab extension ("Check Cell/
  Notebook for Bugs" commands, `jupyterlab-nbfix/src/index.ts`).
- `notebook_loading.py` - per-cell-resilient loading, scoped to this
  package only (core `analyzer.py`/`resource_utils.utils.load_notebook`
  and the `open_notebook` flow are untouched and still fail-fast).
- `scripts/benchmark_llm.py` - harness comparing model configs
  (`NAME=MODEL@BASE_URL`), with `--ablation` for the with/without-context
  comparison the whole feature is motivated by, and optional precision/
  recall scoring against a `notebook.ipynb.expected.json` sidecar.

Never a core dependency: `nbfix`/`nbfix[jupyter]` have zero import-time
dependency on this package (see the lazy-import guards in `dispatch.py`
and `cli.py`) - `nbfix[llm]` is opt-in throughout.

## Backlog (next up, in this order)

- [ ] **Repair.** Already designed, not yet built: a `RepairCellEvent`
  sibling to `DetectBugsEvent`, reusing the same context-builder/client
  infrastructure, asking the model for a code patch rather than (or in
  addition to) a diagnosis. Output shape should map directly onto the
  existing `ChangeCellCodeEvent(new_code, cell_index, with_result)` -
  no new "apply this patch" plumbing needed, it already exists. Repair
  should be **propose, not auto-apply** - a UI/CLI surfaces the suggested
  patch for the user to accept, never silently rewrites a cell -
  especially for data-leak findings specifically, where a subtly wrong
  auto-fix could be worse than the original warning (see the original
  design discussion: this caution was explicit from the start). Natural
  input is a `DetectBugsEvent` finding (cell + diagnosis), not a fully
  separate detection pass.
- [ ] **Expose NBFix as a tool Claude Code can call.** Most natural
  mechanism is an MCP server wrapping the same event/engine surface
  `serverextension/` already adapts for HTTP - i.e. a new adapter layer
  (`src/nbfix/mcp/` or a separate package, mirroring how
  `jupyterlab-nbfix/` is a separate package from the core), not a new
  analysis engine. Lets Claude Code call "run NBFix detection/repair on
  this notebook" as a tool mid-session rather than needing the user to
  run the CLI/JupyterLab extension separately.
- [ ] **Measure NBFix's output against Claude Code's.** Note this is a
  different axis from the item above (NBFix *feeding* Claude Code vs.
  NBFix *compared against* Claude Code) - don't conflate them when this
  gets picked up. Two distinct things this could mean, worth deciding
  explicitly rather than assuming:
  1. Add Claude/Anthropic as another config in `benchmark_llm.py`'s
     existing model-comparison harness - needs checking whether Anthropic
     exposes (or the `openai` SDK can target) an OpenAI-compatible
     endpoint for this, since `LLMClient` is built on the `openai` SDK's
     chat-completions shape, which Anthropic's native Messages API
     doesn't match - not yet verified.
  2. A higher-level, task-level comparison: point Claude Code itself at
     the same eval notebooks with an equivalent "find and fix the bugs"
     prompt, and compare its output to NBFix's - a different, likely
     harder-to-automate harness than the current config-level one, since
     it means driving Claude Code as the thing under test, not just
     another API endpoint.
