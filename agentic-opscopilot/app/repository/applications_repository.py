# app/repository/applications_repository.py
"""
SQLite persistence for job application records.
Pure persistence layer: no business logic, no FastAPI.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.tools.email_extractor import ApplicationRecord


_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    company TEXT,
    role TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    event_date TEXT,
    confidence REAL,
    raw_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_PROCESSED_MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY
)
"""

_INSERT_PROCESSED_SQL = "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)"
_GET_PROCESSED_SQL = "SELECT 1 FROM processed_messages WHERE message_id = ? LIMIT 1"

_UPSERT_SQL = """
INSERT INTO applications (
    message_id, company, role, status, stage, event_date,
    confidence, raw_reason, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(message_id) DO UPDATE SET
    company = excluded.company,
    role = excluded.role,
    status = excluded.status,
    stage = excluded.stage,
    event_date = excluded.event_date,
    confidence = excluded.confidence,
    raw_reason = excluded.raw_reason,
    updated_at = excluded.updated_at
"""

_LIST_SQL = """
SELECT id, message_id, company, role, status, stage, event_date,
       confidence, raw_reason, created_at, updated_at
FROM applications
ORDER BY updated_at DESC
LIMIT ?
"""

_LIST_BY_STATUS_SQL = """
SELECT id, message_id, company, role, status, stage, event_date,
       confidence, raw_reason, created_at, updated_at
FROM applications
WHERE status = ?
ORDER BY updated_at DESC
LIMIT ?
"""

_GET_BY_MESSAGE_ID_SQL = """
SELECT id, message_id, company, role, status, stage, event_date,
       confidence, raw_reason, created_at, updated_at
FROM applications
WHERE message_id = ?
"""

_GET_BY_COMPANY_ROLE_SQL = """
SELECT id, message_id, company, role, status, stage, event_date,
       confidence, raw_reason, created_at, updated_at
FROM applications
WHERE company = ? AND ((role = ?) OR (role IS NULL AND ? IS NULL))
ORDER BY updated_at DESC
LIMIT 1
"""

_UPDATE_ROW_STATUS_SQL = """
UPDATE applications
SET status = ?, event_date = ?, message_id = ?, updated_at = ?
WHERE id = ?
"""

_COUNT_SQL = "SELECT COUNT(*) FROM applications"


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a dict with column names as keys."""
    return dict(zip([c[0] for c in cursor.description], row))


def init_db(db_path: str) -> None:
    """Create the applications and processed_messages tables if they do not exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_TABLE_SQL)
        conn.execute(_PROCESSED_MESSAGES_TABLE_SQL)
        conn.commit()


def mark_message_processed(db_path: str, message_id: str) -> None:
    """Record that we've processed this message_id (e.g. when we updated by company+role and didn't insert)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_INSERT_PROCESSED_SQL, (message_id,))
        conn.commit()


def is_message_processed(db_path: str, message_id: str) -> bool:
    """True if this message_id is in applications or in processed_messages (so we can skip it)."""
    if get_by_message_id(db_path, message_id) is not None:
        return True
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(_GET_PROCESSED_SQL, (message_id,))
        return cursor.fetchone() is not None


def count_applications(db_path: str) -> int:
    """Return number of rows in applications (for first-sync detection)."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(_COUNT_SQL)
        return cursor.fetchone()[0]


def get_by_company_role(
    db_path: str,
    company: Optional[str],
    role: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return one row matching (company, role) or None. Used to update existing application when we get rejection/offer."""
    if not company or not company.strip():
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            _GET_BY_COMPANY_ROLE_SQL,
            (company.strip(), role if role else None, role if role else None),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(cursor, row)


def update_application_status(
    db_path: str,
    row_id: int,
    status: str,
    event_date: Optional[str],
    message_id: str,
    updated_at: str,
) -> None:
    """Update an existing row's status, event_date, message_id, updated_at (e.g. rejection/offer)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            _UPDATE_ROW_STATUS_SQL,
            (status, event_date or None, message_id, updated_at, row_id),
        )
        conn.commit()


def upsert_application(db_path: str, record: ApplicationRecord) -> None:
    """
    If record has company (and optionally role) and we find an existing row for that (company, role),
    update that row's status/event_date/message_id (so rejection/offer updates the same application).
    Otherwise insert or update by message_id (idempotent).
    """
    now = datetime.now(timezone.utc).isoformat()
    company = record.company.strip() if (record.company and record.company.strip()) else None
    role = record.role.strip() if (record.role and record.role.strip()) else None

    if company:
        existing = get_by_company_role(db_path, company, role)
        if existing:
            update_application_status(
                db_path,
                row_id=existing["id"],
                status=record.status,
                event_date=record.event_date,
                message_id=existing["message_id"],
                updated_at=now,
            )
            mark_message_processed(db_path, record.source_message_id)
            return

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            _UPSERT_SQL,
            (
                record.source_message_id,
                record.company,
                record.role,
                record.status,
                record.stage,
                record.event_date,
                record.confidence,
                record.raw_reason,
                record.created_at,
                now,
            ),
        )
        conn.commit()


def list_applications(
    db_path: str,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return applications ordered by updated_at DESC. Optionally filter by status."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if status is not None and status.strip():
            cursor = conn.execute(_LIST_BY_STATUS_SQL, (status.strip(), limit))
        else:
            cursor = conn.execute(_LIST_SQL, (limit,))
        rows = cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]


def get_by_message_id(
    db_path: str,
    message_id: str,
) -> Optional[Dict[str, Any]]:
    """Return a single application by message_id, or None if not found."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(_GET_BY_MESSAGE_ID_SQL, (message_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(cursor, row)
