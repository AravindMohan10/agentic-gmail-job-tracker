# app/agent/policies.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from app.agent.state import AgentState, PlanStep, StructuredError, RequestSource


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    side_effect: bool
    required_keys: Set[str]
    optional_keys: Set[str]
    allow_unknown_keys: bool = True


TOOL_POLICIES: Dict[str, ToolPolicy] = {
    # Gmail (read-only)
    "gmail_search_messages": ToolPolicy(
        name="gmail_search_messages",
        side_effect=False,
        required_keys={"query"},
        optional_keys={"max_results", "after", "before"},
        allow_unknown_keys=True,
    ),
    "gmail_get_message": ToolPolicy(
        name="gmail_get_message",
        side_effect=False,
        required_keys={"message_id"},
        optional_keys={"format"},
        allow_unknown_keys=True,
    ),
    "gmail_get_thread": ToolPolicy(
        name="gmail_get_thread",
        side_effect=False,
        required_keys={"thread_id"},
        optional_keys={"format"},
        allow_unknown_keys=True,
    ),

    # Local DB write (side effect)
    "applications_upsert": ToolPolicy(
        name="applications_upsert",
        side_effect=True,
        required_keys={"rows"},
        optional_keys={"dedupe_key"},
        allow_unknown_keys=True,
    ),
    "applications_list": ToolPolicy(
        name="applications_list",
        side_effect=False,
        required_keys=set(),
        optional_keys={"limit", "status"},
        allow_unknown_keys=True,
    ),

    # Export file (side effect)
    "export_excel": ToolPolicy(
        name="export_excel",
        side_effect=True,
        required_keys={"path"},
        optional_keys={"sheet_name"},
        allow_unknown_keys=True,
    ),

    # Internal report step
    "write_report": ToolPolicy(
        name="write_report",
        side_effect=False,
        required_keys=set(),
        optional_keys={"format"},
        allow_unknown_keys=True,
    ),
}


SOURCE_RULES: Dict[RequestSource, Dict[str, Any]] = {
    RequestSource.API: {"allow_side_effects": True},
    RequestSource.CLI: {"allow_side_effects": True},
    RequestSource.WEB: {"allow_side_effects": True},
}


def validate_step(state: AgentState, step: PlanStep) -> Tuple[bool, Optional[StructuredError]]:
    policy = TOOL_POLICIES.get(step.action)
    if policy is None:
        return False, _err(
            error_type="POLICY_DENIED",
            message=f"Unknown or disallowed action: {step.action}",
            details={"allowed_actions": sorted(TOOL_POLICIES.keys())},
            step_id=step.stepId,
            attempt=None,
            retryable=False,
        )

    # source-based restriction for side effects
    src_rule = SOURCE_RULES.get(state.context.requestSource, {"allow_side_effects": False})
    if policy.side_effect and not src_rule.get("allow_side_effects", False):
        return False, _err(
            error_type="POLICY_DENIED",
            message=f"Side-effect tool '{step.action}' not allowed for requestSource={state.context.requestSource}.",
            details={"requestSource": str(state.context.requestSource), "tool": step.action},
            step_id=step.stepId,
            attempt=None,
            retryable=False,
        )

    # idempotency required for side effects
    if policy.side_effect:
        per_step_key = step.inputs.get("idempotency_key") if isinstance(step.inputs, dict) else None
        if not state.context.idempotencyKey and not per_step_key:
            return False, _err(
                error_type="POLICY_DENIED",
                message="Missing idempotencyKey for side-effecting step.",
                details={
                    "tool": step.action,
                    "hint": "Provide state.context.idempotencyKey or inputs.idempotency_key",
                },
                step_id=step.stepId,
                attempt=None,
                retryable=False,
            )

    if not isinstance(step.inputs, dict):
        return False, _err(
            error_type="VALIDATION_ERROR",
            message="Step inputs must be a dict.",
            details={"tool": step.action, "got_type": str(type(step.inputs))},
            step_id=step.stepId,
            attempt=None,
            retryable=False,
        )

    missing = sorted(list(policy.required_keys - set(step.inputs.keys())))
    if missing:
        return False, _err(
            error_type="VALIDATION_ERROR",
            message=f"Missing required inputs for tool '{step.action}'.",
            details={"missing": missing, "required": sorted(policy.required_keys)},
            step_id=step.stepId,
            attempt=None,
            retryable=False,
        )

    if not policy.allow_unknown_keys:
        allowed = policy.required_keys | policy.optional_keys
        unknown = sorted([k for k in step.inputs.keys() if k not in allowed])
        if unknown:
            return False, _err(
                error_type="VALIDATION_ERROR",
                message=f"Unknown input keys for tool '{step.action}'.",
                details={"unknown": unknown, "allowed": sorted(allowed)},
                step_id=step.stepId,
                attempt=None,
                retryable=False,
            )

    ok, err = _validate_tool_specific(step.action, step.inputs, step.stepId)
    if not ok:
        return False, err

    return True, None


