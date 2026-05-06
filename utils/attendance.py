from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from utils.db import supabase
from utils.helpers import now_vn, now_vn_iso, today_vn

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

DEFAULT_BRANCH_SHIFTS: dict[str, list[dict[str, Any]]] = {
    "100 Lê Quý Đôn": [
        {"shift_no": 1, "name": "Ca 1", "start": "07:00", "end": "14:00"},
        {"shift_no": 2, "name": "Ca 2", "start": "14:00", "end": "21:00"},
    ],
    "GO BÀ RỊA": [
        {"shift_no": 1, "name": "Ca 1", "start": "08:00", "end": "15:00"},
        {"shift_no": 2, "name": "Ca 2", "start": "15:00", "end": "22:00"},
    ],
}

OPEN = "open"
CLOSED = "closed"


def _parse_hhmm(v: str) -> time:
    hh, mm = v.split(":")
    return time(int(hh), int(mm), tzinfo=TZ)


def _combine(work_date: date, hhmm: str) -> datetime:
    return datetime.combine(work_date, _parse_hhmm(hhmm))


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        dt = ts.to_pydatetime()
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)
    except Exception:
        return None


def shift_defs(branch_name: str) -> list[dict[str, Any]]:
    branch = (branch_name or "").strip()
    if branch in DEFAULT_BRANCH_SHIFTS:
        return DEFAULT_BRANCH_SHIFTS[branch]
    return [
        {"shift_no": 1, "name": "Ca 1", "start": "07:00", "end": "14:00"},
        {"shift_no": 2, "name": "Ca 2", "start": "14:00", "end": "21:00"},
    ]


def get_shift(branch_name: str, shift_no: int) -> dict[str, Any] | None:
    for item in shift_defs(branch_name):
        if int(item["shift_no"]) == int(shift_no):
            return item
    return None


def get_shift_window(branch_name: str, work_date: date, shift_no: int) -> tuple[datetime, datetime] | None:
    item = get_shift(branch_name, shift_no)
    if not item:
        return None
    return _combine(work_date, item["start"]), _combine(work_date, item["end"])


