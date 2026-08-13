from argparse import ArgumentParser

from .analyzer import NBSynth
from .events import RunBatchEvent
from .resource_utils.utils import is_script, read_file, read_json


def _load_notebook(filename, notebook, level=5) -> NBSynth:
    code_nbsynth = NBSynth(level=level)
    assert(not (filename and notebook))
    if (notebook is None):
        assert(filename)
        if is_script(filename):
            notebook = read_file(filename)
            code_nbsynth.load_script(notebook)
        else:
            notebook = read_json(filename)
            code_nbsynth.load_notebook(notebook["cells"])
    else:
        code_nbsynth.load_notebook(notebook["cells"])
    return code_nbsynth


def nbsynth(filename, notebook,  analyses,  start, level=5):
    code_nbsynth = _load_notebook(filename, notebook, level)
    code_nbsynth.add_analyses(analyses)
    event = RunBatchEvent(start)
    results = code_nbsynth.execute_event(event).dumps(True)

    return results


def detect_bugs(filename, notebook, scope, cell_index):
    """
    Runs LLM-assisted bug detection instead of the -a analyses. Imports
    from .llm are lazy so plain `nbsynth -f ... -a ...` invocations never
    depend on the (optional) llm extra being installed.
    """
    try:
        from .llm.client import LLMClientError
        from .llm.detect_bugs_event import DetectBugsEvent
    except ImportError as exc:
        raise RuntimeError(
            "LLM bug detection is not installed - pip install nbsynth[llm]"
        ) from exc

    code_nbsynth = _load_notebook(filename, notebook)
    event = DetectBugsEvent(scope, cell_index)
    try:
        result = code_nbsynth.execute_event(event)
    except LLMClientError as exc:
        raise RuntimeError(str(exc)) from exc

    return result.dumps(True)


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="NBSynth version 1.0 ")
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("-f", "--filename",  type=str, help='Filename of notebook.')
    group.add_argument("-n", "--notebook", type=str, help='Notebook json string.')
    parser.add_argument("-a", "--analyses", nargs="+", type=str, default=[], help='Analyses to perform.')
    parser.add_argument("-s", "--start", type=int, default=0, help='Starting cell ID (default is 0).')
    parser.add_argument("-l", "--level", nargs="?", type=int, default=5, help='Depth level of the analysis (default is inf).')
    parser.add_argument(
        "--detect-bugs", action="store_true",
        help='Run LLM-assisted bug detection instead of -a. Requires the llm extra (pip install nbsynth[llm]).',
    )
    parser.add_argument(
        "--scope", choices=["cell", "subgraph", "full"], default="full",
        help='Scope for --detect-bugs (default: full notebook).',
    )
    parser.add_argument(
        "--cell", type=int, default=None,
        help='Cell index to check. Required when --scope is cell or subgraph.',
    )
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.detect_bugs:
        if args.scope in ("cell", "subgraph") and args.cell is None:
            parser.error(f"--cell is required when --scope {args.scope}")
        try:
            results = detect_bugs(args.filename, args.notebook, args.scope, args.cell)
        except RuntimeError as exc:
            raise SystemExit(f"Error: {exc}")
        print(results)
        return

    results = nbsynth(args.filename, args.notebook, args.analyses, args.start, args.level)
    print(results)

if __name__ == "__main__":
    main()
