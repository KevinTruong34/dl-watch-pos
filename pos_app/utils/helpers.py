"""Helpers chung: timezone VN, format tiền VND."""

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    """Datetime hiện tại theo giờ VN (Asia/Ho_Chi_Minh)."""
    return datetime.now(_TZ_VN)


def now_vn_iso() -> str:
    """ISO string giờ VN — dùng để ghi DB cột timestamptz."""
    return datetime.now(_TZ_VN).isoformat()


def today_vn() -> date:
    """Ngày hôm nay theo giờ VN."""
    return datetime.now(_TZ_VN).date()


def end_of_today_vn_iso() -> str:
    """
    ISO string cho 23:59:59 của hôm nay (giờ VN).
    Dùng để set expires_at cho session POS — hết ngày tự logout.
    """
    today = datetime.now(_TZ_VN)
    end = today.replace(hour=23, minute=59, second=59, microsecond=0)
    return end.isoformat()


def fmt_vnd(amount: int | float) -> str:
    """Format số tiền VND: 1700000 → '1.700.000đ'"""
    if amount is None:
        return "0đ"
    try:
        return f"{int(amount):,}đ".replace(",", ".")
    except (ValueError, TypeError):
        return "0đ"


def fmt_vnd_no_unit(amount: int | float) -> str:
    """Format số tiền không kèm chữ 'đ': 1700000 → '1.700.000'"""
    if amount is None:
        return "0"
    try:
        return f"{int(amount):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"
