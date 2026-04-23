"""Approval (signature) page (Supabase-backed)."""

from datetime import date as _date

import streamlit as st
from supabase import Client

from modules.approval.crud import approvals_inbox, approval_mark
from modules.request.crud import req_get
from modules.outputs.crud import generate_all_outputs
from shared.signature import ui_signature_block
from shared.helpers import req_display_id


def _pending_my_requests(con: Client, project_id: str, user_name: str):
    """협력사가 등록한 요청 중 승인 대기 건 — 가장 낮은 PENDING 단계 정보 병합."""
    reqs = (
        con.table("requests")
        .select("id,company_name,item_name,kind,date,time_from,time_to,gate,status,created_at,requester_name")
        .eq("project_id", project_id)
        .eq("requester_name", user_name)
        .eq("status", "PENDING_APPROVAL")
        .execute()
    ).data or []
    if not reqs:
        return []

    rids = [r["id"] for r in reqs]
    appr_pend = (
        con.table("approvals")
        .select("req_id,role_required,status,step_no")
        .eq("status", "PENDING")
        .in_("req_id", rids)
        .execute()
    ).data or []

    min_pend: dict = {}
    for a in appr_pend:
        rid = a["req_id"]
        cur = min_pend.get(rid)
        if cur is None or (a.get("step_no") or 0) < (cur.get("step_no") or 0):
            min_pend[rid] = a

    out = []
    for r in reqs:
        ap = min_pend.get(r["id"], {})
        out.append({
            **r,
            "role_required": ap.get("role_required"),
            "ap_status":     ap.get("status"),
            "step_no":       ap.get("step_no"),
        })
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def page_approval(con: Client):
    st.markdown("### ✍️ 승인(서명)")

    user_role = st.session_state.get("USER_ROLE", "")
    is_admin  = st.session_state.get("IS_ADMIN", False)
    user_name = st.session_state.get("USER_NAME", "")
    project_id = st.session_state.get("PROJECT_ID", "")

    inbox = approvals_inbox(con, user_role, is_admin)
    _today = _date.today().isoformat()
    inbox = [i for i in inbox if i.get("date", "") >= _today]

    if not inbox and user_role == "협력사":
        pending = _pending_my_requests(con, project_id, user_name)
        if not pending:
            st.info("대기 중인 승인 건이 없습니다.")
            return

        st.caption("📋 내가 등록한 요청 중 승인 대기 중인 건")
        KIND_LABEL = {"IN": "반입", "OUT": "반출"}

        for r in pending:
            kind_lbl = KIND_LABEL.get(r.get("kind", ""), r.get("kind", ""))
            role_req  = r.get("role_required") or "-"
            step_no   = r.get("step_no") or "-"
            st.markdown(
                f"<div style='background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;"
                f"padding:10px 14px;margin-bottom:8px;'>"
                f"<div style='font-weight:600;font-size:14px;margin-bottom:4px'>"
                f"{r['company_name']} &nbsp;·&nbsp; {r['item_name']}</div>"
                f"<div style='font-size:12px;color:#64748b;display:flex;gap:12px;flex-wrap:wrap'>"
                f"<span>📦 {kind_lbl}</span>"
                f"<span>📅 {r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')}</span>"
                f"<span>📍 {r.get('gate','')}</span>"
                f"</div>"
                f"<div style='margin-top:6px;font-size:12px;color:#92400e'>"
                f"⏳ {step_no}단계 승인 대기 중 &nbsp;→&nbsp; <b>{role_req}</b> 서명 필요</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        return

    if not inbox:
        st.info("대기 중인 승인 건이 없습니다.")
        return

    st.markdown("""
    <style>
    [data-testid="stSelectbox"] [data-testid="stWidgetLabel"],
    [data-testid="stSelectbox"] label {
        margin-bottom: -10px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    items = [(f"[{i['role_required']}] {i['company_name']} / {i['item_name']}", i["id"]) for i in inbox]
    sel = st.selectbox("승인 대상", items, format_func=lambda x: x[0])
    approval_id = sel[1]
    target = next((x for x in inbox if x["id"] == approval_id), None)
    rid = target["req_id"]
    req = req_get(con, rid)
    st.markdown(f"**{req_display_id(req)}** / {req.get('company_name')} / {req.get('item_name')}")
    st.markdown("""
    <style>
    [data-testid="stTextArea"] [data-testid="stWidgetLabel"],
    [data-testid="stTextArea"] label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    sign_path, stamp_path = ui_signature_block(con, rid, "서명 입력", key_prefix=f"ap_{approval_id}")
    reject_reason = st.text_area("반려 사유(반려 시)", height=60)
    st.markdown("""
    <style>
    .st-key-approval_btns button {
        height: 44px !important;
        min-height: 44px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
    }
    .st-key-approval_btns button p {
        line-height: 1 !important;
        margin: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    with st.container(key="approval_btns"):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("승인", type="primary", use_container_width=True):
                if not sign_path:
                    st.error("서명이 필요합니다.")
                else:
                    rid2, msg = approval_mark(con, approval_id, "APPROVE", user_name, user_role, sign_path, stamp_path, "")
                    st.success(msg)
                    if req_get(con, rid2).get("status") == "APPROVED":
                        generate_all_outputs(con, rid2)
                    st.rerun()
        with c2:
            if st.button("반려", use_container_width=True):
                if not reject_reason.strip():
                    st.error("사유 필수")
                else:
                    rid2, msg = approval_mark(con, approval_id, "REJECT", user_name, user_role, None, None, reject_reason.strip())
                    st.success(msg)
                    st.rerun()
