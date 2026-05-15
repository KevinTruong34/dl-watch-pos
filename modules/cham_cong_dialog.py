"""Dialog Chấm công cho POS — Phase 3.

Mở từ avatar popover (nút "⏱️ Chấm công"):
1. Detect client IP (st.context.ip_address → X-Forwarded-For fallback)
2. Call RPC validate_check_in_pos để check NV active + lịch trong khung + IP whitelist
3. Render info (chi nhánh / ca / IN hay OUT) + nút confirm
4. Click confirm → RPC record_attendance_event → toast success

Refs: PLAN_CHAM_CONG.md section 8.

Note: RPC wrappers inline trong module này (chỉ dùng cho dialog) để tránh
sửa utils/db.py — surgical scope theo feature.
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_user
from utils.db import supabase

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ─────────────────────────────────────────────────────────────
# RPC wrappers (deploy trong DLW Phase 1 schema migration)
# ─────────────────────────────────────────────────────────────

def _validate_check_in_pos(nv_id: int, ip: str) -> dict:
    """Wrap RPC validate_check_in_pos. Returns dict shape from PLAN section 5.1."""
    try:
        res = supabase.rpc("validate_check_in_pos", {
            "p_nhan_vien_id": nv_id,
            "p_ip_address": ip,
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _record_attendance_event(nv_id: int, event_type: str,
                             ip: str, note: str | None = None) -> dict:
    """Wrap RPC record_attendance_event. Returns {ok, event_id?, error?}."""
    try:
        res = supabase.rpc("record_attendance_event", {
            "p_nhan_vien_id": nv_id,
            "p_event_type": event_type,
            "p_ip_address": ip,
            "p_note": note,
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# IP detection
# ─────────────────────────────────────────────────────────────

def _detect_client_ip() -> tuple[str | None, str]:
    """Return (ip, source). Source dùng cho debug expander."""
    # Method 1: st.context.ip_address (Streamlit 1.31+)
    try:
        ip = getattr(st.context, "ip_address", None)
        if ip:
            return ip, "context.ip_address"
    except Exception:
        pass
    # Method 2: X-Forwarded-For header (first IP = original client)
    try:
        headers = getattr(st.context, "headers", None) or {}
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip()
            if ip:
                return ip, "x_forwarded_for"
    except Exception:
        pass
    return None, "none"


# ─────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────

@st.dialog("⏱️ Chấm công")
def show_cham_cong_dialog():
    user = get_user()
    if not user:
        st.error("⛔ Bạn cần đăng nhập trước.")
        return

    ip, ip_source = _detect_client_ip()

    if not ip:
        st.error(
            "❌ Không lấy được địa chỉ IP. "
            "Liên hệ admin để xử lý (có thể Streamlit Cloud chưa expose client IP)."
        )
        return

    # Validate → check NV / schedule / IP whitelist
    result = _validate_check_in_pos(user["id"], ip)

    # Debug expander cho admin verify IP detection (collapsed default)
    with st.expander("🔍 Debug IP (admin)", expanded=False):
        st.caption(f"IP detected: `{ip}` (source: {ip_source})")
        st.caption(f"NV: {user.get('ho_ten','?')} (id={user.get('id')})")

    if not result or not result.get("ok"):
        err = (result or {}).get("error", "Lỗi không xác định")
        st.error(f"⛔ {err}")
        if "IP" in err or "mạng" in err.lower():
            st.caption(
                "💡 NV cần dùng Wi-Fi cửa hàng để chấm công. "
                "Nếu IP đúng nhưng vẫn lỗi, báo admin cập nhật IP whitelist."
            )
        elif "lịch" in err.lower():
            st.caption(
                "💡 Chỉ chấm được trong khung ±2h quanh giờ ca. "
                "Liên hệ admin nếu lịch sai."
            )
        return

    # Happy path — hiển thị info + confirm
    action = result["action_expected"]
    action_lbl = "CHẤM VÀO" if action == "IN" else "CHẤM RA"
    branch = result.get("branch_name", "?")
    shift = result.get("shift_label", "?")

    st.markdown(
        f"<div style='text-align:center;padding:8px 0;'>"
        f"<div style='font-size:0.85rem;color:#888;'>Nhân viên</div>"
        f"<div style='font-size:1.1rem;font-weight:700;'>{user.get('ho_ten','?')}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"<div style='text-align:center;padding:6px;background:#f5f6f8;"
            f"border-radius:8px;'>"
            f"<div style='font-size:0.78rem;color:#888;'>Chi nhánh</div>"
            f"<div style='font-size:0.95rem;font-weight:600;'>{branch}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='text-align:center;padding:6px;background:#f5f6f8;"
            f"border-radius:8px;'>"
            f"<div style='font-size:0.78rem;color:#888;'>Ca</div>"
            f"<div style='font-size:0.95rem;font-weight:600;'>{shift}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    now_vn_str = datetime.now(VN_TZ).strftime("%H:%M · %d/%m/%Y")
    action_color = "#1a7f37" if action == "IN" else "#cf4c2c"
    st.markdown(
        f"<div style='text-align:center;padding:14px;margin:12px 0;"
        f"background:#fff;border:2px solid {action_color};border-radius:12px;'>"
        f"<div style='font-size:0.85rem;color:#888;'>Bạn sắp</div>"
        f"<div style='font-size:1.4rem;font-weight:800;color:{action_color};'>"
        f"{action_lbl}</div>"
        f"<div style='font-size:0.95rem;color:#444;margin-top:4px;'>{now_vn_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    note = st.text_area(
        "Ghi chú (optional)", height=68,
        key=f"cc_note_{action}",
        placeholder="vd: Đến trễ vì kẹt xe",
    )

    if st.button(
        f"✅ Xác nhận {action_lbl}",
        type="primary",
        use_container_width=True,
        key="cc_confirm_btn",
    ):
        record = _record_attendance_event(
            nv_id=user["id"],
            event_type=action,
            ip=ip,
            note=note or None,
        )
        if record.get("ok"):
            st.toast(
                f"✓ Đã ghi nhận {action_lbl}",
                icon="✅",
            )
            st.rerun()
        else:
            st.error(f"❌ Lỗi: {record.get('error', 'không xác định')}")
