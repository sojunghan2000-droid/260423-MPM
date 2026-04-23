"""Schedule-specific query helpers."""
from supabase import Client

TIME_SLOTS_START = "06:00"
TIME_SLOTS_END = "18:00"
SLOT_INTERVAL_MINUTES = 30


def generate_time_slots():
    slots = []
    start_h, start_m = [int(x) for x in TIME_SLOTS_START.split(":")]
    end_h, end_m = [int(x) for x in TIME_SLOTS_END.split(":")]
    h, m = start_h, start_m
    while (h, m) < (end_h, end_m):
        slots.append(f"{h:02d}:{m:02d}")
        m += SLOT_INTERVAL_MINUTES
        if m >= 60:
            m -= 60
            h += 1
    return slots


def check_conflict(con: Client, project_id: str, schedule_date: str,
                   time_from: str, time_to: str, exclude_id=None):
    """Return list of schedules overlapping [time_from, time_to) on schedule_date."""
    q = (
        con.table("schedules")
        .select("*")
        .eq("project_id", project_id)
        .eq("schedule_date", schedule_date)
        .lt("time_from", time_to)
        .gt("time_to", time_from)
    )
    if exclude_id:
        q = q.neq("id", exclude_id)
    r = q.execute()
    return r.data or []
