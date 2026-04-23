"""Authentication and session management."""
import hashlib
import os
import sqlite3
from typing import Dict, Optional, Tuple
import streamlit as st
from config import ROLES, DEFAULT_SITE_PIN, DEFAULT_ADMIN_PIN
from db.models import settings_get, project_get
from shared.helpers import new_id, now_str


# ── 비밀번호 해싱 ──────────────────────────────────────────────────────────

def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


# ── 계정 CRUD ─────────────────────────────────────────────────────────────

def user_create(con: sqlite3.Connection, project_id: str, username: str,
                password: str, name: str, role: str,
                is_admin: bool = False, company_name: str = "") -> Tuple[bool, str]:
    """새 계정 생성. Returns (success, message)."""
    cur = con.cursor()
    cur.execute(
        "SELECT id FROM users WHERE project_id=? AND username=?",
        (project_id, username),
    )
    if cur.fetchone():
        return False, "이미 사용 중인 아이디입니다."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    salt    = _new_salt()
    pw_hash = _hash_pw(password, salt)
    cur.execute(
        """INSERT INTO users(id, project_id, username, password_hash, salt,
           name, role, is_admin, company_name, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (new_id(), project_id, username.strip(), pw_hash, salt,
         name.strip(), role, int(is_admin), company_name.strip(), now_str()),
    )
    con.commit()
    return True, "계정이 생성되었습니다."


def user_authenticate(con: sqlite3.Connection, project_id: str,
                      username: str, password: str) -> Tuple[bool, Optional[Dict]]:
    """자격증명 검증. Returns (success, user_dict | None)."""
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM users WHERE project_id=? AND username=?",
        (project_id, username.strip()),
    )
    row = cur.fetchone()
    if not row:
        return False, None
    user = dict(row)
    if _hash_pw(password, user["salt"]) != user["password_hash"]:
        return False, None
    return True, user


def project_has_users(con: sqlite3.Connection, project_id: str) -> bool:
    """프로젝트에 등록된 계정이 있는지 확인."""
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE project_id=?", (project_id,))
    row = cur.fetchone()
    return (row["cnt"] if row else 0) > 0


def user_list(con: sqlite3.Connection, project_id: str):
    """프로젝트의 계정 목록 반환."""
    cur = con.cursor()
    cur.execute(
        "SELECT id, username, name, role, is_admin, created_at FROM users "
        "WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def user_delete(con: sqlite3.Connection, user_id: str) -> None:
    cur = con.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    con.commit()


def auth_reset():
    """Reset all auth session state."""
    st.session_state["AUTH_OK"] = False
    st.session_state["IS_ADMIN"] = False
    st.session_state["USER_NAME"] = ""
    st.session_state["USER_ROLE"] = "협력사"
    st.session_state["ACTIVE_PAGE"] = "홈"
    # Project selection is preserved — user goes back to project select


def auth_login(con: sqlite3.Connection, username: str,
               password: str) -> Tuple[bool, str]:
    """계정 기반 로그인. Returns (success, message)."""
    project_id = st.session_state.get("PROJECT_ID")
    ok, user = user_authenticate(con, project_id, username, password)
    if not ok:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."
    st.session_state["AUTH_OK"]        = True
    st.session_state["IS_ADMIN"]       = bool(user["is_admin"])
    st.session_state["USER_NAME"]      = user["name"]
    st.session_state["USER_ROLE"]      = user["role"]
    st.session_state["USER_COMPANY"]   = user.get("company_name", "")
    st.session_state["USER_ID"]        = user["username"]
    return True, "로그인 완료"


def session_has_project() -> bool:
    """Check if a project has been selected."""
    return bool(st.session_state.get("PROJECT_ID"))


def session_is_authed() -> bool:
    """Check if user is authenticated."""
    return st.session_state.get("AUTH_OK", False)


def current_project_id() -> str:
    """Get current project ID from session."""
    return st.session_state.get("PROJECT_ID", "")
