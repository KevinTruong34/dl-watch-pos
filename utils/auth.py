import streamlit as st
import streamlit.components.v1 as components
from utils.db import get_supabase_client
import pandas as pd

# ══════════════════════════════════════════
# CSS CẤU HÌNH GIAO DIỆN NUMPAD
# ══════════════════════════════════════════
_NUMPAD_CSS = """
<style>
/* Style chung cho nút bấm Numpad */
div[data-testid="stButton"] button {
    height: 64px !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    width: 100% !important;
    padding: 0 !important;
    background-color: white !important;
    color: #1a1a2e !important;
    border: 1px solid #e0e0e0 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
}

div[data-testid="stButton"] button:active {
    background-color: #f0f2f6 !important;
    transform: scale(0.98);
}

/* Ép Numpad (block 3 cột) luôn nằm ngang trên Mobile */
@media (max-width: 640px) {
    div[data-testid="stButton"] button {
        height: 58px !important;
        font-size: 1.4rem !important;
    }
    
    /* Nhắm vào block st.columns(3) có cột thứ 3 là cột cuối cùng */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3):last-child) {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 8px !important;
    }
    
    /* Chia đều 33% cho mỗi cột phím */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3):last-child) > div[data-testid="column"] {
        flex: 1 1 0 !important;
        min-width: 0 !important;
        width: 33.33% !important;
    }
}
</style>
"""

def _render_numpad_input(key_prefix: str, max_len: int = 4) -> str:
    """
    Vẽ bàn phím số và ô hiển thị mã PIN.
    """
    pin_key = f"{key_prefix}_pin_value"
    if pin_key not in st.session_state:
        st.session_state[pin_key] = ""

    current_pin = st.session_state[pin_key]

    # 1. Hiển thị các chấm mã PIN (● ● ○ ○)
    dots = ""
    for i in range(max_len):
        dots += "● " if i < len(current_pin) else "○ "
    
    st.markdown(
        f"<div style='text-align:center; font-size:2.2rem; letter-spacing:10px; "
        f"margin:25px 0; color:#1a1a2e;'>{dots.strip()}</div>",
        unsafe_allow_html=True
    )

    # 2. Inject CSS fix Mobile
    st.markdown(_NUMPAD_CSS, unsafe_allow_html=True)

    # 3. Vẽ lưới bàn phím 3x4
    rows = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["", "0", "⌫"]
    ]

    for row in rows:
        cols = st.columns(3)
        for i, label in enumerate(row):
            with cols[i]:
                if label == "":
                    st.write("") # Cột trống
                elif label == "⌫":
                    if st.button("⌫", key=f"{key_prefix}_btn_del", use_container_width=True):
                        if len(current_pin) > 0:
                            st.session_state[pin_key] = current_pin[:-1]
                            st.rerun()
                else:
                    # Disable nút nếu đã nhập đủ max_len
                    is_disabled = len(current_pin) >= max_len
                    if st.button(label, key=f"{key_prefix}_btn_{label}", 
                                 use_container_width=True, disabled=is_disabled):
                        st.session_state[pin_key] = current_pin + label
                        st.rerun()

    return st.session_state[pin_key]

def check_auth():
    """
    Hàm kiểm tra đăng nhập chính cho App POS.
    """
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if st.session_state.authenticated:
        return True

    # Giao diện màn hình khóa (Lock Screen)
    st.markdown("<h2 style='text-align:center; color:#1a1a2e;'>MÃ PIN NHÂN VIÊN</h2>", unsafe_allow_html=True)
    
    pin = _render_numpad_input("auth_screen")

    if len(pin) == 4:
        # Kiểm tra PIN từ Database Supabase
        supabase = get_supabase_client()
        try:
            res = supabase.table("nhan_vien") \
                .select("id, ho_ten, id_chi_nhanh, role") \
                .eq("pin", pin) \
                .eq("is_active", True) \
                .execute()
            
            if res.data and len(res.data) > 0:
                user = res.data[0]
                st.session_state.authenticated = True
                st.session_state.user_info = user
                st.success(f"Chào mừng {user['ho_ten']}!")
                st.rerun()
            else:
                st.error("Mã PIN không đúng hoặc tài khoản bị khóa")
                # Reset mã PIN để nhập lại
                st.session_state["auth_screen_pin_value"] = ""
                st.rerun()
        except Exception as e:
            st.error(f"Lỗi kết nối hệ thống: {str(e)}")

    return False

def logout():
    """Xóa session và đăng xuất"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