def minutes_between(a: datetime, b: datetime) -> int:
    return max(0, int((b - a).total_seconds() // 60))


def calc_minutes(check_in: datetime, check_out: datetime, shift_start: datetime, shift_end: datetime) -> dict[str, Any]:
    raw_in = _to_dt(check_in)
    raw_out = _to_dt(check_out)
    if raw_in is None or raw_out is None:
        return {"worked_minutes": 0, "regular_minutes": 0, "ot_minutes": 0, "actual_check_in": None, "actual_check_out": None}

    actual_in = max(raw_in, shift_start)
    regular_out = min(raw_out, shift_end)
    regular_minutes = max(0, minutes_between(actual_in, regular_out))
    ot_minutes = max(0, minutes_between(shift_end, raw_out)) if raw_out > shift_end else 0
    return {
        "worked_minutes": regular_minutes + ot_minutes,
        "regular_minutes": regular_minutes,
        "ot_minutes": ot_minutes,
        "actual_check_in": actual_in,
        "actual_check_out": raw_out,
    }


def salary_from_minutes(minutes: int, hourly_rate: float | int) -> float:
    return round((float(hourly_rate or 0) / 60.0) * max(0, int(minutes or 0)), 2)


@st.cache_data(ttl=60)
def load_work_schedules(work_date: date | None = None, employee_id: int | None = None, branch_name: str | None = None) -> pd.DataFrame:
    try:
        q = supabase.table("attendance_work_schedules").select("*").order("work_date", desc=True).order("shift_no")
        if work_date:
            q = q.eq("work_date", str(work_date))
        if employee_id:
            q = q.eq("nhan_vien_id", employee_id)
        if branch_name:
            q = q.eq("branch_name", branch_name)
        res = q.execute()
        df = pd.DataFrame(res.data or [])
        if df.empty:
            return df
        for col in ["scheduled_start_at", "scheduled_end_at", "created_at", "updated_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_attendance_sessions(work_date: date | None = None, employee_id: int | None = None, branch_name: str | None = None, status: str | None = None) -> pd.DataFrame:
    try:
        q = supabase.table("attendance_sessions").select("*").order("created_at", desc=True)
        if work_date:
            q = q.eq("work_date", str(work_date))
        if employee_id:
            q = q.eq("nhan_vien_id", employee_id)
        if branch_name:
            q = q.eq("branch_name", branch_name)
        if status:
            q = q.eq("status", status)
        res = q.execute()
        df = pd.DataFrame(res.data or [])
        if df.empty:
            return df
        for col in ["scheduled_start_at", "scheduled_end_at", "check_in_at", "check_out_at", "actual_check_in_at", "actual_check_out_at", "created_at", "updated_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_attendance_events(work_date: date | None = None, employee_id: int | None = None, branch_name: str | None = None) -> pd.DataFrame:
    try:
        q = supabase.table("attendance_events").select("*").order("event_time", desc=True)
        if work_date:
            q = q.eq("work_date", str(work_date))
        if employee_id:
            q = q.eq("nhan_vien_id", employee_id)
        if branch_name:
            q = q.eq("branch_name", branch_name)
        res = q.execute()
        df = pd.DataFrame(res.data or [])
        if df.empty:
            return df
        for col in ["event_time", "created_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def get_branch_network(branch_name: str) -> dict[str, Any] | None:
    try:
        res = supabase.table("attendance_branch_networks").select("*").eq("branch_name", branch_name).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def network_is_valid(branch_name: str, wifi_name: str | None = None, ip_address: str | None = None) -> tuple[bool, str]:
    cfg = get_branch_network(branch_name)
    if not cfg:
        return True, "Chưa cấu hình mạng cho chi nhánh này"
    expected_wifi = (cfg.get("wifi_name") or "").strip()
    prefixes = [x.strip() for x in str(cfg.get("ip_prefixes") or "").split(",") if x.strip()]
    if not wifi_name and not ip_address:
        return True, "Chưa có dữ liệu mạng từ thiết bị"
    wifi_ok = bool(expected_wifi) and wifi_name and wifi_name.strip() == expected_wifi
    ip_ok = bool(ip_address and prefixes and any(str(ip_address).startswith(p) for p in prefixes))
    if wifi_ok or ip_ok:
        return True, ""
    return False, "Sai mạng cửa hàng"


def _session_payload(employee_id: int, work_date: date, branch_name: str, shift_no: int, schedule_id: int | None, check_in_at: datetime, check_out_at: datetime | None = None, is_auto_checkout: bool = False, note: str = "") -> dict[str, Any]:
    window = get_shift_window(branch_name, work_date, shift_no)
    if not window:
        raise ValueError("Không tìm thấy khung ca")
    shift_start, shift_end = window
    result = calc_minutes(check_in_at, check_out_at or shift_end, shift_start, shift_end)
    return {
        "nhan_vien_id": employee_id,
        "work_date": str(work_date),
        "branch_name": branch_name,
        "shift_no": int(shift_no),
        "schedule_id": schedule_id,
        "scheduled_start_at": shift_start.isoformat(),
        "scheduled_end_at": shift_end.isoformat(),
        "check_in_at": check_in_at.isoformat(),
        "check_out_at": (check_out_at or shift_end).isoformat() if check_out_at or is_auto_checkout else None,
        "actual_check_in_at": result["actual_check_in"].isoformat() if result["actual_check_in"] else None,
        "actual_check_out_at": result["actual_check_out"].isoformat() if result["actual_check_out"] else None,
        "worked_minutes": int(result["worked_minutes"]),
        "regular_minutes": int(result["regular_minutes"]),
        "ot_minutes": int(result["ot_minutes"]),
        "is_auto_checkout": bool(is_auto_checkout),
        "status": CLOSED if (check_out_at or is_auto_checkout) else OPEN,
        "note": note or None,
        "updated_at": now_vn_iso(),
    }


def record_check_in(employee_id: int, branch_name: str, schedule_id: int | None = None, source: str = "POS", wifi_name: str | None = None, ip_address: str | None = None, note: str = "") -> dict[str, Any]:
    now = now_vn()
    work_date = now.date()
    schedule = None
    if schedule_id:
        res = supabase.table("attendance_work_schedules").select("*").eq("id", schedule_id).limit(1).execute()
        schedule = res.data[0] if res.data else None
    else:
        schedules = load_work_schedules(work_date=work_date, employee_id=employee_id, branch_name=branch_name)
        if not schedules.empty:
            current = schedules[(schedules["scheduled_start_at"] <= now) & (schedules["scheduled_end_at"] >= now)]
            if current.empty:
                current = schedules.sort_values("scheduled_start_at").head(1)
            if not current.empty:
                schedule = current.iloc[0].to_dict()
    if not schedule:
        return {"ok": False, "error": "Không có lịch làm việc phù hợp"}
    if str(schedule.get("branch_name") or "").strip() != branch_name.strip():
        return {"ok": False, "error": "Sai chi nhánh - không cho chấm công"}
    ok, msg = network_is_valid(branch_name, wifi_name=wifi_name, ip_address=ip_address)
    if not ok:
        return {"ok": False, "error": msg}
    schedule_id = int(schedule.get("id") or 0)
    existing = load_attendance_sessions(work_date=work_date, employee_id=employee_id, branch_name=branch_name, status=OPEN)
    if not existing.empty and int(existing.iloc[0].get("shift_no") or 0) == int(schedule.get("shift_no") or 0) and pd.isna(existing.iloc[0].get("check_out_at")):
        return {"ok": False, "error": "Ca này đã có chấm vào, chỉ còn chấm ra"}
    try:
        supabase.table("attendance_events").insert({
            "nhan_vien_id": employee_id,
            "work_date": str(work_date),
            "branch_name": branch_name,
            "shift_no": int(schedule.get("shift_no") or 0),
            "event_type": "IN",
            "event_time": now.isoformat(),
            "source": source,
            "schedule_id": schedule_id,
            "wifi_name": wifi_name or None,
            "ip_address": ip_address or None,
            "note": note or None,
            "created_at": now_vn_iso(),
        }).execute()
        session_payload = _session_payload(employee_id, work_date, branch_name, int(schedule.get("shift_no") or 0), schedule_id, now, None, False, note)
        session_payload["status"] = OPEN
        session_payload["check_out_at"] = None
        session_payload["created_at"] = now_vn_iso()
        res = supabase.table("attendance_sessions").upsert(session_payload, on_conflict="nhan_vien_id,work_date,branch_name,shift_no").execute()
        return {"ok": True, "data": res.data or []}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def record_check_out(employee_id: int, branch_name: str, schedule_id: int | None = None, source: str = "POS", wifi_name: str | None = None, ip_address: str | None = None, note: str = "") -> dict[str, Any]:
    now = now_vn()
    work_date = now.date()
    ok, msg = network_is_valid(branch_name, wifi_name=wifi_name, ip_address=ip_address)
    if not ok:
        return {"ok": False, "error": msg}
    try:
        q = supabase.table("attendance_sessions").select("*").eq("nhan_vien_id", employee_id).eq("work_date", str(work_date)).eq("status", OPEN)
        if schedule_id:
            q = q.eq("schedule_id", schedule_id)
        res = q.order("created_at", desc=True).limit(1).execute()
        session = res.data[0] if res.data else None
    except Exception as exc:
        return {"ok": False, "error": f"Không tìm được phiên chấm công mở: {exc}"}
    if not session:
        return {"ok": False, "error": "Chưa có chấm vào cho ca này"}
    if str(session.get("branch_name") or "").strip() != branch_name.strip():
        return {"ok": False, "error": "Sai chi nhánh - không cho chấm công"}
    check_in_at = _to_dt(session.get("check_in_at"))
    shift_start = _to_dt(session.get("scheduled_start_at"))
    shift_end = _to_dt(session.get("scheduled_end_at"))
    if check_in_at is None or shift_start is None or shift_end is None:
        return {"ok": False, "error": "Thiếu dữ liệu ca chấm công"}
    try:
        supabase.table("attendance_events").insert({
            "nhan_vien_id": employee_id,
            "work_date": str(work_date),
            "branch_name": branch_name,
            "shift_no": int(session.get("shift_no") or 0),
            "event_type": "OUT",
            "event_time": now.isoformat(),
            "source": source,
            "schedule_id": int(session.get("schedule_id") or schedule_id or 0),
            "wifi_name": wifi_name or None,
            "ip_address": ip_address or None,
            "note": note or None,
            "created_at": now_vn_iso(),
        }).execute()
        calc = calc_minutes(check_in_at, now, shift_start, shift_end)
        res = supabase.table("attendance_sessions").update({
            "check_out_at": now.isoformat(),
            "actual_check_in_at": calc["actual_check_in"].isoformat() if calc["actual_check_in"] else check_in_at.isoformat(),
            "actual_check_out_at": calc["actual_check_out"].isoformat() if calc["actual_check_out"] else now.isoformat(),
            "worked_minutes": int(calc["worked_minutes"]),
            "regular_minutes": int(calc["regular_minutes"]),
            "ot_minutes": int(calc["ot_minutes"]),
            "status": CLOSED,
            "is_auto_checkout": False,
            "updated_at": now_vn_iso(),
            "note": note or session.get("note"),
        }).eq("id", session["id"]).execute()
        return {"ok": True, "data": res.data or []}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def finalize_open_sessions(work_date: date | None = None) -> dict[str, Any]:
    work_date = work_date or today_vn()
    try:
        res = supabase.table("attendance_sessions").select("*").eq("work_date", str(work_date)).eq("status", OPEN).execute()
        rows = res.data or []
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finalized = 0
    errors: list[str] = []
    for session in rows:
        try:
            check_in_at = _to_dt(session.get("check_in_at"))
            shift_start = _to_dt(session.get("scheduled_start_at"))
            shift_end = _to_dt(session.get("scheduled_end_at"))
            if not check_in_at or not shift_start or not shift_end:
                continue
            calc = calc_minutes(check_in_at, shift_end, shift_start, shift_end)
            supabase.table("attendance_sessions").update({
                "check_out_at": shift_end.isoformat(),
                "actual_check_in_at": calc["actual_check_in"].isoformat() if calc["actual_check_in"] else check_in_at.isoformat(),
                "actual_check_out_at": shift_end.isoformat(),
                "worked_minutes": int(calc["worked_minutes"]),
                "regular_minutes": int(calc["regular_minutes"]),
                "ot_minutes": int(calc["ot_minutes"]),
                "status": CLOSED,
                "is_auto_checkout": True,
                "updated_at": now_vn_iso(),
            }).eq("id", session["id"]).execute()
            finalized += 1
        except Exception as exc:
            errors.append(f"{session.get('id')}: {exc}")
    return {"ok": len(errors) == 0, "finalized": finalized, "errors": errors}
