from pathlib import Path

from lark import Lark
from lark.indenter import Indenter

_GRAMMAR_PATH = Path(__file__).parent / "grammar" / "notebook_python.lark"


class NotebookIndenter(Indenter):
    NL_type = "_NEWLINE"
    OPEN_PAREN_types = ["LPAR", "LSQB", "LBRACE"]
    CLOSE_PAREN_types = ["RPAR", "RSQB", "RBRACE"]
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 8


def _build_parser():
    grammar_text = _GRAMMAR_PATH.read_text()
    return Lark(
        grammar_text,
        parser="lalr",
        postlex=NotebookIndenter(),
        start="start",
        propagate_positions=True,
        maybe_placeholders=True,
    )


_parser = None


def get_parser():
    global _parser
    if _parser is None:
        _parser = _build_parser()
    return _parser


def parse_to_tree(source: str):
    """Parse notebook-cell source into a raw Lark parse tree."""
    if not source.endswith("\n"):
        source += "\n"
    return get_parser().parse(source)
