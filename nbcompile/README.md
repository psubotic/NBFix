# NBCompile

Notebook → script converter - the third tool in the NBTooling suite.

**Not implemented yet.** This is a package stub (installable, empty)
reserving the name and dependency on `nbcore` ahead of Part 7's real
design work.

The intended approach (see the project plan): use `nbcore`'s
paper-correct cell propagation dependency graph
(`nbcore.analyses.dependency_analysis`) to compute a notebook's true
execution order - not a naive cell-order dump the way `nbconvert`
does - and emit a linear script from that. NBFix would then consume
that script; NBCompile itself never repairs anything.

See the top-level repo README for how this fits into the wider suite.
