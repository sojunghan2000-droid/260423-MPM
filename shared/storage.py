"""Supabase Storage helpers — upload, URL retrieval, deletion."""
import uuid
from pathlib import Path
from typing import Optional
import streamlit as st
from supabase import Client

from db.connection import storage_bucket


_BUCKET_READY = {"ok": False}


def ensure_bucket(con: Client) -> None:
    """Create the storage bucket if missing (idempotent)."""
    if _BUCKET_READY["ok"]:
        return
    name = storage_bucket()
    try:
        buckets = con.storage.list_buckets()
        existing = {b.name if hasattr(b, "name") else b.get("name") for b in buckets}
        if name not in existing:
            con.storage.create_bucket(name, options={"public": False})
    except Exception:
        pass
    _BUCKET_READY["ok"] = True


def upload_bytes(con: Client, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to storage under `key`. Returns the object key."""
    ensure_bucket(con)
    bucket = storage_bucket()
    try:
        con.storage.from_(bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as e:
        msg = str(e)
        if "already exists" in msg.lower() or "duplicate" in msg.lower():
            con.storage.from_(bucket).update(
                path=key, file=data,
                file_options={"content-type": content_type},
            )
        else:
            raise
    return key


def upload_file(con: Client, key: str, local_path: Path, content_type: Optional[str] = None) -> str:
    data = Path(local_path).read_bytes()
    if not content_type:
        suffix = Path(local_path).suffix.lower()
        content_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".pdf": "application/pdf", ".zip": "application/zip",
        }.get(suffix, "application/octet-stream")
    return upload_bytes(con, key, data, content_type)


def signed_url(con: Client, key: str, expires_in: int = 3600) -> str:
    """Return a signed URL for `key`. Empty string on failure."""
    if not key:
        return ""
    ensure_bucket(con)
    bucket = storage_bucket()
    try:
        resp = con.storage.from_(bucket).create_signed_url(key, expires_in)
        if isinstance(resp, dict):
            return resp.get("signedURL") or resp.get("signed_url") or ""
        return getattr(resp, "signed_url", "") or ""
    except Exception:
        return ""


def download_bytes(con: Client, key: str) -> bytes:
    """Download file bytes from storage."""
    ensure_bucket(con)
    return con.storage.from_(storage_bucket()).download(key)


def delete_key(con: Client, key: str) -> None:
    if not key:
        return
    try:
        con.storage.from_(storage_bucket()).remove([key])
    except Exception:
        pass


def photo_key(project_id: str, req_id: str, slot_key: str, suffix: str = ".jpg") -> str:
    return f"photos/{project_id}/{req_id}/{slot_key}-{uuid.uuid4().hex[:8]}{suffix}"


def sign_key(project_id: str, suffix: str = ".png") -> str:
    return f"signs/{project_id}/{uuid.uuid4().hex}{suffix}"


def stamp_key(project_id: str, suffix: str = ".png") -> str:
    return f"stamps/{project_id}/{uuid.uuid4().hex}{suffix}"


def output_key(project_id: str, req_id: str, kind: str, suffix: str = ".pdf") -> str:
    return f"outputs/{project_id}/{req_id}/{kind}{suffix}"


def as_imagereader(con: Client, key_or_path: str):
    """Return a reportlab ImageReader for a storage key or local path."""
    from io import BytesIO
    from reportlab.lib.utils import ImageReader
    if not key_or_path:
        return None
    try:
        data = download_bytes(con, key_or_path)
        if data:
            return ImageReader(BytesIO(data))
    except Exception:
        pass
    p = Path(key_or_path)
    if p.exists():
        try:
            return ImageReader(str(p))
        except Exception:
            return None
    return None


def get_bytes_or_none(con: Client, key_or_path: str) -> Optional[bytes]:
    if not key_or_path:
        return None
    try:
        data = download_bytes(con, key_or_path)
        if data:
            return data
    except Exception:
        pass
    p = Path(key_or_path)
    if p.exists():
        try:
            return p.read_bytes()
        except Exception:
            return None
    return None
