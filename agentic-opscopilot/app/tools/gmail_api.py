from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError


# Public Gmail API wrappers

def search_messages(
    service: Resource,
    *,
    query: str,
    max_results: int = 25,
) -> List[Dict[str, str]]:
    """
    Execute Gmail search query and return raw message ID objects.

    Returns:
        [
            {"id": "...", "threadId": "..."},
            ...
        ]
    """
    try:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results,
            )
            .execute()
        )
    except HttpError as e:
        raise RuntimeError(f"Gmail search failed: {e}") from e

    return response.get("messages", [])


def get_message_metadata(
    service: Resource,
    message_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch metadata-only view of a message.
    """
    try:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
            .execute()
        )
    except HttpError:
        return None

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    return {
        "message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date": _parse_date(_get_header(headers, "Date")),
        "snippet": msg.get("snippet"),
        "internal_timestamp_ms": msg.get("internalDate"),
    }


def get_message_full(
    service: Resource,
    message_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch full message including decoded body.
    """
    try:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )
    except HttpError:
        return None

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    text, html = _extract_body(payload)

    return {
        "message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date": _parse_date(_get_header(headers, "Date")),
        "text": text,
        "html": html,
        "internal_timestamp_ms": msg.get("internalDate"),
    }


# Internal helpers

def _get_header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    name_lower = name.lower()
    for header in headers or []:
        if (header.get("name") or "").lower() == name_lower:
            return header.get("value")
    return None


def _decode_base64url(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode((data + padding).encode("utf-8"))
    return raw.decode("utf-8", errors="replace")


def _extract_body(payload: Dict[str, Any]) -> Tuple[str, str]:
    """
    Extract text/plain and text/html from Gmail message payload.
    """
    text = ""
    html = ""

    def walk(parts: List[Dict[str, Any]]):
        nonlocal text, html

        for part in parts:
            mime = part.get("mimeType")
            body = part.get("body", {})
            data = body.get("data")

            if mime == "text/plain" and data and not text:
                text = _decode_base64url(data)

            elif mime == "text/html" and data and not html:
                html = _decode_base64url(data)

            if "parts" in part:
                walk(part["parts"])

    if "parts" in payload:
        walk(payload["parts"])
    else:
        body = payload.get("body", {}).get("data")
        if body:
            text = _decode_base64url(body)

    return text, html


def _parse_date(raw_date: Optional[str]) -> Optional[str]:
    if not raw_date:
        return None

    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(raw_date)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat()

    except Exception:
        return None