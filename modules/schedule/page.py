"""Unified 계획 page — schedule timeline + request form side by side."""
import json
import streamlit as st
from datetime import date, timedelta

from modules.schedule.crud import schedule_list_by_date, schedule_sync_from_requests, schedule_insert
from modules.schedule.components.timeline import render_timeline, BLOCKING_STATUSES
from modules.schedule.components.dnd_timeline import dnd_timeline
from modules.schedule.components.summary import render_daily_summary
from modules.schedule.css.schedule import get_schedule_css
from modules.request.crud import req_insert, req_update_time, req_get
from modules.approval.crud import approvals_create_default
from modules.schedule.crud import schedule_delete, schedule_update, schedule_get
from shared.helpers import now_str, req_display_id
from db.models import settings_get
from config import KIND_IN, KIND_OUT, VEHICLE_TONS, GATE_ZONES, TIME_SLOTS


def _insert_extra_slots(con, project_id, sel_list, add_slots, kind_val, gate,
                        company_name, vehicle_info, created_by) -> int:
    """수정 모드에서 추가 선택된 빈 슬롯을 기존 req_id에 삽입. 삽입된 슬롯 수 반환."""
    if not add_slots or not sel_list:
        return 0
    ref      = sel_list[0]
    rid      = ref.get("req_id", "")
    sdate    = ref.get("schedule_date", "")
    if not rid or not sdate:
        return 0
    _rows = (
        con.table("schedules").select("time_from").eq("req_id", rid).eq("schedule_date", sdate).execute()
    ).data or []
    existing_tf = {r["time_from"] for r in _rows}
    n_added = 0
    for slot in add_slots:
        if slot in existing_tf:
            continue
        try:
            idx = TIME_SLOTS.index(slot)
        except ValueError:
            continue
        if idx + 1 >= len(TIME_SLOTS):
            continue
        schedule_insert(con, project_id, {
            "req_id":        rid,
            "title":         company_name,
            "schedule_date": sdate,
            "time_from":     slot,
            "time_to":       TIME_SLOTS[idx + 1],
            "kind":          kind_val,
            "gate":          gate,
            "company_name":  company_name,
            "vehicle_info":  vehicle_info,
            "status":        ref.get("status", "PENDING"),
            "color":         ref.get("color", "#fbbf24"),
            "created_by":    created_by,
        })
        n_added += 1
    if n_added:
        _all_tf_rows = (
            con.table("schedules").select("time_from").eq("req_id", rid)
            .eq("schedule_date", sdate).order("time_from").execute()
        ).data or []
        all_tf = [r["time_from"] for r in _all_tf_rows]
        if all_tf:
            last_idx = TIME_SLOTS.index(all_tf[-1]) if all_tf[-1] in TIME_SLOTS else 0
            con.table("requests").update({
                "time_from": all_tf[0],
                "time_to":   TIME_SLOTS[min(last_idx + 1, len(TIME_SLOTS) - 1)],
            }).eq("id", rid).execute()
    return n_added


def _consecutive_toggle(slots: list, new_slot: str) -> list:
    """슬롯 선택/해제 — 항상 연속 구간 유지.
    - 미선택 슬롯 클릭: 기존 범위와 새 슬롯 사이를 모두 채워 확장
    - 경계(첫/마지막) 슬롯 클릭: 한 칸 축소
    - 중간 슬롯 클릭: 해당 슬롯으로 초기화
    - 단일 선택 슬롯 클릭: 전체 해제
    """
    if new_slot not in slots:
        if not slots:
            return [new_slot]
        try:
            new_idx = TIME_SLOTS.index(new_slot)
            lo = min(TIME_SLOTS.index(x) for x in slots)
            hi = max(TIME_SLOTS.index(x) for x in slots)
            lo, hi = min(lo, new_idx), max(hi, new_idx)
            return [TIME_SLOTS[i] for i in range(lo, hi + 1)]
        except ValueError:
            return [new_slot]
    else:
        s = sorted(slots)
        if len(s) == 1:
            return []
        if new_slot == s[0] or new_slot == s[-1]:
            return [x for x in s if x != new_slot]
        return [new_slot]


def _slot_range(slots: list) -> tuple[str, str]:
    """정렬된 슬롯 리스트에서 time_from, time_to 계산 (폼 제출용)."""
    if not slots:
        return "08:00", "08:30"
    s = sorted(slots)
    t_from = s[0]
    last_idx = TIME_SLOTS.index(s[-1]) if s[-1] in TIME_SLOTS else 4
    t_to = TIME_SLOTS[min(last_idx + 1, len(TIME_SLOTS) - 1)]
    return t_from, t_to


def _format_slot_ranges(slots: list) -> str:
    """슬롯 리스트를 연속 구간으로 묶어 표시. 예) 09:00~09:30, 10:00~11:00"""
    if not slots:
        return "미선택"
    s = sorted(slots)
    groups, group = [], [s[0]]
    for slot in s[1:]:
        try:
            prev_i = TIME_SLOTS.index(group[-1])
            curr_i = TIME_SLOTS.index(slot)
            if curr_i == prev_i + 1:
                group.append(slot)
                continue
        except ValueError:
            pass
        groups.append(group)
        group = [slot]
    groups.append(group)

    parts = []
    for grp in groups:
        t_from = grp[0]
        try:
            last_i = TIME_SLOTS.index(grp[-1])
            t_to   = TIME_SLOTS[min(last_i + 1, len(TIME_SLOTS) - 1)]
        except ValueError:
            t_to = t_from
        parts.append(f"{t_from}~{t_to}")
    return ", ".join(parts)


def _has_conflict(slots: list, schedules: list, kind_val: str) -> bool:
    """선택된 슬롯 중 이미 예약된 슬롯이 있으면 True."""
    booked = [
        s for s in schedules
        if s.get("kind") == kind_val and s.get("status") in BLOCKING_STATUSES
    ]
    for slot in slots:
        if any(b["time_from"] <= slot < b["time_to"] for b in booked):
            return True
    return False


