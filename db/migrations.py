"""Schema migrations — no-op on Supabase (schema is managed via Supabase MCP/Dashboard).

Kept as a stub so app.py's `db_init_and_migrate(con)` call still works.
"""
from supabase import Client


def db_init_and_migrate(con: Client) -> None:
    return None


def set_default(con: Client, key: str, val: str) -> None:
    """Insert a settings row only if *key* does not already exist."""
    from shared.helpers import now_str
    existing = con.table("settings").select("key").eq("key", key).limit(1).execute()
    if existing.data:
        return
    con.table("settings").insert({
        "key": key,
        "value": val,
        "updated_at": now_str(),
    }).execute()
