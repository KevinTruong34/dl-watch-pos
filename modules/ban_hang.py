"""
Module bán hàng — Phase 2A (chưa có quét mã vạch).

UI flow:
- Search hàng → expander mở sẵn, max 3 kết quả gần nhất
- Bấm vào kết quả → thêm vào giỏ với SL = 1
- Card giỏ hàng: hiện tên + SL + thành tiền + nút xóa
- Bấm vào card → mở dialog sửa SL / đơn giá / giảm giá
- Footer: tạm tính + nút "TIẾP TỤC →" sang màn 3
"""

import streamlit as st

from utils.auth import get_active_branch
from utils.db import load_hang_hoa_pos
from utils.helpers import fmt_vnd


# ════════════════════════════════════════════════════════════════
# CART HELPERS
# ════════════════════════════════════════════════════════════════

CART_KEY = "pos_cart"


def _get_cart() -> list[dict]:
    return st.session_state.get(CART_KEY, [])


def _save_cart(cart: list[dict]):
    st.session_state[CART_KEY] = cart


def _add_to_cart(item: dict):
    """
    Thêm 1 sản phẩm vào giỏ.
    Nếu mã hàng đã có → tăng SL +1.
    Nếu chưa có → thêm dòng mới với SL = 1.
    """
    cart = _get_cart()
    ma_hang = item["ma_hang"]
    for line in cart:
        if line["ma_hang"] == ma_hang:
            line["so_luong"] += 1
            _save_cart(cart)
            return
    cart.append({
        "ma_hang":       item["ma_hang"],
        "ten_hang":      item["ten_hang"],
        "so_luong":      1,
        "don_gia":       item["gia_ban"],
        "giam_gia_dong": 0,
        "ton_kho":       item["ton"],
        "loai_sp":       item.get("loai_sp", "Hàng hóa"),
    })
    _save_cart(cart)


def _remove_from_cart(ma_hang: str):
    cart = [x for x in _get_cart() if x["ma_hang"] != ma_hang]
    _save_cart(cart)


def _update_cart_line(ma_hang: str, so_luong: int, don_gia: int, giam_gia_dong: int):
    cart = _get_cart()
    for line in cart:
        if line["ma_hang"] == ma_hang:
            line["so_luong"]      = so_luong
            line["don_gia"]       = don_gia
            line["giam_gia_dong"] = giam_gia_dong
            break
    _save_cart(cart)


def _calc_thanh_tien(line: dict) -> int:
    return max(0, line["so_luong"] * line["don_gia"] - line["giam_gia_dong"])


def _calc_tam_tinh(cart: list[dict]) -> int:
    return sum(_calc_thanh_tien(line) for line in cart)


def _clear_cart():
    st.session_state.pop(CART_KEY, None)


# ════════════════════════════════════════════════════════════════
# SEARCH LOGIC
# ════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Bỏ space/dash để fuzzy match: 'F 94' khớp 'F94'."""
    import re
    return re.sub(r"[\s\-_./]", "", str(text or "")).lower()


def _search_hang_hoa(keyword: str, hh_list: list[dict],
                     max_results: int = 3) -> list[dict]:
    """
    Tìm hàng hóa theo keyword.
    Ưu tiên:
      1. Hàng có tồn (loai_sp = Dịch vụ luôn được coi là còn tồn)
      2. Trong từng nhóm: match đầu mã > đầu tên > trong mã > trong tên
    Trả về tối đa max_results items.
    """
    if not keyword.strip():
        return []
    kw = _normalize(keyword)

    matches = []
    for hh in hh_list:
        ma_n   = _normalize(hh["ma_hang"])
        vach_n = _normalize(hh["ma_vach"])
        ten_n  = _normalize(hh["ten_hang"])

        score = 0
        if ma_n.startswith(kw):
            score = 100
        elif vach_n and vach_n.startswith(kw):
            score = 95
        elif ten_n.startswith(kw):
            score = 80
        elif kw in ma_n:
            score = 60
        elif kw in vach_n:
            score = 50
        elif kw in ten_n:
            score = 40

        if score > 0:
            # Boost +1000 cho hàng còn tồn → luôn xếp trước hàng hết tồn
            # (Dịch vụ có ton = 999999 → cũng được boost)
            if hh["ton"] > 0:
                score += 1000
            matches.append((score, hh))

    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches[:max_results]]


