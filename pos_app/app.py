"""
DL Watch POS — Entry point.

Mobile-first Streamlit app for point-of-sale.
"""

import streamlit as st

from utils.config import APP_NAME, CN_SHORT
from utils.auth import (
    run_auth_gate, get_user, get_active_branch,
    get_accessible_branches, do_logout, _save_branch_localstorage,
    _initials,
)


# ── Page config ──
st.set_page_config(
    page_title=APP_NAME,
    page_icon="🛍️",
    layout="centered",   # mobile-first → không dùng wide
    initial_sidebar_state="collapsed",
)


# ── Mobile-first CSS ──
st.markdown("""
<style>
/* Force light mode + mobile colors */
:root {
    color-scheme: light only !important;
}
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: #f5f6f8 !important;
    color: #1a1a2e !important;
    color-scheme: light only !important;
}

/* Hide Streamlit chrome */
header, footer, #stDecoration, .stAppDeployButton,
[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stElementToolbar"], [data-testid="stDecoration"]
{ display: none !important; }

/* Compact spacing for mobile */
.block-container {
    padding: 0.6rem 0.8rem 1.2rem 0.8rem !important;
    max-width: 480px !important;
}

/* Buttons — large for fingers */
[data-testid="stBaseButton-primary"] {
    background: #e63946 !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    color: #fff !important;
    min-height: 48px !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background: #c1121f !important;
}
[data-testid="stBaseButton-secondary"] {
    border-radius: 10px !important;
    border: 1px solid #ddd !important;
    background: #fff !important;
    color: #1a1a2e !important;
    min-height: 48px !important;
}
[data-testid="stBaseButton-secondary"]:hover {
    background: #f9f9f9 !important;
    border-color: #bbb !important;
}

/* Input fields */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: #fff !important;
    color: #1a1a2e !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    font-size: 1rem !important;
}

/* Hide form border */
[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
}

/* Disable text selection on buttons (better for mobile taps) */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    user-select: none;
}

/* Alerts */
[data-testid="stAlert"] {
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# AUTH GATE — phải pass mới render app
# ════════════════════════════════════════════════════════════════
run_auth_gate()


# ════════════════════════════════════════════════════════════════
# HEADER (sticky-like — render đầu mỗi lần)
# ════════════════════════════════════════════════════════════════

user = get_user()
active_cn = get_active_branch()
ho_ten = user.get("ho_ten", "") if user else ""
initials = _initials(ho_ten)
cn_short = CN_SHORT.get(active_cn, active_cn[:8])
accessible = get_accessible_branches()

# Header bar: Logo | CN | Avatar
col_logo, col_cn, col_avatar = st.columns([2, 2, 1])

with col_logo:
    st.markdown(
        "<div style='font-size:1.05rem;font-weight:700;color:#e63946;"
        "padding-top:8px;'>🛍️ DL POS</div>",
        unsafe_allow_html=True
    )

with col_cn:
    if len(accessible) > 1:
        with st.popover(f"📍 {cn_short}", use_container_width=True):
            st.caption("Đổi chi nhánh:")
            for cn in accessible:
                is_active = (cn == active_cn)
                lbl = f"✓ {cn}" if is_active else cn
                if st.button(
                    lbl, key=f"sw_cn_{cn}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    disabled=is_active,
                ):
                    st.session_state["active_chi_nhanh"] = cn
                    _save_branch_localstorage(cn)
                    # Reset giỏ khi đổi CN — sẽ implement ở bước 2
                    st.session_state.pop("pos_cart", None)
                    st.rerun()
    else:
        st.markdown(
            f"<div style='font-size:0.88rem;font-weight:600;color:#1a1a2e;"
            f"padding-top:10px;text-align:center;'>📍 {cn_short}</div>",
            unsafe_allow_html=True
        )

with col_avatar:
    with st.popover(initials, use_container_width=True):
        st.markdown(
            f"<div style='text-align:center;padding:6px 0 4px;'>"
            f"<div style='font-size:1rem;font-weight:700;'>{ho_ten}</div>"
            f"<div style='font-size:0.78rem;color:#888;'>{user.get('role','')}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
        st.markdown("---")
        if st.button("🚪 Đăng xuất", use_container_width=True, key="logout_btn"):
            do_logout()
            st.rerun()

st.markdown("<hr style='margin:6px 0 12px 0;'>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# MAIN — Tabs Bán hàng / Lịch sử (placeholder cho bước 1)
# ════════════════════════════════════════════════════════════════

# Tab navigation (sẽ implement ở bước 2/4)
tab_choice = st.pills(
    "main_nav",
    ["🛒 Bán hàng", "📋 Lịch sử"],
    default="🛒 Bán hàng",
    label_visibility="collapsed",
    key="main_tab",
)
tab_choice = tab_choice or "🛒 Bán hàng"

st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

if tab_choice == "🛒 Bán hàng":
    st.info(
        "✅ **Bước 1 hoàn tất** — Auth + Setup project đã sẵn sàng.\n\n"
        "Màn hình bán hàng sẽ được build ở **Bước 2**."
    )
    st.markdown(f"**Đăng nhập:** {ho_ten}")
    st.markdown(f"**Chi nhánh hiện tại:** {active_cn}")
    st.markdown(f"**Quyền:** {user.get('role','')}")
    st.markdown(f"**Số chi nhánh được phân:** {len(accessible)}")

elif tab_choice == "📋 Lịch sử":
    st.info("📋 Lịch sử hóa đơn — sẽ build ở **Bước 4**.")
