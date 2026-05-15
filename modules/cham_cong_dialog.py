"""Dialog Chấm công cho POS — Phase 3.

Mở từ avatar popover (nút "⏱️ Chấm công"):
1. Detect client IP NAT egress qua JS fetch api.ipify.org (utils/client_ip_component)
2. Call RPC validate_check_in_pos để check NV active + lịch trong khung +
   active_chi_nhanh khớp + IP whitelist
3. Render info (chi nhánh / ca / IN hay OUT) + nút confirm
4. Click confirm → RPC record_attendance_event → toast success

Refs: PLAN_CHAM_CONG.md section 8 + hotfix #2 (active_chi_nhanh enforcement).

Note: RPC wrappers inline trong module này (chỉ dùng cho dialog) để tránh
sửa utils/db.py — surgical scope theo feature.
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_user, get_active_branch
from utils.db import supabase

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ─────────────────────────────────────────────────────────────
# RPC wrappers (deploy trong DLW Phase 1 schema migration + hotfix #2)
# ─────────────────────────────────────────────────────────────

def _validate_check_in_pos(nv_id: int, ip: str, active_cn: str | None) -> dict:
    """Wrap RPC validate_check_in_pos. Pass active_cn để RPC reject mismatch CN."""
    try:
        res = supabase.rpc("validate_check_in_pos", {
            "p_nhan_vien_id": nv_id,
            "p_ip_address": ip,
            "p_active_chi_nhanh": active_cn,
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _record_attendance_event(nv_id: int, event_type: str, ip: str,
                             active_cn: str | None,
                             note: str | None = None) -> dict:
    """Wrap RPC record_attendance_event. Pass active_cn để defense-in-depth
    re-validate (NV có thể đổi CN giữa lúc dialog mở và click confirm)."""
    try:
        res = supabase.rpc("record_attendance_event", {
            "p_nhan_vien_id": nv_id,
            "p_event_type": event_type,
            "p_ip_address": ip,
            "p_note": note,
            "p_active_chi_nhanh": active_cn,
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
    """Return (ip, source). Dùng JS fetch api.ipify.org để lấy IP NAT egress thật."""
    from utils.client_ip_component import get_client_ip
    ip = get_client_ip()
    if ip:
        return ip, "ipify_js"
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

    active_cn = get_active_branch()
    ip, ip_source = _detect_client_ip()

    if not ip:
        st.error(
            "❌ Không lấy được địa chỉ IP. "
            "Liên hệ admin để xử lý (api.ipify.org có thể bị block)."
        )
        return

    # Validate → check NV / schedule / active_chi_nhanh / IP whitelist
    result = _validate_check_in_pos(user["id"], ip, active_cn)

    # Debug expander cho admin verify (collapsed default)
    with st.expander("🔍 Debug (admin)", expanded=False):
        st.caption(f"IP detected: `{ip}` (source: {ip_source})")
        st.caption(f"NV: {user.get('ho_ten','?')} (id={user.get('id')})")
        st.caption(f"Active CN: `{active_cn}`")
        if ip_source == "ipify_js":
            st.caption("✓ IP NAT egress thật (đã match whatismyip.com)")

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
        # Re-fetch active_cn lúc confirm — phòng NV đổi CN giữa lúc dialog mở
        active_cn_now = get_active_branch()
        record = _record_attendance_event(
            nv_id=user["id"],
            event_type=action,
            ip=ip,
            active_cn=active_cn_now,
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
