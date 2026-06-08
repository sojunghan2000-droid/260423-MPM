"""Approval (signature) page."""

from datetime import date as _date

import streamlit as st
from shared.timing import measure
from supabase import Client

from modules.approval.crud import approvals_inbox, approval_mark
from modules.request.crud import req_get
from modules.outputs.crud import generate_all_outputs
from modules.schedule.models import generate_time_slots
from shared.signature import ui_signature_block
from shared.helpers import req_display_id
from shared.storage_plan import (
    ground_zones, terminals_b1, terminals_b2, default_days, add_days,
    occupancy_on, conflicts, assign_storage, floor_image,
)


def _pending_my_requests(con: Client, project_id: str, user_name: str):
    """협력사 사용자가 등록한 요청 중 승인 대기 중인 건 조회."""
    req_res = (con.table("requests")
               .select("id,company_name,item_name,kind,date,time_from,time_to,gate,status,created_at")
               .eq("project_id", project_id)
               .eq("requester_name", user_name)
               .eq("status", "PENDING_APPROVAL")
               .order("created_at", desc=True)
               .execute())
    reqs = req_res.data or []
    rids = [r["id"] for r in reqs]
    ap_map: dict = {}
    if rids:
        ap_res = (con.table("approvals")
                  .select("req_id,role_required,status,step_no")
                  .in_("req_id", rids)
                  .eq("status", "PENDING")
                  .execute())
        for ap in ap_res.data or []:
            cur = ap_map.get(ap["req_id"])
            if not cur or ap["step_no"] < cur["step_no"]:
                ap_map[ap["req_id"]] = ap
    out = []
    for r in reqs:
        ap = ap_map.get(r["id"], {}) or {}
        out.append({
            **r,
            "role_required": ap.get("role_required"),
            "ap_status": ap.get("status"),
            "step_no": ap.get("step_no"),
        })
    return out


def _occ_grid_html(terminals, occ, selected) -> str:
    cells = []
    for t in terminals:
        o = occ.get(t)
        if o:
            bg, fg = "#fee2e2", "#b91c1c"
            sub = f"{(o['item'] or '')[:6]}<br>~{o['end'][5:]}"
        else:
            bg, fg, sub = "#dcfce7", "#15803d", "빈곳"
        border = "2px solid #2563eb" if t == selected else "1px solid #e2e8f0"
        cells.append(
            f"<div style='width:62px;background:{bg};color:{fg};border:{border};"
            f"border-radius:6px;padding:4px 2px;text-align:center;font-size:10px;line-height:1.2;'>"
            f"<b>{t}</b><br><span style='font-size:9px'>{sub}</span></div>"
        )
    return "<div style='display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;'>" + "".join(cells) + "</div>"


