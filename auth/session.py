"""Authentication and session management (Supabase-backed, table=profiles)."""
import hashlib
import os
from typing import Dict, Optional, Tuple
import streamlit as st
from supabase import Client
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


# ── 계정 CRUD (Supabase table: profiles) ──────────────────────────────────

def user_create(con: Client, project_id: str, username: str,
                password: str, name: str, role: str,
                is_admin: bool = False, company_name: str = "") -> Tuple[bool, str]:
    existing = (
        con.table("profiles")
        .select("id")
        .eq("project_id", project_id)
        .eq("username", username.strip())
        .limit(1)
        .execute()
    )
    if existing.data:
        return False, "이미 사용 중인 아이디입니다."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."

    salt    = _new_salt()
    pw_hash = _hash_pw(password, salt)
    con.table("profiles").insert({
        "id":            new_id(),
        "project_id":    project_id,
        "username":      username.strip(),
        "password_hash": pw_hash,
        "salt":          salt,
        "name":          name.strip(),
        "role":          role,
        "is_admin":      int(is_admin),
        "company_name":  company_name.strip(),
        "created_at":    now_str(),
        "updated_at":    now_str(),
    }).execute()
    return True, "계정이 생성되었습니다."


def user_authenticate(con: Client, project_id: str,
                      username: str, password: str) -> Tuple[bool, Optional[Dict]]:
    r = (
        con.table("profiles")
        .select("*")
        .eq("project_id", project_id)
        .eq("username", username.strip())
        .limit(1)
        .execute()
    )
    if not r.data:
        return False, None
    user = r.data[0]
    if not user.get("password_hash") or not user.get("salt"):
        return False, None
    if _hash_pw(password, user["salt"]) != user["password_hash"]:
        return False, None
    return True, user


def project_has_users(con: Client, project_id: str) -> bool:
    r = (
        con.table("profiles")
        .select("id", count="exact")
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    return (r.count or 0) > 0


def user_list(con: Client, project_id: str):
    r = (
        con.table("profiles")
        .select("id,username,name,role,is_admin,created_at")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    )
    return r.data or []


def user_delete(con: Client, user_id: str) -> None:
    con.table("profiles").delete().eq("id", user_id).execute()


# ── 세션 헬퍼 ─────────────────────────────────────────────────────────────

def auth_reset():
    st.session_state["AUTH_OK"] = False
    st.session_state["IS_ADMIN"] = False
    st.session_state["USER_NAME"] = ""
    st.session_state["USER_ROLE"] = "협력사"
    st.session_state["ACTIVE_PAGE"] = "홈"


def auth_login(con: Client, username: str, password: str) -> Tuple[bool, str]:
    project_id = st.session_state.get("PROJECT_ID")
    ok, user = user_authenticate(con, project_id, username, password)
    if not ok:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."
    st.session_state["AUTH_OK"]      = True
    st.session_state["IS_ADMIN"]     = bool(user["is_admin"])
    st.session_state["USER_NAME"]    = user["name"]
    st.session_state["USER_ROLE"]    = user["role"]
    st.session_state["USER_COMPANY"] = user.get("company_name", "")
    st.session_state["USER_ID"]      = user["username"]
    return True, "로그인 완료"


def session_has_project() -> bool:
    return bool(st.session_state.get("PROJECT_ID"))


def session_is_authed() -> bool:
    return st.session_state.get("AUTH_OK", False)


def current_project_id() -> str:
    return st.session_state.get("PROJECT_ID", "")
