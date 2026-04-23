"""Supabase connection (replaces SQLite). `con` is a Supabase Client."""
from pathlib import Path
from functools import lru_cache
import streamlit as st
from supabase import create_client, Client

from shared.helpers import ensure_dir


def get_base_dir() -> Path:
    return Path(st.session_state.get("BASE_DIR", "MaterialToolShared"))


def path_output_root() -> Path:
    return get_base_dir() / "output"


def path_output() -> dict:
    """Local cache directory for temporarily generated files before upload."""
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


@st.cache_resource(show_spinner=False)
def _make_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def con_open() -> Client:
    """Return a cached Supabase client. Drop-in replacement for old sqlite connection."""
    return _make_client()


def storage_bucket() -> str:
    return st.secrets.get("SUPABASE_STORAGE_BUCKET", "material-gate")
