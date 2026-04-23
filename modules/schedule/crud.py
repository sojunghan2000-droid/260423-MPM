"""Schedule CRUD operations."""
import sqlite3
from typing import List, Dict, Any, Optional
from shared.helpers import now_str, new_id


def schedule_insert(con, project_id, data: dict) -> str:
    """Insert a new schedule entry. Returns schedule id."""
    sid = new_id()
    cur = con.cursor()
    cur.execute(
        """INSERT INTO schedules(id, project_id, req_id, title, schedule_date,
        time_from, time_to, kind, gate, company_name, vehicle_info, status, color, created_by, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            sid,
            project_id,
            data.get("req_id", ""),
            data["title"],
            data["schedule_date"],
            data["time_from"],
            data["time_to"],
            data.get("kind", "IN"),
            data.get("gate", ""),
            data.get("company_name", ""),
            data.get("vehicle_info", ""),
            data.get("status", "PENDING"),
            data.get("color", "#fbbf24"),
            data.get("created_by", ""),
            now_str(),
        ),
    )
    con.commit()
    return sid


def schedule_list_by_date(con, project_id, schedule_date) -> List[Dict[str, Any]]:
    """Get all schedules for a date, ordered by time_from."""
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM schedules WHERE project_id=? AND schedule_date=? ORDER BY time_from ASC",
        (project_id, schedule_date),
    )
    return [dict(r) for r in cur.fetchall()]


def schedule_update(con, sid, **kwargs):
    """Update a schedule entry by id. Pass column=value pairs as kwargs."""
    if not kwargs:
        return
    allowed = {
        "title", "schedule_date", "time_from", "time_to", "kind", "gate",
        "company_name", "vehicle_info", "status", "color", "req_id",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    set_clause = ", ".join(f"{k}=?" for k in filtered)
    values = list(filtered.values()) + [sid]
    cur = con.cursor()
    cur.execute(f"UPDATE schedules SET {set_clause} WHERE id=?", values)
    con.commit()


def schedule_delete(con, sid):
    """Delete a schedule entry by id."""
    cur = con.cursor()
    cur.execute("DELETE FROM schedules WHERE id=?", (sid,))
    con.commit()


def schedule_get(con, sid) -> Optional[Dict[str, Any]]:
    """Get a single schedule entry by id."""
    cur = con.cursor()
    cur.execute("SELECT * FROM schedules WHERE id=?", (sid,))
    row = cur.fetchone()
    return dict(row) if row else None


def schedule_by_req_id(con, req_id: str) -> Optional[Dict[str, Any]]:
    """Get the first schedule entry linked to a request id."""
    cur = con.cursor()
    cur.execute("SELECT * FROM schedules WHERE req_id=? ORDER BY created_at LIMIT 1", (req_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def schedule_sync_from_requests(con, project_id):
    """Sync schedule entries from existing approved requests (auto-populate).

    For each approved request that does not yet have a corresponding schedule
    entry, create one automatically.
    """
    cur = con.cursor()
    # Find approved requests that have no linked schedule entry yet
    cur.execute(
        """SELECT r.* FROM requests r
        LEFT JOIN schedules s ON s.req_id = r.id AND s.project_id = r.project_id
        WHERE r.project_id=? AND r.status IN ('PENDING_APPROVAL', 'APPROVED') AND s.id IS NULL""",
        (project_id,),
    )
    rows = cur.fetchall()
    for r in rows:
        r = dict(r)
        req_status   = r.get("status", "")
        sched_status = "PENDING" if req_status == "PENDING_APPROVAL" else "APPROVED"
        sched_color  = "#fbbf24" if sched_status == "PENDING" else "#22c55e"
        time_from    = r.get("time_from", "08:00") or "08:00"
        time_to      = r.get("time_to") or _add_30min(time_from)

        # 30분 단위 슬롯별로 개별 레코드 생성
        from config import TIME_SLOTS
        try:
            fi = TIME_SLOTS.index(time_from)
            ti = TIME_SLOTS.index(time_to)
        except ValueError:
            fi, ti = 0, 1

        slot_pairs = [(TIME_SLOTS[i], TIME_SLOTS[i + 1])
                      for i in range(fi, ti) if i + 1 < len(TIME_SLOTS)]
        if not slot_pairs:
            slot_pairs = [(time_from, _add_30min(time_from))]

        base = {
            "req_id":        r.get("id", ""),
            "title":         r.get("company_name", "자재 반출입"),
            "schedule_date": r.get("date", r.get("created_at", "")[:10]),
            "kind":          r.get("kind", "IN"),
            "gate":          r.get("gate", ""),
            "company_name":  r.get("company_name", ""),
            "vehicle_info":  f"{r.get('vehicle_type','')} {r.get('vehicle_ton','')}t".strip(),
            "status":        sched_status,
            "color":         sched_color,
            "created_by":    "system",
        }
        for sf, st_ in slot_pairs:
            schedule_insert(con, project_id, {**base, "time_from": sf, "time_to": st_})


def _add_30min(time_str: str) -> str:
    """Add 30 minutes to a HH:MM time string."""
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        m += 30
        if m >= 60:
            m -= 60
            h += 1
        if h >= 24:
            h = 23
            m = 59
        return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        return "08:30"
