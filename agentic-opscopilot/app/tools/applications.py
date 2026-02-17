# app/tools/applications.py
"""
Agent-facing tools for applications store: upsert and list.
Delegates to repository; db_path from env APPLICATIONS_DB_PATH.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.tools.email_extractor import ApplicationRecord
from app.repository.applications_repository import (
    list_applications as _repo_list,
    upsert_application as _repo_upsert,
)

_DEFAULT_DB_PATH = "applications.db"


def _get_db_path() -> str:
    return os.environ.get("APPLICATIONS_DB_PATH", _DEFAULT_DB_PATH)


def _dict_to_record(row: Dict[str, Any]) -> ApplicationRecord:
    """Build ApplicationRecord from dict; accept message_id as alias for source_message_id."""
    normalized = dict(row)
    if "source_message_id" not in normalized and "message_id" in normalized:
        normalized["source_message_id"] = normalized["message_id"]
    return ApplicationRecord(**normalized)


def applications_upsert(
    *,
    rows: List[Dict[str, Any]],
    dedupe_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upsert application records. Uses message_id (source_message_id) as unique key.
    Idempotent; duplicate message_id updates existing row.
    dedupe_key is accepted by policy but not used (repository uses message_id).
    """
    db_path = _get_db_path()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            record = _dict_to_record(row)
        except Exception:
            continue
        _repo_upsert(db_path, record)
    return {"upserted": len(rows)}


def applications_list(
    *,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List application records, optionally filtered by status. Ordered by updated_at DESC."""
    db_path = _get_db_path()
    return _repo_list(db_path, limit=limit, status=status)
