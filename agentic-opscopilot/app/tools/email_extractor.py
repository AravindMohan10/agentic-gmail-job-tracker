from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError
from app.tools.gemini_client import extract_structured_json, extract_structured_json_array


# ApplicationRecord: contract between extraction and persistence

class ApplicationRecord(BaseModel):
    """
    Canonical structured representation of a job application email.
    This is the contract between extraction and persistence layers.
    """

    company: Optional[str] = None
    role: Optional[str] = None

    status: Literal[
        "applied",
        "interview",
        "rejected",
        "offer",
        "other",
    ]

    stage: Optional[str] = None
    event_date: Optional[str] = None  # ISO string

    source_message_id: str

    confidence: float = Field(ge=0.0, le=1.0)

    raw_reason: Optional[str] = None

    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Candidate filtering: keywords and known ATS domains

APPLICATION_KEYWORDS = [
    "application",
    "applied",
    "interview",
    "recruiter",
    "talent acquisition",
    "hiring",
    "offer",
    "regret to inform",
    "not moving forward",
]

KNOWN_ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "ashbyhq.com",
    "smartrecruiters.com",
]

HISTORICAL_MEMORY = {
    "trusted_domains": set(),
    "known_companies": set(),
    "historical_senders": set(),
}


def extract_application_record(
    message: Dict[str, Any],
) -> Optional[ApplicationRecord]:
    """
    Hybrid pipeline:

    1. Candidate filter (cheap heuristics)
    2. LLM extraction
    3. Validation + normalization
    4. Rule fallback if needed
    """

    if not message or not isinstance(message, dict):
        return None

    message_id = message.get("message_id")
    if not message_id:
        return None

    if not _is_candidate_email(message):
        return None

    extraction_input = _build_extraction_input(message)

    llm_output = _extract_with_llm(
        extraction_input,
        message_id=message_id,
    )

    record = _validate_and_normalize(llm_output)

    if record:
        _update_memory(record, message)
        return record

    fallback_record = _fallback_rule_based(
        message,
        message_id=message_id,
    )

    if fallback_record:
        _update_memory(fallback_record, message)

    return fallback_record


def is_candidate_email(message: Dict[str, Any]) -> bool:
    """True if the message looks like a job-application email (for batching / pre-filter)."""
    return _is_candidate_email(message)


def _is_candidate_email(message: Dict[str, Any]) -> bool:
    subject = (message.get("subject") or "").lower()
    sender = (message.get("from") or "").lower()
    snippet = (message.get("snippet") or "").lower()
    body_preview = (message.get("text") or "")[:500].lower()

    combined = f"{subject} {snippet} {body_preview}"

    # 1️⃣ Keyword signal
    if any(k in combined for k in APPLICATION_KEYWORDS):
        return True

    # 2️⃣ ATS domain signal
    for domain in KNOWN_ATS_DOMAINS:
        if domain in sender:
            return True

    # 3️⃣ Historical memory signal
    sender_domain = sender.split("@")[-1] if "@" in sender else None

    if sender in HISTORICAL_MEMORY["historical_senders"]:
        return True

    if sender_domain in HISTORICAL_MEMORY["trusted_domains"]:
        return True

    return False


def _build_extraction_input(message: Dict[str, Any]) -> str:
    subject = message.get("subject") or ""
    sender = message.get("from") or ""
    snippet = message.get("snippet") or ""
    body_text = message.get("text") or ""

    body_text = body_text[:4000]  # prevent token explosion

    return (
        f"From: {sender}\n"
        f"Subject: {subject}\n\n"
        f"Snippet:\n{snippet}\n\n"
        f"Body:\n{body_text}"
    )


def _build_batch_extraction_input(messages: List[Dict[str, Any]]) -> str:
    """Build one prompt with multiple emails, each with message_id for source_message_id."""
    parts = []
    for i, message in enumerate(messages, 1):
        msg_id = message.get("message_id") or ""
        parts.append(f"---EMAIL {i} (message_id: {msg_id})---")
        parts.append(_build_extraction_input(message))
        parts.append("")
    return "\n".join(parts)


def _extract_with_llm(
    input_text: str,
    message_id: str,
) -> Dict[str, Any]:

    prompt = f"""
You are extracting structured job application information.

Return ONLY valid JSON.

Fields:
- company (string or null)
- role (string or null)
- status (one of: applied, interview, rejected, offer, other)
- stage (string or null)
- event_date (ISO 8601 string or null)
- confidence (float between 0 and 1)
- raw_reason (short explanation)

If unsure, set confidence below 0.6.

Email:
{input_text}
"""

    result = extract_structured_json(prompt)
    result["source_message_id"] = message_id
    return result


