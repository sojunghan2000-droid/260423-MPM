"""자재 반출입 관리 App. v3.0.0 — Entry Point.

Modular architecture with project-based authentication
and configurable feature modules.
"""
import html
from datetime import date
import streamlit as st

# ── Page config (must be first Streamlit call) ──
st.set_page_config(
    page_title="자재 반출입 관리",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── Imports ──
from db.connection import con_open
from core.css import inject_css
from core.header import ui_header
from core.nav import render_topnav
from core.sidebar import render_sidebar
from auth.session import session_has_project, session_is_authed
from auth.login import page_project_select, page_login
from modules.approval.page import page_approval
from modules.execution.page import page_execute
from modules.outputs.page import page_outputs
from modules.ledger.page import page_ledger
from modules.admin.page import page_admin
from modules.schedule.page import page_schedule
from modules.profile.page import page_profile
from modules.dashboard.page import page_dashboard


# ── Page router ──
PAGE_ROUTER = {
    "대시보드":  page_dashboard,
    "신청":      page_schedule,
    "승인":      page_approval,
    "사진등록":  page_execute,
    "계획서":    page_outputs,
    "산출물":    page_outputs,
    "대장":      page_ledger,
    "관리자":    page_admin,
    "내정보":    page_profile,
}


def page_home(con):
    """Home page — imported here to avoid circular deps."""
    from modules.request.crud import req_list, req_delete
    from modules.approval.crud import approvals_inbox
    from modules.execution.crud import photos_for_req
    from config import KIND_IN
    from pathlib import Path
    from shared.helpers import today_str

    role      = st.session_state.get("USER_ROLE", "")
    is_admin  = st.session_state.get("IS_ADMIN", False)
    user_name = st.session_state.get("USER_NAME", "")

    st.markdown("""
    <style>
:root [class*="st-key-home_edit_"] button {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
        border-radius: 4px !important;
    }
    :root [class*="st-key-home_edit_"] button:hover {
        background-color: #1e40af !important;
        border-color: #1e40af !important;
    }
    :root [class*="st-key-home_edit_"] button,
    :root [class*="st-key-home_edit_"] button p,
    :root [class*="st-key-home_edit_"] button * {
        color: #f8f8f8 !important;
    }
    :root [class*="st-key-home_del_"] button {
        background-color: #b91c1c !important;
        border-color: #b91c1c !important;
        border-radius: 4px !important;
    }
    :root [class*="st-key-home_del_"] button:hover {
        background-color: #991b1b !important;
        border-color: #991b1b !important;
    }
    :root [class*="st-key-home_del_"] button,
    :root [class*="st-key-home_del_"] button p,
    :root [class*="st-key-home_del_"] button span,
    :root [class*="st-key-home_del_"] button * {
        color: #f8f8f8 !important;
    }
    [class*="st-key-home_goto_btn_"] button {
        overflow: hidden !important;
    }
    [class*="st-key-home_goto_btn_"] button p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        max-width: 100% !important;
    }
    /* 항목 간 여백 */
    [class*="st-key-home_goto_"] {
        margin-bottom: 2px !important;
    }
    /* 항상 가로 배치 유지 (모바일 스택킹 방지) */
    [class*="st-key-home_goto_"] .stHorizontalBlock {
        flex-wrap: nowrap !important;
    }
    /* 메인 버튼 컬럼: 남은 공간 차지, 넘침 숨김 */
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
        max-width: none !important;
    }
    /* 컬럼 간격 축소 */
    [class*="st-key-home_goto_"] .stHorizontalBlock {
        gap: 4px !important;
    }
    /* 수정·삭제 버튼 컬럼: 동일 고정 폭 */
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:nth-child(2),
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:nth-child(3) {
        flex: 0 0 72px !important;
        min-width: 72px !important;
        max-width: 72px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    inbox = approvals_inbox(con, role, st.session_state.get("IS_ADMIN", False))
    st.markdown(f"""
    <div class="card">
      <h3 style="margin:0 0 1px 0;">🏠 홈</h3>
      <p style="margin:0 0 8px 0; color:var(--text-secondary); font-size:13px;">신청 → 승인(공사/안전) → 점검/등록 → SNS 공유</p>
      <p style="margin:0; font-size:13px;"><strong>내 승인함 :</strong> {len(inbox)}건</p>
    </div>
    """, unsafe_allow_html=True)

    # 신규 신청 버튼
    if st.button("＋ 신규 신청", key="home_new_req", type="primary", use_container_width=False):
        st.session_state["ACTIVE_PAGE"] = "신청"
        st.rerun()

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    # 전체 요청 목록 (진행 중인 건 우선)
    all_reqs = req_list(con, limit=100)
    today = date.today().isoformat()
    active_reqs = [r for r in all_reqs if r.get("status") not in ("DONE",) and (not r.get("date") or r.get("date") >= today)]
    active_reqs = sorted(active_reqs, key=lambda r: r.get("created_at", ""), reverse=True)

    STATUS_LABEL = {
        "PENDING_APPROVAL": ("대기중", "status-pending"),
        "APPROVED":         ("승인됨", "status-approved"),
        "REJECTED":         ("반려됨", "status-rejected"),
        "EXECUTING":        ("실행중", "status-executing"),
        "DONE":             ("완료",   "status-done"),
    }
    PAGE_FOR_STATUS = {
        "PENDING_APPROVAL": "승인",
        "APPROVED":         "사진등록",
        "REJECTED":         "승인",
        "EXECUTING":        "사진등록",
        "DONE":             "산출물",
    }

    if not active_reqs:
        st.markdown('<div class="card" style="text-align:center;color:var(--text-muted);font-size:13px;">진행 중인 요청이 없습니다.</div>', unsafe_allow_html=True)
        return

    for r in active_reqs[:20]:
        rid = r["id"]
        kind = "반입" if r.get("kind") == KIND_IN else "반출"
        status = r.get("status", "PENDING_APPROVAL")
        slabel, _ = STATUS_LABEL.get(status, (status, "status-pending"))
        status_icon = {
            "PENDING_APPROVAL": "✍️",
            "APPROVED":         "🚛",
            "EXECUTING":        "📸",
            "DONE":             "📦",
            "REJECTED":         "❌",
        }.get(status, "📋")
        title = f"{kind} · {r.get('company_name','')} · {r.get('item_name','')}"
        sub = f"{r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')} | {r.get('driver_name','')}"
        target_page = PAGE_FOR_STATUS.get(status, "승인")
        _zone = r.get('booking_zone') or ''
        _gate = r.get('gate') or ''
        _gate_txt = f" · {_gate}" if _gate and _gate != '선택' else ''
        _zone_txt = f"[{_zone}] " if _zone else ''
        label = f"{status_icon} {_zone_txt}{title} · {r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')}{_gate_txt} | {slabel}"

        can_delete = is_admin or (
            role == "협력사" and r.get("requester_name") == user_name
        )
        can_edit = is_admin or (
            role == "협력사" and r.get("requester_name") == user_name
            and status == "PENDING_APPROVAL"
        )

        with st.container(key=f"home_goto_{rid}"):
            if can_edit and can_delete:
                gcol, ecol, dcol = st.columns([7, 1.5, 1.5])
            elif can_edit or can_delete:
                gcol, acol = st.columns([8, 2])
                ecol = acol if can_edit else None
                dcol = acol if can_delete else None
            else:
                gcol = st.columns(1)[0]
                ecol = dcol = None
            with gcol:
                if st.button(label, key=f"home_goto_btn_{rid}", use_container_width=True):
                    st.session_state["ACTIVE_PAGE"] = target_page
                    st.session_state["SELECTED_REQ_ID"] = rid
                    st.rerun()
            if ecol and can_edit:
                with ecol:
                    if st.button("수정", key=f"home_edit_{rid}", use_container_width=True):
                        from modules.schedule.crud import schedule_by_req_id
                        from datetime import date as _date
                        sched = schedule_by_req_id(con, rid)
                        if sched:
                            sched_date = sched.get("schedule_date", str(_date.today()))
                            import datetime
                            st.session_state["sched_current_date"] = datetime.date.fromisoformat(sched_date)
                            if is_admin:
                                st.session_state["admin_sel_sched_ids"]  = [sched["id"]]
                                st.session_state["admin_sel_sched_list"] = [sched]
                                st.session_state["admin_sel_sched_kind"] = sched.get("kind", "IN")
                            else:
                                st.session_state["user_sel_sched_list"] = [sched]
                        st.session_state["sched_sel_in_slots"]   = []
                        st.session_state["sched_sel_out_slots"]  = []
                        st.session_state["sched_edit_from_home"] = True
                        st.session_state["ACTIVE_PAGE"] = "신청"
                        st.rerun()
            if dcol and can_delete:
                with dcol:
                    if st.button("삭제", key=f"home_del_{rid}", use_container_width=True):
                        req_delete(con, rid)
                        st.toast("삭제되었습니다.", icon="🗑️")
                        st.rerun()


def main():
    """Main application entry point."""
    # ── DB init (Supabase: schema is managed via Supabase CLI / SQL migrations) ──
    con = con_open()

    # ── CSS ──
    inject_css()

    # ── Session defaults ──
    if "AUTH_OK" not in st.session_state:
        st.session_state["AUTH_OK"] = False
    if "BASE_DIR" not in st.session_state:
        st.session_state["BASE_DIR"] = "MaterialToolShared"
    if "ACTIVE_PAGE" not in st.session_state:
        st.session_state["ACTIVE_PAGE"] = "홈"

    # ── Step 1: Project selection (단일 프로젝트면 자동 선택) ──
    if not session_has_project():
        from db.models import project_list
        projects = project_list(con)
        if len(projects) == 1:
            st.session_state["PROJECT_ID"]   = projects[0]["id"]
            st.session_state["PROJECT_NAME"] = projects[0]["name"]
        else:
            page_project_select(con)
            return

    # ── Step 2: Authentication ──
    if not session_is_authed():
        page_login(con)
        return

    # ── Step 3: Main app ──
    render_sidebar()
    ui_header(con)
    render_topnav(con)

    active_page = st.session_state.get("ACTIVE_PAGE", "홈")
    if active_page == "홈":
        page_home(con)
    elif active_page in PAGE_ROUTER:
        PAGE_ROUTER[active_page](con)
    else:
        st.warning(f"알 수 없는 페이지: {active_page}")


if __name__ == "__main__":
    main()
