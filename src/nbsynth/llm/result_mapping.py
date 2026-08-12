from __future__ import annotations

import logging

from ..analyses.runner.analysis_results import ErrorInfo, PathResult, Result

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"critical", "warning"}


def map_findings_to_result(findings_json: dict, notebook_IR) -> Result:
    """
    Builds a Result from parsed LLM JSON output (see prompts.SYSTEM_PROMPT
    for the expected shape), validating each finding against notebook_IR.

    A finding that fails validation is dropped, with a logged warning,
    rather than raising - a single hallucinated finding must not break the
    rest of the result. No changes to ErrorInfo/PathResult/Result are
    needed; they're used exactly as the deterministic analyses use them.
    """
    result = Result()

    findings = findings_json.get("findings") if isinstance(findings_json, dict) else None
    if not isinstance(findings, list):
        logger.warning("LLM response missing a 'findings' list: %r", findings_json)
        return result

    for finding in findings:
        error_info = _build_error_info(finding, notebook_IR)
        if error_info is None:
            continue
        result.add_path_result(
            PathResult(path=list(finding["cell_ids"]), error_infos=[error_info])
        )

    return result


def _build_error_info(finding, notebook_IR) -> ErrorInfo | None:
    if not isinstance(finding, dict):
        logger.warning("Skipping non-dict finding: %r", finding)
        return None

    cell_ids = finding.get("cell_ids")
    if (
        not isinstance(cell_ids, list)
        or not cell_ids
        or not all(isinstance(cid, int) for cid in cell_ids)
    ):
        logger.warning("Skipping finding with invalid cell_ids: %r", finding)
        return None

    anchor_cell_id = cell_ids[-1]
    if any(cid not in notebook_IR for cid in cell_ids):
        logger.warning("Skipping finding referencing unknown cell(s): %r", finding)
        return None

    line = finding.get("line")
    anchor_code = notebook_IR[anchor_cell_id].cell_code
    line_count = len(anchor_code.splitlines()) or 1
    if not isinstance(line, int) or isinstance(line, bool) or not (1 <= line <= line_count):
        logger.warning("Skipping finding with out-of-range line: %r", finding)
        return None

    severity = finding.get("severity")
    if severity not in _VALID_SEVERITIES:
        logger.warning("Skipping finding with invalid severity: %r", finding)
        return None

    label = finding.get("label", "")
    if not isinstance(label, str):
        label = ""

    message = finding.get("message")
    if not isinstance(message, str) or not message:
        logger.warning("Skipping finding with missing message: %r", finding)
        return None

    return ErrorInfo(
        cell_id=anchor_cell_id,
        line=line,
        label=label,
        error_type=f"LLM_{severity.upper()}",
        error_message=message,
    )
