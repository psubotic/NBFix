# nbcore

Shared parser, CFG builder, def-use analysis, dependency graph, and
analysis framework behind the NBTooling suite (NBHarness, NBCompile,
NBFix). Not a standalone tool - a library the three tools depend on.

Includes the general, cell-dict-generic LLM bug-detection support
(`llm/`) - it's here rather than in any one tool because it works
identically over notebook cells or script pseudo-cells, and both
NBHarness (live) and NBFix (batch) use it as-is.

See the top-level repo README for how this fits into the wider suite.
