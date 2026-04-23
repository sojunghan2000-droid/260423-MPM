"""CRUD for projects and project_modules tables."""
import sqlite3
import uuid
from typing import Optional, List, Dict, Any
from shared.helpers import now_str


# ── Settings ──────────────────────────────────────────────────────────

def settings_get(con: sqlite3.Connection, key: str, default: str = "") -> str:
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    return r["value"] if r else default


def settings_set(con: sqlite3.Connection, key: str, value: str) -> None:
    cur = con.cursor()
    cur.execute("""
    INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
    """, (key, value, now_str()))
    con.commit()


# ── Projects ──────────────────────────────────────────────────────────

def project_create(con: sqlite3.Connection, name: str, description: str,
                   site_pin: str, admin_pin: str) -> str:
    """Create a project and insert default modules. Returns project id."""
    pid = uuid.uuid4().hex
    ts = now_str()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO projects(id, name, description, site_pin, admin_pin, created_at)
    VALUES(?,?,?,?,?,?)
    """, (pid, name, description, site_pin, admin_pin, ts))
    con.commit()
    modules_init_for_project(con, pid)
    return pid


def project_list(con: sqlite3.Connection) -> List[Dict[str, Any]]:
    """List all projects."""
    cur = con.cursor()
    cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]


def project_get(con: sqlite3.Connection, project_id: str) -> Optional[Dict[str, Any]]:
    """Get a single project by id."""
    cur = con.cursor()
    cur.execute("SELECT * FROM projects WHERE id=?", (project_id,))
    r = cur.fetchone()
    return dict(r) if r else None


def project_update(con: sqlite3.Connection, project_id: str, **kwargs) -> None:
    """Update project fields."""
    if not kwargs:
        return
    allowed = {"name", "description", "site_pin", "admin_pin"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [project_id]
    cur = con.cursor()
    cur.execute(f"UPDATE projects SET {set_clause} WHERE id=?", values)
    con.commit()


# ── Project Modules ───────────────────────────────────────────────────

DEFAULT_MODULES = [
    ("schedule",  "📅 신청",    "일정 캘린더 + 신규 요청 등록 통합",              1, 0),
    ("approval",  "✍️ 승인",    "안전/공사 담당자의 요청 승인·반려 처리",          1, 1),
    ("execution", "📸 사진등록", "현장 사진 촬영 및 등록",                         1, 2),
    ("outputs",   "📦 계획서",  "PDF 계획서·허가서·실행요약 생성 및 공유",        1, 3),
    ("ledger",    "📋 대장",    "전체 요청·승인 내역 검색 및 엑셀 다운로드",      1, 4),
    ("dashboard", "📊 대시보드", "날짜별 반출입 현황 요약",                        1, 5),
]


def modules_init_for_project(con: sqlite3.Connection, project_id: str) -> None:
    """Insert default modules for a new project."""
    cur = con.cursor()
    ts = now_str()
    for key, module_name, module_desc, enabled, sort_order in DEFAULT_MODULES:
        cur.execute("""
        INSERT OR IGNORE INTO project_modules(project_id, module_key, module_name, module_desc, enabled, sort_order)
        VALUES(?,?,?,?,?,?)
        """, (project_id, key, module_name, module_desc, enabled, sort_order))
    con.commit()


def modules_for_project(con: sqlite3.Connection, project_id: str) -> List[Dict[str, Any]]:
    """Get all modules for a project, ordered by sort_order."""
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM project_modules WHERE project_id=? ORDER BY sort_order",
        (project_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def modules_enabled_for_project(
    con: sqlite3.Connection, project_id: str, is_admin: bool = False
) -> List[Dict[str, Any]]:
    """Get enabled modules for a project, filtered by role."""
    cur = con.cursor()
    col = "enabled_admin" if is_admin else "enabled_user"
    # fallback: if column doesn't exist yet, use enabled
    try:
        cur.execute(
            f"SELECT * FROM project_modules WHERE project_id=? AND enabled=1 AND {col}=1 ORDER BY sort_order",
            (project_id,),
        )
    except Exception:
        cur.execute(
            "SELECT * FROM project_modules WHERE project_id=? AND enabled=1 ORDER BY sort_order",
            (project_id,),
        )
    return [dict(r) for r in cur.fetchall()]


def module_toggle_role(
    con: sqlite3.Connection, project_id: str, module_key: str, role: str, enabled: int
) -> None:
    """Toggle a module on/off for a specific role ('admin' or 'user')."""
    col = "enabled_admin" if role == "admin" else "enabled_user"
    cur = con.cursor()
    cur.execute(
        f"UPDATE project_modules SET {col}=? WHERE project_id=? AND module_key=?",
        (enabled, project_id, module_key),
    )
    con.commit()


def module_toggle(con: sqlite3.Connection, project_id: str, module_key: str, enabled: int) -> None:
    """Toggle a module on/off for a project."""
    cur = con.cursor()
    cur.execute(
        "UPDATE project_modules SET enabled=? WHERE project_id=? AND module_key=?",
        (enabled, project_id, module_key),
    )
    con.commit()
