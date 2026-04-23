"""내 정보 수정 페이지."""
import sqlite3
import streamlit as st
from shared.helpers import now_str
from auth.session import _hash_pw, _new_salt
from config import ROLES


def page_profile(con: sqlite3.Connection):
    st.markdown("""
    <style>
    .st-key-profile_wrap [data-testid="stWidgetLabel"],
    .st-key-profile_wrap label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    .st-key-profile_wrap [data-testid="stElementContainer"] {
        margin-bottom: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("### 👤 내 정보 수정")

    project_id = st.session_state.get("PROJECT_ID", "")
    username   = st.session_state.get("USER_ID", "")
    user_name  = st.session_state.get("USER_NAME", "")

    con.row_factory = __import__('sqlite3').Row
    cur = con.cursor()
    # username으로 먼저 조회, 없으면 name으로 조회
    cur.execute("SELECT * FROM users WHERE project_id=? AND username=?", (project_id, username))
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT * FROM users WHERE project_id=? AND name=?", (project_id, user_name))
        row = cur.fetchone()
    user = dict(row) if row else {}
    if not user:
        st.error("계정 정보를 불러올 수 없습니다.")
        return

    with st.container(key="profile_wrap"):
        st.markdown("#### 기본 정보")
        new_name    = st.text_input("이름/직책 *", value=user.get("name", ""))
        new_company = st.text_input("업체명 *", value=user.get("company_name", ""))
        new_role    = st.selectbox("부서 *", ROLES,
                                   index=ROLES.index(user["role"]) if user.get("role") in ROLES else 0)

        st.markdown("#### 비밀번호 변경 (변경 시에만 입력)")
        cur_pw  = st.text_input("현재 비밀번호", type="password")
        new_pw1 = st.text_input("새 비밀번호", type="password", placeholder="4자 이상")
        new_pw2 = st.text_input("새 비밀번호 확인", type="password")

        if st.button("저장", type="primary", use_container_width=True):
            errors = []
            if not new_name.strip():    errors.append("이름/직책")
            if not new_company.strip(): errors.append("업체명")
            if errors:
                st.error(f"필수 항목을 입력하세요: {', '.join(errors)}")
                return

            # 비밀번호 변경 요청 시 검증
            if cur_pw or new_pw1 or new_pw2:
                if _hash_pw(cur_pw, user["salt"]) != user["password_hash"]:
                    st.error("현재 비밀번호가 올바르지 않습니다.")
                    return
                if not new_pw1:
                    st.error("새 비밀번호를 입력하세요.")
                    return
                if len(new_pw1) < 4:
                    st.error("비밀번호는 4자 이상이어야 합니다.")
                    return
                if new_pw1 != new_pw2:
                    st.error("새 비밀번호가 일치하지 않습니다.")
                    return
                new_salt = _new_salt()
                new_hash = _hash_pw(new_pw1, new_salt)
                con.execute(
                    "UPDATE users SET name=?, company_name=?, role=?, password_hash=?, salt=?, updated_at=? WHERE id=?",
                    (new_name.strip(), new_company.strip(), new_role, new_hash, new_salt, now_str(), user["id"])
                )
            else:
                con.execute(
                    "UPDATE users SET name=?, company_name=?, role=?, updated_at=? WHERE id=?",
                    (new_name.strip(), new_company.strip(), new_role, now_str(), user["id"])
                )
            con.commit()

            # 세션 업데이트
            st.session_state["USER_NAME"]    = new_name.strip()
            st.session_state["USER_COMPANY"] = new_company.strip()
            st.session_state["USER_ROLE"]    = new_role
            st.toast("내 정보가 저장되었습니다.", icon="✅")
            st.session_state["ACTIVE_PAGE"] = "홈"
            st.rerun()
