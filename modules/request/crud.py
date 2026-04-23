"""Request CRUD operations (Supabase-backed)."""

import uuid
from typing import Dict, Any, List, Optional

from supabase import Client
from shared.helpers import now_str


REQ_COLS = [
    "id", "created_at", "updated_at", "status", "kind", "project_id",
    "company_name", "item_name", "item_type", "work_type", "date", "time_from", "time_to",
    "gate", "vehicle_type", "vehicle_ton", "vehicle_count",
    "driver_name", "driver_phone",
    "worker_supervisor", "worker_guide", "worker_manager",
    "loading_method", "notes",
    "requester_name", "requester_role", "risk_level", "sic_training_url",
]


def req_insert(con: Client, data: Dict[str, Any]) -> str:
    rid = uuid.uuid4().hex
    row = {
        "id": rid,
        "created_at": now_str(),
        "updated_at": now_str(),
        "status": "PENDING_APPROVAL",
        **{k: data.get(k) for k in REQ_COLS
           if k not in ("id", "created_at", "updated_at", "status")},
    }
    row = {k: row[k] for k in REQ_COLS if k in row}
    con.table("requests").insert(row).execute()
    return rid


def _rank_day_seq(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Assign `day_seq` per (project_id, date) partition — ordered by (date, created_at, id)."""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("project_id") or "", r.get("date") or "")
        groups.setdefault(key, []).append(r)
    for bucket in groups.values():
        bucket.sort(key=lambda x: (x.get("date") or "", x.get("created_at") or "", x.get("id") or ""))
        for i, r in enumerate(bucket, 1):
            r["day_seq"] = i
    return rows


def req_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    r = con.table("requests").select("*").eq("id", rid).limit(1).execute()
    if not r.data:
        return None
    target = r.data[0]
    pid = target.get("project_id") or ""
    dt  = target.get("date") or ""
    # fetch only same-partition rows for ranking efficiency
    same = (
        con.table("requests")
        .select("*")
        .eq("project_id", pid)
        .eq("date", dt)
        .execute()
    )
    ranked = _rank_day_seq(same.data or [])
    for row in ranked:
        if row["id"] == rid:
            return row
    return target


def req_list(
    con: Client,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 300,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    import streamlit as st
    pid = project_id or st.session_state.get("PROJECT_ID", "")

    # fetch all requests for this project (needed for day_seq ranking)
    q = con.table("requests").select("*")
    if pid:
        q = q.eq("project_id", pid)
    all_rows = (q.execute().data or [])
    _rank_day_seq(all_rows)

    filtered = all_rows
    if status:
        filtered = [r for r in filtered if r.get("status") == status]
    if kind:
        filtered = [r for r in filtered if r.get("kind") == kind]

    filtered.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return filtered[:limit]


def req_update_status(con: Client, rid: str, status: str) -> None:
    con.table("requests").update({
        "status": status, "updated_at": now_str(),
    }).eq("id", rid).execute()


def req_update_time(con: Client, rid: str, time_from: str, time_to: str) -> None:
    con.table("requests").update({
        "time_from": time_from, "time_to": time_to, "updated_at": now_str(),
    }).eq("id", rid).execute()


def req_delete(con: Client, rid: str) -> None:
    """Delete a request and all associated records (manual cascade)."""
    for table in ("approvals", "executions", "photos", "outputs", "schedules"):
        con.table(table).delete().eq("req_id", rid).execute()
    con.table("requests").delete().eq("id", rid).execute()
