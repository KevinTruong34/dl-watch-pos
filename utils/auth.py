"""Auth: login PIN flow + session quản lý."""

import streamlit as st
import bcrypt
import uuid
from datetime import datetime

from utils.db import supabase, load_nhan_vien_active, load_pin, set_pin
from utils.helpers import now_vn, end_of_today_vn_iso


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
# SESSION TOKEN MANAGEMENT
# ════════════════════════════════════════════════════════════════

def create_session_token(nv_id: int) -> str:
    """
    Tạo session token mới, hết hạn 23:59:59 hôm nay (giờ VN).
    Trả về token string.
    """
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({
        "token":        token,
        "nhan_vien_id": nv_id,
        "expires_at":   end_of_today_vn_iso(),
    }).execute()
    return token


def delete_session(token: str):
    try:
        supabase.table("sessions").delete().eq("token", token).execute()
    except Exception:
        pass


def restore_session(token: str) -> dict | None:
    """
    Khôi phục user info từ token.
    Return user dict nếu token còn hiệu lực, None nếu hết hạn / không tồn tại.
    """
    if not token:
        return None
    try:
        res = supabase.table("sessions") \
            .select("nhan_vien_id,expires_at") \
            .eq("token", token).limit(1).execute()
        if not res.data:
            return None

        s = res.data[0]
        # So sánh thời điểm hết hạn với hiện tại (cả 2 đều là tz-aware)
        expires = datetime.fromisoformat(s["expires_at"])
        if expires < now_vn():
            delete_session(token)
            return None

        # Load thông tin user
        nv_res = supabase.table("nhan_vien") \
            .select("id,username,ho_ten,role,active") \
            .eq("id", s["nhan_vien_id"]).limit(1).execute()
        if not nv_res.data:
            return None
        user = nv_res.data[0]
        if not user.get("active"):
            return None

        # Load chi nhánh phân quyền
        cn_res = supabase.table("nhan_vien_chi_nhanh") \
            .select("chi_nhanh(ten)").eq("nhan_vien_id", user["id"]).execute()
        user["chi_nhanh_list"] = [
            x["chi_nhanh"]["ten"] for x in (cn_res.data or [])
            if x.get("chi_nhanh")
        ]
        return user
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# URL PARAMS — dùng để giữ session khi reload trang
# ════════════════════════════════════════════════════════════════

def get_token_from_url() -> str | None:
    return st.query_params.get("token")


def save_token_to_url(token: str):
    st.query_params["token"] = token


def clear_url_params():
    for k in ("token",):
        if k in st.query_params:
            del st.query_params[k]


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
    """Xóa session khỏi DB + clear state."""
    token = get_token_from_url()
    if token:
        delete_session(token)
    clear_url_params()
    st.session_state.clear()


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


