"""Database connection — Supabase client factory (with optional sqlite fallback for dev)."""
from pathlib import Path

import streamlit as st
from supabase import Client, create_client

from shared.helpers import ensure_dir


# ── Supabase client (singleton per Streamlit runtime) ─────────────────────

@st.cache_resource
def get_supabase() -> Client:
    """Return a cached Supabase client. Reads SUPABASE_URL and SUPABASE_KEY from secrets."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def db_backend() -> str:
    """Backend toggle. 'supabase' (default) | 'sqlite'."""
    return str(st.secrets.get("DB_BACKEND", "supabase")).lower()


def con_open():
    """Compatibility shim — returns a Supabase Client (preferred) or sqlite Connection.

    All call sites have been migrated to expect a Supabase ``Client``; the sqlite
    branch is kept only as a manual fallback for offline diagnostics.
    """
    if db_backend() == "sqlite":
        import sqlite3
        ensure_dir(get_base_dir())
        con = sqlite3.connect(str(path_db()), check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con
    return get_supabase()


# ── Local file paths (PDF/photo cache, fonts, signatures) ────────────────

def get_base_dir() -> Path:
    return Path(st.session_state.get("BASE_DIR", "MaterialToolShared"))


def path_db() -> Path:
    """Legacy SQLite path (only used when DB_BACKEND='sqlite')."""
    return get_base_dir() / "gate_tool.db"


def path_output_root() -> Path:
    return get_base_dir() / "output"


def path_output() -> dict:
    """Local output directories (used as a tmp cache for PDF/QR generation)."""
    root = path_output_root()
    return {
        "plan":   ensure_dir(root / "plan"),
        "permit": ensure_dir(root / "permit"),
        "check":  ensure_dir(root / "check"),
        "exec":   ensure_dir(root / "exec"),
        "photo":  ensure_dir(root / "photo"),
        "qr":     ensure_dir(root / "qr"),
        "bundle": ensure_dir(root / "bundle"),
        "zip":    ensure_dir(root / "zip"),
        "sign":   ensure_dir(root / "sign"),
        "stamp":  ensure_dir(root / "stamp"),
    }


# ── Storage helpers ───────────────────────────────────────────────────────

def photos_bucket() -> str:
    return str(st.secrets.get("SUPABASE_PHOTOS_BUCKET", "photos"))


def outputs_bucket() -> str:
    return str(st.secrets.get("SUPABASE_OUTPUTS_BUCKET", "material-gate"))
