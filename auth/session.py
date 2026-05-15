"""Authentication and session management — Supabase Auth (신규) + PBKDF2 (legacy fallback).

신규 가입: Supabase Auth `sign_up`(email/password) → profiles 행에 supabase_uid + email 저장
기존 PBKDF2 계정: profiles.password_hash/salt 로컬 검증 (마이그레이션 안 함)
비밀번호 재설정: Supabase Auth `reset_password_for_email` → OTP 코드 메일 발송 →
                `verify_otp(type='recovery')` → `update_user(password=...)`
"""
import hashlib
import os
from typing import Dict, Optional, Tuple

import streamlit as st
from supabase import Client

from shared.helpers import new_id, now_str


# ── 비밀번호 해싱 (legacy PBKDF2-SHA256) ──────────────────────────────────

def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def _make_email(project_id: str, username: str) -> str:
    """레거시: 합성 이메일 (수신 불가). 신규 계정은 실 이메일을 사용."""
    return f"{username.strip()}@{project_id[:8]}.gate"


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# ── 계정 CRUD ─────────────────────────────────────────────────────────

def user_create(sb: Client, project_id: str, username: str, password: str,
                name: str, role: str, is_admin: bool = False,
                company_name: str = "", email: str = "") -> Tuple[bool, str]:
    """신규 계정 생성 — Supabase Auth `sign_up` + profiles 행 INSERT.

    Confirm email 이 켜져 있으면 가입 직후 로그인 불가 (메일 확인 필요).
    """
    if len(password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    email = _norm_email(email)
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return False, "올바른 이메일 주소를 입력하세요."

    # 1) 같은 프로젝트 내 아이디 중복 체크
    dup = (sb.table("profiles").select("id")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if dup.data:
        return False, "이미 사용 중인 아이디입니다."

    # 1-1) profiles 의 email 중복 체크 (다른 username 으로 같은 이메일 등록 방지)
    dup_em = (sb.table("profiles").select("id,username")
              .eq("email", email).limit(1).execute())
    if dup_em.data:
        return False, "이미 가입된 이메일입니다."

    # 2) Supabase Auth 가입
    try:
        res = sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "project_id":   project_id,
                    "username":     username.strip(),
                    "name":         name.strip(),
                    "role":         role,
                    "company_name": company_name.strip(),
                }
            },
        })
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg or "registered" in msg or "exists" in msg:
            return False, "이미 가입된 이메일입니다."
        return False, f"가입 실패: {e}"

    if not getattr(res, "user", None):
        return False, "가입 실패: 알 수 없는 오류"

    # 2-1) Supabase Auth 의 silent-success 감지 (Confirm email ON 시 중복 이메일이면
    #      identities 가 빈 배열로 반환됨 — 진짜 신규는 identities 가 1개)
    identities = getattr(res.user, "identities", None)
    if identities is not None and len(identities) == 0:
        return False, "이미 가입된 이메일입니다. 비밀번호 찾기를 이용하세요."

    auth_uid = res.user.id

    # 3) profiles 행 INSERT (supabase_uid 연결, PBKDF2 컬럼은 NULL)
    sb.table("profiles").insert({
        "id":            new_id(),
        "project_id":    project_id,
        "username":      username.strip(),
        "name":          name.strip(),
        "role":          role,
        "is_admin":      int(is_admin),
        "supabase_uid":  auth_uid,
        "email":         email,
        "password_hash": None,
        "salt":          None,
        "company_name":  company_name.strip(),
        "created_at":    now_str(),
        "updated_at":    now_str(),
    }).execute()

    # 가입 직후 SDK가 보유할 수 있는 세션을 정리해 로그인 흐름과 분리
    try:
        sb.auth.sign_out()
    except Exception:
        pass

    return True, "계정이 생성되었습니다. 가입 확인 메일의 링크를 눌러 인증한 뒤 로그인하세요."


