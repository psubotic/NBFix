"""
Graph node classes for the CFG, ported from
externals/simple_cfg/simple_cfg/cfg_nodes.py so analyses keep working via
`isinstance` checks against the *same shapes* (label / ast_node / line_number
/ ingoing / outgoing, and the AssignmentNode/CondNode/... subtypes) without
depending on the `simple_cfg` package.

Difference from the original: `label` is always passed in by the CFG
builder instead of being computed internally via simple_cfg's ast-coupled
LabelVisitor -- see cfg_builder.unparse().
"""

from collections import namedtuple

ControlFlowNode = namedtuple("ControlFlowNode", ("test", "last_nodes", "break_statements"))


class IgnoredNode:
    pass


class ConnectToExitNode:
    pass


class Node:
    id = 0

    def __init__(self, label, ast_node, *, line_number=None, path):
        Node.id += 1
        self.label = label
        self.ast_node = ast_node
        if line_number:
            self.line_number = line_number
        elif ast_node is not None:
            self.line_number = ast_node.lineno
        else:
            self.line_number = None
        self.path = path
        self.ingoing = list()
        self.outgoing = list()

    def connect(self, successor):
        if isinstance(self, ConnectToExitNode) and not isinstance(successor, EntryOrExitNode):
            return
        self.outgoing.append(successor)
        successor.ingoing.append(self)

    def connect_predecessors(self, predecessors):
        for pred in predecessors:
            self.ingoing.append(pred)
            pred.outgoing.append(self)

    def __str__(self):
        return "".join((" Label: ", self.label))

    def __repr__(self):
        ingoing = "ingoing:\t" + str([x.label for x in self.ingoing])
        outgoing = "outgoing:\t" + str([x.label for x in self.outgoing])
        return "\n" + "\n".join(("Label: " + self.label, "Line number: " + str(self.line_number), ingoing, outgoing))


class BreakNode(Node):
    def __init__(self, ast_node, *, path):
        super().__init__(self.__class__.__name__, ast_node, path=path)


class CondNode(Node):
    def __init__(self, test_node, ast_node, *, label, path):
        self.test = test_node
        self.positive_nodes = []
        super().__init__(label, ast_node, path=path)


class TryNode(Node):
    def __init__(self, ast_node, *, path):
        super().__init__("try:", ast_node, path=path)


class EntryOrExitNode(Node):
    def __init__(self, label):
        super().__init__(label, None, line_number=None, path=None)


class RaiseNode(Node, ConnectToExitNode):
    def __init__(self, ast_node, *, label, path):
        super().__init__(label, ast_node, path=path)


class AssignmentNode(Node):
    def __init__(self, label, left_hand_side, ast_node, right_hand_side, *,
                 right_hand_side_literals=None, line_number=None, path):
        super().__init__(label, ast_node, line_number=line_number, path=path)
        self.left_hand_side = left_hand_side
        self.right_hand_side = right_hand_side


class RestoreNode(AssignmentNode):
    def __init__(self, label, left_hand_side, right_hand_side_variables, *, line_number, path):
        super().__init__(label, left_hand_side, None, right_hand_side_variables, line_number=line_number, path=path)


class BBorBInode(AssignmentNode):
    """Black-Box-or-Builtin node: a call whose target isn't (yet) inlined.

    Phase 1 note: every call is currently treated as black-box -- same-cell
    user-defined-function inlining (simple_cfg's process_function /
    save_local_scope / restore_saved_local_scope machinery) is deferred, not
    dropped. See parser/README.md.
    """

    def __init__(self, label, left_hand_side, ast_node, right_hand_side_variables, *,
                 line_number, path, func_name):
        super().__init__(label, left_hand_side, ast_node, right_hand_side_variables, line_number=line_number, path=path)
        self.args = list()
        self.inner_most_call = self
        self.func_name = func_name


class AssignmentCallNode(AssignmentNode):
    def __init__(self, label, left_hand_side, ast_node, right_hand_side_variables, *,
                 line_number, path, call_node):
        super().__init__(label, left_hand_side, ast_node, right_hand_side_variables, line_number=line_number, path=path)
        self.call_node = call_node
        self.blackbox = False


class ReturnNode(AssignmentNode, ConnectToExitNode):
    def __init__(self, label, left_hand_side, ast_node, right_hand_side_variables, *, path):
        super().__init__(label, left_hand_side, ast_node, right_hand_side_variables, line_number=ast_node.lineno, path=path)


class YieldNode(AssignmentNode):
    pass