# ════════════════════════════════════════════════════════════════
# MODAL — Sửa chi tiết dòng (st.dialog)
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết sản phẩm")
def _dialog_sua_dong(line: dict):
    """Dialog sửa SL / đơn giá / giảm giá cho 1 dòng giỏ."""
    is_dich_vu = line.get("loai_sp") == "Dịch vụ"

    # Header
    if is_dich_vu:
        ton_label = "🛠 Dịch vụ"
    else:
        ton_label = f"Tồn kho: {line['ton_kho']}"

    st.markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:#1a1a2e;'>"
        f"{line['ten_hang']}</div>"
        f"<div style='font-size:0.82rem;color:#888;font-family:monospace;'>"
        f"{line['ma_hang']}</div>"
        f"<div style='font-size:0.82rem;color:#666;margin-top:4px;'>"
        f"{ton_label}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    # Số lượng — Dịch vụ không giới hạn theo tồn
    st.markdown("**Số lượng:**")
    sl_max = 99999 if is_dich_vu else max(1, line["ton_kho"])
    new_sl = st.number_input(
        "Số lượng", min_value=1, max_value=sl_max,
        value=line["so_luong"], step=1, key=f"dlg_sl_{line['ma_hang']}",
        label_visibility="collapsed"
    )

    # Đơn giá
    st.markdown("**Đơn giá:**")
    new_dg = st.number_input(
        "Đơn giá", min_value=0, value=line["don_gia"], step=10000,
        key=f"dlg_dg_{line['ma_hang']}", label_visibility="collapsed"
    )
    if new_dg > 0:
        st.caption(f"= {fmt_vnd(new_dg)}")

    # Giảm giá — toggle %/tiền
    st.markdown("**Giảm giá:**")
    gg_mode = st.radio(
        "Loại giảm giá",
        ["Số tiền", "Phần %"],
        horizontal=True,
        key=f"dlg_gg_mode_{line['ma_hang']}",
        label_visibility="collapsed",
    )

    if gg_mode == "Số tiền":
        new_gg = st.number_input(
            "Giảm (đ)", min_value=0,
            max_value=new_sl * new_dg,
            value=line["giam_gia_dong"], step=10000,
            key=f"dlg_gg_tien_{line['ma_hang']}",
            label_visibility="collapsed"
        )
        if new_gg > 0:
            st.caption(f"= {fmt_vnd(new_gg)}")
    else:
        gg_pct = st.number_input(
            "Giảm (%)", min_value=0, max_value=100,
            value=0, step=1,
            key=f"dlg_gg_pct_{line['ma_hang']}",
            label_visibility="collapsed"
        )
        new_gg = int(new_sl * new_dg * gg_pct / 100)
        if gg_pct > 0:
            st.caption(f"= {fmt_vnd(new_gg)}")

    # Thành tiền dự kiến
    thanh_tien_moi = max(0, new_sl * new_dg - new_gg)
    st.markdown("---")
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<span style='font-size:0.95rem;color:#555;'>Thành tiền:</span>"
        f"<span style='font-size:1.2rem;font-weight:700;color:#e63946;'>"
        f"{fmt_vnd(thanh_tien_moi)}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("💾 LƯU", type="primary", use_container_width=True,
                     key=f"dlg_save_{line['ma_hang']}"):
            _update_cart_line(line["ma_hang"], int(new_sl), int(new_dg), int(new_gg))
            st.rerun()
    with col_cancel:
        if st.button("HỦY", use_container_width=True,
                     key=f"dlg_cancel_{line['ma_hang']}"):
            st.rerun()


# ════════════════════════════════════════════════════════════════
# MODAL — Xác nhận xóa hết giỏ
# ════════════════════════════════════════════════════════════════

@st.dialog("Xóa hết giỏ?")
def _dialog_clear_cart():
    n = len(_get_cart())
    st.markdown(
        f"<div style='font-size:1rem;color:#1a1a2e;margin-bottom:10px;'>"
        f"Bạn sẽ xóa <b>{n} sản phẩm</b> khỏi giỏ. Tiếp tục?</div>",
        unsafe_allow_html=True
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✓ Xóa hết", type="primary", use_container_width=True,
                     key="dlg_clear_confirm"):
            _clear_cart()
            st.rerun()
    with col2:
        if st.button("Hủy", use_container_width=True, key="dlg_clear_cancel"):
            st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Search section
