"""Small expression pretty-printer used to build human-readable CFG node
labels. Not required to be byte-identical to the source (unlike the field
values on the AST nodes themselves, which analyses do pattern-match on),
since `.label` is read by the analyses either as a display string or, in a
couple of narrow cases, as a bare variable name -- both of which this
produces correctly."""

from . import ast_nodes as n

_BINOP_SYMBOLS = {
    n.Add: "+", n.Sub: "-", n.Mult: "*", n.Div: "/", n.FloorDiv: "//",
    n.Mod: "%", n.Pow: "**", n.BitAnd: "&", n.BitOr: "|", n.BitXor: "^",
    n.RShift: ">>", n.LShift: "<<", n.MatMult: "@",
}
_UNARY_SYMBOLS = {n.UAdd: "+", n.USub: "-", n.Invert: "~", n.Not: "not "}
_CMP_SYMBOLS = {
    n.Lt: "<", n.Gt: ">", n.Eq: "==", n.GtE: ">=", n.LtE: "<=",
    n.NotEq: "!=", n.In: "in", n.NotIn: "not in", n.Is: "is", n.IsNot: "is not",
}


def unparse(node):
    if node is None:
        return ""
    if isinstance(node, n.Name):
        return node.id
    if isinstance(node, n.Constant):
        return repr(node.value)
    if isinstance(node, n.Attribute):
        return f"{unparse(node.value)}.{node.attr}"
    if isinstance(node, n.Subscript):
        return f"{unparse(node.value)}[{unparse(node.slice)}]"
    if isinstance(node, n.Slice):
        parts = [unparse(node.lower) if node.lower else "", unparse(node.upper) if node.upper else ""]
        text = ":".join(parts)
        if node.step is not None:
            text += ":" + unparse(node.step)
        return text
    if isinstance(node, n.Call):
        args = [unparse(a) for a in node.args]
        args += [f"{kw.arg}={unparse(kw.value)}" if kw.arg else f"**{unparse(kw.value)}" for kw in node.keywords]
        return f"{unparse(node.func)}({', '.join(args)})"
    if isinstance(node, n.BinOp):
        return f"{unparse(node.left)} {_BINOP_SYMBOLS.get(type(node.op), '?')} {unparse(node.right)}"
    if isinstance(node, n.BoolOp):
        joiner = " and " if isinstance(node.op, n.And) else " or "
        return joiner.join(unparse(v) for v in node.values)
    if isinstance(node, n.UnaryOp):
        return f"{_UNARY_SYMBOLS.get(type(node.op), '?')}{unparse(node.operand)}"
    if isinstance(node, n.Compare):
        text = unparse(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            text += f" {_CMP_SYMBOLS.get(type(op), '?')} {unparse(comparator)}"
        return text
    if isinstance(node, n.Tuple):
        return "(" + ", ".join(unparse(e) for e in node.elts) + ")"
    if isinstance(node, n.List):
        return "[" + ", ".join(unparse(e) for e in node.elts) + "]"
    if isinstance(node, n.Dict):
        return "{" + ", ".join(f"{unparse(k)}: {unparse(v)}" for k, v in zip(node.keys, node.values)) + "}"
    if isinstance(node, n.Starred):
        return "*" + unparse(node.value)
    return node.__class__.__name__
