"""Request registration page."""

import sqlite3
from datetime import date

import streamlit as st

from config import KIND_IN, KIND_OUT, RISK_LEVELS
from modules.request.crud import req_insert, req_get
from modules.approval.crud import approvals_create_default
from shared.helpers import req_display_id, phone_input

_TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(7, 21) for m in (0, 30)] + ["20:00"]
# 중복 제거 및 정렬
_TIME_SLOTS = sorted(set(_TIME_SLOTS))


def _time_picker(key_prefix: str) -> tuple:
    """Range slider time picker — consecutive selection only. Returns (time_from_str, time_to_str)."""
    result = st.select_slider(
        "시간*",
        options=_TIME_SLOTS,
        value=("09:00", "17:00"),
        key=key_prefix,
    )
    return result[0], result[1]


def page_request(con: sqlite3.Connection):
    st.markdown("### 📝 요청 등록")

    # 그룹1 - 기본정보
    st.markdown("**📋 기본 정보**")
    c1, c2 = st.columns(2)
    with c1:
        company_name = st.text_input("협력사*")
    with c2:
        item_name = st.text_input("자재명*")
    c1, c2 = st.columns(2)
    with c1:
        date_val = st.date_input("일자*", value=date.today())
    with c2:
        kind_display = st.selectbox("구분*", ["반입", "반출"])
    kind_val = KIND_IN if kind_display == "반입" else KIND_OUT

    time_from_str, time_to_str = _time_picker("req_time")

    c1, _ = st.columns(2)
    with c1:
        gate = st.text_input("GATE", value="1GATE")

    # 그룹2 - 차량정보
    st.markdown("**🚛 차량 정보**")
    c1, c2 = st.columns(2)
    with c1:
        vehicle_type = st.text_input("차량종류")
        vehicle_ton = st.text_input("톤수", value="5")
    with c2:
        vehicle_count = st.number_input("대수", min_value=1, value=1)
        risk_level = st.selectbox(
            "위험도",
            options=[code for code, _ in RISK_LEVELS],
            format_func=lambda code: next(label for c, label in RISK_LEVELS if c == code),
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
    # 그룹3 - 운전원정보
    st.markdown("**👤 운전원**")
    c1, c2 = st.columns(2)
    with c1:
        driver_name = st.text_input("운전원*")
    with c2:
        driver_phone = phone_input("연락처", key="req_driver_phone")

    # 비고
    notes = st.text_area("비고", height=60)

    if st.button("요청 등록", type="primary", use_container_width=True):
        if not company_name.strip():
            st.error("협력사를 입력하세요.")
            return
        if not item_name.strip():
            st.error("자재명을 입력하세요.")
            return
        if not driver_name.strip():
            st.error("운전원을 입력하세요.")
            return
        if time_from_str is None or time_to_str is None:
            st.error("시간을 선택하세요. (시작 → 종료 순으로 선택)")
            return

        rid = req_insert(con, dict(
            kind=kind_val,
            project_id=st.session_state.get("PROJECT_ID", ""),
            company_name=company_name,
            item_name=item_name,
            item_type="",
            work_type="",
            date=str(date_val),
            time_from=time_from_str,
            time_to=time_to_str,
            gate=gate,
            vehicle_type=vehicle_type,
            vehicle_ton=vehicle_ton,
            vehicle_count=int(vehicle_count),
            driver_name=driver_name,
            driver_phone=driver_phone,
            notes=notes,
            requester_name=st.session_state.get("USER_NAME", ""),
            requester_role=st.session_state.get("USER_ROLE", ""),
            risk_level=risk_level,
            sic_training_url="",
        ))
        approvals_create_default(con, rid, kind_val)
        disp = req_display_id(req_get(con, rid) or {"id": rid})
        st.success(f"요청 등록 완료 · {disp}")
        st.rerun()
