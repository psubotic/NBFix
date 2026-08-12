# Running NBSynth

NBSynth can be used three ways: as a standalone CLI, through a VS Code
extension prototype, or through a JupyterLab extension. This document covers
setup and commands for all three.

## 1. Command line (`nbsynth` CLI)

This is the only interface that's fully working today - no server, no
editor integration, just a notebook or script in, JSON diagnostics out.

### Setup

```bash
git clone git@github.com:psubotic/NBSynth.git
cd NBSynth
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Usage

```bash
nbsynth -f <path-to-notebook-or-script> -a <analysis-name> [<analysis-name> ...] [-s <start-cell>] [-l <level>]
```

| Flag | Meaning |
| --- | --- |
| `-f`, `--filename` | Path to a `.ipynb` notebook or `.py` script. Mutually exclusive with `-n`. |
| `-n`, `--notebook` | Currently broken - see note below. Use `-f` instead. |
| `-a`, `--analyses` | One or more analysis names (space-separated), see table below. Required. |
| `-s`, `--start` | Cell id to start the analysis from. Default `0`. |
| `-l`, `--level` | Analysis depth. Default `5`. |

Only four analyses are actually implemented and safe to pass to `-a`:

| Analysis name (pass exactly as shown) |
| --- |
| `Data Leak Analysis` |
| `Stale Cells Analysis` |
| `Idle Cells Analysis` |
| `Isolated Cells Analysis` |

`Fresh Cells Analysis` and `Safe Path Analysis` exist as constants in the
code but have no implementation behind them - passing either to `-a` raises
a `KeyError` and crashes the CLI.

### Examples

Run one analysis on a notebook:

```bash
nbsynth -f tests/resources/Basic.ipynb -a "Idle Cells Analysis"
```

Run multiple analyses at once:

```bash
nbsynth -f tests/resources/dataleak_true.ipynb -a "Data Leak Analysis" "Stale Cells Analysis"
```

Analyze a plain Python script instead of a notebook:

```bash
nbsynth -f my_script.py -a "Idle Cells Analysis"
```

Output is a JSON array of per-cell results printed to stdout, e.g.:

```json
[{"cell_id":0,"errors":[{"line":1,"label":"x","error_type":"ErrorType.TERMINAL","message":"Variable is not used outside this cell."}],"path":[0]}]
```

**Known issue:** `-n`/`--notebook` is meant to accept a raw notebook JSON
string on the command line, but the CLI passes that string straight to
`load_notebook()` without parsing it, so it always fails with
`TypeError: string indices must be integers, not 'str'`. Use `-f` with a
file path instead.

## 2. VS Code extension

**Status: unfinished prototype, not currently runnable.** `extension/`
predates the JupyterLab extension and was never completed:

- There's no `package.json`, so it can't be built or installed as a real
  VS Code extension (`vsce package` / `code --install-extension` have
  nothing to work with).
- It talks to `nbsynth.server` (`src/nbsynth/server.py`) over a raw TCP
  socket on port 9999, but that server module uses non-relative imports
  (`from events import *`), so it only runs if launched as a loose script
  from inside `src/nbsynth/` with that directory on `sys.path` - it does
  not work when NBSynth is installed normally as a package.
- `extension/src/constants.ts` hardcodes the server's location as a
  Windows-style path (`SERVER_PATH = "\nbsynth\src\server.py"`), so even
  the socket-spawning logic assumes a specific machine layout.

If you want to pick this up and finish it, the missing pieces are: a
`package.json` (`vscode` extension manifest + esbuild/webpack config), a
fixed `nbsynth.server` entry point using relative imports so it runs via
`python -m nbsynth.server`, and a cross-platform way to locate that
entry point instead of the hardcoded path in `constants.ts`. Until then,
there's no working setup/run sequence to give here.

## 3. JupyterLab extension

This is the fully working, live-diagnostics integration: squiggly
underlines on notebook cells as you edit, add, remove, and run them. It's
split into two packages so installing the JupyterLab UI (which needs
`jupyterlab` and a Node/npm toolchain) never weighs down a plain
`pip install nbsynth`:

- `nbsynth[jupyter]` - the `jupyter_server` REST extension
  (`src/nbsynth/serverextension/`) that runs NBSynth's analysis engine and
  returns diagnostics over HTTP. Pure Python, no Node required.
- `jupyterlab-nbsynth/` - the JupyterLab labextension (TypeScript) that
  calls that API and renders diagnostics via CodeMirror. Building it
  requires Node/npm.

### Setup

```bash
git clone git@github.com:psubotic/NBSynth.git
cd NBSynth
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 1. Install the core package + server extension
pip install -e ".[jupyter]"

# 2. Build and install the labextension (requires Node.js/npm)
pip install ./jupyterlab-nbsynth
```

The second `pip install` runs `npm install` and a webpack build under the
hood via `hatch-jupyter-builder` - expect it to take a minute or two the
first time.

### Verify both pieces registered

```bash
jupyter server extension list
# should show: nbsynth.serverextension  enabled  OK

jupyter labextension list
# should show: jupyterlab-nbsynth v0.1.0  enabled  OK  (python, nbsynth)
```

### Run it

```bash
jupyter lab
```

Open any notebook. The extension opens a session for it automatically
(`open_notebook` event) and starts reporting diagnostics as you run cells
and edit/add/remove them; no further setup or commands are needed once
JupyterLab is running.

### Rebuilding after frontend changes

If you edit `jupyterlab-nbsynth/src/*.ts`, rebuild with:

```bash
cd jupyterlab-nbsynth
npm run build:prod
```

then restart `jupyter lab` (a hard browser refresh may also be needed to
pick up the new bundle).
