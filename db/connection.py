"""Database connection and initialization."""
import sqlite3
from pathlib import Path
import streamlit as st
from shared.helpers import ensure_dir

def get_base_dir() -> Path:
    return Path(st.session_state.get("BASE_DIR", "MaterialToolShared"))

def path_db() -> Path:
    return get_base_dir() / "gate_tool.db"

def path_output_root() -> Path:
    return get_base_dir() / "output"

def path_output() -> dict:
    root = path_output_root()
    return {
        "plan": ensure_dir(root / "plan"),
        "permit": ensure_dir(root / "permit"),
        "check": ensure_dir(root / "check"),
        "exec": ensure_dir(root / "exec"),
        "photo": ensure_dir(root / "photo"),
        "qr": ensure_dir(root / "qr"),
        "bundle": ensure_dir(root / "bundle"),
        "zip": ensure_dir(root / "zip"),
        "sign": ensure_dir(root / "sign"),
        "stamp": ensure_dir(root / "stamp"),
    }

def con_open() -> sqlite3.Connection:
    ensure_dir(get_base_dir())
    con = sqlite3.connect(str(path_db()), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con
