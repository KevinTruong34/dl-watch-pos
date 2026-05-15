"""Dialog 'Lương của tôi' cho POS — Phase 8.

NV login POS → tap avatar → "📋 Lương của tôi" → dialog overlay xem bảng công
+ tổng lương theo kỳ. Gọi RPC `get_payroll_for_self(nv_id, period_id)`.

UI:
- Dropdown chọn period (chỉ kỳ có items cho NV này)
- 2 sub-tabs: 📊 Bảng công / 💵 Tổng kết
- Footer: 🔒 Chốt kỳ / 📂 Đang tính

Refs: PLAN_CHAM_CONG.md section 13.
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_user
from utils.db import supabase

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


_ITEM_TYPE_LABEL = {
    "shift":         "🕐 Ca",
    "monthly_fixed": "📅 Cố định tháng",
    "leave_paid":    "🌴 Nghỉ phép",
}

_ADJUSTMENT_TYPE_LABEL = {
    "bonus_holiday":  "🎁 Thưởng lễ",
    "allowance_meal": "🍱 Phụ cấp ăn",
    "penalty":        "⚠️ Phạt",
    "other":          "📝 Khác",
}


def _format_minutes(m: int) -> str:
    """123 minutes → '2h 3p'."""
    if not m or m <= 0:
        return "0"
    h, p = m // 60, m % 60
    if h and p:
        return f"{h}h {p}p"
    if h:
        return f"{h}h"
    return f"{p}p"


def _load_periods_for_self(nv_id: int) -> list[dict]:
    """Periods có items cho NV này. Sort newest first."""
    res = supabase.table("attendance_payroll_items").select("period_id") \
        .eq("nhan_vien_id", nv_id).execute()
    pids = list({r["period_id"] for r in (res.data or [])})
    if not pids:
        return []
    res = supabase.table("attendance_payroll_periods").select("*") \
        .in_("id", pids).order("start_date", desc=True).execute()
    return res.data or []


def _get_payroll_for_self(nv_id: int, period_id: int) -> dict:
    """Wrap RPC get_payroll_for_self."""
    try:
        res = supabase.rpc("get_payroll_for_self", {
            "p_nhan_vien_id": nv_id,
            "p_period_id": period_id,
        }).execute()
        data = res.data
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


@st.dialog("📋 Lương của tôi")
def show_my_payroll_dialog():
    user = get_user()
    if not user:
        st.error("⛔ Cần đăng nhập trước.")
        return
    nv_id = user["id"]

    periods = _load_periods_for_self(nv_id)
    if not periods:
        st.info(
            "📭 Chưa có dữ liệu lương nào cho bạn.\n\n"
            "Quản lý sẽ tính lương sau mỗi kỳ — vui lòng đợi."
        )
        return

    options = {
        f"{p['label']} ({p['start_date']} → {p['end_date']}) — "
        f"{'🔒 Đã chốt' if p.get('status') == 'finalized' else '📂 Đang tính'}": p
        for p in periods
    }
    picked_label = st.selectbox(
        "Chọn kỳ lương", list(options.keys()), key="my_payroll_period_pick"
    )
    period = options[picked_label]
    pid = period["id"]

    data = _get_payroll_for_self(nv_id, pid)
    if not data.get("ok"):
        st.error(f"⛔ {data.get('error', 'Lỗi không xác định')}")
        return

    items = data.get("items", []) or []
    adjustments = data.get("adjustments", []) or []
    totals = data.get("totals", {}) or {}

    sub = st.tabs(["📊 Bảng công", "💵 Tổng kết"])
    with sub[0]:
        _render_my_bang_cong(items)
    with sub[1]:
        _render_my_summary(totals, adjustments)

    # Footer
    st.markdown("---")
    is_finalized = period.get("status") == "finalized"
    finalized_at = period.get("finalized_at")
    if is_finalized and finalized_at:
        try:
            ft = datetime.fromisoformat(finalized_at).astimezone(VN_TZ)
            st.caption(f"🔒 Chốt kỳ: {ft.strftime('%d/%m/%Y %H:%M')}")
        except Exception:
            st.caption("🔒 Đã chốt kỳ")
    else:
        st.caption("📂 Đang tính (chưa chốt kỳ — số liệu có thể thay đổi)")


def _render_my_bang_cong(items: list[dict]):
    """Show chi tiết items: monthly_fixed / shift / leave_paid."""
    fixed_items = [i for i in items if i.get("item_type") == "monthly_fixed"]
    other_items = [i for i in items if i.get("item_type") in ("shift", "leave_paid")]

    if not items:
        st.info("📭 Chưa có chi tiết lương ca trong kỳ này.")
        return

    if fixed_items:
        for f in fixed_items:
            salary = int(f.get("salary_amount") or 0)
            st.markdown(
                f"<div style='padding:12px;background:#e8f4ff;border-radius:8px;"
                f"margin-bottom:8px;'>"
                f"<div style='font-weight:600;font-size:0.95rem;'>"
                f"📅 Lương cố định tháng</div>"
                f"<div style='font-size:1.3rem;font-weight:700;color:#1a7f37;"
                f"margin-top:4px;'>{salary:,}đ</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if other_items:
        for it in other_items:
            work_date = it.get("work_date") or ""
            try:
                wd = datetime.strptime(work_date, "%Y-%m-%d").date()
                ngay = wd.strftime("%d/%m")
            except Exception:
                ngay = work_date

            item_type = it.get("item_type", "")
            type_lbl = _ITEM_TYPE_LABEL.get(item_type, item_type)
            label = it.get("shift_label") or "?"
            worked_min = int(it.get("worked_minutes") or 0)
            ot_min = int(it.get("ot_minutes") or 0)
            salary = int(it.get("salary_amount") or 0)
            rate = int(it.get("rate_snapshot") or 0)

            ot_str = f" · OT {_format_minutes(ot_min)}" if ot_min else ""

            with st.container(border=True):
                st.markdown(
                    f"**{ngay}** · {type_lbl} {label}  \n"
                    f"⏱ {_format_minutes(worked_min)}{ot_str} × "
                    f"<span style='color:#888;font-size:0.85rem;'>"
                    f"{rate:,}đ/giờ</span>  \n"
                    f"<span style='font-size:1.05rem;font-weight:700;"
                    f"color:#1a7f37;'>{salary:,}đ</span>",
                    unsafe_allow_html=True,
                )


def _render_my_summary(totals: dict, adjustments: list[dict]):
    """Show totals + adjustments + tổng cộng highlight."""
    worked = int(totals.get("worked_minutes", 0) or 0)
    ot = int(totals.get("ot_minutes", 0) or 0)
    leave = int(totals.get("leave_minutes", 0) or 0)
    luong_ca = int(totals.get("luong_ca", 0) or 0)
    adj_total = int(totals.get("adjustments", 0) or 0)
    tong_cong = int(totals.get("tong_cong", 0) or 0)

    # Hours stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Giờ làm", _format_minutes(worked) if worked else "—")
    with col2:
        st.metric("Giờ OT", _format_minutes(ot) if ot else "—")
    if leave:
        st.metric("Nghỉ phép", _format_minutes(leave))

    st.markdown("---")

    # Breakdown
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;padding:8px 0;'>"
        f"<span>💵 Lương ca</span>"
        f"<span style='font-weight:600;'>{luong_ca:,}đ</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if adjustments:
        for a in adjustments:
            type_lbl = _ADJUSTMENT_TYPE_LABEL.get(
                a.get("adjustment_type", ""), a.get("adjustment_type", "")
            )
            amount = int(a.get("amount") or 0)
            sign = "+" if amount > 0 else ""
            color = "#1a7f37" if amount > 0 else "#cf4c2c"
            note = a.get("note") or ""
            note_html = (
                f"<span style='color:#888;font-size:0.85rem;'> · {note}</span>"
                if note else ""
            )
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"padding:6px 0;'>"
                f"<span>{type_lbl}{note_html}</span>"
                f"<span style='font-weight:600;color:{color};'>"
                f"{sign}{amount:,}đ</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:8px 0;color:#888;'>"
            f"<span>Phụ cấp / Phạt</span><span>—</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Tổng cộng highlight
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;padding:14px;"
        f"background:#fff0f1;border-radius:10px;margin-top:8px;"
        f"border:2px solid #e63946;'>"
        f"<span style='font-size:1.05rem;font-weight:700;'>TỔNG CỘNG</span>"
        f"<span style='font-size:1.4rem;font-weight:800;color:#e63946;'>"
        f"{tong_cong:,}đ</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
