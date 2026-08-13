from .context_builder import BugDetectionContext

SYSTEM_PROMPT = """You are reviewing Python code from Jupyter notebook cells for bugs.

You will be given the source code of one or more cells. You may also be
given a dependency graph showing which cells define variables that other
cells read, and/or findings from NBFix's own deterministic analyses -
both derived from static analysis, not your own inference, so trust them
as ground truth where present.

Identify concrete bugs: logic errors, incorrect variable usage, misuse of
functions/libraries, or bugs that only manifest from how cells interact
with each other (e.g. a cell using a variable in a way that's inconsistent
with how a dependency cell defined it). Do not report style preferences,
missing docstrings, or purely stylistic issues.

Respond with a single JSON object of exactly this shape and nothing else:

{
  "findings": [
    {
      "cell_ids": [<int>, ...],
      "line": <int>,
      "label": "<the specific identifier/token the bug concerns, or \\"\\" if none applies>",
      "severity": "critical" | "warning",
      "message": "<concise explanation of the bug>"
    }
  ]
}

"cell_ids" lists every cell involved in the bug, ordered so the LAST entry
is the cell the bug should be anchored/displayed on - for a bug local to
one cell, this is just that cell's id. "line" is a 1-indexed line number
within that anchor cell. If you find no bugs, respond with {"findings": []}.
"""


def build_user_prompt(context: BugDetectionContext, include_dependency_graph: bool = True) -> str:
    sections = ["## Notebook cells"]
    for cell in context.cells:
        sections.append(f"### Cell {cell.cell_id}\n```python\n{cell.code}\n```")

    if include_dependency_graph:
        dependency_lines = []
        for cell_id in sorted(context.dependency_edges):
            deps = sorted(context.dependency_edges[cell_id])
            if deps:
                dep_list = ", ".join(f"Cell {d}" for d in deps)
                dependency_lines.append(f"- Cell {cell_id} depends on: {dep_list}")

        sections.append(
            "## Dependency graph\n"
            + ("\n".join(dependency_lines) if dependency_lines else "(no cross-cell dependencies detected)")
        )

    if context.deterministic_findings:
        finding_lines = [
            f"- Cell {f.cell_id}, line {f.line}: [{f.error_type}] {f.error_message}"
            for f in context.deterministic_findings
        ]
        sections.append("## Static analysis findings\n" + "\n".join(finding_lines))

    target_list = ", ".join(f"Cell {cid}" for cid in context.target_cell_ids)
    sections.append(f"## Cells to check\nFocus your review on: {target_list}")

    return "\n\n".join(sections)
