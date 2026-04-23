"""Outputs CRUD operations and generation."""

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from shared.helpers import now_str, req_display_id
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
)


def outputs_upsert(con: sqlite3.Connection, rid: str, **paths: str) -> None:
    """Insert or update output file paths for a request."""
    cur = con.cursor()
    cur.execute("SELECT req_id FROM outputs WHERE req_id=?", (rid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO outputs(req_id, created_at, updated_at) VALUES(?,?,?)",
            (rid, now_str(), now_str()),
        )
        con.commit()
    for k, v in paths.items():
        if v is not None:
            cur.execute(f"UPDATE outputs SET {k}=?, updated_at=? WHERE req_id=?", (v, now_str(), rid))
            con.commit()


def outputs_get(con: sqlite3.Connection, rid: str) -> Optional[Dict[str, Any]]:
    """Get the outputs record for a request."""
    cur = con.cursor()
    cur.execute("SELECT * FROM outputs WHERE req_id=?", (rid,))
    r = cur.fetchone()
    return dict(r) if r else None


def zip_build(con: sqlite3.Connection, rid: str, out_zip: Path, include_files: List[Path]) -> Path:
    """Build a ZIP archive from the given files."""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in include_files:
            if f and f.exists():
                z.write(str(f), arcname=f.name)
    return out_zip


def generate_all_outputs(con: sqlite3.Connection, rid: str) -> Dict[str, str]:
    """Generate all output files (PDFs, QR, ZIP) for a request."""
    req = req_get(con, rid)
    if not req:
        raise ValueError("요청을 찾을 수 없습니다.")
    out = path_output()
    approvals = approvals_for_req(con, rid)
    exec_row = execution_get(con, rid)
    photos = photos_for_req(con, rid)
    sic_default = settings_get(con, "sic_training_url_default", "https://example.com/visitor-training")
    sic_url = (req.get("sic_training_url") or "").strip() or sic_default

    # day_seq 직접 계산 — 반입예정일(date) 기준 당일 순번
    planned_date = (req.get('date') or req.get('created_at') or '')[:10]
    pid = req.get('project_id', '')
    cur2 = con.cursor()
    cur2.execute(
        "SELECT COUNT(*) FROM requests WHERE project_id=? AND date=? AND (date < ? OR (date = ? AND created_at <= ?))",
        (pid, planned_date, planned_date, planned_date, req['created_at']),
    )
    day_seq = cur2.fetchone()[0] or 1
    req['day_seq'] = day_seq
    disp = req_display_id(req)

    qr_path = out["qr"] / f"{disp}_sic_qr.png"
    qr_saved = qr_generate_png(sic_url, qr_path) if QR_AVAILABLE else None
    if qr_saved:
        outputs_upsert(con, rid, qr_png_path=str(qr_saved))

    plan_pdf = out["plan"] / f"{disp}_plan.pdf"
    pdf_plan(con, req, approvals, plan_pdf, photos=photos)

    permit_pdf = out["permit"] / f"{disp}_permit.pdf"
    pdf_permit(con, req, sic_url, qr_saved, permit_pdf)

    check_pdf: Optional[Path] = None
    check_json: Dict[str, Any] = {}
    if exec_row and exec_row.get("check_json"):
        try:
            check_json = json.loads(exec_row["check_json"])
        except Exception:
            check_json = {}
        check_pdf = out["check"] / f"{disp}_checkcard.pdf"
        pdf_check_card(con, req, check_json, check_pdf)

    exec_pdf = out["exec"] / f"{disp}_exec.pdf"
    pdf_exec_summary(con, req, photos, exec_pdf)

    bundle_pdf = out["bundle"] / f"{disp}_bundle.pdf"
    c = canvas.Canvas(str(bundle_pdf), pagesize=A4)
    pdf_simple_header(c, "산출물 번들 안내", f"요청ID: {rid} · 생성: {now_str()} · {APP_VERSION}")
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, 260 * mm, "아래 파일들이 함께 생성되었습니다.")
    c.setFont("Helvetica", 10)
    y = 248 * mm
    for f in [plan_pdf, permit_pdf, check_pdf, exec_pdf, qr_saved]:
        if f and Path(f).exists():
            c.drawString(22 * mm, y, f"- {Path(f).name}")
            y -= 7 * mm
    c.drawString(20 * mm, 220 * mm, f"저장 위치: {str(path_output_root())}")
    c.showPage()
    c.save()

    zip_path = out["zip"] / f"{disp}_outputs.zip"
    include: List[Path] = [plan_pdf, permit_pdf, exec_pdf, bundle_pdf]
    if check_pdf:
        include.append(check_pdf)
    if qr_saved:
        include.append(qr_saved)
    for p in photos:
        fp = Path(p["file_path"])
        if fp.exists():
            include.append(fp)
    zip_build(con, rid, zip_path, include)

    outputs_upsert(
        con, rid,
        plan_pdf_path=str(plan_pdf),
        permit_pdf_path=str(permit_pdf),
        check_pdf_path=str(check_pdf) if check_pdf else "",
        exec_pdf_path=str(exec_pdf),
        bundle_pdf_path=str(bundle_pdf),
        zip_path=str(zip_path),
    )
    return {
        "plan_pdf": str(plan_pdf),
        "permit_pdf": str(permit_pdf),
        "check_pdf": str(check_pdf) if check_pdf else "",
        "exec_pdf": str(exec_pdf),
        "bundle_pdf": str(bundle_pdf),
        "zip": str(zip_path),
        "qr": str(qr_saved) if qr_saved else "",
        "root": str(path_output_root()),
    }
