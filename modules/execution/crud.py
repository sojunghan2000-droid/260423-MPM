"""Execution CRUD operations."""

import json
import uuid
import sqlite3
from typing import Dict, Any, List, Optional

from shared.helpers import now_str, file_sha1
from db.connection import path_output
from config import EXEC_REQUIRED_PHOTOS


def photo_exists_same(con: sqlite3.Connection, rid: str, slot_key: str, file_hash: str) -> bool:
    """Check if a photo with the same hash already exists for the given slot."""
    cur = con.cursor()
    cur.execute(
        "SELECT 1 FROM photos WHERE req_id=? AND slot_key=? AND file_hash=? LIMIT 1",
        (rid, slot_key, file_hash),
    )
    return cur.fetchone() is not None


def photo_add(
    con: sqlite3.Connection,
    rid: str,
    slot_key: str,
    label: str,
    file_bytes: bytes,
    suffix: str = ".jpg",
) -> str:
    """Add a photo for a request. Returns file path or empty string if duplicate."""
    fhash = file_sha1(file_bytes)
    if photo_exists_same(con, rid, slot_key, fhash):
        return ""
    out = path_output()["photo"]
    fname = f"{rid}{slot_key}{uuid.uuid4().hex[:8]}{suffix}"
    fpath = out / fname
    fpath.write_bytes(file_bytes)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO photos(id, req_id, slot_key, label, file_path, file_hash, created_at) VALUES(?,?,?,?,?,?,?)",
        (uuid.uuid4().hex, rid, slot_key, label, str(fpath), fhash, now_str()),
    )
    con.commit()
    return str(fpath)


def photo_delete_slot(con: sqlite3.Connection, rid: str, slot_key: str) -> None:
    """Delete photo record(s) for a given slot and remove file(s) from disk."""
    cur = con.cursor()
    cur.execute("SELECT file_path FROM photos WHERE req_id=? AND slot_key=?", (rid, slot_key))
    rows = cur.fetchall()
    for row in rows:
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    cur.execute("DELETE FROM photos WHERE req_id=? AND slot_key=?", (rid, slot_key))
    con.commit()


def photos_for_req(con: sqlite3.Connection, rid: str) -> List[Dict[str, Any]]:
    """Get all photos for a given request."""
    cur = con.cursor()
    cur.execute("SELECT * FROM photos WHERE req_id=? ORDER BY created_at ASC", (rid,))
    return [dict(x) for x in cur.fetchall()]


def required_photos_ok(con: sqlite3.Connection, rid: str) -> bool:
    """Check if all required photos have been uploaded for a request."""
    keys = {p["slot_key"] for p in photos_for_req(con, rid)}
    return all(k in keys for k, _ in EXEC_REQUIRED_PHOTOS)


def execution_upsert(
    con: sqlite3.Connection,
    rid: str,
    executed_by: str,
    executed_role: str,
    check_json: Dict[str, Any],
    notes: str,
) -> None:
    """Insert or update an execution record."""
    ok = 1 if required_photos_ok(con, rid) else 0
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO executions(req_id, executed_by, executed_role, executed_at, check_json, required_photo_ok, notes)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(req_id) DO UPDATE SET executed_by=excluded.executed_by, executed_role=excluded.executed_role,
          executed_at=excluded.executed_at, check_json=excluded.check_json, required_photo_ok=excluded.required_photo_ok, notes=excluded.notes
        """,
        (rid, executed_by, executed_role, now_str(), json.dumps(check_json, ensure_ascii=False), ok, notes),
    )
    con.commit()


def execution_get(con: sqlite3.Connection, rid: str) -> Optional[Dict[str, Any]]:
    """Get the execution record for a request."""
    cur = con.cursor()
    cur.execute("SELECT * FROM executions WHERE req_id=?", (rid,))
    r = cur.fetchone()
    return dict(r) if r else None


def final_approved_signs(con: sqlite3.Connection, rid: str) -> List[Dict[str, Any]]:
    """Get all approved signatures for a request."""
    cur = con.cursor()
    cur.execute("SELECT * FROM approvals WHERE req_id=? AND status='APPROVED' ORDER BY step_no ASC", (rid,))
    return [dict(x) for x in cur.fetchall()]
