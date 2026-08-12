# NBSynth

[![Tests](https://github.com/psubotic/NBSynth/actions/workflows/tests.yml/badge.svg)](https://github.com/psubotic/NBSynth/actions/workflows/tests.yml)

Static analysis framework for data science notebooks.

NBSynth parses notebook-cell code with its own grammar/parser (built on
[Lark](https://github.com/lark-parser/lark)), builds a control-flow graph
and def-use analysis from that, and runs a set of analyses over the
result:

1. **Stale cell detection** — a cell is stale if it uses identifiers whose
   definitions were affected by changes made in another cell.
2. **Idle cell detection** — a cell is idle if running it (regardless of
   edits) can't change the state of any other cell.
3. **Isolated cell detection** — a cell is isolated if none of its
   definitions depend on identifiers from other cells, and none of its
   identifiers are used outside the cell.
4. **Data leakage analysis** — flags training a model on data that overlaps
   with its test set.

All analyses are still evolving (WIP).

## Project layout

```
src/nbsynth/
  parser/       grammar, AST, CFG builder, def-use analysis (see parser/README.md)
  ir/           per-cell intermediate representation, built on top of parser/
  analyses/     the four analyses above, plus their abstract domains/states
  resource_utils/  notebook loading (local files or Azure blob storage)
  analyzer.py   NBSynth: the top-level per-notebook analysis driver
  cli.py, server.py, events.py, benchmarker.py
tests/          pytest test suite + notebook fixtures
extension/      VS Code extension (TypeScript)
```

## Getting started

```
pip install -e ".[dev]"
pytest tests/
```

## VS Code extension

`extension/` is a VS Code extension that talks to a running NBSynth
server (`nbsynth.server`) over a local socket to surface analysis results
in the editor. See `extension/src/`.
