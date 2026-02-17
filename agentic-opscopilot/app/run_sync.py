# app/run_sync.py
"""
Scheduled sync pipeline: Gmail → extract → upsert → export Excel.
Run every 12 hours (via cron or scheduler). No user input.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.repository.applications_repository import count_applications, init_db, is_message_processed
from app.tools.applications import applications_upsert
from app.tools.email_extractor import (
    ApplicationRecord,
    extract_application_records_batch,
    is_candidate_email,
)
from app.tools.export_excel import export_excel
from app.tools.gmail_get_message import gmail_get_message
from app.tools.gmail_search import gmail_search_messages


# Config from env

def _config() -> Dict[str, Any]:
    # Default: current day only (so first sync and every sync stay within daily Gemini quota)
    gmail_after = os.environ.get("SYNC_GMAIL_AFTER") or None
    if not (gmail_after and gmail_after.strip()):
        gmail_after = datetime.now().strftime("%Y/%m/%d")

    return {
        "db_path": os.environ.get("APPLICATIONS_DB_PATH", "applications.db"),
        "excel_path": os.environ.get("SYNC_EXCEL_PATH", "applications.xlsx"),
        "gmail_query": os.environ.get("SYNC_GMAIL_QUERY") or None,
        "gmail_after": gmail_after,
        "max_messages": int(os.environ.get("SYNC_MAX_MESSAGES", "100")),
        "max_extractions_per_run": max(1, min(int(os.environ.get("SYNC_MAX_EXTRACTIONS_PER_RUN", "80")), 200)),
        "batch_size": max(1, min(int(os.environ.get("SYNC_BATCH_SIZE", "5")), 20)),
        "log_path": os.environ.get("SYNC_LOG_PATH") or None,
    }


def _validate_setup(cfg: Dict[str, Any]) -> None:
    """Fail fast with clear errors if required setup is missing."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Set it in your environment or .env. "
            "Get a key at https://ai.google.dev/"
        )
    creds_path = os.environ.get("GMAIL_CREDENTIALS_FILE", "credentials.json")
    if not os.path.exists(creds_path):
        raise RuntimeError(
            f"Gmail credentials not found at {creds_path}. "
            "Download OAuth client credentials from Google Cloud Console, "
            "save as credentials.json, or set GMAIL_CREDENTIALS_FILE. See README."
        )


# Pipeline

def run_sync() -> Dict[str, Any]:
    """
    Run the full sync once:
    1. Validate setup (API key, credentials)
    2. Init DB
    3. Search Gmail for application-related messages
    4. For each: skip if in DB → get full message → extract → collect records
    5. Upsert all records
    6. Export to Excel
    7. Optionally append metrics to SYNC_LOG_PATH
    """
    cfg = _config()
    _validate_setup(cfg)

    db_path = cfg["db_path"]
    excel_path = cfg["excel_path"]
    max_messages = max(1, min(cfg["max_messages"], 500))
    max_extractions = cfg["max_extractions_per_run"]
    batch_size = cfg["batch_size"]
    log_path = cfg["log_path"]

    if not excel_path.lower().endswith(".xlsx"):
        excel_path = excel_path.rstrip("/") + ".xlsx"

    os.environ.setdefault("APPLICATIONS_DB_PATH", db_path)

    started_at = time.perf_counter()
    init_db(db_path)

    # First sync (empty DB): use last 7 days so user gets recent history. Subsequent: today only (stay under API limits).
    if count_applications(db_path) == 0:
        gmail_after = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
    else:
        gmail_after = cfg["gmail_after"]

    messages_meta = gmail_search_messages(
        query=cfg["gmail_query"],
        max_results=max_messages,
        after=gmail_after,
    )

    # Collect up to max_extractions unprocessed messages and get full body
    to_process: List[Dict[str, Any]] = []
    skipped_already_seen = 0
    for meta in messages_meta:
        if len(to_process) >= max_extractions:
            break
        message_id = meta.get("message_id") or meta.get("id")
        if not message_id:
            continue
        if is_message_processed(db_path, message_id):
            skipped_already_seen += 1
            continue
        full_message = gmail_get_message(message_id=message_id)
        if not full_message:
            continue
        to_process.append(full_message)

    # Filter to candidates only, then batch extract (fewer LLM calls)
    candidates = [m for m in to_process if is_candidate_email(m)]
    records: List[ApplicationRecord] = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        batch_records = extract_application_records_batch(batch)
        records.extend(batch_records)

    if records:
        rows = [r.model_dump() for r in records]
        applications_upsert(rows=rows)

    export_excel(path=excel_path, sheet_name="Applications")

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    result = {
        "messages_seen": len(messages_meta),
        "skipped_already_seen": skipped_already_seen,
        "records_extracted": len(records),
        "excel_path": excel_path,
        "duration_ms": duration_ms,
        "status": "success",
    }

    if log_path:
        _append_run_log(log_path, result)

    return result


def _append_run_log(log_path: str, result: Dict[str, Any]) -> None:
    """Append one line per run for metrics (timestamp, duration_ms, records, etc.)."""
    ts = datetime.now(timezone.utc).isoformat()
    line = (
        f"ts={ts} duration_ms={result['duration_ms']} messages_seen={result['messages_seen']} "
        f"skipped={result['skipped_already_seen']} records_extracted={result['records_extracted']} "
        f"status={result['status']}\n"
    )
    try:
        with open(log_path, "a") as f:
            f.write(line)
    except OSError:
        pass


def main() -> None:
    try:
        result = run_sync()
        print(
            f"Sync done: {result['records_extracted']} records from {result['messages_seen']} messages "
            f"(skipped {result['skipped_already_seen']} already seen) in {result['duration_ms']}ms → {result['excel_path']}"
        )
    except Exception as e:
        print(f"Sync failed: {e}", file=sys.stderr)
        if os.environ.get("SYNC_LOG_PATH"):
            try:
                with open(os.environ["SYNC_LOG_PATH"], "a") as f:
                    f.write(
                        f"ts={datetime.now(timezone.utc).isoformat()} status=failed error={e!r}\n"
                    )
            except OSError:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
