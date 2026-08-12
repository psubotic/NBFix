<p align="center">
  <img src="assets/logo.png" alt="NBSynth" width="800">
</p>

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
  resource_utils/  local notebook/file loading
  serverextension/ jupyter_server REST extension exposing NBSynth's events over HTTP
  analyzer.py   NBSynth: the top-level per-notebook analysis driver
  cli.py, events.py, benchmarker.py
tests/            pytest test suite + notebook fixtures
extension/        VS Code extension prototype (TypeScript, unfinished)
jupyterlab-nbsynth/  JupyterLab labextension (TypeScript) - live diagnostics in the editor
```

## Getting started

```
pip install -e ".[dev]"
pytest tests/
```

## VS Code extension

`extension/` is an unfinished VS Code extension prototype that talks to a
local socket server to surface analysis results in the editor. It predates
the JupyterLab extension below and isn't currently buildable (no
`package.json`).

## JupyterLab extension

Live NBSynth diagnostics inside JupyterLab - squiggly underlines on cells as
you edit, add, remove, and run them - are split across two packages so that
installing the JupyterLab UI (which needs `jupyterlab` and a Node/npm
toolchain at build time) never weighs down a plain `pip install nbsynth`:

- `nbsynth[jupyter]` - registers the `jupyter_server` REST API
  (`src/nbsynth/serverextension/`) that runs NBSynth's analysis engine
  against a notebook and returns diagnostics. Pure Python, no Node needed.
- `jupyterlab-nbsynth/` - the JupyterLab labextension (TypeScript) that
  talks to that API and renders diagnostics via CodeMirror.

To use it in a running JupyterLab:

```
pip install "nbsynth[jupyter]"
pip install ./jupyterlab-nbsynth   # builds the labextension; needs Node/npm
jupyter lab
```

`jupyter server extension list` / `jupyter labextension list` should show
`nbsynth.serverextension` and `jupyterlab-nbsynth` respectively as enabled.
