"""Execution CRUD operations (Supabase-backed)."""

import json
import uuid
from typing import Dict, Any, List, Optional

import streamlit as st
from supabase import Client

from shared.helpers import now_str, file_sha1
from shared.storage import (
    upload_bytes, photo_key as build_photo_key,
    signed_url, delete_key,
)
from config import EXEC_REQUIRED_PHOTOS


def photo_exists_same(con: Client, rid: str, slot_key: str, file_hash: str) -> bool:
    r = (
        con.table("photos")
        .select("id")
        .eq("req_id", rid)
        .eq("slot_key", slot_key)
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    return bool(r.data)


def photo_add(
    con: Client,
    rid: str,
    slot_key: str,
    label: str,
    file_bytes: bytes,
    suffix: str = ".jpg",
) -> str:
    """Upload to Supabase Storage; insert photos row. Returns storage key or '' if dup."""
    fhash = file_sha1(file_bytes)
    if photo_exists_same(con, rid, slot_key, fhash):
        return ""

    project_id = st.session_state.get("PROJECT_ID", "")
    key = build_photo_key(project_id, rid, slot_key, suffix)
    content_type = "image/jpeg" if suffix.lower() in (".jpg", ".jpeg") else "image/png"
    upload_bytes(con, key, file_bytes, content_type)

    con.table("photos").insert({
        "id":          uuid.uuid4().hex,
        "req_id":      rid,
        "slot_key":    slot_key,
        "label":       label,
        "file_path":   key,
        "storage_url": key,
        "file_hash":   fhash,
        "created_at":  now_str(),
    }).execute()
    return key


def photo_delete_slot(con: Client, rid: str, slot_key: str) -> None:
    rows = (
        con.table("photos")
        .select("id,file_path,storage_url")
        .eq("req_id", rid)
        .eq("slot_key", slot_key)
        .execute()
    ).data or []
    for row in rows:
        k = row.get("storage_url") or row.get("file_path") or ""
        delete_key(con, k)
    con.table("photos").delete().eq("req_id", rid).eq("slot_key", slot_key).execute()


def photos_for_req(con: Client, rid: str) -> List[Dict[str, Any]]:
    r = (
        con.table("photos")
        .select("*")
        .eq("req_id", rid)
        .order("created_at")
        .execute()
    )
    rows = r.data or []
    for p in rows:
        key = p.get("storage_url") or p.get("file_path") or ""
        p["display_url"] = signed_url(con, key) if key else ""
    return rows


def required_photos_ok(con: Client, rid: str) -> bool:
    keys = {p["slot_key"] for p in photos_for_req(con, rid)}
    return all(k in keys for k, _ in EXEC_REQUIRED_PHOTOS)


def execution_upsert(
    con: Client,
    rid: str,
    executed_by: str,
    executed_role: str,
    check_json: Dict[str, Any],
    notes: str,
) -> None:
    ok = 1 if required_photos_ok(con, rid) else 0
    con.table("executions").upsert({
        "req_id":            rid,
        "executed_by":       executed_by,
        "executed_role":     executed_role,
        "executed_at":       now_str(),
        "check_json":        json.dumps(check_json, ensure_ascii=False),
        "required_photo_ok": ok,
        "notes":             notes,
    }, on_conflict="req_id").execute()


def execution_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    r = con.table("executions").select("*").eq("req_id", rid).limit(1).execute()
    return r.data[0] if r.data else None


def final_approved_signs(con: Client, rid: str) -> List[Dict[str, Any]]:
    r = (
        con.table("approvals")
        .select("*")
        .eq("req_id", rid)
        .eq("status", "APPROVED")
        .order("step_no")
        .execute()
    )
    return r.data or []
