"""Admin settings page."""

import json

import streamlit as st
from supabase import Client

from config import DEFAULT_SITE_NAME, DEFAULT_SITE_PIN, DEFAULT_ADMIN_PIN, ROLES
from db.models import settings_get, settings_set
from modules.approval.crud import routing_get
from modules.admin.module_manager import render_module_manager


def page_admin(con: Client):
    st.markdown("""
    <style>
    .st-key-admin_wrap [data-testid="stWidgetLabel"],
    .st-key-admin_wrap label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    .st-key-admin_wrap [data-testid="stElementContainer"] {
        margin-bottom: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("### 🛠 관리자 설정")
    if not st.session_state.get("IS_ADMIN", False):
        st.warning("관리자 모드로 로그인해야 합니다.")
        return

    with st.container(key="admin_wrap"):
        st.markdown("#### ⚙️ 현장 설정")
        site_name = st.text_input("현장명", value=settings_get(con, "site_name", DEFAULT_SITE_NAME))
        site_pin = st.text_input("현장 PIN", value=settings_get(con, "site_pin", DEFAULT_SITE_PIN))
        admin_pin = st.text_input("Admin PIN", value=settings_get(con, "admin_pin", DEFAULT_ADMIN_PIN))

        st.markdown("---")

        st.markdown("#### 🔄 승인 라우팅")
        routing = routing_get(con)
        in_default  = [r for r in routing.get("IN",  []) if r in ROLES]
        out_default = [r for r in routing.get("OUT", []) if r in ROLES]
        in_route  = st.multiselect("반입(IN) 승인순서",  options=ROLES, default=in_default)
        out_route = st.multiselect("반출(OUT) 승인순서", options=ROLES, default=out_default)

        if st.button("저장", type="primary", use_container_width=True):
            new_site_name = site_name.strip() or DEFAULT_SITE_NAME
            settings_set(con, "site_name", new_site_name)
            settings_set(con, "site_pin", site_pin.strip() or DEFAULT_SITE_PIN)
            settings_set(con, "admin_pin", admin_pin.strip() or DEFAULT_ADMIN_PIN)
            settings_set(con, "approval_routing_json", json.dumps({"IN": in_route, "OUT": out_route}, ensure_ascii=False))
            st.session_state["PROJECT_NAME"] = new_site_name
            st.success("저장 완료")
            st.rerun()

    st.markdown("---")

    # ── 터미널 설정 ────────────────────────────────────────────────────
    st.markdown("#### 🚧 터미널 설정")
    st.caption("신청 탭 예약 폼에서 선택할 터미널(반출입 장소) 목록입니다.")
    _zones_raw = settings_get(con, "gate_zones_json", "[]")
    try:
        _zones: list = json.loads(_zones_raw)
    except Exception:
        _zones = []

    _disabled_raw = settings_get(con, "gate_zones_disabled_json", "[]")
    try:
        _disabled: list = json.loads(_disabled_raw)
    except Exception:
        _disabled = []

    if _zones:
        st.caption("등록된 터미널 · 토글로 활성/비활성 전환, 삭제 버튼으로 제거")
        st.markdown("""<style>
        [class*="st-key-zone_row_"] .stHorizontalBlock {
            align-items: center !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
        }
        [class*="st-key-zone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important; min-width: 0 !important;
        }
        [class*="st-key-zone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 52px !important; min-width: 52px !important; max-width: 52px !important;
        }
        [class*="st-key-zone_row_"] [data-testid="stElementContainer"] {
            margin: 0 !important; padding: 0 !important;
        }
        [class*="st-key-zone_toggle_"] label {
            font-size: 14px !important;
            color: #0f172a !important;
        }
        [class*="st-key-zone_toggle_"] label p {
            font-size: 14px !important;
            margin: 0 !important;
        }
        [class*="st-key-del_zone_"] button {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
            border-radius: 4px !important;
            height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
        }
        [class*="st-key-del_zone_"] button:hover { background-color: #991b1b !important; border-color: #991b1b !important; }
        [class*="st-key-del_zone_"] button,
        [class*="st-key-del_zone_"] button p,
        [class*="st-key-del_zone_"] button span,
        [class*="st-key-del_zone_"] button div {
            color: #f8f8f8 !important; font-size: 11px !important;
            line-height: 1 !important; margin: 0 !important; padding: 0 !important;
        }
        </style>""", unsafe_allow_html=True)
        for i, z in enumerate(_zones):
            is_disabled = z in _disabled
            _badge = "  ⚠️비활성" if is_disabled else ""
            with st.container(key=f"zone_row_{i}"):
                zc1, zc2 = st.columns([6, 1])
                with zc1:
                    active = st.toggle(f"{z}{_badge}", value=not is_disabled,
                                       key=f"zone_toggle_{i}")
                    if active == is_disabled:
                        if active:
                            _disabled = [d for d in _disabled if d != z]
                        else:
                            if z not in _disabled:
                                _disabled.append(z)
                        settings_set(con, "gate_zones_disabled_json", json.dumps(_disabled, ensure_ascii=False))
                        st.rerun()
                with zc2:
                    if st.button("삭제", key=f"del_zone_{i}", use_container_width=True):
                        _zones.pop(i)
                        _disabled = [d for d in _disabled if d != z]
                        settings_set(con, "gate_zones_json", json.dumps(_zones, ensure_ascii=False))
                        settings_set(con, "gate_zones_disabled_json", json.dumps(_disabled, ensure_ascii=False))
                        st.rerun()
    else:
        st.caption("등록된 터미널이 없습니다.")

    st.markdown("""<style>
    .st-key-zone_add_wrap [data-testid="stForm"] {
        padding-bottom: 4px !important;
    }
    </style>""", unsafe_allow_html=True)
    with st.container(key="zone_add_wrap"):
        with st.form("zone_add_form", clear_on_submit=True):
            zf1, zf2 = st.columns([5, 1])
            with zf1:
                new_zone = st.text_input("새 터미널 추가", placeholder="예) A터미널, 101동 앞, 정문 하역장")
            with zf2:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                add_zone = st.form_submit_button("추가", use_container_width=True)
            if add_zone:
                nz = new_zone.strip()
                if nz and nz not in _zones:
                    _zones.append(nz)
                    settings_set(con, "gate_zones_json", json.dumps(_zones, ensure_ascii=False))
                    st.rerun()
                elif nz in _zones:
                    st.warning(f"'{nz}'은 이미 등록되어 있습니다.")

    # ── 터미널 사용 예약존 ────────────────────────────────────────────────
    st.markdown("##### 터미널 드롭다운 사용 예약존")
    st.caption("선택된 예약존에서만 신청 폼에 터미널 선택이 표시됩니다.")
    try:
        _tz_active = [z for z in json.loads(settings_get(con, "booking_zones_json", '["A"]'))
                      if z not in json.loads(settings_get(con, "booking_zones_disabled_json", "[]"))]
    except Exception:
        _tz_active = []
    try:
        _tz_sel: list = json.loads(settings_get(con, "terminal_zones_json", '["A"]'))
    except Exception:
        _tz_sel = ["A"]
    _tz_default = [z for z in _tz_sel if z in _tz_active]
    _tz_new = st.multiselect("터미널 사용 존 선택", options=_tz_active, default=_tz_default,
                              key="terminal_zones_ms")
    if st.button("저장", key="terminal_zones_save", type="primary", use_container_width=True):
        settings_set(con, "terminal_zones_json", json.dumps(_tz_new, ensure_ascii=False))
        st.success("저장되었습니다.")
        st.rerun()

    st.markdown("---")

    # ── 예약존 설정 ────────────────────────────────────────────────────────
    st.markdown("#### 🏗️ 예약존 설정")
    st.caption("신청 탭에서 시간대별로 관리할 구역입니다. (예: A존, B존, 크레인1)")
    _bz_raw = settings_get(con, "booking_zones_json", '["A"]')
    try:
        _bzones: list = json.loads(_bz_raw)
    except Exception:
        _bzones = ["A"]
    _bz_dis_raw = settings_get(con, "booking_zones_disabled_json", "[]")
    try:
        _bz_disabled: list = json.loads(_bz_dis_raw)
    except Exception:
        _bz_disabled = []

    if _bzones:
        st.markdown("""<style>
        [class*="st-key-bzone_row_"] .stHorizontalBlock {
            align-items: center !important; flex-wrap: nowrap !important; gap: 8px !important;
        }
        [class*="st-key-bzone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important; min-width: 0 !important;
        }
        [class*="st-key-bzone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 52px !important; min-width: 52px !important; max-width: 52px !important;
        }
        [class*="st-key-bzone_row_"] [data-testid="stElementContainer"] { margin: 0 !important; padding: 0 !important; }
        [class*="st-key-bzone_toggle_"] label { font-size: 14px !important; color: #0f172a !important; }
        [class*="st-key-bzone_toggle_"] label p { font-size: 14px !important; margin: 0 !important; }
        [class*="st-key-del_bzone_"] button {
            background-color: #b91c1c !important; border-color: #b91c1c !important;
            border-radius: 4px !important; height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important; display: flex !important; align-items: center !important; justify-content: center !important;
        }
        [class*="st-key-del_bzone_"] button:hover { background-color: #991b1b !important; }
        [class*="st-key-del_bzone_"] button,
        [class*="st-key-del_bzone_"] button p,
        [class*="st-key-del_bzone_"] button span {
            color: #f8f8f8 !important; font-size: 11px !important; line-height: 1 !important; margin: 0 !important; padding: 0 !important;
        }
        </style>""", unsafe_allow_html=True)
        for i, bz in enumerate(_bzones):
            is_bz_dis = bz in _bz_disabled
            _bz_badge = "  ⚠️비활성" if is_bz_dis else ""
            with st.container(key=f"bzone_row_{i}"):
                bc1, bc2 = st.columns([6, 1])
                with bc1:
                    bz_active = st.toggle(f"{bz}{_bz_badge}", value=not is_bz_dis, key=f"bzone_toggle_{i}")
                    if bz_active == is_bz_dis:
                        if bz_active:
                            _bz_disabled = [d for d in _bz_disabled if d != bz]
                        else:
                            if bz not in _bz_disabled:
                                _bz_disabled.append(bz)
                        settings_set(con, "booking_zones_disabled_json", json.dumps(_bz_disabled, ensure_ascii=False))
                        st.rerun()
                with bc2:
                    if st.button("삭제", key=f"del_bzone_{i}", use_container_width=True):
                        _bzones.pop(i)
                        _bz_disabled = [d for d in _bz_disabled if d != bz]
                        settings_set(con, "booking_zones_json", json.dumps(_bzones, ensure_ascii=False))
                        settings_set(con, "booking_zones_disabled_json", json.dumps(_bz_disabled, ensure_ascii=False))
                        st.rerun()
    else:
        st.caption("등록된 예약존이 없습니다.")

    with st.container(key="bzone_add_wrap"):
        with st.form("bzone_add_form", clear_on_submit=True):
            bf1, bf2 = st.columns([5, 1])
            with bf1:
                new_bzone = st.text_input("새 예약존 추가", placeholder="예) A존, 크레인1, 하역장")
            with bf2:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                add_bzone = st.form_submit_button("추가", use_container_width=True)
            if add_bzone:
                nbz = new_bzone.strip()
                if nbz and nbz not in _bzones:
                    _bzones.append(nbz)
                    settings_set(con, "booking_zones_json", json.dumps(_bzones, ensure_ascii=False))
                    st.rerun()
                elif nbz in _bzones:
                    st.warning(f"'{nbz}'은 이미 등록되어 있습니다.")

    st.markdown("---")

    # Module management section
    project_id = st.session_state.get("PROJECT_ID")
    if project_id:
        render_module_manager(con, project_id)
    else:
        st.caption("프로젝트를 선택하면 모듈 설정을 관리할 수 있습니다.")