# CSS cho numpad — force horizontal layout cả trên mobile
_NUMPAD_CSS = """
<style>
/* Scoped bằng st.container(key=...) để chỉ apply cho numpad */
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
/* Override Streamlit mobile rule that forces columns to stack */
@media (max-width: 640px) {
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div {
        flex: 0 0 calc((100% - 12px) / 3) !important;
        width: calc((100% - 12px) / 3) !important;
        max-width: calc((100% - 12px) / 3) !important;
    }
}
/* Style cho numpad buttons */
.st-key-__ZONE_KEY__ div[data-testid="stButton"] button {
    height: 64px !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    width: 100% !important;
    padding: 0 !important;
}
/* Mobile - tăng nhẹ kích thước button */
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
    """
    Vẽ ô PIN input native (bàn phím số trên mobile) + numpad button làm backup.

    UX:
      - Ô input chính: kích hoạt bàn phím số native (inputmode="numeric")
      - Numpad button bên dưới: backup khi user đóng bàn phím native
      - Cả 2 cùng cập nhật vào st.session_state[pin_key]
      - Trả về PIN hiện tại (string)
    """
    pin_key = f"{key_prefix}_pin_value"
    if pin_key not in st.session_state:
        st.session_state[pin_key] = ""

    # ── 1. Hiển thị dots ●●○○ (đẹp) ──
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

    # ── 2. Input native (mobile keyboard số qua key prefix numkb) ──
    # Dùng key có suffix counter để reset được khi cần
    rk = st.session_state.get(f"{key_prefix}_input_reset_cnt", 0)
    input_key = f"{key_prefix}_native_input_{rk}"

    # Container key bắt đầu bằng "numkb-" → MutationObserver global trong app.py
    # sẽ tự apply inputmode="numeric" cho input bên trong
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
        )

    # Filter typed: chỉ giữ chữ số, max max_len
    typed_clean = "".join(c for c in (typed or "") if c.isdigit())[:max_len]

    # Đồng bộ giá trị: nếu input native khác state hiện tại → cập nhật state
    if typed_clean != current:
        st.session_state[pin_key] = typed_clean
        st.rerun()

    current = st.session_state[pin_key]

    # ── 3. Numpad button (backup, dưới input) ──
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
    """
    Set PIN state + tăng input reset counter để input native re-render với
    giá trị mới (cần thiết khi numpad button thay đổi state).
    """
    pin_key = f"{key_prefix}_pin_value"
    st.session_state[pin_key] = new_value
    # Tăng counter → input native dùng key mới → re-render với placeholder rỗng
    cnt_key = f"{key_prefix}_input_reset_cnt"
    st.session_state[cnt_key] = st.session_state.get(cnt_key, 0) + 1


def _reset_numpad(key_prefix: str):
    """Xóa giá trị PIN + reset input native."""
    pin_key = f"{key_prefix}_pin_value"
    st.session_state[pin_key] = ""
    # Tăng counter để input native re-render với giá trị rỗng
    cnt_key = f"{key_prefix}_input_reset_cnt"
    st.session_state[cnt_key] = st.session_state.get(cnt_key, 0) + 1


# ════════════════════════════════════════════════════════════════
# VERTICAL CENTERING — Đẩy nội dung xuống giữa màn hình
# ════════════════════════════════════════════════════════════════

def _vertical_spacer(min_vh: int = 12):
    """
    Tạo khoảng trống ở đầu để đẩy nội dung xuống giữa.
    Dùng vh (viewport height) để responsive theo chiều cao màn hình.
    """
    st.markdown(
        f"<div style='min-height:{min_vh}vh;'></div>",
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════════════
# LOGIN UI — Bước 1: Chọn NV → Bước 2: PIN → Bước 3: Chi nhánh
# ════════════════════════════════════════════════════════════════

def _show_step_choose_nv():
    """Bước 1: Chọn nhân viên — canh giữa theo chiều dọc."""
    nv_list = load_nhan_vien_active()
    if not nv_list:
        st.info("Chưa có nhân viên nào trong hệ thống.")
        return

    # Spacer động theo số lượng NV để luôn cân giữa:
    #   ít NV → spacer lớn, nhiều NV → spacer nhỏ
    n = len(nv_list)
    if n <= 3:
        spacer_vh = 20
    elif n <= 5:
        spacer_vh = 12
    elif n <= 8:
        spacer_vh = 6
    else:
        spacer_vh = 2

    _vertical_spacer(spacer_vh)

    st.markdown(
        "<div style='text-align:center;padding:0 0 16px;'>"
        "<div style='font-size:1.4rem;font-weight:700;color:#1a1a2e;'>DL Watch POS</div>"
        "<div style='font-size:0.9rem;color:#888;margin-top:4px;'>Chọn tài khoản</div>"
        "</div>",
        unsafe_allow_html=True
    )

    # Style cho avatar card
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
        ini = _initials(nv["ho_ten"])
        col_btn = st.container()
        with col_btn:
            if st.button(
                f"{ini}    {nv['ho_ten']}",
                key=f"login_nv_{nv['id']}",
                use_container_width=True,
            ):
                st.session_state["_pending_nv"] = nv
                _reset_numpad("login")
                st.rerun()


def _show_step_pin(nv: dict, has_pin: bool):
    """Bước 2: Nhập PIN (set lần đầu hoặc xác thực)."""
    # Header với nút back
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("←", key="login_back_to_nv", use_container_width=True):
            st.session_state.pop("_pending_nv", None)
            st.session_state.pop("_setting_pin_step", None)
            st.session_state.pop("_setting_pin_first", None)
            _reset_numpad("login")
            st.rerun()

    st.markdown(
        f"<div style='text-align:center;padding:8px 0;'>"
        f"<div style='font-size:1.1rem;font-weight:700;color:#1a1a2e;'>"
        f"Xin chào, {nv['ho_ten']}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Phân biệt: chưa có PIN → set 2 bước (nhập + xác nhận)
    #            có PIN → nhập 1 lần để xác thực
    if not has_pin:
        # Bước 2A: Set PIN lần đầu
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

        # Khi đủ 4 số → tự xử lý
        if len(pin) == 4:
            if step == 1:
                # Lưu PIN lần 1, chuyển sang bước 2
                st.session_state["_setting_pin_first"] = pin
                st.session_state["_setting_pin_step"] = 2
                _reset_numpad("login")
                st.rerun()
            else:
                # Bước 2: so sánh
                first_pin = st.session_state.get("_setting_pin_first", "")
                if pin == first_pin:
                    # Khớp → lưu vào DB
                    pin_h = hash_pin(pin)
                    if set_pin(nv["id"], pin_h):
                        # Login luôn
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
        # Bước 2B: Nhập PIN xác thực
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
    """Bước 3: Chọn chi nhánh — canh giữa theo chiều dọc."""
    user = get_user()
    branches = get_accessible_branches()

    # Spacer dynamic theo số CN (thường ít — chỉ 1-3 CN)
    n = len(branches)
    if n <= 2:
        spacer_vh = 22
    elif n == 3:
        spacer_vh = 18
    else:
        spacer_vh = 12

    _vertical_spacer(spacer_vh)

    st.markdown(
        f"<div style='text-align:center;padding:0 0 16px;'>"
        f"<div style='font-size:1.05rem;color:#1a7f37;'>✓ Đăng nhập thành công!</div>"
        f"<div style='font-size:0.92rem;color:#666;margin-top:8px;'>"
        f"Chọn chi nhánh:</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    from utils.config import CN_SHORT
    for cn in branches:
        short = CN_SHORT.get(cn, cn)
        if st.button(
            f"📍 {short}\n{cn}",
            key=f"login_cn_{cn}",
            use_container_width=True,
        ):
            st.session_state["active_chi_nhanh"] = cn
            # Lưu vào localStorage qua components.html
            _save_branch_localstorage(cn)
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Đăng xuất", key="login_logout_branch", use_container_width=True):
        do_logout()
        st.rerun()


def _save_branch_localstorage(branch: str):
    """Lưu chi nhánh đã chọn vào localStorage để nhớ cho lần sau."""
    import streamlit.components.v1 as components
    components.html(
        f"""<script>
        try {{
            localStorage.setItem('pos_active_branch', {repr(branch)});
        }} catch(e) {{}}
        </script>""",
        height=0
    )


def _read_branch_localstorage_js() -> None:
    """
    Inject JS đọc localStorage và set vào URL params nếu có.
    Chạy 1 lần khi user mới login mà chưa có active_chi_nhanh.
    """
    import streamlit.components.v1 as components
    components.html(
        """<script>
        try {
            var b = localStorage.getItem('pos_active_branch');
            if (b) {
                var url = new URL(window.parent.location.href);
                if (!url.searchParams.get('branch')) {
                    url.searchParams.set('branch', b);
                    window.parent.location.replace(url.toString());
                }
            }
        } catch(e) {}
        </script>""",
        height=0
    )


def _finalize_login(nv: dict):
    """Tạo session token, set state, redirect."""
    token = create_session_token(nv["id"])

    # Load đầy đủ user info (có chi_nhanh_list)
    user = restore_session(token)
    if not user:
        st.error("Lỗi khôi phục session. Thử đăng nhập lại.")
        return

    st.session_state["user"] = user
    save_token_to_url(token)

    # Clean up state
    st.session_state.pop("_pending_nv", None)
    st.session_state.pop("_setting_pin_step", None)
    st.session_state.pop("_setting_pin_first", None)
    _reset_numpad("login")

    st.rerun()


# ════════════════════════════════════════════════════════════════
# AUTH GATE — gọi từ app.py
# ════════════════════════════════════════════════════════════════

def run_auth_gate():
    """
    Cổng kiểm tra auth. Gọi đầu app.py.
    Nếu chưa login: hiện flow login.
    Nếu chưa chọn chi nhánh: hiện flow chọn CN.
    Nếu đã login + có CN: pass, app.py tiếp tục render.
    """
    # Restore session từ token URL nếu có
    if "user" not in st.session_state:
        token = get_token_from_url()
        if token:
            user = restore_session(token)
            if user:
                st.session_state["user"] = user
            else:
                clear_url_params()

    # Chưa login
    if "user" not in st.session_state:
        pending_nv = st.session_state.get("_pending_nv")
        if not pending_nv:
            _show_step_choose_nv()
        else:
            has_pin = load_pin(pending_nv["id"]) is not None
            _show_step_pin(pending_nv, has_pin)
        st.stop()

    # Đã login, kiểm tra chi nhánh
    if "active_chi_nhanh" not in st.session_state:
        # Thử đọc từ URL (set bởi localStorage)
        url_branch = st.query_params.get("branch")
        accessible = get_accessible_branches()

        if url_branch and url_branch in accessible:
            st.session_state["active_chi_nhanh"] = url_branch
        elif len(accessible) == 1:
            # Chỉ thuộc 1 CN → tự chọn
            st.session_state["active_chi_nhanh"] = accessible[0]
            _save_branch_localstorage(accessible[0])
        else:
            # Hiện màn chọn CN
            _show_step_choose_branch()
            st.stop()