def page_schedule(con):
    """Unified schedule calendar + request registration — single screen."""
    st.markdown(f"<style>{get_schedule_css()}</style>", unsafe_allow_html=True)

    project_id = st.session_state.get("PROJECT_ID", "default")
    is_admin   = st.session_state.get("IS_ADMIN", False)
    user_name  = st.session_state.get("USER_NAME", "")

    # ── 작업 처리 세션 키 ─────────────────────────────────────────────────────
    _ADMIN_KEYS = ("admin_sel_sched_ids", "admin_sel_sched_list", "admin_sel_sched_kind")
    _USER_KEYS  = ("user_sel_sched_list",)

    # DnD 그룹 이동 처리 (드래그)
    if "admin_dnd_move" in st.session_state:
        mv = st.session_state.pop("admin_dnd_move")
        req_id     = mv.get("req_id")
        drag_index = mv.get("drag_index", 0)
        to_slot    = mv.get("to_slot", "")
        try:
            drop_fi = TIME_SLOTS.index(to_slot)
        except ValueError:
            drop_fi = 0
        start_fi = max(0, drop_fi - drag_index)
        date_str = str(st.session_state.get("sched_current_date", date.today()))
        if req_id:
            group = (
                con.table("schedules").select("*").eq("req_id", req_id)
                .eq("schedule_date", date_str).order("time_from").execute()
            ).data or []
            for i, sched in enumerate(group):
                nfi = start_fi + i
                if nfi + 1 >= len(TIME_SLOTS):
                    break
                schedule_update(con, sched["id"],
                                time_from=TIME_SLOTS[nfi], time_to=TIME_SLOTS[nfi + 1])
            if group:
                actual_end = min(start_fi + len(group), len(TIME_SLOTS) - 1)
                con.table("requests").update({
                    "time_from": TIME_SLOTS[start_fi],
                    "time_to":   TIME_SLOTS[actual_end],
                }).eq("id", req_id).execute()
        else:
            nf = TIME_SLOTS[drop_fi]
            nt = TIME_SLOTS[min(drop_fi + 1, len(TIME_SLOTS) - 1)]
            schedule_update(con, mv["sched_id"], time_from=nf, time_to=nt)
        st.rerun()

    # 단일 슬롯 삭제 (× 버튼)
    if "admin_del_single_slot" in st.session_state:
        sid = st.session_state.pop("admin_del_single_slot")
        del_sched = schedule_get(con, sid)
        if del_sched:
            req_id   = del_sched.get("req_id")
            date_str = del_sched.get("schedule_date")
            remaining = (
                con.table("schedules").select("*").eq("req_id", req_id)
                .eq("schedule_date", date_str).neq("id", sid).order("time_from").execute()
            ).data or []
            schedule_delete(con, sid)
            if remaining and req_id:
                con.table("requests").update({
                    "time_from": remaining[0]["time_from"],
                    "time_to":   remaining[-1]["time_to"],
                }).eq("id", req_id).execute()
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    if "admin_del_sched" in st.session_state:
        for sid in st.session_state.pop("admin_del_sched"):
            schedule_delete(con, sid)
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    if "admin_move_slot" in st.session_state:
        move_slot = st.session_state.pop("admin_move_slot")
        st.session_state.pop("admin_move_kind", None)
        sel_list  = sorted(st.session_state.get("admin_sel_sched_list", []),
                           key=lambda s: s.get("time_from", ""))
        try:
            start_fi = TIME_SLOTS.index(move_slot)
        except ValueError:
            start_fi = 0
        _mv_date = str(st.session_state.get("sched_current_date", date.today()))
        # 선택된 슬롯의 req_id 수집 (연속 그룹 이동)
        _mv_req_ids = [s.get("req_id") for s in sel_list if s.get("req_id")]
        if _mv_req_ids:
            # req_id 기준으로 해당 날짜의 ALL 슬롯을 연속 배치
            _seen = set()
            for _req_id in _mv_req_ids:
                if _req_id in _seen:
                    continue
                _seen.add(_req_id)
                _group = (
                    con.table("schedules").select("*").eq("req_id", _req_id)
                    .eq("schedule_date", _mv_date).order("time_from").execute()
                ).data or []
                for i, _sched in enumerate(_group):
                    nfi = start_fi + i
                    if nfi + 1 >= len(TIME_SLOTS):
                        break
                    schedule_update(con, _sched["id"],
                                    time_from=TIME_SLOTS[nfi], time_to=TIME_SLOTS[nfi + 1])
                if _group:
                    _actual_end = min(start_fi + len(_group), len(TIME_SLOTS) - 1)
                    con.table("requests").update({
                        "time_from": TIME_SLOTS[start_fi],
                        "time_to":   TIME_SLOTS[_actual_end],
                    }).eq("id", _req_id).execute()
        else:
            # req_id 없는 단독 슬롯은 개별 이동
            for i, sched in enumerate(sel_list):
                nfi = start_fi + i
                if nfi + 1 >= len(TIME_SLOTS):
                    break
                schedule_update(con, sched["id"],
                                time_from=TIME_SLOTS[nfi], time_to=TIME_SLOTS[nfi + 1])
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    # 세션 초기화
    for key, default in [
        ("sched_current_date",     date.today()),
        ("sched_sel_in_slots",     []),
        ("sched_sel_out_slots",    []),
        ("sched_last_kind",        "반입"),
        ("user_sel_sched_list",    []),
        ("sched_mobile_show_form", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 전일/익일 버튼 클릭으로 예약된 날짜를 위젯 렌더 전에 반영
    if "sched_pending_date" in st.session_state:
        st.session_state["sched_date_pick"] = st.session_state.pop("sched_pending_date")

    current_date = st.session_state["sched_current_date"]
    # 세션에 저장된 날짜가 오늘보다 과거면 오늘로 자동 보정
    if current_date < date.today():
        current_date = date.today()
        st.session_state["sched_current_date"] = current_date
    schedule_sync_from_requests(con, project_id)

    col_left, col_right = st.columns([3, 2], gap="large")

    # ── 모바일: 타임라인 ↔ 폼 전환 CSS ──────────────────────────────────────
    _mbf = st.session_state.get("sched_mobile_show_form", False)
    _hide_tl   = "[data-testid='stColumn']:has([class*='st-key-sched_nav_row']){display:none!important}"
    _hide_form = "[data-testid='stColumn']:has([class*='st-key-sched_back_to_timeline']){display:none!important}"
    _show_back = ".st-key-sched_back_to_timeline{display:block!important;margin-bottom:8px!important}"
    _btn_size  = ".st-key-sched_back_to_timeline button,.st-key-sched_go_form_wrap button{min-height:44px!important;height:44px!important;font-size:15px!important;width:100%!important;display:flex!important;align-items:center!important;justify-content:center!important;} .st-key-sched_back_to_timeline button p,.st-key-sched_go_form_wrap button p{margin:0!important;line-height:1!important}"
    st.markdown(f"""<style>
    .st-key-sched_back_to_timeline{{display:none!important}}
    @media(max-width:480px){{
        {_hide_tl if _mbf else _hide_form}
        {_show_back if _mbf else ""}
        {_btn_size}
    }}
    </style>""", unsafe_allow_html=True)

    # ── LEFT: 날짜 네비 + 타임라인 ───────────────────────────────────────────
    with col_left:
        st.markdown("#### 📅 일정 현황")

        st.markdown("""<style>
        .st-key-sched_prev button,
        .st-key-sched_next button {
            height: 38px !important;
            min-height: 38px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-sched_prev button p,
        .st-key-sched_next button p {
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-sched_nav_row .stHorizontalBlock {
            align-items: center !important;
        }
        .st-key-sched_nav_row .stHorizontalBlock > div {
            display: flex !important;
            align-items: center !important;
        }
        </style>""", unsafe_allow_html=True)
        with st.container(key="sched_nav_row"):
            nav1, nav2, nav3 = st.columns([1, 1.75, 1])
            with nav1:
                today = date.today()
                max_date = today + timedelta(days=90) if is_admin else today + timedelta(days=2)
                if st.button("‹ 전일", key="sched_prev", use_container_width=True,
                             disabled=(current_date <= today)):
                    new_date = current_date - timedelta(days=1)
                    st.session_state["sched_current_date"]    = new_date
                    st.session_state["sched_pending_date"]    = new_date
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()
            with nav2:
                today = date.today()
                max_date = today + timedelta(days=90) if is_admin else today + timedelta(days=2)
                _wd_list = ["월", "화", "수", "목", "금", "토", "일"]
                _wd       = _wd_list[current_date.weekday()]
                _is_sun   = current_date.weekday() == 6
                _bg       = "#fee2e2" if _is_sun else "#dbeafe"
                _fg       = "#b91c1c" if _is_sun else "#1d4ed8"
                _date_disp = current_date.strftime("%Y/%m/%d")
                # 표시용 박스
                st.markdown(
                    f'<div style="background:{_bg};border:1px solid #d1d5db;border-radius:6px;'
                    f'height:38px;display:flex;align-items:center;justify-content:center;'
                    f'font-size:14px;font-weight:600;color:{_fg};">'
                    f'{_date_disp} ({_wd})</div>',
                    unsafe_allow_html=True,
                )
                # 투명 date_input을 표시 박스 위로 겹침 (달력 클릭용)
                st.markdown(f"""<style>
                .st-key-sched_date_pick {{
                    margin-top: -42px !important;
                    position: relative !important;
                    z-index: 10 !important;
                    opacity: 0 !important;
                }}
                </style>""", unsafe_allow_html=True)
                picked = st.date_input(
                    "날짜", value=current_date,
                    min_value=today,
                    max_value=max_date,
                    key="sched_date_pick", label_visibility="collapsed",
                )
                if picked != current_date:
                    st.session_state["sched_current_date"]    = picked
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()
            with nav3:
                max_date = date.today() + timedelta(days=90) if is_admin else date.today() + timedelta(days=2)
                if st.button("익일 ›", key="sched_next", use_container_width=True,
                             disabled=(current_date >= max_date)):
                    new_date = current_date + timedelta(days=1)
                    st.session_state["sched_current_date"]    = new_date
                    st.session_state["sched_pending_date"]    = new_date
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()

        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
        date_str  = current_date.isoformat()
        schedules = schedule_list_by_date(con, project_id, date_str)

        # schedules에 requester_name 첨부 (본인 예약 식별용)
        _req_ids = [s["req_id"] for s in schedules if s.get("req_id")]
        if _req_ids:
            _rows = (
                con.table("requests").select("id,requester_name").in_("id", _req_ids).execute()
            ).data or []
            _rmap = {r["id"]: (r["requester_name"] or "") for r in _rows}
        else:
            _rmap = {}
        for s in schedules:
            s["requester_name"] = _rmap.get(s.get("req_id", ""), "")

        if is_admin:
            in_items  = [s for s in schedules if s.get("kind") == KIND_IN]
            out_items = [s for s in schedules if s.get("kind") == KIND_OUT]
            _from_home_tl = st.session_state.get("sched_edit_from_home", False)
            _in_edit_mode = bool(st.session_state.get("admin_sel_sched_list")) and _from_home_tl
            dnd_result = dnd_timeline(
                slots=TIME_SLOTS,
                in_schedules=in_items,
                out_schedules=out_items,
                is_admin=True,
                sel_ids=list(st.session_state.get("admin_sel_sched_ids", [])),
                sel_in_slots=st.session_state.get("sched_sel_in_slots", []),
                sel_out_slots=st.session_state.get("sched_sel_out_slots", []),
                admin_sel_kind=st.session_state.get("admin_sel_sched_kind"),
                in_edit_mode=_in_edit_mode,
                key="admin_dnd",
            )
            # 새 이벤트인지 확인 (ts 기반 중복 방지)
            if dnd_result and dnd_result.get("ts") != st.session_state.get("_dnd_ts"):
                st.session_state["_dnd_ts"] = dnd_result["ts"]
                action = dnd_result.get("action")

                if action == "select":
                    # 관리자 슬롯 선택/해제
                    sid   = dnd_result["sched_id"]
                    kind_ = dnd_result["kind"]
                    sched_ = next((s for s in schedules if s["id"] == sid), None)
                    if sched_:
                        ids  = set(st.session_state.get("admin_sel_sched_ids", []))
                        lst  = list(st.session_state.get("admin_sel_sched_list", []))
                        prev = st.session_state.get("admin_sel_sched_kind")
                        if prev and prev != kind_:
                            ids, lst = set(), []
                        if sid in ids:
                            ids.discard(sid)
                            lst = [s for s in lst if s["id"] != sid]
                        else:
                            ids.add(sid)
                            lst.append(sched_)
                        st.session_state["admin_sel_sched_ids"]  = list(ids)
                        st.session_state["admin_sel_sched_list"] = lst
                        st.session_state["admin_sel_sched_kind"] = kind_ if ids else None
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()

                elif action in ("move", "move_group"):
                    # 드래그로 그룹 이동
                    st.session_state["admin_dnd_move"] = {
                        "sched_id":  dnd_result.get("sched_id"),
                        "req_id":    dnd_result.get("req_id"),
                        "drag_index": dnd_result.get("drag_index", 0),
                        "to_slot":   dnd_result["to_slot"],
                    }
                    st.rerun()

                elif action == "delete_slot":
                    st.session_state["admin_del_single_slot"] = dnd_result["sched_id"]
                    st.rerun()

                elif action == "move_click":
                    # 이동 버튼 클릭 → 선택된 모든 슬롯 이동
                    st.session_state["admin_move_slot"] = dnd_result["to_slot"]
                    st.session_state["admin_move_kind"] = dnd_result.get("kind")
                    st.rerun()

                elif action == "toggle_book":
                    key_ = "sched_sel_in_slots" if dnd_result["kind"] == KIND_IN else "sched_sel_out_slots"
                    lst  = list(st.session_state.get(key_, []))
                    new_slots = _consecutive_toggle(lst, dnd_result["slot"])
                    st.session_state[key_] = new_slots
                    st.session_state["sched_last_kind"] = "반입" if dnd_result["kind"] == KIND_IN else "반출"
                    st.rerun()
        else:
            user_sel_ids_cur = [s["id"] for s in st.session_state.get("user_sel_sched_list", [])]
            user_dnd = dnd_timeline(
                slots=TIME_SLOTS,
                in_schedules=[s for s in schedules if s.get("kind") == KIND_IN],
                out_schedules=[s for s in schedules if s.get("kind") == KIND_OUT],
                is_admin=False,
                sel_in_slots=st.session_state.get("sched_sel_in_slots", []),
                sel_out_slots=st.session_state.get("sched_sel_out_slots", []),
                username=user_name,
                user_sel_ids=user_sel_ids_cur,
                key="user_dnd",
            )
            if user_dnd and user_dnd.get("ts") != st.session_state.get("_user_dnd_ts"):
                st.session_state["_user_dnd_ts"] = user_dnd["ts"]
                action = user_dnd.get("action")
                if action == "toggle_book":
                    key_ = "sched_sel_in_slots" if user_dnd["kind"] == KIND_IN else "sched_sel_out_slots"
                    lst  = list(st.session_state.get(key_, []))
                    new_slots = _consecutive_toggle(lst, user_dnd["slot"])
                    st.session_state[key_] = new_slots
                    st.session_state["sched_last_kind"] = "반입" if user_dnd["kind"] == KIND_IN else "반출"
                    st.rerun()
                elif action == "user_select":
                    sid   = user_dnd["sched_id"]
                    sched_ = next((s for s in schedules if s["id"] == sid), None)
                    if sched_:
                        lst = list(st.session_state.get("user_sel_sched_list", []))
                        if any(s["id"] == sid for s in lst):
                            lst = [s for s in lst if s["id"] != sid]
                        else:
                            lst = [sched_]  # 단일 선택
                        st.session_state["user_sel_sched_list"] = lst
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()

        # 모바일 전용 상세 입력 버튼 (daily summary 위, 타임라인과 간격 최소화)
        _sel_in  = st.session_state.get("sched_sel_in_slots",  [])
        _sel_out = st.session_state.get("sched_sel_out_slots", [])
        if _sel_in or _sel_out:
            st.markdown("""<style>
            .st-key-sched_go_form_wrap { display: none !important; }
            @media (max-width: 480px) {
                .st-key-sched_go_form_wrap { display: block !important; margin-top: -8px !important; }
            }
            </style>""", unsafe_allow_html=True)
            with st.container(key="sched_go_form_wrap"):
                if st.button("📝 상세 입력 →", key="sched_go_form_btn",
                             type="primary", use_container_width=True):
                    st.session_state["sched_mobile_show_form"] = True
                    st.rerun()

        render_daily_summary(schedules, con=con)


    # ── RIGHT: 반입·반출 예약 신청 (슬롯 선택 시 기존 정보 자동 입력) ────────
    with col_right:
        # 모바일 전용 뒤로 가기 버튼 (desktop에서는 CSS로 숨김)
        with st.container(key="sched_back_to_timeline"):
            if st.button("← 일정으로", key="sched_back_btn",
                         use_container_width=True):
                st.session_state["sched_mobile_show_form"] = False
                st.rerun()
        admin_sel_list = st.session_state.get("admin_sel_sched_list", [])
        user_sel_list  = st.session_state.get("user_sel_sched_list", []) if not is_admin else []
        _from_home     = st.session_state.get("sched_edit_from_home", False)
        is_admin_edit  = is_admin and bool(admin_sel_list) and _from_home
        is_user_edit   = not is_admin and bool(user_sel_list) and _from_home
        is_edit        = is_admin_edit or is_user_edit
        sel_list       = admin_sel_list if is_admin_edit else user_sel_list

        st.markdown("#### 📝 반입·반출 예약 신청")
        # 홈 수정 버튼 없이 타임라인에서 직접 선택한 경우 안내
        _has_sel_no_home = (
            (is_admin and bool(admin_sel_list) and not _from_home) or
            (not is_admin and bool(user_sel_list) and not _from_home)
        )
        st.components.v1.html("""
        <script>
        (function() {
            function formatPhone(v) {
                var d = v.replace(/[^0-9]/g, '').slice(0, 11);
                if (d.length >= 8) return d.slice(0,3) + '-' + d.slice(3,7) + '-' + d.slice(7);
                if (d.length >= 4) return d.slice(0,3) + '-' + d.slice(3);
                return d;
            }
            function attachPhoneFormatter() {
                var inputs = window.parent.document.querySelectorAll('input[placeholder="숫자만 (-제외)"]');
                inputs.forEach(function(inp) {
                    if (inp._phoneAttached) return;
                    inp._phoneAttached = true;
                    inp.addEventListener('input', function() {
                        var pos = inp.selectionStart;
                        var oldLen = inp.value.length;
                        var formatted = formatPhone(inp.value);
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, formatted);
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        var diff = formatted.length - oldLen;
                        inp.setSelectionRange(Math.max(0, pos + diff), Math.max(0, pos + diff));
                    });
                });
            }
            var observer = new MutationObserver(attachPhoneFormatter);
            observer.observe(window.parent.document.body, {childList: true, subtree: true});
            attachPhoneFormatter();
        })();
        </script>
        """, height=0)

        # ── 슬롯 선택 시: 기존 예약 정보 로드 ────────────────────────────
        if is_edit:
            n   = len(sel_list)
            ref = sel_list[0]
            req = (req_get(con, ref["req_id"]) or {}) if ref.get("req_id") else {}
            times = sorted(s.get("time_from", "") for s in sel_list)
            can_delete = is_admin_edit or ref.get("status") == "PENDING"
            if is_admin_edit:
                st.caption("⬅️ 타임라인 [→ 이동]: 시간 이동 | 아래 폼: 내용 수정 후 저장")
            else:
                st.caption("✏️ 내 예약 수정 | 승인 전(대기중)만 삭제 가능")
            _edit_date = ref.get("schedule_date", str(current_date))
            st.markdown(
                f'<div style="font-size:14px;background:#fff8f4;border:1px solid #ED7D31;'
                f'border-radius:6px;padding:6px 10px;margin-bottom:8px;">'
                f'선택된 예약: <b>{_edit_date}, {times[0]} ~ {times[-1]}</b> ({n}개 슬롯)</div>',
                unsafe_allow_html=True,
            )
            # 추가 슬롯: 타임라인에서 직접 선택 (toggle_book → sched_sel_in/out_slots)
            _ref_kind    = ref.get("kind", KIND_IN)
            _add_key_now = "sched_sel_in_slots" if _ref_kind == KIND_IN else "sched_sel_out_slots"
            _cur_add     = sorted(st.session_state.get(_add_key_now, []))
            if _cur_add:
                st.markdown(
                    f'<div style="font-size:13px;background:#f0fdf4;border:1px solid #86efac;'
                    f'border-radius:6px;padding:6px 10px;margin-bottom:4px;">'
                    f'➕ 추가 예정: <b>{_format_slot_ranges(_cur_add)}</b></div>',
                    unsafe_allow_html=True,
                )
            def_company = req.get("company_name", ref.get("company_name", ""))
            def_item    = req.get("item_name", "")
            def_loading = req.get("loading_method", "")
            def_kind_i  = 0 if ref.get("kind") == KIND_IN else 1
            _gate_val   = req.get("gate", "")
            _gate_parts = _gate_val.split("|", 1) if "|" in _gate_val else [_gate_val, ""]
            def_gate_zone  = _gate_parts[0].strip()
            def_gate_place = _gate_parts[1].strip() if len(_gate_parts) > 1 else ""
            def_ton     = req.get("vehicle_ton", "")
            def_count   = str(req.get("vehicle_count", "1"))
            def_supervisor = req.get("worker_supervisor", "")
            def_guide      = req.get("worker_guide", "")
            def_manager    = req.get("worker_manager", "")
            def_notes   = req.get("notes", "")
            form_key     = f"slot_edit_{ref['id'][:8]}"
            conflict     = False
            is_view_only = False
        elif _has_sel_no_home:
            # ── 뷰 모드: 타임라인 직접 클릭 → 예약 정보 표시 (읽기 전용) ────────
            _vl   = admin_sel_list if is_admin else user_sel_list
            ref   = _vl[0]
            req   = (req_get(con, ref["req_id"]) or {}) if ref.get("req_id") else {}
            times = sorted(s.get("time_from", "") for s in _vl)
            _vdate = ref.get("schedule_date", str(current_date))
            _vstatus_label = {
                "PENDING": "대기중", "APPROVED": "승인됨",
                "PENDING_APPROVAL": "대기중", "EXECUTING": "실행중",
                "DONE": "완료", "REJECTED": "반려됨",
            }
            _vstatus = _vstatus_label.get(ref.get("status", ""), ref.get("status", ""))
            st.caption("📋 선택된 예약 정보 (읽기 전용) | 수정은 홈 화면 수정 버튼 이용")
            st.markdown(
                f'<div style="font-size:14px;background:#f0f9ff;border:1px solid #bae6fd;'
                f'border-radius:6px;padding:6px 10px;margin-bottom:8px;">'
                f'선택된 예약: <b>{_vdate}, {times[0]} ~ {times[-1]}</b>'
                f'<span style="float:right;background:#dbeafe;color:#1d4ed8;font-size:11px;'
                f'padding:2px 8px;border-radius:10px;">{_vstatus}</span></div>',
                unsafe_allow_html=True,
            )
            def_company   = req.get("company_name", ref.get("company_name", ""))
            def_item      = req.get("item_name", "")
            def_loading   = req.get("loading_method", "")
            def_kind_i    = 0 if ref.get("kind") == KIND_IN else 1
            _gate_val     = req.get("gate", ref.get("gate", ""))
            _gate_parts   = _gate_val.split("|", 1) if "|" in _gate_val else [_gate_val, ""]
            def_gate_zone  = _gate_parts[0].strip()
            def_gate_place = _gate_parts[1].strip() if len(_gate_parts) > 1 else ""
            def_ton       = req.get("vehicle_ton", "")
            def_count     = str(req.get("vehicle_count", "1"))
            def_supervisor = req.get("worker_supervisor", "")
            def_guide     = req.get("worker_guide", "")
            def_manager   = req.get("worker_manager", "")
            def_notes     = req.get("notes", "")
            form_key      = f"slot_view_{ref['id'][:8]}"
            conflict      = False
            can_delete    = False
            is_view_only  = True
        else:
            # ── 선택 없음: 시간 선택 배지 ─────────────────────────────────
            is_view_only = False
            sel_in    = sorted(st.session_state.get("sched_sel_in_slots",  []))
            sel_out   = sorted(st.session_state.get("sched_sel_out_slots", []))
            last_kind = st.session_state.get("sched_last_kind", "반입")

            def _badge(slots, kind_label, color, bg, border):
                if not slots:
                    return (
                        f'<div style="font-size:14px;color:{color};background:{bg};'
                        f'border:1px solid {border};border-radius:6px;padding:6px 10px;'
                        f'margin-bottom:4px;">{kind_label}: '
                        f'<span style="color:#94a3b8;">미선택</span></div>'
                    )
                return (
                    f'<div style="font-size:14px;color:{color};background:{bg};'
                    f'border:1px solid {border};border-radius:6px;padding:6px 10px;'
                    f'margin-bottom:4px;">{kind_label}: '
                    f'<b>{current_date.strftime("%Y/%m/%d")}, {_format_slot_ranges(slots)}</b></div>'
                )
            st.markdown(
                _badge(sel_in,  "➡️ 반입", "#2563eb", "#eff6ff", "#bfdbfe") +
                _badge(sel_out, "⬅️ 반출", "#dc2626", "#fff1f2", "#fecaca"),
                unsafe_allow_html=True,
            )

            if last_kind == "반입" and sel_in:
                sel_from, sel_to = _slot_range(sel_in)
                conflict = _has_conflict(sel_in, schedules, KIND_IN)
            elif last_kind == "반출" and sel_out:
                sel_from, sel_to = _slot_range(sel_out)
                conflict = _has_conflict(sel_out, schedules, KIND_OUT)
            else:
                sel_from, sel_to = "08:00", "08:30"
                conflict = False

            if conflict and not is_admin:
                st.markdown(
                    f'<div style="font-size:12px;color:#dc2626;background:#fff1f2;'
                    f'border:1px solid #fecaca;border-radius:6px;padding:4px 10px;'
                    f'margin-bottom:6px;">🔒 선택된 시간대에 이미 예약이 있습니다. 다른 슬롯을 선택하세요.</div>',
                    unsafe_allow_html=True,
                )

            def_company = st.session_state.get("USER_COMPANY", "")
            def_item    = ""
            def_kind_i  = 0 if last_kind == "반입" else 1
            def_gate_zone  = ""
            def_gate_place = ""
            def_ton     = ""
            def_count   = "1"
            def_loading    = ""
            def_supervisor = ""
            def_guide      = ""
            def_manager    = ""
            def_notes   = ""
            # 슬롯 선택이 바뀌면 폼 위젯 기본값도 갱신되도록 key에 시간 포함
            form_key    = f"req_unified_form_{sel_from}_{sel_to}"

        # ── Zone 옵션 로드 (비활성 제외) ─────────────────────────────────
        try:
            _zone_all      = json.loads(settings_get(con, "gate_zones_json", "[]"))
            _zone_disabled = json.loads(settings_get(con, "gate_zones_disabled_json", "[]"))
            _zone_options  = [z for z in _zone_all if z not in _zone_disabled]
        except Exception:
            _zone_options = []

        # ── 통합 폼 ───────────────────────────────────────────────────────
        with st.form(form_key, clear_on_submit=False):
            company_name = st.text_input("업체명 *", value=def_company,
                                         placeholder="예) OO내장, OO설비")
            item_name    = st.text_input("자재종류 *", value=def_item,
                                         placeholder="예) 백관, 석고보드, 시멘트")
            loading_method = st.text_input("상·하차 방식 *", value=def_loading,
                                           placeholder="예) 지게차, 크레인, 인력")
            st.markdown("---")

            st.markdown("""<style>
            .st-key-gate_row .stHorizontalBlock,
            .st-key-vehicle_row .stHorizontalBlock,
            .st-key-worker_row .stHorizontalBlock {
                flex-wrap: nowrap !important;
            }
            .st-key-gate_row .stHorizontalBlock > [data-testid="stColumn"],
            .st-key-vehicle_row .stHorizontalBlock > [data-testid="stColumn"],
            .st-key-worker_row .stHorizontalBlock > [data-testid="stColumn"] {
                flex: 1 1 0 !important;
                min-width: 0 !important;
                max-width: none !important;
            }
            </style>""", unsafe_allow_html=True)

            # Zone 드롭다운 옵션 (관리자 설정값)
            _zopts = ["선택"] + _zone_options
            def _zone_sel(cur_val):
                return st.selectbox("Zone *", options=_zopts,
                                    index=_zopts.index(cur_val) if cur_val in _zopts else 0)

            if is_admin_edit or is_view_only:
                new_kind = st.selectbox("구분 *", ["반입", "반출"], index=def_kind_i)
                with st.container(key="gate_row"):
                    gr1, gr2 = st.columns(2)
                    with gr1:
                        gate_zone = _zone_sel(def_gate_zone)
                    with gr2:
                        gate_place = st.text_input("장소 *", value=def_gate_place, placeholder="예) 201동 주변")
                gate = f"{gate_zone}|{gate_place}" if gate_place else gate_zone
            elif is_edit:
                # 일반 사용자 수정: 구분 변경 불가, gate만 수정 가능
                with st.container(key="gate_row"):
                    gr1, gr2 = st.columns(2)
                    with gr1:
                        gate_zone = _zone_sel(def_gate_zone)
                    with gr2:
                        gate_place = st.text_input("장소 *", value=def_gate_place, placeholder="예) 201동 주변")
                gate = f"{gate_zone}|{gate_place}" if gate_place else gate_zone
            else:
                # 신규 신청
                if is_admin:
                    new_kind = last_kind
                    with st.container(key="gate_row"):
                        gr1, gr2 = st.columns(2)
                        with gr1:
                            gate_zone = _zone_sel(def_gate_zone)
                        with gr2:
                            gate_place = st.text_input("장소 *", value=def_gate_place, placeholder="예) 201동 주변")
                    gate = f"{gate_zone}|{gate_place}" if gate_place else gate_zone
                    admin_req_date = current_date
                    admin_tf = sel_from
                    admin_tt = sel_to
                else:
                    # 일반 사용자: 구분 + Zone/장소
                    new_kind = st.selectbox("구분 *", ["반입", "반출"], index=def_kind_i)
                    with st.container(key="gate_row"):
                        gr1, gr2 = st.columns(2)
                        with gr1:
                            gate_zone = _zone_sel(def_gate_zone)
                        with gr2:
                            gate_place = st.text_input("장소 *", value=def_gate_place, placeholder="예) 201동 주변")
                    gate = f"{gate_zone}|{gate_place}" if gate_place else gate_zone

            with st.container(key="vehicle_row"):
                fv1, fv2 = st.columns(2)
                with fv1:
                    vehicle_ton = st.text_input("차량 규격 *", value=def_ton, placeholder="예) 5톤")
                with fv2:
                    with st.container(key="vehicle_count_wrap"):
                        vehicle_count = st.text_input("차량 대수 *", value=def_count, placeholder="예) 1")

            st.markdown("---")
            worker_supervisor = st.text_input("작업지휘자 *", value=def_supervisor, placeholder="예) 홍길동")
            with st.container(key="worker_row"):
                wr1, wr2 = st.columns(2)
                with wr1:
                    worker_guide   = st.text_input("유도원 *", value=def_guide,   placeholder="예) 홍길동")
                with wr2:
                    worker_manager = st.text_input("담당자 *", value=def_manager, placeholder="예) 홍길동")
            notes        = st.text_input("비고", value=def_notes,
                                         placeholder="예) 파레트 타입 포장, 지게차 양중 시 주의")

            if is_edit:
                ca, cb = st.columns(2)
                with ca:
                    with st.container(key="sched_save_btn"):
                        save = st.form_submit_button("저장", type="primary", use_container_width=True)
                with cb:
                    if can_delete:
                        delete = st.form_submit_button("삭제", use_container_width=True)
                    else:
                        delete = False
                        st.markdown(
                            '<div style="font-size:11px;color:#94a3b8;text-align:center;padding-top:10px;">승인됨 — 삭제 불가</div>',
                            unsafe_allow_html=True,
                        )
                submitted = False
            elif is_view_only:
                st.markdown("---")
                st.markdown(
                    '<div style="text-align:center;color:#64748b;font-size:12px;padding:6px 0;">'
                    '✏️ 수정하려면 홈 화면 목록의 <b>수정</b> 버튼을 이용하세요.</div>',
                    unsafe_allow_html=True,
                )
                save = delete = submitted = False
            else:
                st.markdown("---")
                with st.container(key="sched_submit_btn"):
                    submitted = st.form_submit_button("📋 예약 신청", type="primary",
                                                      use_container_width=True)
                save = delete = False

        # ── 수정 저장 ─────────────────────────────────────────────────────
        if is_edit and save:
            save_errors = []
            if not loading_method.strip():                    save_errors.append("상·하차 방식")
            if gate_zone == "선택":                           save_errors.append("Zone")
            if not gate_place.strip():                        save_errors.append("장소")
            if not worker_supervisor.strip():  save_errors.append("작업지휘자")
            if not worker_guide.strip():       save_errors.append("유도원")
            if not worker_manager.strip():     save_errors.append("담당자")
            if save_errors:
                st.error(f"필수 입력 항목을 확인하세요: {', '.join(save_errors)}")
                st.stop()
            final_ton = vehicle_ton.strip()
            if is_admin_edit:
                new_kind_val = KIND_IN if new_kind == "반입" else KIND_OUT
                # 선택된 슬롯에서 req_id 수집
                updated_req_ids = set()
                for sched in sel_list:
                    _rid = sched.get("req_id")
                    if _rid:
                        updated_req_ids.add(_rid)
                # ① requests 테이블 업데이트
                _req_payload = {
                    "company_name":      company_name.strip(),
                    "item_name":         item_name.strip(),
                    "loading_method":    loading_method.strip(),
                    "kind":              new_kind_val,
                    "gate":              gate,
                    "vehicle_ton":       final_ton,
                    "vehicle_count":     int(vehicle_count or 1),
                    "worker_supervisor": worker_supervisor.strip(),
                    "worker_guide":      worker_guide.strip(),
                    "worker_manager":    worker_manager.strip(),
                    "notes":             notes.strip(),
                    "updated_at":        now_str(),
                }
                for rid in updated_req_ids:
                    con.table("requests").update(_req_payload).eq("id", rid).execute()
                # ② 동일 req_id의 모든 schedules 슬롯 일괄 업데이트
                for rid in updated_req_ids:
                    _sched_rows = (
                        con.table("schedules").select("id").eq("req_id", rid).execute()
                    ).data or []
                    for _row in _sched_rows:
                        schedule_update(con, _row["id"],
                                        company_name=company_name.strip(),
                                        kind=new_kind_val, gate=gate)
                for k in _ADMIN_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                # 추가 슬롯 삽입 (관리자 — 타임라인 toggle_book 선택값 사용)
                add_kind_val = KIND_IN if new_kind == "반입" else KIND_OUT
                _add_key2    = "sched_sel_in_slots" if add_kind_val == KIND_IN else "sched_sel_out_slots"
                add_slots2   = sorted(st.session_state.get(_add_key2, []))
                n_added = _insert_extra_slots(con, project_id, sel_list, add_slots2,
                                              add_kind_val, gate, company_name.strip(),
                                              final_ton, user_name)
                st.session_state[_add_key2] = []
                extra_msg = f" + {n_added}개 슬롯 추가" if n_added else ""
                st.success(f"✅ {n}개 슬롯이 수정되었습니다{extra_msg}.")
            else:
                # 일반 사용자 — 본인 예약만 수정 (requester_name 조건)
                rid = ref.get("req_id")
                if rid:
                    # ① requests 테이블 업데이트 — requester_name 일치할 때만
                    _existing = (
                        con.table("requests").select("id").eq("id", rid)
                        .eq("requester_name", user_name).limit(1).execute()
                    )
                    if _existing.data:
                        con.table("requests").update({
                            "company_name":      company_name.strip(),
                            "item_name":         item_name.strip(),
                            "loading_method":    loading_method.strip(),
                            "gate":              gate,
                            "vehicle_ton":       final_ton,
                            "vehicle_count":     int(vehicle_count or 1),
                            "worker_supervisor": worker_supervisor.strip(),
                            "worker_guide":      worker_guide.strip(),
                            "worker_manager":    worker_manager.strip(),
                            "notes":             notes.strip(),
                            "updated_at":        now_str(),
                        }).eq("id", rid).eq("requester_name", user_name).execute()
                    # ② 동일 req_id의 모든 schedules 슬롯 일괄 업데이트
                    _sched_rows = (
                        con.table("schedules").select("id").eq("req_id", rid).execute()
                    ).data or []
                    for _row in _sched_rows:
                        schedule_update(con, _row["id"], company_name=company_name.strip(), gate=gate)
                # 추가 슬롯 삽입 (일반 사용자)
                add_kind_user = ref.get("kind", KIND_IN)
                _add_key3     = "sched_sel_in_slots" if add_kind_user == KIND_IN else "sched_sel_out_slots"
                add_slots3    = sorted(st.session_state.get(_add_key3, []))
                n_added = _insert_extra_slots(con, project_id, sel_list, add_slots3,
                                              add_kind_user, gate, company_name.strip(),
                                              final_ton, user_name)
                st.session_state[_add_key3] = []
                for k in _USER_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                extra_msg = f" + {n_added}개 슬롯 추가" if n_added else ""
                st.success(f"✅ 예약이 수정되었습니다{extra_msg}.")
            st.rerun()

        # ── 삭제 ─────────────────────────────────────────────────────────
        if is_edit and delete:
            if is_admin_edit:
                st.session_state["admin_del_sched"] = [s["id"] for s in sel_list]
            else:
                # 일반 사용자 — 본인 PENDING 예약만 삭제
                from modules.schedule.crud import schedule_delete as _sdel
                _sdel(con, ref["id"])
                rid = ref.get("req_id")
                if rid:
                    con.table("requests").delete().eq("id", rid).eq("requester_name", user_name).execute()
                for k in _USER_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                st.success("✅ 예약이 취소되었습니다.")
            st.rerun()

        # ── 예약 신청 ─────────────────────────────────────────────────────
        if not is_edit and submitted:
            if conflict and not is_admin:
                st.error("⛔ 선택된 시간대에 이미 예약이 있습니다. 좌측 타임라인에서 빈 슬롯을 선택하세요.")
                st.stop()

            errors = []
            if not company_name.strip():                      errors.append("업체명")
            if not item_name.strip():                         errors.append("자재종류")
            if not loading_method.strip():                    errors.append("상·하차 방식")
            if gate_zone == "선택":                           errors.append("Zone")
            if not gate_place.strip():                        errors.append("장소")
            if not vehicle_ton.strip():        errors.append("차량 규격")
            if not worker_supervisor.strip():  errors.append("작업지휘자")
            if not worker_guide.strip():       errors.append("유도원")
            if not worker_manager.strip():     errors.append("담당자")

            if errors:
                st.error(f"필수 입력 항목을 확인하세요: {', '.join(errors)}")
            else:
                final_ton = vehicle_ton.strip()
                kind_val  = KIND_IN if new_kind == "반입" else KIND_OUT
                if is_admin:
                    req_date = str(admin_req_date)
                    req_from = admin_tf
                    req_to   = admin_tt
                else:
                    req_date = str(current_date)
                    req_from = sel_from
                    req_to   = sel_to
                rid = req_insert(con, dict(
                    project_id=project_id,
                    kind=kind_val,
                    company_name=company_name.strip(),
                    item_name=item_name.strip(),
                    loading_method=loading_method.strip(),
                    item_type="", work_type="",
                    date=req_date,
                    time_from=req_from, time_to=req_to,
                    gate=gate,
                    vehicle_type="", vehicle_ton=final_ton,
                    vehicle_count=int(vehicle_count or 1),
                    worker_supervisor=worker_supervisor.strip(),
                    worker_guide=worker_guide.strip(),
                    worker_manager=worker_manager.strip(),
                    notes=notes.strip(),
                    requester_name=st.session_state.get("USER_NAME", ""),
                    requester_role=st.session_state.get("USER_ROLE", ""),
                    risk_level="MID", sic_training_url="",
                ))
                approvals_create_default(con, rid, kind_val)
                disp = req_display_id(req_get(con, rid) or {"id": rid})
                st.success(f"✅ 예약 신청 완료 ({disp}) — {req_date} {req_from}~{req_to} / {gate}")
                if kind_val == KIND_IN:
                    st.session_state["sched_sel_in_slots"] = []
                else:
                    st.session_state["sched_sel_out_slots"] = []
                st.session_state["sched_current_date"]     = current_date
                st.session_state["sched_mobile_show_form"] = False
                st.rerun()