def _validate_tool_specific(tool_name: str, inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    if tool_name == "gmail_search_messages":
        return _validate_gmail_search(inputs, step_id)
    if tool_name == "gmail_get_message":
        return _validate_gmail_get_message(inputs, step_id)
    if tool_name == "gmail_get_thread":
        return _validate_gmail_get_thread(inputs, step_id)
    if tool_name == "applications_upsert":
        return _validate_applications_upsert(inputs, step_id)
    if tool_name == "applications_list":
        return _validate_applications_list(inputs, step_id)
    if tool_name == "export_excel":
        return _validate_export_excel(inputs, step_id)
    if tool_name == "write_report":
        return True, None
    return True, None


def _validate_gmail_search(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    q = inputs.get("query")
    if not isinstance(q, str) or not q.strip():
        return False, _err("VALIDATION_ERROR", "gmail_search_messages.query must be a non-empty string.", {"query": q}, step_id, None, False)

    mr = inputs.get("max_results", 25)
    if not isinstance(mr, int) or mr < 1 or mr > 200:
        return False, _err("VALIDATION_ERROR", "gmail_search_messages.max_results out of range (1..200).", {"max_results": mr}, step_id, None, False)

    for k in ("after", "before"):
        v = inputs.get(k)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            return False, _err("VALIDATION_ERROR", f"gmail_search_messages.{k} must be a non-empty string if provided.", {k: v}, step_id, None, False)

    return True, None


def _validate_gmail_get_message(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    mid = inputs.get("message_id")
    if not isinstance(mid, str) or not mid.strip():
        return False, _err("VALIDATION_ERROR", "gmail_get_message.message_id must be a non-empty string.", {"message_id": mid}, step_id, None, False)

    fmt = inputs.get("format")
    if fmt is not None and fmt not in ("metadata", "full", "raw"):
        return False, _err("VALIDATION_ERROR", "gmail_get_message.format must be one of: metadata, full, raw.", {"format": fmt}, step_id, None, False)

    return True, None


def _validate_gmail_get_thread(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    tid = inputs.get("thread_id")
    if not isinstance(tid, str) or not tid.strip():
        return False, _err("VALIDATION_ERROR", "gmail_get_thread.thread_id must be a non-empty string.", {"thread_id": tid}, step_id, None, False)

    fmt = inputs.get("format")
    if fmt is not None and fmt not in ("metadata", "full"):
        return False, _err("VALIDATION_ERROR", "gmail_get_thread.format must be one of: metadata, full.", {"format": fmt}, step_id, None, False)

    return True, None


def _validate_applications_upsert(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    rows = inputs.get("rows")
    if not isinstance(rows, list) or not rows:
        return False, _err("VALIDATION_ERROR", "applications_upsert.rows must be a non-empty list.", {"rows_type": str(type(rows))}, step_id, None, False)

    if len(rows) > 1000:
        return False, _err("VALIDATION_ERROR", "applications_upsert.rows too large (max 1000 per call).", {"count": len(rows)}, step_id, None, False)

    for i, r in enumerate(rows[:50]):
        if not isinstance(r, dict):
            return False, _err("VALIDATION_ERROR", "applications_upsert.rows must contain dict rows.", {"bad_index": i, "row_type": str(type(r))}, step_id, None, False)

    return True, None


def _validate_applications_list(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    limit = inputs.get("limit", 50)
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        return False, _err("VALIDATION_ERROR", "applications_list.limit out of range (1..500).", {"limit": limit}, step_id, None, False)
    return True, None


def _validate_export_excel(inputs: Dict[str, Any], step_id: str) -> Tuple[bool, Optional[StructuredError]]:
    path = inputs.get("path")
    if not isinstance(path, str) or not path.strip():
        return False, _err("VALIDATION_ERROR", "export_excel.path must be a non-empty string.", {"path": path}, step_id, None, False)
    if not path.lower().endswith(".xlsx"):
        return False, _err("VALIDATION_ERROR", "export_excel.path must end with .xlsx", {"path": path}, step_id, None, False)
    return True, None


def _err(
    error_type: str,
    message: str,
    details: Dict[str, Any],
    step_id: Optional[str],
    attempt: Optional[int],
    retryable: bool,
) -> StructuredError:
    return StructuredError(
        errorType=error_type,
        errorMessage=message,
        errorDetails=details,
        stepId=step_id,
        attempt=attempt,
        retryable=retryable,
    )