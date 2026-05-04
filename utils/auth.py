"""Auth: login PIN flow + session quản lý qua localStorage."""

import streamlit as st
import bcrypt
import uuid
from datetime import datetime

from utils.db import supabase, load_nhan_vien_active, load_pin, set_pin
from utils.helpers import now_vn, end_of_today_vn_iso

# URL query params — lưu token + branch trong URL.
# Đây là cách an toàn + persist được, không cần external library.
# Lý do không dùng cookie: trên Streamlit Cloud share environment,
# cả 2 pattern (session_state cache, @st.cache_resource) đều fail —
# hoặc mất persist hoặc leak session giữa users.
# URL nội bộ shop, không public → an toàn về thực tế.

_URL_TOKEN_KEY  = "t"
_URL_BRANCH_KEY = "b"
_URL_USER_KEY   = "u" # Thêm param u để nhớ nhân viên


# ════════════════════════════════════════════════════════════════
# PASSWORD/PIN HELPERS
# ════════════════════════════════════════════════════════════════

def hash_pin(pin: str) -> str:
    """Hash PIN bằng bcrypt — không lưu plain text."""
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin_input: str, pin_hash: str) -> bool:
    """So sánh PIN nhập với hash đã lưu."""
    if not pin_hash:
        return False
    try:
        return bcrypt.checkpw(pin_input.encode(), pin_hash.encode())
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
# SESSION TOKEN MANAGEMENT (qua RPC mới)
# ════════════════════════════════════════════════════════════════

