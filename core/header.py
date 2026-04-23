"""Hero header rendering."""
import sqlite3
import streamlit as st
from datetime import date
from config import APP_VERSION, DEFAULT_SITE_NAME
from db.models import settings_get

def ui_header(con: sqlite3.Connection):
    """Render hero header with KPI stats."""
    # 프로젝트명 우선, 없으면 settings의 site_name 사용
    site_name = st.session_state.get("PROJECT_NAME") or settings_get(con, "site_name", DEFAULT_SITE_NAME)
    user_name = st.session_state.get("USER_NAME", "")
    user_role = st.session_state.get("USER_ROLE", "")
    is_admin = st.session_state.get("IS_ADMIN", False)
    project_id = st.session_state.get("PROJECT_ID", "")
    today = date.today().isoformat()
    cur = con.cursor()
    cur.execute(
        "SELECT"
        " COUNT(*) AS total,"
        " SUM(CASE WHEN status='PENDING_APPROVAL' THEN 1 ELSE 0 END) AS pending,"
        " SUM(CASE WHEN status IN ('APPROVED','EXECUTING') THEN 1 ELSE 0 END) AS approved,"
        " SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) AS done,"
        " SUM(COALESCE(vehicle_count,0)) AS total_v,"
        " SUM(CASE WHEN status='PENDING_APPROVAL' THEN COALESCE(vehicle_count,0) ELSE 0 END) AS pending_v,"
        " SUM(CASE WHEN status IN ('APPROVED','EXECUTING') THEN COALESCE(vehicle_count,0) ELSE 0 END) AS approved_v,"
        " SUM(CASE WHEN status='DONE' THEN COALESCE(vehicle_count,0) ELSE 0 END) AS done_v"
        " FROM requests WHERE project_id=? AND date=?",
        (project_id, today),
    )
    row = cur.fetchone()
    total    = (row["total"]    if row else 0) or 0
    pending  = (row["pending"]  if row else 0) or 0
    approved = (row["approved"] if row else 0) or 0
    done     = (row["done"]     if row else 0) or 0
    total_v    = (row["total_v"]    if row else 0) or 0
    pending_v  = (row["pending_v"]  if row else 0) or 0
    approved_v = (row["approved_v"] if row else 0) or 0
    done_v     = (row["done_v"]     if row else 0) or 0
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
