"""Outputs CRUD — generates PDFs to temp, uploads to Supabase Storage."""

import json
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from supabase import Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from shared.helpers import now_str, req_display_id
from shared.storage import upload_file, output_key, get_bytes_or_none
from db.models import settings_get
from db.connection import path_output, path_output_root
from config import APP_VERSION
from modules.request.crud import req_get
from modules.approval.crud import approvals_for_req
from modules.execution.crud import execution_get, photos_for_req
from modules.outputs.pdf import (
    QR_AVAILABLE,
    qr_generate_png,
    pdf_simple_header,
    pdf_plan,
    pdf_permit,
    pdf_check_card,
    pdf_exec_summary,
    _FONT_NORMAL,
    _FONT_BOLD,
)


def outputs_upsert(con: Client, rid: str, **paths: str) -> None:
    """Upsert output storage keys for a request."""
    payload = {k: v for k, v in paths.items() if v is not None}
    if not payload:
        con.table("outputs").upsert({
            "req_id": rid, "created_at": now_str(), "updated_at": now_str(),
        }, on_conflict="req_id").execute()
        return
    payload["updated_at"] = now_str()
    existing = (
        con.table("outputs").select("req_id").eq("req_id", rid).limit(1).execute()
    )
    if not existing.data:
        payload.setdefault("created_at", now_str())
        payload["req_id"] = rid
        con.table("outputs").insert(payload).execute()
    else:
        con.table("outputs").update(payload).eq("req_id", rid).execute()


def outputs_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    r = con.table("outputs").select("*").eq("req_id", rid).limit(1).execute()
    return r.data[0] if r.data else None


def _compute_day_seq(con: Client, req: Dict[str, Any]) -> int:
    """Count of same-day (project_id, date) rows whose created_at <= this one's."""
    pid = req.get("project_id", "") or ""
    planned_date = (req.get("date") or req.get("created_at") or "")[:10]
    same_day = (
        con.table("requests")
        .select("id,created_at,date")
        .eq("project_id", pid)
        .eq("date", planned_date)
        .execute()
    ).data or []
    my_created = req.get("created_at", "")
    n = sum(1 for r in same_day if (r.get("created_at") or "") <= my_created)
    return max(n, 1)


def zip_build(out_zip: Path, include: List[tuple]) -> Path:
    """Build a ZIP archive. `include` is list of (arcname, bytes)."""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, data in include:
            if data:
                z.writestr(arcname, data)
    return out_zip


def generate_all_outputs(con: Client, rid: str) -> Dict[str, str]:
    """Generate all PDFs, upload to Storage, persist keys, return keys + signed URLs."""
    req = req_get(con, rid)
    if not req:
        raise ValueError("요청을 찾을 수 없습니다.")
    out = path_output()
    approvals = approvals_for_req(con, rid)
    exec_row = execution_get(con, rid)
    photos = photos_for_req(con, rid)
    sic_default = settings_get(con, "sic_training_url_default", "https://example.com/visitor-training")
    sic_url = (req.get("sic_training_url") or "").strip() or sic_default

    req["day_seq"] = _compute_day_seq(con, req)
    disp = req_display_id(req)
    pid = req.get("project_id", "")

    # QR
    qr_local = out["qr"] / f"{disp}_sic_qr.png"
    qr_saved = qr_generate_png(sic_url, qr_local) if QR_AVAILABLE else None
    qr_key = ""
    if qr_saved:
        qr_key = upload_file(con, output_key(pid, rid, "sic_qr", ".png"), qr_saved, "image/png")
        outputs_upsert(con, rid, qr_png_path=qr_key)

    # Plan PDF
    plan_local = out["plan"] / f"{disp}_plan.pdf"
    pdf_plan(con, req, approvals, plan_local, photos=photos)
    plan_key = upload_file(con, output_key(pid, rid, "plan"), plan_local, "application/pdf")

    # Permit PDF
    permit_local = out["permit"] / f"{disp}_permit.pdf"
    pdf_permit(con, req, sic_url, qr_saved, permit_local)
    permit_key = upload_file(con, output_key(pid, rid, "permit"), permit_local, "application/pdf")

    # Check card PDF
    check_key = ""
    check_local: Optional[Path] = None
    check_json: Dict[str, Any] = {}
    if exec_row and exec_row.get("check_json"):
        try:
            check_json = json.loads(exec_row["check_json"])
        except Exception:
            check_json = {}
        check_local = out["check"] / f"{disp}_checkcard.pdf"
        pdf_check_card(con, req, check_json, check_local)
        check_key = upload_file(con, output_key(pid, rid, "checkcard"), check_local, "application/pdf")

    # Exec summary PDF
    exec_local = out["exec"] / f"{disp}_exec.pdf"
    pdf_exec_summary(con, req, photos, exec_local)
    exec_key = upload_file(con, output_key(pid, rid, "exec"), exec_local, "application/pdf")

    # Bundle PDF (index)
    bundle_local = out["bundle"] / f"{disp}_bundle.pdf"
    c = canvas.Canvas(str(bundle_local), pagesize=A4)
    pdf_simple_header(c, "산출물 번들 안내", f"요청ID: {rid} · 생성: {now_str()} · {APP_VERSION}")
    c.setFont(_FONT_NORMAL, 11)
    c.drawString(20 * mm, 260 * mm, "아래 파일들이 함께 생성되었습니다.")
    c.setFont(_FONT_NORMAL, 10)
    y = 248 * mm
    for name in (f"{disp}_plan.pdf", f"{disp}_permit.pdf",
                 f"{disp}_checkcard.pdf" if check_local else None,
                 f"{disp}_exec.pdf",
                 f"{disp}_sic_qr.png" if qr_saved else None):
        if name:
            c.drawString(22 * mm, y, f"- {name}")
            y -= 7 * mm
    c.drawString(20 * mm, 220 * mm, "저장 위치: Supabase Storage")
    c.showPage()
    c.save()
    bundle_key = upload_file(con, output_key(pid, rid, "bundle"), bundle_local, "application/pdf")

    # ZIP (of all generated artefacts)
    zip_local = out["zip"] / f"{disp}_outputs.zip"
    include: List[tuple] = [
        (f"{disp}_plan.pdf",   plan_local.read_bytes()),
        (f"{disp}_permit.pdf", permit_local.read_bytes()),
        (f"{disp}_exec.pdf",   exec_local.read_bytes()),
        (f"{disp}_bundle.pdf", bundle_local.read_bytes()),
    ]
    if check_local:
        include.append((f"{disp}_checkcard.pdf", check_local.read_bytes()))
    if qr_saved:
        include.append((f"{disp}_sic_qr.png", qr_saved.read_bytes()))
    for p in photos:
        key = p.get("storage_url") or p.get("file_path") or ""
        data = get_bytes_or_none(con, key)
        if data:
            include.append((f"photos/{key.split('/')[-1]}", data))
    zip_build(zip_local, include)
    zip_key = upload_file(con, output_key(pid, rid, "outputs", ".zip"), zip_local, "application/zip")

    outputs_upsert(
        con, rid,
        plan_pdf_path=plan_key,
        permit_pdf_path=permit_key,
        check_pdf_path=check_key,
        exec_pdf_path=exec_key,
        bundle_pdf_path=bundle_key,
        zip_path=zip_key,
    )
    return {
        "plan_pdf":   plan_key,
        "permit_pdf": permit_key,
        "check_pdf":  check_key,
        "exec_pdf":   exec_key,
        "bundle_pdf": bundle_key,
        "zip":        zip_key,
        "qr":         qr_key,
        "root":       str(path_output_root()),
    }
