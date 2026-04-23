"""Schedule CRUD operations (Supabase-backed)."""
from typing import List, Dict, Any, Optional
from supabase import Client
from shared.helpers import now_str, new_id


def schedule_insert(con: Client, project_id: str, data: dict) -> str:
    sid = new_id()
    con.table("schedules").insert({
        "id":            sid,
        "project_id":    project_id,
        "req_id":        data.get("req_id", ""),
        "title":         data["title"],
        "schedule_date": data["schedule_date"],
        "time_from":     data["time_from"],
        "time_to":       data["time_to"],
        "kind":          data.get("kind", "IN"),
        "gate":          data.get("gate", ""),
        "company_name":  data.get("company_name", ""),
        "vehicle_info":  data.get("vehicle_info", ""),
        "status":        data.get("status", "PENDING"),
        "color":         data.get("color", "#fbbf24"),
        "created_by":    data.get("created_by", ""),
        "created_at":    now_str(),
    }).execute()
    return sid


def schedule_list_by_date(con: Client, project_id: str, schedule_date: str) -> List[Dict[str, Any]]:
    r = (
        con.table("schedules")
        .select("*")
        .eq("project_id", project_id)
        .eq("schedule_date", schedule_date)
        .order("time_from")
        .execute()
    )
    return r.data or []


def schedule_update(con: Client, sid: str, **kwargs):
    if not kwargs:
        return
    allowed = {
        "title", "schedule_date", "time_from", "time_to", "kind", "gate",
        "company_name", "vehicle_info", "status", "color", "req_id",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    con.table("schedules").update(filtered).eq("id", sid).execute()


def schedule_delete(con: Client, sid: str):
    con.table("schedules").delete().eq("id", sid).execute()


def schedule_get(con: Client, sid: str) -> Optional[Dict[str, Any]]:
    r = con.table("schedules").select("*").eq("id", sid).limit(1).execute()
    return r.data[0] if r.data else None


def schedule_by_req_id(con: Client, req_id: str) -> Optional[Dict[str, Any]]:
    r = (
        con.table("schedules")
        .select("*")
        .eq("req_id", req_id)
        .order("created_at")
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def schedule_sync_from_requests(con: Client, project_id: str):
    """For each approved/pending request without a schedule, auto-create slot(s)."""
    reqs = (
        con.table("requests")
        .select("*")
        .eq("project_id", project_id)
        .in_("status", ["PENDING_APPROVAL", "APPROVED"])
        .execute()
    ).data or []
    if not reqs:
        return
    sch = (
        con.table("schedules")
        .select("req_id")
        .eq("project_id", project_id)
        .in_("req_id", [r["id"] for r in reqs])
        .execute()
    ).data or []
    already = {s.get("req_id") for s in sch if s.get("req_id")}

    from config import TIME_SLOTS

    for r in reqs:
        if r.get("id") in already:
            continue
        req_status   = r.get("status", "")
        sched_status = "PENDING" if req_status == "PENDING_APPROVAL" else "APPROVED"
        sched_color  = "#fbbf24" if sched_status == "PENDING" else "#22c55e"
        time_from    = r.get("time_from", "08:00") or "08:00"
        time_to      = r.get("time_to") or _add_30min(time_from)

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
            "schedule_date": r.get("date", (r.get("created_at") or "")[:10]),
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
