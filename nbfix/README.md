# NBFix

Batch analysis and repair for data science scripts - the only tool in
the NBTooling suite that repairs. Does not handle notebooks; scripts
produced by NBCompile (or written directly) are its input.

Splits a script into pseudo-cells at top-level-statement boundaries so
`nbcore`'s cell-based analyses (dependency graph, data leakage, LLM
context building) apply to it the same way they do to a notebook.

See the top-level repo README for how this fits into the wider suite.
