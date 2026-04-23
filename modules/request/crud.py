"""Request CRUD operations."""

import uuid
import sqlite3
from typing import Dict, Any, List, Optional

from shared.helpers import now_str


def req_insert(con: sqlite3.Connection, data: Dict[str, Any]) -> str:
    """Insert a new request and return its ID."""
    rid = uuid.uuid4().hex
    cur = con.cursor()
    cols = [
        "id", "created_at", "updated_at", "status", "kind", "project_id",
        "company_name", "item_name", "item_type", "work_type", "date", "time_from", "time_to",
        "gate", "vehicle_type", "vehicle_ton", "vehicle_count",
        "driver_name", "driver_phone",
        "worker_supervisor", "worker_guide", "worker_manager",
        "loading_method", "notes",
        "requester_name", "requester_role", "risk_level", "sic_training_url",
    ]
    row = {
        "id": rid,
        "created_at": now_str(),
        "updated_at": now_str(),
        "status": "PENDING_APPROVAL",
        **{k: data.get(k) for k in cols if k not in ["id", "created_at", "updated_at", "status"]},
    }
    cur.execute(
        f"INSERT INTO requests({','.join(cols)}) VALUES({','.join(['?'] * len(cols))})",
        [row.get(c) for c in cols],
    )
    con.commit()
    return rid


def req_get(con: sqlite3.Connection, rid: str) -> Optional[Dict[str, Any]]:
    """Get a single request by ID, including day_seq for display ID."""
    cur = con.cursor()
    cur.execute(
        """
        WITH numbered AS (
          SELECT *, ROW_NUMBER() OVER (
            PARTITION BY project_id, date
            ORDER BY date, created_at, id
          ) AS day_seq
          FROM requests
        )
        SELECT * FROM numbered WHERE id=?
        """,
        (rid,),
    )
    r = cur.fetchone()
    return dict(r) if r else None


def req_list(
    con: sqlite3.Connection,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 300,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List requests with optional filters, including day_seq for display ID."""
    import streamlit as st
    pid = project_id or st.session_state.get("PROJECT_ID", "")
    w: List[str] = []
    args: List[Any] = []
    if pid:
        w.append("project_id=?")
        args.append(pid)
    if status:
        w.append("status=?")
        args.append(status)
    if kind:
        w.append("kind=?")
        args.append(kind)
    where_clause = (" WHERE " + " AND ".join(w)) if w else ""
    q = f"""
        WITH numbered AS (
          SELECT *, ROW_NUMBER() OVER (
            PARTITION BY project_id, date
            ORDER BY date, created_at, id
          ) AS day_seq
          FROM requests
        )
        SELECT * FROM numbered{where_clause}
        ORDER BY created_at DESC LIMIT ?
    """
    args.append(limit)
    cur = con.cursor()
    cur.execute(q, args)
    return [dict(x) for x in cur.fetchall()]


def req_update_status(con: sqlite3.Connection, rid: str, status: str) -> None:
    """Update the status of a request."""
    cur = con.cursor()
    cur.execute("UPDATE requests SET status=?, updated_at=? WHERE id=?", (status, now_str(), rid))
    con.commit()


def req_update_time(con: sqlite3.Connection, rid: str, time_from: str, time_to: str) -> None:
    """Update time_from / time_to of a request."""
    cur = con.cursor()
    cur.execute(
        "UPDATE requests SET time_from=?, time_to=?, updated_at=? WHERE id=?",
        (time_from, time_to, now_str(), rid),
    )
    con.commit()


def req_delete(con: sqlite3.Connection, rid: str) -> None:
    """Delete a request and all associated records (cascade)."""
    cur = con.cursor()
    cur.execute("DELETE FROM approvals   WHERE req_id=?", (rid,))
    cur.execute("DELETE FROM executions  WHERE req_id=?", (rid,))
    cur.execute("DELETE FROM photos      WHERE req_id=?", (rid,))
    cur.execute("DELETE FROM outputs     WHERE req_id=?", (rid,))
    cur.execute("DELETE FROM schedules   WHERE req_id=?", (rid,))
    cur.execute("DELETE FROM requests    WHERE id=?",     (rid,))
    con.commit()