def _extract_batch_with_llm(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One LLM call for multiple emails. Returns list of raw dicts (one per email in order)."""
    if not messages:
        return []
    batch_text = _build_batch_extraction_input(messages)
    message_ids = [m.get("message_id") or "" for m in messages]

    prompt = f"""
You are extracting structured job application information for MULTIPLE emails below.

Return a JSON ARRAY with one object per email, in the SAME ORDER as the emails.
Each object must have:
- company (string or null)
- role (string or null)
- status (one of: applied, interview, rejected, offer, other)
- stage (string or null)
- event_date (ISO 8601 string or null)
- confidence (float 0-1)
- raw_reason (short explanation or null)
- source_message_id (copy the message_id from that email's header exactly)

If an email is not about a job application, use status "other" and confidence 0.5.
If unsure, set confidence below 0.6.

Emails:
{batch_text}
"""

    raw_list = extract_structured_json_array(prompt)
    out = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            continue
        if "source_message_id" not in item and i < len(message_ids):
            item["source_message_id"] = message_ids[i]
        out.append(item)
    return out


def extract_application_records_batch(
    messages: List[Dict[str, Any]],
) -> List[ApplicationRecord]:
    """
    Extract multiple emails in one LLM call. Returns only valid, confident records.
    Caller should pass only candidate emails (e.g. after _is_candidate_email).
    """
    if not messages:
        return []
    raw_list = _extract_batch_with_llm(messages)
    records: List[ApplicationRecord] = []
    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            continue
        if "source_message_id" not in raw and i < len(messages):
            raw["source_message_id"] = messages[i].get("message_id") or ""
        record = _validate_and_normalize(raw)
        if record:
            if i < len(messages):
                _update_memory(record, messages[i])
            records.append(record)
    return records


def _validate_and_normalize(
    raw_output: Dict[str, Any],
) -> Optional[ApplicationRecord]:

    try:
        record = ApplicationRecord(**raw_output)
    except ValidationError:
        return None

    # Reject low confidence
    if record.confidence < 0.6:
        return None

    # Allow records without company/role ONLY if status is clear and confidence is good
    clear_statuses = {"applied", "rejected", "interview", "offer"}
    if not record.company and not record.role:
        if record.status not in clear_statuses or record.confidence < 0.6:
            return None

    return record


REJECTION_PATTERNS = [
    "regret to inform",
    "unfortunately",
    "not moving forward",
    "moving forward with other candidates",
]

INTERVIEW_PATTERNS = [
    "interview",
    "schedule a call",
    "phone screen",
]

OFFER_PATTERNS = [
    "offer letter",
    "pleased to offer",
]

APPLIED_PATTERNS = [
    "application received",
    "thank you for applying",
    "application submitted",
    "application confirmation",
    "we received your application",
    "your application has been received",
]


def _fallback_rule_based(
    message: Dict[str, Any],
    message_id: str,
) -> Optional[ApplicationRecord]:

    subject = (message.get("subject") or "").lower()
    snippet = (message.get("snippet") or "").lower()
    body = (message.get("text") or "").lower()

    combined = f"{subject} {snippet} {body[:800]}"

    status = None

    if any(p in combined for p in REJECTION_PATTERNS):
        status = "rejected"
    elif any(p in combined for p in OFFER_PATTERNS):
        status = "offer"
    elif any(p in combined for p in INTERVIEW_PATTERNS):
        status = "interview"
    elif any(p in combined for p in APPLIED_PATTERNS):
        status = "applied"

    if not status:
        return None

    return ApplicationRecord(
        company=None,
        role=None,
        status=status,
        stage=None,
        event_date=None,
        source_message_id=message_id,
        confidence=0.6,
        raw_reason="Fallback heuristic pattern match",
    )


def _update_memory(record: ApplicationRecord, message: Dict[str, Any]) -> None:
    sender = (message.get("from") or "").lower()

    if sender:
        HISTORICAL_MEMORY["historical_senders"].add(sender)

        if "@" in sender:
            domain = sender.split("@")[-1]
            HISTORICAL_MEMORY["trusted_domains"].add(domain)

    if record.company:
        HISTORICAL_MEMORY["known_companies"].add(record.company)