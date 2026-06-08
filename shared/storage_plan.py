"""자재 저장(지하 터미널) 배정 + 점유 현황 헬퍼.

- 하역(지상 A~G존) / 저장(지하 터미널 B1·B2-01~13)은 별개 위치.
- 저장은 여러 날 점유(기본 14일, 관리자 수정 가능). 터미널 = 1자재 배타적.
- requests.store_terminal / store_start / store_end / store_released 사용.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from supabase import Client

from db.models import settings_get


def floor_image(name: str) -> Optional[str]:
    """도면 이미지 경로. name: 'b1' | 'b2' | 'ground'. 없으면 None."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "assets", f"floor_{name}.jpg")
    return p if os.path.exists(p) else None


# ── 위치 상수 ─────────────────────────────────────────────────────────

def terminals_b1() -> List[str]:
    return [f"B1-{i:02d}" for i in range(1, 14)]


def terminals_b2() -> List[str]:
    return [f"B2-{i:02d}" for i in range(1, 14)]


def all_terminals() -> List[str]:
    return terminals_b1() + terminals_b2()


def ground_zones(con: Client) -> List[str]:
    """하역 지상 존 (A~G). booking_zones_json 재사용."""
    try:
        zs = json.loads(settings_get(con, "booking_zones_json", '["A-Zone"]'))
        return [z for z in zs if z] or ["A-Zone"]
    except Exception:
        return ["A-Zone"]


def default_days(con: Client) -> int:
    """기본 저장 기간(일). 관리자 설정."""
    try:
        return max(1, int(settings_get(con, "storage_default_days", "14")))
    except Exception:
        return 14


# ── 날짜 유틸 ─────────────────────────────────────────────────────────

def add_days(date_str: str, days: int) -> str:
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (d + timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return date_str


def _overlaps(s1: str, e1: str, s2: str, e2: str) -> bool:
    """[s1,e1] 와 [s2,e2] (YYYY-MM-DD, 포함) 겹침 여부."""
    return s1 <= e2 and s2 <= e1


# ── 점유 현황 / 충돌 ──────────────────────────────────────────────────

def _active_storage_rows(con: Client, project_id: str) -> List[Dict[str, Any]]:
    res = (con.table("requests")
           .select("id,item_name,company_name,store_terminal,store_start,store_end,store_released")
           .eq("project_id", project_id)
           .execute())
    rows = res.data or []
    return [r for r in rows
            if r.get("store_terminal")
            and not r.get("store_released")
            and r.get("store_start") and r.get("store_end")]


def occupancy_on(con: Client, project_id: str, on_date: str) -> Dict[str, Dict[str, Any]]:
    """특정 날짜에 점유 중인 터미널 → 점유 정보. {terminal: {...}}"""
    d = on_date[:10]
    out: Dict[str, Dict[str, Any]] = {}
    for r in _active_storage_rows(con, project_id):
        if r["store_start"][:10] <= d <= r["store_end"][:10]:
            out[r["store_terminal"]] = {
                "rid": r["id"], "item": r.get("item_name") or "",
                "company": r.get("company_name") or "",
                "start": r["store_start"][:10], "end": r["store_end"][:10],
            }
    return out


def conflicts(con: Client, project_id: str, terminal: str,
              start: str, end: str, exclude_rid: Optional[str] = None) -> List[Dict[str, Any]]:
    """선택 터미널이 [start,end] 기간에 다른 점유와 겹치는지."""
    out = []
    for r in _active_storage_rows(con, project_id):
        if r["store_terminal"] != terminal:
            continue
        if exclude_rid and r["id"] == exclude_rid:
            continue
        if _overlaps(start[:10], end[:10], r["store_start"][:10], r["store_end"][:10]):
            out.append(r)
    return out


# ── 배정 저장 ─────────────────────────────────────────────────────────

def assign_storage(con: Client, rid: str, *, store_terminal: Optional[str],
                   store_start: str, store_end: str,
                   booking_zone: Optional[str] = None,
                   time_from: Optional[str] = None,
                   time_to: Optional[str] = None) -> None:
    """요청에 하역존/시간 + 저장 터미널/기간 반영."""
    patch: Dict[str, Any] = {
        "store_terminal": store_terminal or None,
        "store_start":    store_start,
        "store_end":      store_end,
        "store_released": 0,
    }
    if booking_zone is not None:
        patch["booking_zone"] = booking_zone
    if time_from is not None:
        patch["time_from"] = time_from
    if time_to is not None:
        patch["time_to"] = time_to
    con.table("requests").update(patch).eq("id", rid).execute()


def release_storage(con: Client, rid: str) -> None:
    con.table("requests").update({"store_released": 1}).eq("id", rid).execute()