# ════════════════════════════════════════════════════════════════

def _inject_mobile_cart_css(zone_key: str):
    """CSS scoped theo container để giữ layout giỏ hàng ổn định trên mobile."""
    css = """
    <style>
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: stretch !important;
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
        gap: 8px !important;
    }
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        min-width: 0 !important;
    }
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
        flex: 0 0 52px !important;
        width: 52px !important;
        max-width: 52px !important;
    }
    .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child {
        flex: 1 1 auto !important;
    }
    @media (max-width: 640px) {
        .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] {
            gap: 6px !important;
        }
        .st-key-__ZONE_KEY__ div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
            flex: 0 0 46px !important;
            width: 46px !important;
            max-width: 46px !important;
        }
    }
    </style>
    """
    st.markdown(css.replace("__ZONE_KEY__", zone_key), unsafe_allow_html=True)


def _render_search_section():
    """Search expander mở sẵn, max 3 kết quả."""
    chi_nhanh = get_active_branch()
    hh_list = load_hang_hoa_pos(chi_nhanh)

    cart = _get_cart()
    # Khi giỏ có hàng → expander tự thu lại để thấy giỏ rõ hơn
    expand_default = len(cart) == 0

    with st.expander("🔍 Tìm hàng hóa", expanded=expand_default):
        # Reset key counter để clear input sau khi thêm
        rk = st.session_state.get("pos_search_reset_cnt", 0)
        keyword = st.text_input(
            "Search input",
            placeholder="Gõ mã hoặc tên hàng...",
            key=f"pos_search_kw_{rk}",
            label_visibility="collapsed",
        )

        if not keyword.strip():
            if not hh_list:
                st.caption("⚠ Chưa có hàng hóa active có giá > 0 trong hệ thống.")
            else:
                st.caption(f"📦 {len(hh_list)} sản phẩm — gõ để tìm")
            return

        results = _search_hang_hoa(keyword, hh_list, max_results=3)

        if not results:
            st.caption("Không tìm thấy sản phẩm.")
            return

        for hh in results:
            _render_search_result_card(hh)


