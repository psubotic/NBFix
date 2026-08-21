from argparse import ArgumentParser

from nbcore.events import RunBatchEvent
from nbcore.analyses.dataleak_analysis import DATA_LEAK
from nbcore.resource_utils.utils import read_file

from .script_loader import script_cells_from_source
from .session_factory import new_session


def _load_script(filename) -> "AnalysisSession":
    session = new_session()
    session.load(script_cells_from_source(read_file(filename)))
    return session


def nbfix(filename, analyses, start, level=5):
    session = _load_script(filename)
    session.level = level
    session.add_analyses(analyses)
    event = RunBatchEvent(start)
    results = session.execute_event(event).dumps(True)

    return results


def detect_bugs(filename, scope, cell_index, context_mode="deps", finding_types=None):
    """
    Runs LLM-assisted bug detection instead of the -a analyses. Imports
    from nbcore.llm are lazy so plain `nbfix -f ... -a ...` invocations
    never depend on the (optional) llm extra being installed.

    If finding_types is given, runs those analyses over the whole script
    first so DetectBugsEvent has fresh results to filter into context - it
    deliberately never does this itself (see its docstring).
    """
    try:
        from nbcore.llm.client import LLMClientError
        from nbcore.llm.detect_bugs_event import DetectBugsEvent
    except ImportError as exc:
        raise RuntimeError(
            "LLM bug detection is not installed - pip install nbcore[llm]"
        ) from exc

    session = _load_script(filename)
    if finding_types:
        session.add_analyses(list(finding_types))
        session.run_analyses(-1, list(finding_types))
    event = DetectBugsEvent(scope, cell_index, context_mode=context_mode, finding_types=finding_types)
    try:
        result = session.execute_event(event)
    except LLMClientError as exc:
        raise RuntimeError(str(exc)) from exc

    return result.dumps(True)


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="NBFix - script analysis and repair")

    parser.add_argument("-f", "--filename", type=str, required=True, help='Filename of the script to analyze.')
    parser.add_argument("-a", "--analyses", nargs="+", type=str, default=[], help='Analyses to perform.')
    parser.add_argument("-s", "--start", type=int, default=0, help='Starting pseudo-cell index (default is 0).')
    parser.add_argument("-l", "--level", nargs="?", type=int, default=5, help='Depth level of the analysis (default is inf).')
    parser.add_argument(
        "--detect-bugs", action="store_true",
        help='Run LLM-assisted bug detection instead of -a. Requires the llm extra (pip install nbcore[llm]).',
    )
    parser.add_argument(
        "--scope", choices=["cell", "subgraph", "full"], default="full",
        help='Scope for --detect-bugs (default: full script).',
    )
    parser.add_argument(
        "--cell", type=int, default=None,
        help='Pseudo-cell index to check. Required when --scope is cell or subgraph.',
    )
    parser.add_argument(
        "--context-mode", choices=["none", "deps"], default="deps",
        help='Context mode for --detect-bugs: "deps" includes the dependency '
             'graph (default), "none" omits it entirely.',
    )
    parser.add_argument(
        "--finding-types", nargs="+", choices=[DATA_LEAK], default=None,
        help='Deterministic analysis names to run and feed the LLM as extra '
             'context, for --detect-bugs.',
    )
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.detect_bugs:
        if args.scope in ("cell", "subgraph") and args.cell is None:
            parser.error(f"--cell is required when --scope {args.scope}")
        try:
            results = detect_bugs(
                args.filename, args.scope, args.cell,
                args.context_mode, args.finding_types,
            )
        except RuntimeError as exc:
            raise SystemExit(f"Error: {exc}")
        print(results)
        return

    results = nbfix(args.filename, args.analyses, args.start, args.level)
    print(results)

if __name__ == "__main__":
    main()
