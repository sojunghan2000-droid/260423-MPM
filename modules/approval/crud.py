"""Approval CRUD operations."""

import json
import uuid
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

from shared.helpers import now_str
from db.models import settings_get
from modules.request.crud import req_update_status


def routing_get(con: sqlite3.Connection) -> Dict[str, List[str]]:
    """Get the approval routing configuration."""
    try:
        return json.loads(settings_get(con, "approval_routing_json", "{}"))
    except Exception:
        return {"IN": ["공사"], "OUT": ["안전", "공사"]}


def approvals_create_default(con: sqlite3.Connection, rid: str, kind: str) -> None:
    """Create default approval steps for a request based on its kind."""
    roles = routing_get(con).get(kind, ["공사"]) or ["공사"]
    cur = con.cursor()
    for i, role in enumerate(roles, start=1):
        cur.execute(
            "INSERT INTO approvals(id, req_id, step_no, role_required, status, created_at) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, rid, i, role, "PENDING", now_str()),
        )
    con.commit()


def approvals_inbox(
    con: sqlite3.Connection, user_role: str, is_admin: bool,
    project_id: str = "",
) -> List[Dict[str, Any]]:
    """Get pending approvals for the current user's inbox."""
    import streamlit as st
    pid = project_id or st.session_state.get("PROJECT_ID", "")
    cur = con.cursor()
    base = """
    SELECT a.*, r.kind, r.company_name, r.item_name, r.date, r.time_from, r.time_to, r.gate, r.status AS req_status
    FROM approvals a
    JOIN requests r ON a.req_id=r.id
    WHERE r.project_id=? AND a.status='PENDING' AND a.step_no = (
      SELECT MIN(a2.step_no) FROM approvals a2 WHERE a2.req_id=a.req_id AND a2.status='PENDING'
    )
    """
    if is_admin:
        q = base + " ORDER BY r.created_at DESC, a.step_no ASC"
        cur.execute(q, (pid,))
    else:
        q = base + " AND a.role_required=? ORDER BY r.created_at DESC, a.step_no ASC"
        cur.execute(q, (pid, user_role))
    return [dict(x) for x in cur.fetchall()]


def approvals_for_req(con: sqlite3.Connection, rid: str) -> List[Dict[str, Any]]:
    """Get all approval steps for a given request."""
    cur = con.cursor()
    cur.execute("SELECT * FROM approvals WHERE req_id=? ORDER BY step_no ASC", (rid,))
    return [dict(x) for x in cur.fetchall()]


def approval_mark(
    con: sqlite3.Connection,
    approval_id: str,
    action: str,
    signer_name: str,
    signer_role: str,
    sign_path: Optional[str],
    stamp_path: Optional[str],
    reject_reason: str = "",
) -> Tuple[str, str]:
    """Mark an approval as APPROVED or REJECTED."""
    cur = con.cursor()
    cur.execute("SELECT req_id, status FROM approvals WHERE id=?", (approval_id,))
    row = cur.fetchone()
    if not row:
        return "", "승인항목을 찾지 못했습니다."
    rid = row["req_id"]
    if row["status"] != "PENDING":
        return rid, "이미 처리된 승인입니다."
    if action == "APPROVE":
        cur.execute(
            """
            UPDATE approvals SET status='APPROVED', signer_name=?, signer_role=?, sign_png_path=?, stamp_png_path=?, signed_at=?
            WHERE id=?
            """,
            (signer_name, signer_role, sign_path, stamp_path, now_str(), approval_id),
        )
        con.commit()
        cur.execute("SELECT COUNT(*) AS cnt FROM approvals WHERE req_id=? AND status='PENDING'", (rid,))
        left = cur.fetchone()["cnt"]
        if left == 0:
            req_update_status(con, rid, "APPROVED")
            return rid, "최종 승인 완료"
        return rid, "승인 완료(다음 승인자 대기)"
    cur.execute(
        """
        UPDATE approvals SET status='REJECTED', signer_name=?, signer_role=?, reject_reason=?, signed_at=?
        WHERE id=?
        """,
        (signer_name, signer_role, reject_reason, now_str(), approval_id),
    )
    con.commit()
    req_update_status(con, rid, "REJECTED")
    return rid, "반려 처리 완료"
