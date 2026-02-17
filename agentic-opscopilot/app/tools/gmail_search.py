from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.tools.gmail_client import get_gmail_service
from app.tools.gmail_api import search_messages, get_message_metadata


DEFAULT_QUERY = "(application OR applied OR interview OR recruiter)"


def gmail_search_messages(
    *,
    query: Optional[str] = None,
    max_results: int = 25,
    after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Agent-facing Gmail search tool.

    Responsibilities:
    - Build safe Gmail query
    - Fetch message IDs
    - Retrieve metadata
    - Return structured summaries

    No extraction.
    No persistence.
    No agent state mutation.
    """

    service = get_gmail_service()

    full_query = _build_query(query or DEFAULT_QUERY, after)

    raw_messages = search_messages(
        service,
        query=full_query,
        max_results=max_results,
    )

    results: List[Dict[str, Any]] = []

    for msg in raw_messages:
        msg_id = msg.get("id")
        if not msg_id:
            continue

        metadata = get_message_metadata(service, msg_id)
        if metadata:
            results.append(metadata)

    return results


# Internal query builder

def _build_query(base_query: str, after: Optional[str]) -> str:
    """
    Construct Gmail-compatible query string.

    If `after` is provided, it must be YYYY/MM/DD.
    """

    parts = [base_query.strip()]

    if after:
        parts.append(f"after:{after}")

    return " ".join(parts)