def _render_search_result_card(hh: dict):
    """1 card kết quả search — bấm để thêm vào giỏ (hoặc xám nếu hết hàng)."""
    is_dich_vu = hh.get("loai_sp") == "Dịch vụ"
    # Dịch vụ không bao giờ hết — chỉ hàng hóa mới có thể out of stock
    is_out_of_stock = (not is_dich_vu) and (hh["ton"] == 0)

    if is_out_of_stock:
        st.markdown(
            f"<div style='background:#f4f4f4;border:1px solid #e0e0e0;"
            f"border-radius:10px;padding:10px 12px;margin:6px 0;opacity:0.6;'>"
            f"<div style='font-weight:600;color:#888;'>{hh['ten_hang']}</div>"
            f"<div style='font-family:monospace;font-size:0.78rem;color:#aaa;'>"
            f"{hh['ma_hang']} · <b>Hết hàng</b></div>"
            f"<div style='font-size:0.85rem;color:#aaa;margin-top:2px;'>"
            f"{fmt_vnd(hh['gia_ban'])}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
        return

    # Còn hàng (hoặc dịch vụ) → button thêm vào giỏ
    if is_dich_vu:
        info_line = f"{hh['ma_hang']} · 🛠 Dịch vụ · {fmt_vnd(hh['gia_ban'])}"
    else:
        info_line = f"{hh['ma_hang']} · Tồn: {hh['ton']} · {fmt_vnd(hh['gia_ban'])}"

    btn_label = f"{hh['ten_hang']}\n{info_line}"
    if st.button(
        btn_label,
        key=f"pos_add_{hh['ma_hang']}",
        use_container_width=True,
    ):
        _add_to_cart(hh)
        # Reset search input để gõ tìm hàng tiếp theo
        st.session_state["pos_search_reset_cnt"] = \
            st.session_state.get("pos_search_reset_cnt", 0) + 1
        st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Cart section
# ════════════════════════════════════════════════════════════════

def _render_cart_section():
    cart = _get_cart()

    # Header giỏ + nút xóa hết
    col_h, col_clear = st.columns([3, 1])
    with col_h:
        st.markdown(
            f"<div style='font-size:1rem;font-weight:700;color:#1a1a2e;"
            f"padding-top:6px;'>🛒 Giỏ hàng ({len(cart)})</div>",
            unsafe_allow_html=True
        )
    with col_clear:
        if cart:
            if st.button("🗑 Xóa hết", key="pos_clear_cart_btn",
                         use_container_width=True):
                _dialog_clear_cart()

    if not cart:
        st.markdown(
            "<div style='background:#fafafa;border:1px dashed #ddd;"
            "border-radius:10px;padding:24px 16px;text-align:center;"
            "color:#999;margin:8px 0;'>"
            "Giỏ hàng trống<br>"
            "<span style='font-size:0.82rem;'>Tìm và thêm sản phẩm ở trên</span>"
            "</div>",
            unsafe_allow_html=True
        )
        return

    # Render từng dòng
    for line in cart:
        _render_cart_line(line)


def _render_cart_line(line: dict):
    """1 dòng trong giỏ — bấm vào card → mở dialog sửa SL/giá/giảm giá."""
    thanh_tien = _calc_thanh_tien(line)
    has_giam = line["giam_gia_dong"] > 0

    col_info, col_x = st.columns([6, 1])

    with col_info:
        # Button label đa dòng — Streamlit hiển thị xuống dòng được
        suffix = f" (giảm {fmt_vnd(line['giam_gia_dong'])})" if has_giam else ""
        if st.button(
            f"{line['ten_hang']}\n"
            f"SL: {line['so_luong']}  ·  Đơn giá: {fmt_vnd(line['don_gia'])}\n"
            f"Thành tiền: {fmt_vnd(thanh_tien)}{suffix}",
            key=f"pos_edit_{line['ma_hang']}",
            use_container_width=True,
        ):
            _dialog_sua_dong(line)

    with col_x:
        if st.button("✕", key=f"pos_del_{line['ma_hang']}",
                     use_container_width=True,
                     help="Xóa khỏi giỏ"):
            _remove_from_cart(line["ma_hang"])
            st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Footer (Tạm tính + Tiếp tục)
# ════════════════════════════════════════════════════════════════

def _render_footer():
    cart = _get_cart()
    tam_tinh = _calc_tam_tinh(cart)

    st.markdown("<hr style='margin:14px 0 8px;'>", unsafe_allow_html=True)

    # Tạm tính card
    st.markdown(
        f"<div style='background:#fff;border:1px solid #ffd5d9;border-radius:10px;"
        f"padding:12px 14px;margin-bottom:10px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<span style='font-size:0.92rem;color:#555;'>Tạm tính:</span>"
        f"<span style='font-size:1.3rem;font-weight:700;color:#e63946;'>"
        f"{fmt_vnd(tam_tinh)}</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )

    # Nút tiếp tục
    can_continue = len(cart) > 0
    if st.button(
        "TIẾP TỤC →",
        type="primary",
        use_container_width=True,
        disabled=not can_continue,
        key="pos_continue_btn",
    ):
        # Sang màn 3 — Bước 3 sẽ implement
        st.session_state["pos_step"] = "thanh_toan"
        st.rerun()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_ban_hang():
    """Màn bán hàng chính — search + giỏ hàng + nút tiếp tục."""
    # Phase 2A chưa có màn 3 — nếu user lỡ bấm "Tiếp tục" → reset
    if st.session_state.get("pos_step") == "thanh_toan":
        st.success("✅ Đã sang màn thanh toán — sẽ build ở **Bước 3**.")
        st.markdown(f"**Số sản phẩm trong giỏ:** {len(_get_cart())}")
        st.markdown(f"**Tạm tính:** {fmt_vnd(_calc_tam_tinh(_get_cart()))}")
        if st.button("← Quay lại bán hàng", key="pos_back_from_step3"):
            st.session_state.pop("pos_step", None)
            st.rerun()
        return

    _render_search_section()
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    cart_zone_key = "pos_cart_zone"
    _inject_mobile_cart_css(cart_zone_key)
    with st.container(key=cart_zone_key):
        _render_cart_section()

    _render_footer()
