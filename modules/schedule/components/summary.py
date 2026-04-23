"""Daily summary component."""
import sqlite3
import streamlit as st
from datetime import date
from typing import List, Dict, Any
from config import KIND_IN, KIND_OUT


def render_daily_summary(schedules: List[Dict[str, Any]], con: sqlite3.Connection = None):
    """Render daily summary card — counts based on today's requests (date field)."""
    today = date.today().isoformat()

    if con is not None:
        # 금일 반입예정일 기준 요청 집계
        pid = st.session_state.get("PROJECT_ID", "")
        cur = con.cursor()
        cur.execute(
            "SELECT kind, gate FROM requests WHERE project_id=? AND date=?",
            (pid, today),
        )
        rows = [dict(r) for r in cur.fetchall()]
    else:
        rows = [s for s in schedules if (s.get("date") or "")[:10] == today]

    in_count  = sum(1 for r in rows if r.get("kind") == KIND_IN)
    out_count = sum(1 for r in rows if r.get("kind") == KIND_OUT)
    gates: Dict[str, int] = {}
    for r in rows:
        g = r.get("gate", "N/A") or "N/A"
        gates[g] = gates.get(g, 0) + 1

    gate_text = " / ".join(f"{k}: {v}건" for k, v in sorted(gates.items()))

    st.markdown(
        f"""
    <div class="card" style="margin-top:12px;">
      <h4 style="margin:0 0 8px 0;">금일 요약</h4>
      <p style="margin:0; font-size:13px;">
        반입: <strong>{in_count}건</strong> / 반출: <strong>{out_count}건</strong>
      </p>
      <p style="margin:4px 0 0 0; font-size:12px; color:var(--text-muted);">
        GATE별: {gate_text or '없음'}
      </p>
    </div>
    """,
        unsafe_allow_html=True,
    )
