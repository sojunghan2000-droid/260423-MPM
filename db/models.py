"""CRUD for projects and project_modules tables (Supabase-backed)."""
import uuid
from typing import Optional, List, Dict, Any
from supabase import Client
from shared.helpers import now_str


# ── Settings ──────────────────────────────────────────────────────────

def settings_get(con: Client, key: str, default: str = "") -> str:
    r = con.table("settings").select("value").eq("key", key).limit(1).execute()
    return r.data[0]["value"] if r.data else default


def settings_set(con: Client, key: str, value: str) -> None:
    con.table("settings").upsert({
        "key": key,
        "value": value,
        "updated_at": now_str(),
    }, on_conflict="key").execute()


# ── Projects ──────────────────────────────────────────────────────────

def project_create(con: Client, name: str, description: str,
                   site_pin: str, admin_pin: str) -> str:
    pid = uuid.uuid4().hex
    ts = now_str()
    con.table("projects").insert({
        "id": pid,
        "name": name,
        "description": description,
        "site_pin": site_pin,
        "admin_pin": admin_pin,
        "created_at": ts,
    }).execute()
    modules_init_for_project(con, pid)
    return pid


def project_list(con: Client) -> List[Dict[str, Any]]:
    r = con.table("projects").select("*").order("created_at", desc=True).execute()
    return r.data or []


def project_get(con: Client, project_id: str) -> Optional[Dict[str, Any]]:
    r = con.table("projects").select("*").eq("id", project_id).limit(1).execute()
    return r.data[0] if r.data else None


def project_update(con: Client, project_id: str, **kwargs) -> None:
    if not kwargs:
        return
    allowed = {"name", "description", "site_pin", "admin_pin"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    con.table("projects").update(fields).eq("id", project_id).execute()


# ── Project Modules ───────────────────────────────────────────────────

DEFAULT_MODULES = [
    ("schedule",  "📅 신청",    "일정 캘린더 + 신규 요청 등록 통합",              1, 0),
    ("approval",  "✍️ 승인",    "안전/공사 담당자의 요청 승인·반려 처리",          1, 1),
    ("execution", "📸 사진등록", "현장 사진 촬영 및 등록",                         1, 2),
    ("outputs",   "📦 계획서",  "PDF 계획서·허가서·실행요약 생성 및 공유",        1, 3),
    ("ledger",    "📋 대장",    "전체 요청·승인 내역 검색 및 엑셀 다운로드",      1, 4),
    ("dashboard", "📊 대시보드", "날짜별 반출입 현황 요약",                        1, 5),
]


def modules_init_for_project(con: Client, project_id: str) -> None:
    """Insert default modules for a new project — skip if already present."""
    existing = con.table("project_modules").select("module_key").eq("project_id", project_id).execute()
    have = {r["module_key"] for r in (existing.data or [])}
    rows = []
    for key, module_name, module_desc, enabled, sort_order in DEFAULT_MODULES:
        if key in have:
            continue
        rows.append({
            "project_id": project_id,
            "module_key": key,
            "module_name": module_name,
            "module_desc": module_desc,
            "enabled": enabled,
            "sort_order": sort_order,
            "enabled_admin": 1,
            "enabled_user": 1,
        })
    if rows:
        con.table("project_modules").insert(rows).execute()


def modules_for_project(con: Client, project_id: str) -> List[Dict[str, Any]]:
    r = (
        con.table("project_modules")
        .select("*")
        .eq("project_id", project_id)
        .order("sort_order")
        .execute()
    )
    return r.data or []


def modules_enabled_for_project(
    con: Client, project_id: str, is_admin: bool = False
) -> List[Dict[str, Any]]:
    col = "enabled_admin" if is_admin else "enabled_user"
    r = (
        con.table("project_modules")
        .select("*")
        .eq("project_id", project_id)
        .eq("enabled", 1)
        .eq(col, 1)
        .order("sort_order")
        .execute()
    )
    return r.data or []


def module_toggle_role(con: Client, project_id: str, module_key: str, role: str, enabled: int) -> None:
    col = "enabled_admin" if role == "admin" else "enabled_user"
    (
        con.table("project_modules")
        .update({col: enabled})
        .eq("project_id", project_id)
        .eq("module_key", module_key)
        .execute()
    )


def module_toggle(con: Client, project_id: str, module_key: str, enabled: int) -> None:
    (
        con.table("project_modules")
        .update({"enabled": enabled})
        .eq("project_id", project_id)
        .eq("module_key", module_key)
        .execute()
    )