def _render_storage_module(con: Client, req: dict, rid: str) -> None:
    """승인 대상 ↔ 서명 입력 사이: 하역(지상존/시간) + 저장(지하 터미널/기간) + 현황."""
    import datetime as _dt

    st.markdown("#### 📦 하역 · 저장 위치 / 현황")

    # ── 도면 보기 (참조) ────────────────────────────────────────────
    _img_g, _img_b1, _img_b2 = floor_image("ground"), floor_image("b1"), floor_image("b2")
    if _img_g or _img_b1 or _img_b2:
        with st.expander("🗺 도면 보기 (지상 · B1F · B2F)"):
            _t_g, _t_b1, _t_b2 = st.tabs(["지상(하역)", "B1F(저장)", "B2F(저장)"])
            with _t_g:
                if _img_g: st.image(_img_g, use_container_width=True)
            with _t_b1:
                if _img_b1: st.image(_img_b1, use_container_width=True)
            with _t_b2:
                if _img_b2: st.image(_img_b2, use_container_width=True)

    project_id = st.session_state.get("PROJECT_ID", "")
    slots = generate_time_slots()
    ddays = default_days(con)

    # ── 신청 입력값 요약 (신청 시 입력한 존·터미널·시간) ────────────────
    _in_zone = req.get("booking_zone") or "-"
    _in_gate = req.get("gate") or "-"
    _in_time = f"{req.get('time_from','')}~{req.get('time_to','')}".strip("~")
    st.info(f"📥 신청 입력 — 하역존: **{_in_zone}** · 터미널: **{_in_gate}** · 시간: **{_in_time or '-'}**")

    def _to_date(s, fallback):
        try:
            return _dt.date.fromisoformat((s or "")[:10])
        except Exception:
            return fallback

    today = _dt.date.today()
    req_date = _to_date(req.get("date"), today)

    # ── 하역 (지상) ──────────────────────────────────────────────────
    st.markdown("**하역 (지상)**")
    gz = ground_zones(con)
    cur_zone = req.get("booking_zone") or (gz[0] if gz else "A-Zone")
    z_idx = gz.index(cur_zone) if cur_zone in gz else 0
    c1, c2, c3 = st.columns(3)
    with c1:
        sel_zone = st.selectbox("하역 존", gz, index=z_idx, key=f"st_zone_{rid}")
    with c2:
        tf = req.get("time_from") or slots[0]
        tf_idx = slots.index(tf) if tf in slots else 0
        sel_from = st.selectbox("하역 시작", slots, index=tf_idx, key=f"st_tf_{rid}")
    with c3:
        tt = req.get("time_to") or slots[min(tf_idx + 1, len(slots) - 1)]
        tt_idx = slots.index(tt) if tt in slots else min(tf_idx + 1, len(slots) - 1)
        sel_to = st.selectbox("하역 종료", slots, index=tt_idx, key=f"st_tt_{rid}")

    # ── 저장 (지하 터미널) ──────────────────────────────────────────
    st.markdown("**저장 (지하 터미널)**")
    term_opts = ["(미지정)"] + terminals_b1() + terminals_b2()
    # 신청 시 입력한 터미널(gate)을 기본값으로 — 저장 배정(store_terminal)이 있으면 우선
    _entered_term = (req.get("gate") or "").split("|")[0].strip()
    cur_term = req.get("store_terminal") or _entered_term or "(미지정)"
    t_idx = term_opts.index(cur_term) if cur_term in term_opts else 0
    d1, d2, d3 = st.columns(3)
    with d1:
        sel_term = st.selectbox("저장 터미널", term_opts, index=t_idx, key=f"st_term_{rid}")
    with d2:
        s_start = st.date_input("저장 시작일", value=_to_date(req.get("store_start"), req_date),
                                key=f"st_start_{rid}")
    with d3:
        _def_end = _to_date(req.get("store_end"),
                            _to_date(add_days(str(s_start), ddays), req_date))
        s_end = st.date_input("저장 종료일", value=_def_end, key=f"st_end_{rid}")

    start_s, end_s = str(s_start), str(s_end)

    # ── 현황 (저장 시작일 기준 터미널 점유) ─────────────────────────
    st.caption(f"📅 {start_s} 기준 터미널 점유 현황 (빨강=점유, 초록=빈곳)")
    occ = occupancy_on(con, project_id, start_s)
    sel_t = None if sel_term == "(미지정)" else sel_term
    st.markdown("<div style='font-size:11px;color:#64748b;margin:2px 0'>B1F</div>", unsafe_allow_html=True)
    st.markdown(_occ_grid_html(terminals_b1(), occ, sel_t), unsafe_allow_html=True)
    st.markdown("<div style='font-size:11px;color:#64748b;margin:2px 0'>B2F</div>", unsafe_allow_html=True)
    st.markdown(_occ_grid_html(terminals_b2(), occ, sel_t), unsafe_allow_html=True)

    # ── 충돌 검사 ───────────────────────────────────────────────────
    blocked = False
    if sel_t and end_s >= start_s:
        cf = conflicts(con, project_id, sel_t, start_s, end_s, exclude_rid=rid)
        if cf:
            blocked = True
            _names = ", ".join(f"{c.get('item_name') or '?'}(~{(c.get('store_end') or '')[:10]})" for c in cf)
            st.error(f"⛔ {sel_t} 은(는) 해당 기간에 이미 점유 중입니다: {_names}")
    if end_s < start_s:
        st.warning("종료일이 시작일보다 빠릅니다.")

    if st.button("📍 위치·기간 저장", key=f"st_save_{rid}", use_container_width=True,
                 disabled=blocked or end_s < start_s):
        assign_storage(con, rid, store_terminal=sel_t, store_start=start_s, store_end=end_s,
                       booking_zone=sel_zone, time_from=sel_from, time_to=sel_to)
        st.success("저장 위치·기간이 반영되었습니다.")
        st.rerun()

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)


@measure("page.approval")


def page_approval(con: Client):
    st.markdown("### ✍️ 승인(서명)")

    user_role = st.session_state.get("USER_ROLE", "")
    is_admin  = st.session_state.get("IS_ADMIN", False)
    user_name = st.session_state.get("USER_NAME", "")
    project_id = st.session_state.get("PROJECT_ID", "")

    inbox = approvals_inbox(con, user_role, is_admin)
    _today = _date.today().isoformat()
    inbox = [i for i in inbox if i.get("date", "") >= _today]

    # ── 협력사: 서명 권한 없음 → 본인 요청의 대기 현황만 표시 ──────────────
    if not inbox and user_role == "협력사":
        pending = _pending_my_requests(con, project_id, user_name)
        if not pending:
            st.info("대기 중인 승인 건이 없습니다.")
            return

        st.caption("📋 내가 등록한 요청 중 승인 대기 중인 건")
        KIND_LABEL = {"IN": "반입", "OUT": "반출"}
        STATUS_COLOR = {"PENDING_APPROVAL": "#f59e0b"}

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

    # ── 승인 권한 있는 계정 ───────────────────────────────────────────────
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

    # ── 하역·저장 위치/현황 모듈 (승인 대상 ↔ 서명 입력 사이) ──────────
    st.markdown("---")
    _render_storage_module(con, req, rid)
    st.markdown("---")

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
    sign_path, stamp_path = ui_signature_block(rid, "서명 입력", key_prefix=f"ap_{approval_id}")
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
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