def create_session_token(nv_id: int, user_agent: str = "") -> str | None:
    """Tạo session token mới qua RPC. Token expire cuối ngày VN."""
    try:
        res = supabase.rpc("create_session", {
            "p_nhan_vien_id": nv_id,
            "p_user_agent":   user_agent or "",
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if isinstance(result, dict) and result.get("ok"):
            return result.get("token")
    except Exception:
        pass
    return None


def restore_session(token: str) -> dict | None:
    """
    Khôi phục user info từ token qua RPC validate_session.
    Cộng thêm chi_nhanh_list từ bảng nhan_vien_chi_nhanh.
    """
    if not token:
        return None
    try:
        res = supabase.rpc("validate_session", {"p_token": token}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict) or not result.get("ok"):
            return None

        user = dict(result.get("user") or {})
        if not user:
            return None

        # Load chi nhánh phân quyền (RPC chưa trả về vì để tách concern)
        try:
            cn_res = supabase.table("nhan_vien_chi_nhanh") \
                .select("chi_nhanh(ten)").eq("nhan_vien_id", user["id"]).execute()
            user["chi_nhanh_list"] = [
                x["chi_nhanh"]["ten"] for x in (cn_res.data or [])
                if x.get("chi_nhanh")
            ]
        except Exception:
            user["chi_nhanh_list"] = []

        # Lưu thời điểm session hết hạn cho banner cảnh báo
        user["session_expires_at"] = result.get("expires_at")
        return user
    except Exception:
        return None


def revoke_all_user_sessions(nv_id: int) -> int:
    """Revoke tất cả session của NV trên mọi thiết bị. Return số session bị revoke."""
    try:
        res = supabase.rpc("revoke_user_sessions", {
            "p_nhan_vien_id": nv_id,
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if isinstance(result, dict) and result.get("ok"):
            return int(result.get("revoked_count", 0))
    except Exception:
        pass
    return 0


# ════════════════════════════════════════════════════════════════
# LOCALSTORAGE HELPERS
# ════════════════════════════════════════════════════════════════

def _ls_get_token() -> str | None:
    """Đọc token từ URL query param. Return None nếu chưa có hoặc rỗng."""
    try:
        val = st.query_params.get(_URL_TOKEN_KEY)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None


def _ls_set_token(token: str):
    """Ghi token vào URL query param."""
    try:
        st.query_params[_URL_TOKEN_KEY] = token
    except Exception:
        pass


def _ls_delete_token():
    """Xóa token khỏi URL query param."""
    try:
        if _URL_TOKEN_KEY in st.query_params:
            del st.query_params[_URL_TOKEN_KEY]
    except Exception:
        pass


def _ls_get_branch() -> str | None:
    """Đọc branch đã chọn từ URL query param."""
    try:
        val = st.query_params.get(_URL_BRANCH_KEY)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None


def _save_branch_localstorage(branch: str):
    """Lưu chi nhánh đã chọn vào URL query param."""
    try:
        st.query_params[_URL_BRANCH_KEY] = branch
    except Exception:
        pass

# Thêm logic xử lý URL params cho ID người dùng
def _ls_get_user_id() -> str | None:
    """Đọc user id đã chọn từ URL query param."""
    try:
        val = st.query_params.get(_URL_USER_KEY)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None

def _save_user_localstorage(user_id: str):
    """Lưu id người dùng đã chọn vào URL query param."""
    try:
        st.query_params[_URL_USER_KEY] = str(user_id)
    except Exception:
        pass

def _ls_delete_user():
    """Xóa user khỏi URL query param."""
    try:
        if _URL_USER_KEY in st.query_params:
            del st.query_params[_URL_USER_KEY]
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════
# SESSION STATE HELPERS
# ════════════════════════════════════════════════════════════════

def get_user() -> dict | None:
    return st.session_state.get("user")


def is_admin() -> bool:
    u = get_user()
    return bool(u and u.get("role") == "admin")


def get_active_branch() -> str:
    return st.session_state.get("active_chi_nhanh", "")


def get_accessible_branches() -> list[str]:
    """Chi nhánh NV có quyền bán."""
    u = get_user()
    if not u:
        return []
    if u.get("role") == "admin":
        from utils.config import ALL_BRANCHES
        return ALL_BRANCHES
    return u.get("chi_nhanh_list", [])


def do_logout():
    """
    Logout: revoke TẤT CẢ session của NV trên mọi thiết bị.
    Xóa localStorage + clear state nhưng giữ lại branch và user.
    """
    # Lấy thông tin branch và user trước khi clear state
    current_b = _ls_get_branch()
    current_u = ""
    user = get_user()
    if user and user.get("id"):
        current_u = str(user["id"])
        revoke_all_user_sessions(user["id"])

    _ls_delete_token()
    st.session_state.clear()
    
    # Cập nhật lại URL parameters
    if current_b:
        _save_branch_localstorage(current_b)
    if current_u:
         _save_user_localstorage(current_u)


# ════════════════════════════════════════════════════════════════
# UI HELPERS — vẽ numpad + avatar card
# ════════════════════════════════════════════════════════════════

def _initials(ho_ten: str) -> str:
    """Lấy chữ cái đầu của họ tên: 'Nguyễn Văn Tuấn' → 'T'"""
    if not ho_ten:
        return "?"
    words = ho_ten.strip().split()
    if not words:
        return "?"
    return words[-1][0].upper()


def _display_name_no_prefix(ho_ten: str) -> str:
    """Bỏ tiền tố 1 ký tự kiểu 'K Đăng Khoa' -> 'Đăng Khoa'."""
    words = (ho_ten or "").strip().split()
    if len(words) >= 2 and len(words[0]) == 1:
        return " ".join(words[1:])
    return ho_ten


# CSS cho numpad — force horizontal layout cả trên mobile
_NUMPAD_CSS = """
<style>
.st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 8px !important;
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
}
.st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div {
    flex: 0 0 calc((100% - 16px) / 3) !important;
    min-width: 0 !important;
    width: calc((100% - 16px) / 3) !important;
    max-width: calc((100% - 16px) / 3) !important;
}
@media (max-width: 640px) {
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div {
        flex: 0 0 calc((100% - 12px) / 3) !important;
        width: calc((100% - 12px) / 3) !important;
        max-width: calc((100% - 12px) / 3) !important;
    }
}
.st-key-__ZONE_KEY__ div[data-testid="stButton"] button {
    height: 64px !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    width: 100% !important;
    padding: 0 !important;
}
@media (max-width: 640px) {
    .st-key-__ZONE_KEY__ div[data-testid="stButton"] button {
        height: 50px !important;
        font-size: 1.1rem !important;
    }
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] {
        gap: 6px !important;
    }
}
</style>
"""


def _render_numpad_input(key_prefix: str, max_len: int = 4) -> str:
    """Vẽ ô PIN input native + numpad button. Return PIN hiện tại (string)."""
    pin_key = f"{key_prefix}_pin_value"
    if pin_key not in st.session_state:
        st.session_state[pin_key] = ""

    current = st.session_state[pin_key]
    dots = ""
    for i in range(max_len):
        if i < len(current):
            dots += "● "
        else:
            dots += "○ "
    st.markdown(
        f"<div style='text-align:center;font-size:2rem;letter-spacing:8px;"
        f"margin:16px 0 10px;color:#1a1a2e;'>{dots.strip()}</div>",
        unsafe_allow_html=True
    )

    rk = st.session_state.get(f"{key_prefix}_input_reset_cnt", 0)
    input_key = f"{key_prefix}_native_input_{rk}"
    input_zone_key = f"numkb-{key_prefix}-input-zone"
    st.markdown(
        """<style>
        .st-key-__INPUT_ZONE__ input {
            text-align: center !important;
            font-size: 1.3rem !important;
            letter-spacing: 8px !important;
            font-weight: 600 !important;
            height: 50px !important;
        }
        </style>
        """.replace("__INPUT_ZONE__", input_zone_key),
        unsafe_allow_html=True
    )

    with st.container(key=input_zone_key):
        typed = st.text_input(
            "PIN",
            max_chars=max_len,
            key=input_key,
            label_visibility="collapsed",
            placeholder="• • • •",
            type="password",
        )

    typed_clean = "".join(c for c in (typed or "") if c.isdigit())[:max_len]

    if typed_clean != current:
        st.session_state[pin_key] = typed_clean
        st.rerun()

    current = st.session_state[pin_key]

    zone_key = f"{key_prefix}_numpad_zone"
    st.markdown(_NUMPAD_CSS.replace("__ZONE_KEY__", zone_key), unsafe_allow_html=True)

    rows = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["", "0", "⌫"]]
    with st.container(key=zone_key):
        for row in rows:
            cols = st.columns(3)
            for i, label in enumerate(row):
                with cols[i]:
                    if label == "":
                        st.markdown("&nbsp;", unsafe_allow_html=True)
                    elif label == "⌫":
                        if st.button("⌫", key=f"{key_prefix}_back",
                                     use_container_width=True):
                            if len(current) > 0:
                                _set_pin_state(key_prefix, current[:-1])
                                st.rerun()
                    else:
                        if st.button(label, key=f"{key_prefix}_n{label}",
                                     use_container_width=True,
                                     disabled=(len(current) >= max_len)):
                            _set_pin_state(key_prefix, current + label)
                            st.rerun()

    return st.session_state[pin_key]


def _set_pin_state(key_prefix: str, new_value: str):
    pin_key = f"{key_prefix}_pin_value"
    st.session_state[pin_key] = new_value
    cnt_key = f"{key_prefix}_input_reset_cnt"
    st.session_state[cnt_key] = st.session_state.get(cnt_key, 0) + 1


def _reset_numpad(key_prefix: str):
    pin_key = f"{key_prefix}_pin_value"
    st.session_state[pin_key] = ""
    cnt_key = f"{key_prefix}_input_reset_cnt"
    st.session_state[cnt_key] = st.session_state.get(cnt_key, 0) + 1


# ════════════════════════════════════════════════════════════════
# VERTICAL CENTERING
# ════════════════════════════════════════════════════════════════

def _vertical_spacer(min_vh: int = 12):
    st.markdown(
        f"<div style='min-height:{min_vh}vh;'></div>",
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════════════
# LOGIN UI — Bước 1: Chọn NV → Bước 2: PIN → Bước 3: Chi nhánh
# ════════════════════════════════════════════════════════════════

def _show_step_choose_nv():
    nv_list = load_nhan_vien_active()
    if not nv_list:
        st.info("Chưa có nhân viên nào trong hệ thống.")
        return

    n = len(nv_list)
    if n <= 3:    spacer_vh = 20
    elif n <= 5:  spacer_vh = 12
    elif n <= 8:  spacer_vh = 6
    else:         spacer_vh = 2

    _vertical_spacer(spacer_vh)

    st.markdown(
        "<div style='text-align:center;padding:0 0 16px;'>"
        "<div style='font-size:1.4rem;font-weight:700;color:#1a1a2e;'>DL Watch POS</div>"
        "<div style='font-size:0.9rem;color:#888;margin-top:4px;'>Chọn tài khoản</div>"
        "</div>",
        unsafe_allow_html=True
    )

    st.markdown("""
    <style>
    .nv-card {
        display: flex; align-items: center; gap: 14px;
        background: #fff; border: 1px solid #e8e8e8;
        border-radius: 12px; padding: 14px 16px;
        margin: 6px 0; cursor: pointer;
    }
    .nv-avatar {
        width: 44px; height: 44px; border-radius: 50%;
        background: #e63946; color: #fff;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.2rem; font-weight: 700;
        flex-shrink: 0;
    }
    .nv-name { font-size: 1rem; font-weight: 600; color: #1a1a2e; }
    </style>
    """, unsafe_allow_html=True)

    for nv in nv_list:
        display_name = _display_name_no_prefix(nv["ho_ten"])
        col_btn = st.container()
        with col_btn:
            if st.button(
                display_name,
                key=f"login_nv_{nv['id']}",
                use_container_width=True,
            ):
                st.session_state["_pending_nv"] = nv
                # Ghi đè vào URL để lưu thiết bị
                _save_user_localstorage(nv['id'])
                _reset_numpad("login")
                st.rerun()


def _show_step_pin(nv: dict, has_pin: bool):
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("←", key="login_back_to_nv", use_container_width=True):
            st.session_state.pop("_pending_nv", None)
            st.session_state.pop("_setting_pin_step", None)
            st.session_state.pop("_setting_pin_first", None)
            # Xoá u khỏi url khi bấm back để có thể chọn lại nhân viên khác.
            _ls_delete_user()
            _reset_numpad("login")
            st.rerun()

    st.markdown(
        f"<div style='text-align:center;padding:8px 0;'>"
        f"<div style='font-size:1.1rem;font-weight:700;color:#1a1a2e;'>"
        f"Xin chào, {nv['ho_ten']}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    if not has_pin:
        step = st.session_state.get("_setting_pin_step", 1)

        if step == 1:
            st.markdown(
                "<div style='text-align:center;font-size:0.92rem;color:#666;"
                "margin-bottom:10px;'>Đây là lần đầu — tạo mã PIN 4 số:</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='text-align:center;font-size:0.92rem;color:#666;"
                "margin-bottom:10px;'>Nhập lại để xác nhận:</div>",
                unsafe_allow_html=True
            )

        pin = _render_numpad_input("login", max_len=4)

        if len(pin) == 4:
            if step == 1:
                st.session_state["_setting_pin_first"] = pin
                st.session_state["_setting_pin_step"] = 2
                _reset_numpad("login")
                st.rerun()
            else:
                first_pin = st.session_state.get("_setting_pin_first", "")
                if pin == first_pin:
                    pin_h = hash_pin(pin)
                    if set_pin(nv["id"], pin_h):
                        _finalize_login(nv)
                    else:
                        st.error("Lỗi lưu PIN, thử lại.")
                        _reset_numpad("login")
                else:
                    st.error("PIN không khớp — nhập lại từ đầu")
                    st.session_state["_setting_pin_step"] = 1
                    st.session_state.pop("_setting_pin_first", None)
                    _reset_numpad("login")
                    import time
                    time.sleep(1)
                    st.rerun()
    else:
        st.markdown(
            "<div style='text-align:center;font-size:0.92rem;color:#666;"
            "margin-bottom:10px;'>Nhập mã PIN:</div>",
            unsafe_allow_html=True
        )

        pin = _render_numpad_input("login", max_len=4)

        if len(pin) == 4:
            pin_hash = load_pin(nv["id"])
            if verify_pin(pin, pin_hash):
                _finalize_login(nv)
            else:
                st.error("Sai PIN — thử lại")
                _reset_numpad("login")
                import time
                time.sleep(0.8)
                st.rerun()

        st.markdown(
            "<div style='text-align:center;font-size:0.78rem;color:#aaa;"
            "margin-top:14px;'>Quên PIN? Liên hệ admin</div>",
            unsafe_allow_html=True
        )


def _show_step_choose_branch():
    branches = get_accessible_branches()

    n = len(branches)
    if n <= 2:    spacer_vh = 22
    elif n == 3:  spacer_vh = 18
    else:         spacer_vh = 12

    _vertical_spacer(spacer_vh)

    st.markdown(
        "<div style='text-align:center;padding:0 0 16px;'>"
        "<div style='font-size:1.05rem;color:#1a7f37;'>✓ Đăng nhập thành công!</div>"
        "<div style='font-size:0.92rem;color:#666;margin-top:8px;'>"
        "Chọn chi nhánh:</div>"
        "</div>",
        unsafe_allow_html=True
    )

    from utils.config import CN_SHORT
    st.markdown(
        """<style>
        [class*="st-key-login-branch-zone"] button[kind] p {
            font-weight: 700 !important;
            font-size: 1rem !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="login-branch-zone"):
        for cn in branches:
            label = CN_SHORT.get(cn, cn) if cn == "GO BÀ RỊA" else cn
            if st.button(
                f"📍 {label}",
                key=f"login_cn_{cn}",
                use_container_width=True,
            ):
                st.session_state["active_chi_nhanh"] = cn
                _save_branch_localstorage(cn)
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Đăng xuất", key="login_logout_branch", use_container_width=True):
        do_logout()
        st.rerun()


def _finalize_login(nv: dict):
    """Tạo session token, lưu vào localStorage, set state."""
    # User agent ngắn gọn (Streamlit không expose UA dễ — dùng placeholder)
    user_agent = "POS App"

    token = create_session_token(nv["id"], user_agent)
    if not token:
        st.error("Lỗi tạo phiên đăng nhập. Thử lại.")
        return

    user = restore_session(token)
    if not user:
        st.error("Lỗi khôi phục session. Thử đăng nhập lại.")
        return

    st.session_state["user"] = user
    _ls_set_token(token)
    # Xoá u trên URL khi đã đăng nhập
    _ls_delete_user()
    # Lưu token vào session_state để do_logout() biết hủy session nào nếu cần
    st.session_state["_session_token"] = token

    st.session_state.pop("_pending_nv", None)
    st.session_state.pop("_setting_pin_step", None)
    st.session_state.pop("_setting_pin_first", None)
    _reset_numpad("login")

    st.rerun()


# ════════════════════════════════════════════════════════════════
# AUTH GATE
# ════════════════════════════════════════════════════════════════

def run_auth_gate():
    """
    Cổng kiểm tra auth. Gọi đầu app.py.
    - Restore từ localStorage token nếu có
    - Nếu chưa login: hiện flow login
    - Nếu chưa chọn CN: hiện flow chọn CN
    """
    # ── Restore session từ localStorage ──
    if "user" not in st.session_state:
        token = _ls_get_token()
        if token:
            user = restore_session(token)
            if user:
                st.session_state["user"] = user
                st.session_state["_session_token"] = token
            else:
                # Token invalid → xóa khỏi localStorage
                _ls_delete_token()

    # Chưa login
    if "user" not in st.session_state:
        pending_nv = st.session_state.get("_pending_nv")
        
        # Kiểm tra URL param u để bypass bước chọn nhân viên
        if not pending_nv:
            ls_user_id = _ls_get_user_id()
            if ls_user_id:
                nv_list = load_nhan_vien_active()
                for nv in nv_list:
                    if str(nv["id"]) == ls_user_id:
                        st.session_state["_pending_nv"] = nv
                        pending_nv = nv
                        break
        
        if not pending_nv:
            _show_step_choose_nv()
        else:
            has_pin = load_pin(pending_nv["id"]) is not None
            _show_step_pin(pending_nv, has_pin)
        st.stop()

    # Đã login, kiểm tra chi nhánh
    if "active_chi_nhanh" not in st.session_state:
        accessible = get_accessible_branches()
        # Thử đọc CN từ localStorage
        ls_branch = _ls_get_branch()

        if ls_branch and ls_branch in accessible:
            st.session_state["active_chi_nhanh"] = ls_branch
        elif len(accessible) == 1:
            st.session_state["active_chi_nhanh"] = accessible[0]
            _save_branch_localstorage(accessible[0])
        else:
            _show_step_choose_branch()
            st.stop()


# ════════════════════════════════════════════════════════════════
# SESSION WARNING BANNER
# ════════════════════════════════════════════════════════════════

def render_session_warning_banner():
    """Cảnh báo khi session sắp hết hạn (≤30 phút)."""
    user = get_user()
    if not user:
        return

    expires_at_str = user.get("session_expires_at")
    if not expires_at_str:
        return

    try:
        expires = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        now = now_vn()
        remaining = (expires - now).total_seconds()
    except Exception:
        return

    if remaining <= 0:
        return
    if remaining > 1800:
        return

    minutes = int(remaining // 60)
    from zoneinfo import ZoneInfo
    expires_hhmm = expires.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M")

    st.markdown(
        f"<div style='background:#fff8e0;border:1px solid #f0c36d;"
        f"border-radius:8px;padding:8px 12px;margin:4px 0 10px;"
        f"font-size:0.85rem;color:#856404;'>"
        f"⚠️ <b>Phiên đăng nhập sắp hết hạn</b> "
        f"({minutes} phút · đến {expires_hhmm}). "
        f"Hoàn tất các giao dịch đang dở."
        f"</div>",
        unsafe_allow_html=True
    )
