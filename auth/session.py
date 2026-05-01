"""Authentication and session management — Hybrid Auth on Supabase profiles.

신규 가입: profiles 테이블에 password_hash/salt 저장 (Supabase Auth 미사용)
기존 계정: supabase_uid 보유 → Supabase Auth sign_in_with_password 폴백
로그인:    profile에 password_hash 있으면 로컬 PBKDF2, 없으면 Supabase Auth
"""
import hashlib
import os
from typing import Dict, Optional, Tuple

import streamlit as st
from supabase import Client

from shared.helpers import new_id, now_str


# ── 비밀번호 해싱 (PBKDF2-SHA256) ─────────────────────────────────────

def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def _make_email(project_id: str, username: str) -> str:
    """기존 Supabase Auth 계정에 사용된 이메일 패턴."""
    return f"{username.strip()}@{project_id[:8]}.gate"


# ── 계정 CRUD ─────────────────────────────────────────────────────────

def user_create(sb: Client, project_id: str, username: str, password: str,
                name: str, role: str, is_admin: bool = False,
                company_name: str = "") -> Tuple[bool, str]:
    """신규 계정 생성 — profiles 테이블에 password_hash/salt 저장."""
    dup = (sb.table("profiles").select("id")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if dup.data:
        return False, "이미 사용 중인 아이디입니다."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."

    salt    = _new_salt()
    pw_hash = _hash_pw(password, salt)
    sb.table("profiles").insert({
        "id":            new_id(),
        "project_id":    project_id,
        "username":      username.strip(),
        "name":          name.strip(),
        "role":          role,
        "is_admin":      int(is_admin),
        "supabase_uid":  None,
        "password_hash": pw_hash,
        "salt":          salt,
        "company_name":  company_name.strip(),
        "created_at":    now_str(),
        "updated_at":    now_str(),
    }).execute()
    return True, "계정이 생성되었습니다."


def user_authenticate(sb: Client, project_id: str, username: str,
                      password: str) -> Tuple[bool, Optional[Dict]]:
    """자격증명 검증. (success, user_dict|None)."""
    res = (sb.table("profiles").select("*")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if not res.data:
        return False, None
    user = res.data[0]

    # 경로 A: 로컬 PBKDF2
    if user.get("password_hash") and user.get("salt"):
        if _hash_pw(password, user["salt"]) != user["password_hash"]:
            return False, None
        return True, user

    # 경로 B: 기존 Supabase Auth (supabase_uid 보유)
    if user.get("supabase_uid"):
        try:
            res_auth = sb.auth.sign_in_with_password({
                "email": _make_email(project_id, username),
                "password": password,
            })
            if not res_auth.user:
                return False, None
            st.session_state["SUPABASE_SESSION"] = res_auth.session
            return True, user
        except Exception:
            return False, None

    return False, None


def project_has_users(sb: Client, project_id: str) -> bool:
    res = sb.table("profiles").select("id").eq("project_id", project_id).limit(1).execute()
    return bool(res.data)


def user_list(sb: Client, project_id: str):
    res = (sb.table("profiles")
           .select("id,username,name,role,is_admin,company_name,created_at")
           .eq("project_id", project_id)
           .order("created_at", desc=True)
           .execute())
    return res.data or []


def user_delete(sb: Client, user_id: str) -> None:
    sb.table("profiles").delete().eq("id", user_id).execute()


def auth_reset() -> None:
    st.session_state["AUTH_OK"]    = False
    st.session_state["IS_ADMIN"]   = False
    st.session_state["USER_NAME"]  = ""
    st.session_state["USER_ROLE"]  = "협력사"
    st.session_state["ACTIVE_PAGE"] = "홈"
    st.session_state.pop("SUPABASE_SESSION", None)


def auth_login(sb: Client, username: str, password: str) -> Tuple[bool, str]:
    project_id = st.session_state.get("PROJECT_ID", "")
    ok, user = user_authenticate(sb, project_id, username, password)
    if not ok or not user:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."
    st.session_state["AUTH_OK"]      = True
    st.session_state["IS_ADMIN"]     = bool(user.get("is_admin"))
    st.session_state["USER_NAME"]    = user.get("name", "")
    st.session_state["USER_ROLE"]    = user.get("role", "협력사")
    st.session_state["USER_COMPANY"] = user.get("company_name", "") or ""
    st.session_state["USER_ID"]      = user.get("username", "")
    return True, "로그인 완료"


def session_has_project() -> bool:
    return bool(st.session_state.get("PROJECT_ID"))


def session_is_authed() -> bool:
    return st.session_state.get("AUTH_OK", False)


def current_project_id() -> str:
    return st.session_state.get("PROJECT_ID", "")