def user_authenticate(sb: Client, project_id: str, username: str,
                      password: str) -> Tuple[bool, Optional[Dict], str]:
    """자격증명 검증. (success, user_dict|None, error_code).

    error_code: "" | "NOT_FOUND" | "BAD_PASSWORD" | "EMAIL_NOT_CONFIRMED" | "OTHER"
    """
    res = (sb.table("profiles").select("*")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if not res.data:
        return False, None, "NOT_FOUND"
    user = res.data[0]

    # 경로 A: 로컬 PBKDF2 (legacy 계정)
    if user.get("password_hash") and user.get("salt"):
        if _hash_pw(password, user["salt"]) != user["password_hash"]:
            return False, None, "BAD_PASSWORD"
        return True, user, ""

    # 경로 B: Supabase Auth — 실 이메일 (신규 계정)
    if user.get("supabase_uid") and user.get("email"):
        try:
            res_auth = sb.auth.sign_in_with_password({
                "email":    user["email"],
                "password": password,
            })
            if not getattr(res_auth, "user", None):
                return False, None, "BAD_PASSWORD"
            st.session_state["SUPABASE_SESSION"] = res_auth.session
            return True, user, ""
        except Exception as e:
            msg = str(e).lower()
            if "not confirmed" in msg or "email_not_confirmed" in msg or "confirm" in msg:
                return False, None, "EMAIL_NOT_CONFIRMED"
            return False, None, "BAD_PASSWORD"

    # 경로 C: 레거시 Supabase Auth (합성 이메일, supabase_uid 만 보유)
    if user.get("supabase_uid"):
        try:
            res_auth = sb.auth.sign_in_with_password({
                "email":    _make_email(project_id, username),
                "password": password,
            })
            if not getattr(res_auth, "user", None):
                return False, None, "BAD_PASSWORD"
            st.session_state["SUPABASE_SESSION"] = res_auth.session
            return True, user, ""
        except Exception:
            return False, None, "BAD_PASSWORD"

    return False, None, "OTHER"


def project_has_users(sb: Client, project_id: str) -> bool:
    res = sb.table("profiles").select("id").eq("project_id", project_id).limit(1).execute()
    return bool(res.data)


def user_list(sb: Client, project_id: str):
    res = (sb.table("profiles")
           .select("id,username,name,role,is_admin,company_name,email,created_at")
           .eq("project_id", project_id)
           .order("created_at", desc=True)
           .execute())
    return res.data or []


def user_delete(sb: Client, user_id: str) -> None:
    sb.table("profiles").delete().eq("id", user_id).execute()


def admin_reset_user_password(sb: Client, user_id: str,
                              new_password: str) -> Tuple[bool, str]:
    """관리자용 — 다른 사용자의 비밀번호를 임시 비밀번호로 재설정 (PBKDF2 경로).

    NOTE: 신규 Supabase Auth 계정에는 이 헬퍼가 적용되지 않습니다.
    Supabase Auth 계정의 관리자 reset 은 Service Role Key 가 필요해 클라이언트에서 직접 수행 불가.
    Supabase Auth 계정 사용자는 셀프 reset(메일 OTP) 흐름을 이용해야 합니다.
    """
    if not new_password or len(new_password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    salt    = _new_salt()
    pw_hash = _hash_pw(new_password, salt)
    sb.table("profiles").update({
        "password_hash": pw_hash,
        "salt":          salt,
        "supabase_uid":  None,
        "updated_at":    now_str(),
    }).eq("id", user_id).execute()
    return True, "비밀번호가 재설정되었습니다."


# ── 비밀번호 재설정 (셀프서비스 — Supabase Auth 메일 OTP) ────────────

def request_password_reset(sb: Client, project_id: str,
                           username: str) -> Tuple[bool, str, str]:
    """username 으로 profiles.email 을 조회 → reset 메일 발송.

    Returns (success, message, email_for_next_step).
    레거시 PBKDF2 계정처럼 셀프 reset 이 불가한 경우 success=False.
    """
    res = (sb.table("profiles").select("email,supabase_uid")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if not res.data:
        return False, "해당 아이디를 찾을 수 없습니다.", ""

    row   = res.data[0]
    email = row.get("email") or ""
    if not email or not row.get("supabase_uid"):
        return False, "이 계정은 셀프 재설정을 지원하지 않습니다. 관리자에게 문의하세요.", ""

    try:
        sb.auth.reset_password_for_email(email)
    except Exception as e:
        return False, f"재설정 메일 발송 실패: {e}", ""

    return True, "재설정 메일을 발송했습니다. 메일의 6자리 코드를 입력하세요.", email


def verify_reset_and_update(sb: Client, email: str, token: str,
                            new_password: str) -> Tuple[bool, str]:
    """OTP 코드를 검증한 뒤 새 비밀번호로 변경."""
    if not new_password or len(new_password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    if not token.strip():
        return False, "인증 코드를 입력하세요."

    email = _norm_email(email)
    try:
        res = sb.auth.verify_otp({
            "email": email,
            "token": token.strip(),
            "type":  "recovery",
        })
        if not getattr(res, "session", None):
            return False, "코드가 올바르지 않거나 만료되었습니다."
        sb.auth.update_user({"password": new_password})
    except Exception:
        return False, "코드가 올바르지 않거나 만료되었습니다."
    finally:
        try:
            sb.auth.sign_out()
        except Exception:
            pass

    return True, "비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요."


# ── 세션 헬퍼 ─────────────────────────────────────────────────────────

def auth_reset() -> None:
    st.session_state["AUTH_OK"]    = False
    st.session_state["IS_ADMIN"]   = False
    st.session_state["USER_NAME"]  = ""
    st.session_state["USER_ROLE"]  = "협력사"
    st.session_state["ACTIVE_PAGE"] = "홈"
    st.session_state.pop("SUPABASE_SESSION", None)


def auth_login(sb: Client, username: str, password: str) -> Tuple[bool, str]:
    project_id = st.session_state.get("PROJECT_ID", "")
    ok, user, err = user_authenticate(sb, project_id, username, password)
    if not ok or not user:
        if err == "EMAIL_NOT_CONFIRMED":
            return False, "이메일 확인이 필요합니다. 가입 시 받은 메일의 인증 링크를 클릭한 뒤 다시 시도하세요."
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
