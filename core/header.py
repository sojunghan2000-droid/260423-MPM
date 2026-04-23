"""Hero header rendering (Supabase-backed KPI aggregation in Python)."""
import streamlit as st
from datetime import date
from supabase import Client
from config import APP_VERSION, DEFAULT_SITE_NAME
from db.models import settings_get


def _safe_int(v, default=0) -> int:
    try:
        return int(v) if v is not None and str(v).strip() != "" else default
    except (ValueError, TypeError):
        return default


def ui_header(con: Client):
    site_name = st.session_state.get("PROJECT_NAME") or settings_get(con, "site_name", DEFAULT_SITE_NAME)
    user_name = st.session_state.get("USER_NAME", "")
    user_role = st.session_state.get("USER_ROLE", "")
    is_admin = st.session_state.get("IS_ADMIN", False)
    project_id = st.session_state.get("PROJECT_ID", "")
    today = date.today().isoformat()

    rows_res = (
        con.table("requests")
        .select("status,vehicle_count")
        .eq("project_id", project_id)
        .eq("date", today)
        .execute()
    )
    rows = rows_res.data or []

    total = pending = approved = done = 0
    total_v = pending_v = approved_v = done_v = 0
    for r in rows:
        s = r.get("status") or ""
        vc = _safe_int(r.get("vehicle_count"), 0)
        total   += 1
        total_v += vc
        if s == "PENDING_APPROVAL":
            pending   += 1
            pending_v += vc
        elif s in ("APPROVED", "EXECUTING"):
            approved   += 1
            approved_v += vc
        elif s == "DONE":
            done   += 1
            done_v += vc

    st.markdown(f"""
    <div class="hero">
      <div class="hero-content">
        <div class="title">🏗️ {site_name}</div>
        <div class="sub">{APP_VERSION} · 현장 자재 반출입 관리 · 👤 {user_name} ({user_role}){"&nbsp;&nbsp;🔐 관리자" if is_admin else ""}</div>
        <div class="kpi" style="margin-top:8px;">
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#334155;">{total}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{total_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">전체 요청</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#d97706;">{pending}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{pending_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">대기중</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#16a34a;">{approved}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{approved_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">승인됨</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#2563eb;">{done}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{done_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">완료</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
