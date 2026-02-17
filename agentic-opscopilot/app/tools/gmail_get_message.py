from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools.gmail_client import get_gmail_service
from app.tools.gmail_api import get_message_full


def gmail_get_message(
    *,
    message_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Agent-facing tool to fetch full Gmail message content.

    Responsibilities:
    - Establish Gmail connection
    - Fetch full message (text + html)
    - Return structured dict

    No extraction.
    No persistence.
    No state mutation.
    """

    if not message_id or not isinstance(message_id, str):
        return None

    service = get_gmail_service()

    message = get_message_full(
        service,
        message_id=message_id,
    )

    return message