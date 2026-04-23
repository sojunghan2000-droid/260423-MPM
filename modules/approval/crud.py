"""Approval CRUD operations (Supabase-backed)."""

import json
import uuid
from typing import Dict, Any, List, Optional, Tuple

from supabase import Client
from shared.helpers import now_str
from db.models import settings_get
from modules.request.crud import req_update_status


def routing_get(con: Client) -> Dict[str, List[str]]:
    try:
        return json.loads(settings_get(con, "approval_routing_json", "{}"))
    except Exception:
        return {"IN": ["공사"], "OUT": ["안전", "공사"]}


def approvals_create_default(con: Client, rid: str, kind: str) -> None:
    roles = routing_get(con).get(kind, ["공사"]) or ["공사"]
    rows = []
    for i, role in enumerate(roles, start=1):
        rows.append({
            "id":            uuid.uuid4().hex,
            "req_id":        rid,
            "step_no":       i,
            "role_required": role,
            "status":        "PENDING",
            "created_at":    now_str(),
        })
    if rows:
        con.table("approvals").insert(rows).execute()


def approvals_inbox(
    con: Client, user_role: str, is_admin: bool,
    project_id: str = "",
) -> List[Dict[str, Any]]:
    """Pending approvals — current step (min pending step_no) per request."""
    import streamlit as st
    pid = project_id or st.session_state.get("PROJECT_ID", "")

    reqs_res = con.table("requests").select("*").eq("project_id", pid).execute()
    req_by_id = {r["id"]: r for r in (reqs_res.data or [])}
    if not req_by_id:
        return []

    pend_res = (
        con.table("approvals")
        .select("*")
        .eq("status", "PENDING")
        .in_("req_id", list(req_by_id.keys()))
        .execute()
    )
    pend_by_req: Dict[str, List[Dict[str, Any]]] = {}
    for a in (pend_res.data or []):
        pend_by_req.setdefault(a["req_id"], []).append(a)

    out: List[Dict[str, Any]] = []
    for rid, pends in pend_by_req.items():
        pends.sort(key=lambda x: x.get("step_no") or 0)
        cur = pends[0]
        if not is_admin and cur.get("role_required") != user_role:
            continue
        r = req_by_id.get(rid, {})
        merged = {
            **cur,
            "kind":         r.get("kind"),
            "company_name": r.get("company_name"),
            "item_name":    r.get("item_name"),
            "date":         r.get("date"),
            "time_from":    r.get("time_from"),
            "time_to":      r.get("time_to"),
            "gate":         r.get("gate"),
            "req_status":   r.get("status"),
            "_req_created_at": r.get("created_at", ""),
        }
        out.append(merged)

    out.sort(key=lambda x: (x.get("_req_created_at") or "", -(x.get("step_no") or 0)), reverse=True)
    for o in out:
        o.pop("_req_created_at", None)
    return out


def approvals_for_req(con: Client, rid: str) -> List[Dict[str, Any]]:
    r = (
        con.table("approvals")
        .select("*")
        .eq("req_id", rid)
        .order("step_no")
        .execute()
    )
    return r.data or []


def approval_mark(
    con: Client,
    approval_id: str,
    action: str,
    signer_name: str,
    signer_role: str,
    sign_path: Optional[str],
    stamp_path: Optional[str],
    reject_reason: str = "",
) -> Tuple[str, str]:
    cur = (
        con.table("approvals")
        .select("req_id,status")
        .eq("id", approval_id)
        .limit(1)
        .execute()
    )
    if not cur.data:
        return "", "승인항목을 찾지 못했습니다."
    row = cur.data[0]
    rid = row["req_id"]
    if row["status"] != "PENDING":
        return rid, "이미 처리된 승인입니다."

    if action == "APPROVE":
        con.table("approvals").update({
            "status":         "APPROVED",
            "signer_name":    signer_name,
            "signer_role":    signer_role,
            "sign_png_path":  sign_path,
            "stamp_png_path": stamp_path,
            "signed_at":      now_str(),
        }).eq("id", approval_id).execute()

        left_res = (
            con.table("approvals")
            .select("id", count="exact")
            .eq("req_id", rid)
            .eq("status", "PENDING")
            .execute()
        )
        left = left_res.count or 0
        if left == 0:
            req_update_status(con, rid, "APPROVED")
            return rid, "최종 승인 완료"
        return rid, "승인 완료(다음 승인자 대기)"

    con.table("approvals").update({
        "status":        "REJECTED",
        "signer_name":   signer_name,
        "signer_role":   signer_role,
        "reject_reason": reject_reason,
        "signed_at":     now_str(),
    }).eq("id", approval_id).execute()
    req_update_status(con, rid, "REJECTED")
    return rid, "반려 처리 완료"
