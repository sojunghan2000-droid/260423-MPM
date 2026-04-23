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

    # ── Zone 설정 ──────────────────────────────────────────────────────
    st.markdown("#### 🚧 Zone 설정")
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
        st.caption("등록된 Zone · 토글로 활성/비활성 전환, 삭제 버튼으로 제거")
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
        st.caption("등록된 Zone이 없습니다.")

    st.markdown("""<style>
    .st-key-zone_add_wrap [data-testid="stForm"] {
        padding-bottom: 4px !important;
    }
    </style>""", unsafe_allow_html=True)
    with st.container(key="zone_add_wrap"):
        with st.form("zone_add_form", clear_on_submit=True):
            zf1, zf2 = st.columns([5, 1])
            with zf1:
                new_zone = st.text_input("새 Zone 추가", placeholder="예) A구역, 101동 앞")
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

    st.markdown("---")

    # Module management section
    project_id = st.session_state.get("PROJECT_ID")
    if project_id:
        render_module_manager(con, project_id)
    else:
        st.caption("프로젝트를 선택하면 모듈 설정을 관리할 수 있습니다.")
