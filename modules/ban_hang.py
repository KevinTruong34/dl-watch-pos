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
from utils.db import load_hang_hoa_pos, is_open_price_item
from utils.helpers import fmt_vnd


# ════════════════════════════════════════════════════════════════
# CART HELPERS
# ════════════════════════════════════════════════════════════════

CART_KEY = "pos_cart"

# CSS scoped cho cart section — force horizontal layout trên mobile
# Cover 2 zones: header (chứa nút "Xóa hết") và rows (chứa nút "✕")
_CART_ROW_CSS = """
<style>
.st-key-cart-rows-zone div[data-testid="stHorizontalBlock"],
.st-key-cart-header-zone div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 8px !important;
    width: 100% !important;
    align-items: center !important;
}
.st-key-cart-rows-zone div[data-testid="stHorizontalBlock"] > div,
.st-key-cart-header-zone div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;
}
@media (max-width: 640px) {
    .st-key-cart-rows-zone div[data-testid="stHorizontalBlock"],
    .st-key-cart-header-zone div[data-testid="stHorizontalBlock"] {
        gap: 6px !important;
    }
}

/* Cart line — make info button look like a flat row, not a button */
[class*="st-key-pos-edit-"] button {
    background: transparent !important;
    border: none !important;
    text-align: left !important;
    padding: 8px 6px !important;
    min-height: 0 !important;
    box-shadow: none !important;
}
[class*="st-key-pos-edit-"] button:hover {
    background: #fafafa !important;
}
[class*="st-key-pos-edit-"] button p {
    text-align: left !important;
}

/* × delete button — square, light border */
[class*="st-key-pos-del-"] button {
    min-height: 38px !important;
    min-width: 38px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    color: #888 !important;
}

/* Search result card buttons — flat card style */
[class*="st-key-pos-add-"] button {
    text-align: left !important;
    padding: 10px 12px !important;
    background: #fff !important;
    border: 1px solid #eee !important;
    border-radius: 10px !important;
    min-height: 44px !important;
}
[class*="st-key-pos-add-"] button p {
    text-align: left !important;
    margin: 0 !important;
}

/* Search section — frame as card */
.st-key-pos-search-card details {
    background: #fff !important;
    border: 1px solid #ececec !important;
    border-radius: 12px !important;
    padding: 4px 10px !important;
}
.st-key-pos-search-card summary p {
    font-weight: 600 !important;
    color: #1a1a2e !important;
}

/* Cart card frame */
.st-key-pos-cart-card {
    background: #fff;
    border: 1px solid #ececec;
    border-radius: 12px;
    padding: 6px 12px 10px;
}

/* Xóa hết button — red outline compact */
.st-key-cart-header-zone [data-testid="stBaseButton-secondary"] {
    border: 1px solid #ffd0d3 !important;
    color: #e63946 !important;
    min-height: 34px !important;
    padding: 0 8px !important;
    font-size: 0.7em !important;
    line-height: 1.1 !important;
}
.st-key-cart-header-zone [data-testid="stBaseButton-secondary"] p {
    font-size: 0.7em !important;
    line-height: 1.1 !important;
}
/* Reduce top whitespace and vertical gaps for mobile-like UI */
.main .block-container {
    padding-top: 1rem !important;
}
.st-key-pos-search-card,
.st-key-pos-footer-card {
    margin-top: 6px !important;
}

/* Stretch cart background closer to blocks above/below */
.st-key-pos-cart-card {
    margin-top: -18px !important;
    margin-bottom: -18px !important;
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}

/* Footer breakdown card */
.st-key-pos-footer-card {
    background: #fff;
    border: 1px solid #ececec;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
}

/* Hide Streamlit floating helper/menu bubble on mobile */
div[data-testid="stFloatingActionButton"],
button[title="Manage app"],
button[aria-label="Manage app"] {
    display: none !important;
}
</style>
"""


def _get_cart() -> list[dict]:
    return st.session_state.get(CART_KEY, [])


def _save_cart(cart: list[dict]):
    st.session_state[CART_KEY] = cart


def _add_to_cart(item: dict):
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
        "is_open":       bool(item.get("is_open", False)),
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


def _calc_giam_gia_dong(cart: list[dict]) -> int:
    return sum(int(line.get("giam_gia_dong", 0) or 0) for line in cart)


def _clear_cart():
    st.session_state.pop(CART_KEY, None)


# ════════════════════════════════════════════════════════════════
# STEP 3 SNAPSHOT — giữ form thanh toán khi quay lại sửa giỏ
# ════════════════════════════════════════════════════════════════

# Tất cả keys ở màn thanh toán cần lưu/restore
_STEP3_KEYS = [
    "pos3_kh_data", "pos3_last_lookup_sdt", "pos3_lookup_result",
    "pos3_khach_le", "pos3_sdt_input", "pos3_ten_moi",
    "pos3_gg_mode", "pos3_gg_tien", "pos3_gg_pct",
    "pos3_chia_nhieu", "pos3_pttt_radio",
    "pos3_tm", "pos3_ck", "pos3_the",
]
SNAPSHOT_KEY = "pos_step3_snapshot"


def _save_step3_snapshot():
    """Snapshot form thanh toán trước khi NV bấm ← rời màn."""
    snap = {}
    for k in _STEP3_KEYS:
        if k in st.session_state:
            snap[k] = st.session_state[k]
    st.session_state[SNAPSHOT_KEY] = snap


def _restore_step3_snapshot():
    """Khôi phục form thanh toán khi NV quay lại."""
    snap = st.session_state.pop(SNAPSHOT_KEY, None)
    if not snap:
        return
    for k, v in snap.items():
        st.session_state[k] = v


# ════════════════════════════════════════════════════════════════
# SEARCH LOGIC
# ════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Bỏ space/dash để fuzzy match: 'F 94' khớp 'F94'."""
    import re
    return re.sub(r"[\s\-_./]", "", str(text or "")).lower()


def _search_hang_hoa(keyword: str, hh_list: list[dict],
                     max_results: int = 3) -> list[dict]:
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
    is_dich_vu = line.get("loai_sp") == "Dịch vụ"
    is_open    = bool(line.get("is_open", False))

    if is_open:
        ton_label = "✏️ Giá tự nhập"
    elif is_dich_vu:
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

    st.markdown("**Số lượng:**")
    # Defensive: nếu so_luong > ton_kho (legacy data hoặc scan add quá nhanh),
    # max_value phải bao trùm value hiện tại để không crash StreamlitValueAboveMaxError.
    sl_max = 99999 if (is_dich_vu or is_open) else max(line["so_luong"], line["ton_kho"], 1)
    with st.container(key=f"numkb-dlg-sl-{line['ma_hang']}"):
        new_sl = st.number_input(
            "Số lượng", min_value=1, max_value=sl_max,
            value=line["so_luong"], step=1, key=f"dlg_sl_{line['ma_hang']}",
            label_visibility="collapsed"
        )

    st.markdown("**Đơn giá:**")
    with st.container(key=f"numkb-dlg-dg-{line['ma_hang']}"):
        new_dg = st.number_input(
            "Đơn giá", min_value=0, value=line["don_gia"], step=10000,
            key=f"dlg_dg_{line['ma_hang']}", label_visibility="collapsed",
            disabled=not is_open,
        )
    if new_dg > 0:
        st.caption(f"= {fmt_vnd(new_dg)}")
    if not is_open:
        st.caption("🔒 Đơn giá cố định — chỉ SP nhóm 'Sản phẩm khác' / DVPS được sửa.")

    st.markdown("**Giảm giá:**")
    gg_mode = st.radio(
        "Loại giảm giá",
        ["Số tiền", "Phần %"],
        horizontal=True,
        key=f"dlg_gg_mode_{line['ma_hang']}",
        label_visibility="collapsed",
    )

    if gg_mode == "Số tiền":
        with st.container(key=f"numkb-dlg-gg-tien-{line['ma_hang']}"):
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
        with st.container(key=f"numkb-dlg-gg-pct-{line['ma_hang']}"):
            gg_pct = st.number_input(
                "Giảm (%)", min_value=0, max_value=100,
                value=0, step=1,
                key=f"dlg_gg_pct_{line['ma_hang']}",
                label_visibility="collapsed"
            )
        new_gg = int(new_sl * new_dg * gg_pct / 100)
        if gg_pct > 0:
            st.caption(f"= {fmt_vnd(new_gg)}")

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
# DIALOG — Quét mã vạch (one-shot, dialog auto-close sau scan thành công)
# ════════════════════════════════════════════════════════════════

@st.dialog("📷 Quét mã vạch")
def _dialog_quet_ma_vach(chi_nhanh: str):
    """Live scan barcode trong dialog. One-shot: quét 1 cái → add vào giỏ
    → dialog đóng. Muốn quét tiếp user bấm icon 📷 lại.

    Camera CHỈ mount khi dialog open (vs expander luôn render trong DOM →
    fix: không xin permission lặp lại mỗi lần load trang Bán hàng).
    """
    from utils.scanner_component import live_scanner
    from utils.barcode import lookup_hang_by_ma_vach

    st.caption("Chĩa camera vào tem mã vạch — app tự nhận diện rồi đóng")

    scan = live_scanner(key="scan_ban_hang_dialog")
    if not scan or not isinstance(scan, dict):
        return

    code = (scan.get("code") or "").strip()
    if not code:
        return

    # Dedup ts — component v2 có thể trigger nhiều lần cùng scan trong
    # cùng 1 dialog session. Chỉ process scan đầu tiên.
    last_ts = st.session_state.get("_scan_dialog_last_ts")
    if last_ts == scan.get("ts"):
        return
    st.session_state["_scan_dialog_last_ts"] = scan.get("ts")

    # Lookup ma_vach → hang_hoa + tồn
    result = lookup_hang_by_ma_vach(code, chi_nhanh)

    if not result["ok"]:
        err = result.get("error")
        if err == "not_found":
            st.warning(f"⚠️ Không tìm thấy SP có mã vạch `{code}`")
        elif err == "duplicate":
            st.error(
                f"❌ Nhiều SP cùng mã vạch — báo admin: "
                f"{result.get('ma_hang_list')}"
            )
        elif err == "empty":
            pass
        else:
            st.error(f"❌ Lỗi: {err} {result.get('detail', '')}")
        # Dialog stay open để user thấy error + quét tem khác
        return

    item = result["item"]

    # Gate hàng hóa hết hàng (consistent với _render_search_result_card)
    is_out = (
        item["loai_sp"] != "Dịch vụ"
        and not item["is_open"]
        and item["ton"] == 0
    )
    if is_out:
        st.warning(
            f"⚠️ **{item['ten_hang']}** đã hết hàng — không thể thêm vào giỏ"
        )
        # Dialog stay open
        return

    # Chặn vượt tồn: nếu SP không phải dịch vụ/open-price và SL trong giỏ
    # đã = tồn → không thể add thêm.
    if item["loai_sp"] != "Dịch vụ" and not item["is_open"]:
        existing_qty = next(
            (line["so_luong"] for line in _get_cart()
             if line["ma_hang"] == item["ma_hang"]),
            0,
        )
        if existing_qty + 1 > item["ton"]:
            st.warning(
                f"⚠️ **{item['ten_hang']}** — giỏ đã có {existing_qty}, "
                f"tồn chỉ còn {item['ton']}. Không thể thêm."
            )
            # Dialog stay open
            return

    # Add cart + pending toast + close dialog
    _add_to_cart(item)
    st.session_state["_scan_pending_toast"] = item["ten_hang"]
    st.rerun()  # rerun = close dialog + render toast ngoài


# ════════════════════════════════════════════════════════════════
# RENDER — Search section
# ════════════════════════════════════════════════════════════════

def _render_search_section():
    chi_nhanh = get_active_branch()
    hh_list = load_hang_hoa_pos(chi_nhanh)

    cart = _get_cart()
    expand_default = len(cart) == 0

    # Toast confirm sau khi scan dialog đóng + cart updated (rerun từ st.rerun
    # trong _dialog_quet_ma_vach). Pop để không re-toast ở lần render sau.
    _pending = st.session_state.pop("_scan_pending_toast", None)
    if _pending:
        st.toast(f"✅ Đã thêm: {_pending}", icon="🛒")

    with st.container(key="pos-search-card"):
        with st.expander("🔍   Tìm hàng hóa", expanded=expand_default):
            rk = st.session_state.get("pos_search_reset_cnt", 0)
            # 2-col: search input | icon 📷 mở dialog quét mã vạch.
            # Scan button khóa cứng 48×48px qua CSS (touch target tối thiểu),
            # KHÔNG stretch theo column. Column tỉ lệ rộng để search có chỗ.
            # Force horizontal flex — Streamlit mặc định stack columns trên
            # màn hẹp khi không có hint horizontal.
            st.markdown(
                """<style>
                .st-key-pos-search-row div[data-testid="stHorizontalBlock"] {
                    flex-direction: row !important;
                    flex-wrap: nowrap !important;
                    gap: 8px !important;
                    align-items: center !important;
                }
                .st-key-pos-search-row div[data-testid="stHorizontalBlock"] > div {
                    min-width: 0 !important;
                }
                .st-key-pos-scan-btn-wrap [data-testid="stBaseButton-secondary"] {
                    width: 48px !important;
                    min-width: 48px !important;
                    max-width: 48px !important;
                    height: 48px !important;
                    padding: 0 !important;
                    font-size: 1.2rem !important;
                }
                </style>""",
                unsafe_allow_html=True,
            )
            with st.container(key="pos-search-row"):
                c_input, c_scan = st.columns([5, 1])
                with c_input:
                    keyword = st.text_input(
                        "Search input",
                        placeholder="Gõ mã hoặc tên hàng...",
                        key=f"pos_search_kw_{rk}",
                        label_visibility="collapsed",
                    )
                with c_scan:
                    with st.container(key="pos-scan-btn-wrap"):
                        if st.button("📷", key="pos_scan_btn",
                                     help="Quét mã vạch"):
                            _dialog_quet_ma_vach(chi_nhanh)

            if not keyword.strip():
                if not hh_list:
                    st.markdown(
                        "<div style='background:#fff8e0;border:1px solid #f0c36d;"
                        "border-radius:8px;padding:10px 12px;margin:8px 0;"
                        "font-size:0.85rem;color:#856404;'>"
                        "⚠️ Không tải được danh sách hàng hóa. "
                        "Kiểm tra kết nối mạng rồi thử lại."
                        "</div>",
                        unsafe_allow_html=True
                    )
                else:
                    return

            results = _search_hang_hoa(keyword, hh_list, max_results=3)

            if not results:
                st.caption("Không tìm thấy sản phẩm.")
                return

            for hh in results:
                _render_search_result_card(hh)


def _render_search_result_card(hh: dict):
    is_dich_vu = hh.get("loai_sp") == "Dịch vụ"
    is_open    = bool(hh.get("is_open", False))
    is_out_of_stock = (not is_dich_vu) and (not is_open) and (hh["ton"] == 0)

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

    if is_open:
        gia_text = "giá tự nhập" if hh.get("gia_ban", 0) == 0 else fmt_vnd(hh["gia_ban"])
        icon = "🛠" if is_dich_vu else "📦"
        info_line = (
            f"{icon}✏️ **{hh['ten_hang']}** · **{hh['ma_hang']}** · _{gia_text}_"
        )
    elif is_dich_vu:
        info_line = (
            f"🛠 Dịch vụ · **{hh['ten_hang']}** · **{hh['ma_hang']}** · {fmt_vnd(hh['gia_ban'])}"
        )
    else:
        info_line = (
            f"📦 Hàng hóa · **{hh['ten_hang']}** · **{hh['ma_hang']}** · {fmt_vnd(hh['gia_ban'])}"
        )

    btn_label = info_line
    if st.button(
        btn_label,
        key=f"pos_add_{hh['ma_hang']}",
        use_container_width=True,
    ):
        _add_to_cart(hh)
        st.session_state["pos_search_reset_cnt"] = \
            st.session_state.get("pos_search_reset_cnt", 0) + 1
        st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Cart section
# ════════════════════════════════════════════════════════════════

def _render_cart_section():
    cart = _get_cart()

    st.markdown(_CART_ROW_CSS, unsafe_allow_html=True)

    with st.container(key="pos-cart-card"):
        with st.container(key="cart-header-zone"):
            col_h, col_clear = st.columns([4, 1])
            with col_h:
                st.markdown(
                    f"<div style='font-size:1rem;font-weight:700;color:#1a1a2e;"
                    f"padding-top:6px;'>🛒 Giỏ hàng ({len(cart)})</div>",
                    unsafe_allow_html=True
                )
            with col_clear:
                if cart:
                    if st.button("🗑  Xóa hết", key="pos_clear_cart_btn"):
                        _dialog_clear_cart()

        if not cart:
            st.markdown(
                "<div style='background:#fafafa;border:1px dashed #ddd;"
                "border-radius:10px;padding:24px 16px;text-align:center;"
                "color:#999;margin:8px 0 4px;'>"
                "Giỏ hàng trống<br>"
                "<span style='font-size:0.82rem;'>Tìm và thêm sản phẩm ở trên</span>"
                "</div>",
                unsafe_allow_html=True
            )
            return

        with st.container(key="cart-rows-zone"):
            for i, line in enumerate(cart):
                _render_cart_line(line)
                if i < len(cart) - 1:
                    st.markdown(
                        "<hr style='border:none;border-top:1px solid #f0f0f0;"
                        "margin:2px 0;'>",
                        unsafe_allow_html=True,
                    )


def _render_cart_line(line: dict):
    thanh_tien = _calc_thanh_tien(line)
    has_giam = line["giam_gia_dong"] > 0
    col_info, col_x = st.columns([6, 1])


    with col_info:
        suffix = f"  ·  giảm {fmt_vnd(line['giam_gia_dong'])}" if has_giam else ""
        if st.button(
            f"**{line['ten_hang']}**\n\n"
            f"Mã: {line['ma_hang']}\n\n"
            f"SL: {line['so_luong']} × {fmt_vnd(line['don_gia'])}{suffix}",
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
    giam_gia_dong = _calc_giam_gia_dong(cart)
    n_items = len(cart)
    giam_gia = giam_gia_dong
    tong_cong = max(0, tam_tinh - giam_gia)

    st.markdown(
        """<style>
        [class*="st-key-pos-footer-sticky"] {
            position: sticky;
            bottom: 0;
            z-index: 30;
            background: transparent;
            padding: 14px 0 calc(22px + env(safe-area-inset-bottom));
            margin-top: 8px;
        }
        [class*="st-key-pos-footer-sticky"] [data-testid="stBaseButton-primary"] {
            min-height: 56px !important;
            font-size: 1.02rem !important;
            letter-spacing: 0.3px !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="pos-footer-sticky"):
        with st.container(key="pos-footer-card"):
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;padding:4px 0;'>"
                f"<span style='font-size:0.95rem;color:#666;'>"
                f"Tạm tính ({n_items} sản phẩm)</span>"
                f"<span style='font-size:1.15rem;font-weight:700;color:#e63946;'>"
                f"{fmt_vnd(tam_tinh)}</span>"
                f"</div>"
                f"<hr style='border:none;border-top:1px dashed #e8e8e8;margin:6px 0;'>"
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;padding:4px 0;'>"
                f"<span style='font-size:0.95rem;color:#666;'>Giảm giá</span>"
                f"<span style='font-size:1.05rem;color:#888;'>"
                f"{fmt_vnd(giam_gia)}</span>"
                f"</div>"
                f"<hr style='border:none;border-top:1px dashed #e8e8e8;margin:6px 0;'>"
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;padding:6px 0 2px;'>"
                f"<span style='font-size:1rem;font-weight:700;color:#1a1a2e;'>"
                f"Tổng cộng</span>"
                f"<span style='font-size:1.4rem;font-weight:800;color:#e63946;'>"
                f"{fmt_vnd(tam_tinh)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        overstock = [
            line for line in cart
            if line.get("loai_sp") != "Dịch vụ"
            and not line.get("is_open")
            and line["so_luong"] > line.get("ton_kho", 0)
        ]
        if overstock:
            lines_html = "".join(
                f"<li><b>{line['ten_hang']}</b> — SL {line['so_luong']} "
                f"vượt tồn {line.get('ton_kho', 0)}</li>"
                for line in overstock
            )
            st.markdown(
                f"<div style='background:#fff1f2;border:1px solid #fca5a5;"
                f"border-radius:8px;padding:10px 12px;margin:8px 0;"
                f"color:#991b1b;font-size:0.9rem;'>"
                f"⚠️ <b>Không thể tiếp tục</b> — giỏ có hàng vượt tồn:"
                f"<ul style='margin:6px 0 0 18px;'>{lines_html}</ul>"
                f"<div style='margin-top:6px;'>Bấm vào dòng giỏ để giảm SL.</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        can_continue = len(cart) > 0 and not overstock
        if st.button(
            "💳   TIẾP TỤC THANH TOÁN   ›",
            type="primary",
            use_container_width=True,
            disabled=not can_continue,
            key="pos_continue_btn",
        ):
            # Restore form thanh toán nếu NV đã từng vào và quay ra
            _restore_step3_snapshot()
            st.session_state["pos_step"] = "thanh_toan"
            st.rerun()


# ════════════════════════════════════════════════════════════════
# MÀN 3 — THANH TOÁN
# ════════════════════════════════════════════════════════════════

def _render_man_thanh_toan():
    cart = _get_cart()
    if not cart:
        st.session_state.pop("pos_step", None)
        st.rerun()
        return

    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("←", key="pos3_back",
                     use_container_width=True,
                     help="Quay lại bán hàng"):
            # Snapshot toàn bộ form thanh toán trước khi rời màn
            _save_step3_snapshot()
            st.session_state.pop("pos_step", None)
            st.rerun()
    with col_title:
        st.markdown(
            "<div style='font-size:1.1rem;font-weight:700;color:#1a1a2e;"
            "padding-top:10px;'>💰 Thanh toán</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
    st.markdown(
        """<style>
        [class*="st-key-pos3-section-"] {
            background: #fff;
            border: 1px solid #ececec;
            border-radius: 12px;
            padding: 10px 12px 12px;
            margin: 8px 0;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    with st.container(key="pos3-section-kh-review"):
        _render_section_khach_hang_review()

    tam_tinh = _calc_tam_tinh(cart)

    with st.container(key="pos3-section-tom-tat"):
        _render_section_tom_tat(cart, tam_tinh)
    with st.container(key="pos3-section-giam-gia"):
        giam_gia_don = _render_section_giam_gia(tam_tinh)

    khach_can_tra = max(0, tam_tinh - giam_gia_don)

    with st.container(key="pos3-section-pttt"):
        pttt = _render_section_pttt(khach_can_tra)

    _render_footer_thanh_toan(cart, giam_gia_don, khach_can_tra, pttt)


def _render_section_khach_hang_review():
    """Read-only review KH ở màn thanh toán. Data nhập ở màn 1 qua
    `_render_section_khach_hang` (key pos3_*). Nếu rỗng → warning user
    quay lại màn 1 (validation ở footer cũng sẽ chặn submit).
    """
    is_khach_le = bool(st.session_state.get("pos3_khach_le", False))
    kh_data     = st.session_state.get("pos3_kh_data", {}) or {}

    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:6px 0 8px;'>👤 KHÁCH HÀNG</div>",
        unsafe_allow_html=True
    )

    if is_khach_le:
        st.markdown(
            "<div style='padding:4px 0;font-size:0.92rem;color:#1a1a2e;'>"
            "Khách lẻ <span style='color:#888;font-size:0.85rem;'>"
            "— không cần SĐT</span></div>",
            unsafe_allow_html=True,
        )
        return

    sdt    = (kh_data.get("sdt") or "").strip()
    ten_kh = (kh_data.get("ten_kh") or "").strip()
    is_new = bool(kh_data.get("is_new"))

    if not sdt:
        st.markdown(
            "<div style='background:#fff1f2;border:1px solid #fca5a5;"
            "border-radius:8px;padding:8px 12px;color:#991b1b;"
            "font-size:0.88rem;'>⚠️ Chưa nhập thông tin khách hàng — "
            "bấm ← quay lại nhập SĐT hoặc tick \"Khách lẻ\".</div>",
            unsafe_allow_html=True,
        )
        return

    badge = " <span style='background:#fff3cd;color:#856404;font-size:0.72rem;" \
            "padding:1px 6px;border-radius:6px;margin-left:6px;'>" \
            "Khách mới</span>" if is_new else ""
    st.markdown(
        f"<div style='padding:4px 0;font-size:0.92rem;color:#1a1a2e;'>"
        f"<b>{ten_kh or '(chưa có tên)'}</b>{badge}"
        f"<div style='font-size:0.85rem;color:#666;'>SĐT: {sdt}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_section_khach_hang():
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:6px 0 8px;'>👤 KHÁCH HÀNG</div>",
        unsafe_allow_html=True
    )

    is_khach_le = st.checkbox(
        "Khách lẻ (không cần SĐT)",
        key="pos3_khach_le",
        value=False,
    )

    if is_khach_le:
        st.session_state["pos3_kh_data"] = {
            "ma_kh":  None,
            "ten_kh": "Khách lẻ",
            "sdt":    "",
            "is_new": False,
        }
        return

    with st.container(key="numkb-tel-pos3-sdt"):
        sdt = st.text_input(
            "Số điện thoại:",
            placeholder="0xxx xxx xxx",
            key="pos3_sdt_input",
            max_chars=15,
        )

    from utils.db import clean_phone
    sdt_clean = clean_phone(sdt)

    if not sdt_clean:
        st.session_state["pos3_kh_data"] = {
            "ma_kh":  None,
            "ten_kh": "",
            "sdt":    "",
            "is_new": False,
        }
        return

    last_lookup = st.session_state.get("pos3_last_lookup_sdt", "")
    if sdt_clean != last_lookup:
        from utils.db import lookup_khach_hang_by_sdt
        kh = lookup_khach_hang_by_sdt(sdt_clean)
        st.session_state["pos3_last_lookup_sdt"] = sdt_clean
        st.session_state["pos3_lookup_result"]   = kh

    kh = st.session_state.get("pos3_lookup_result")

    if kh:
        st.success(f"✓ {kh['ten_kh']}")
        st.session_state["pos3_kh_data"] = {
            "ma_kh":  kh.get("ma_kh"),
            "ten_kh": kh.get("ten_kh", ""),
            "sdt":    sdt_clean,
            "is_new": False,
        }
    else:
        st.caption("⚠️ SĐT chưa có — sẽ tạo khách mới khi xác nhận")
        ten_moi = st.text_input(
            "Tên khách:",
            placeholder="Nhập tên khách hàng",
            key="pos3_ten_moi",
        )
        st.session_state["pos3_kh_data"] = {
            "ma_kh":  None,
            "ten_kh": (ten_moi or "").strip(),
            "sdt":    sdt_clean,
            "is_new": True,
        }


def _render_section_tom_tat(cart: list[dict], tam_tinh: int):
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:14px 0 6px;'>🛒 TÓM TẮT GIỎ</div>",
        unsafe_allow_html=True
    )

    items_html = ""
    for line in cart:
        sl = line["so_luong"]
        thanh_tien = _calc_thanh_tien(line)
        items_html += (
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:0.88rem;padding:3px 0;'>"
            f"<div style='flex:1;color:#1a1a2e;'>{line['ten_hang']} "
            f"<span style='color:#888;'>×{sl}</span></div>"
            f"<div style='color:#1a1a2e;font-weight:600;white-space:nowrap;'>"
            f"{fmt_vnd(thanh_tien)}</div>"
            f"</div>"
        )

    st.markdown(
        f"<div style='background:#fff;border:1px solid #e8e8e8;"
        f"border-radius:10px;padding:10px 12px;'>"
        f"{items_html}"
        f"<hr style='border:none;border-top:1px dashed #ddd;margin:6px 0;'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:0.92rem;'>"
        f"<span style='color:#555;'>Tạm tính:</span>"
        f"<span style='font-weight:700;color:#1a1a2e;'>{fmt_vnd(tam_tinh)}</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )


def _render_section_giam_gia(tam_tinh: int) -> int:
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:14px 0 6px;'>🏷️ GIẢM GIÁ TỔNG ĐƠN</div>",
        unsafe_allow_html=True
    )

    gg_mode = st.radio(
        "Loại giảm giá tổng đơn",
        ["Số tiền", "Phần %"],
        horizontal=True,
        key="pos3_gg_mode",
        label_visibility="collapsed",
    )

    if gg_mode == "Số tiền":
        with st.container(key="numkb-pos3-gg-tien"):
            gg = st.number_input(
                "Giảm (đ)", min_value=0, max_value=tam_tinh,
                value=0, step=10000,
                key="pos3_gg_tien",
                label_visibility="collapsed"
            )
        if gg > 0:
            st.caption(f"= {fmt_vnd(gg)}")
        return int(gg)
    else:
        with st.container(key="numkb-pos3-gg-pct"):
            pct = st.number_input(
                "Giảm (%)", min_value=0, max_value=100,
                value=0, step=1,
                key="pos3_gg_pct",
                label_visibility="collapsed"
            )
        gg = int(tam_tinh * pct / 100)
        if pct > 0:
            st.caption(f"= {fmt_vnd(gg)}")
        return gg


def _render_section_pttt(khach_can_tra: int) -> dict:
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:14px 0 6px;'>💳 PHƯƠNG THỨC THANH TOÁN</div>",
        unsafe_allow_html=True
    )

    chia_nhieu = st.checkbox(
        "Chia nhiều phương thức",
        key="pos3_chia_nhieu",
        value=False,
    )

    if not chia_nhieu:
        st.markdown(
            """<style>
            .st-key-pos3-pttt-radio [role="radiogroup"] {
                gap: 8px !important;
                flex-wrap: nowrap !important;
            }
            .st-key-pos3-pttt-radio [role="radiogroup"] > label {
                margin-right: 4px !important;
            }
            .st-key-pos3-pttt-radio [role="radiogroup"] p {
                font-weight: 700 !important;
                font-size: 0.9rem !important;
                white-space: nowrap !important;
            }
            </style>""",
            unsafe_allow_html=True,
        )
        with st.container(key="pos3-pttt-radio"):
            pttt_chon = st.radio(
                "PTTT",
                ["Tiền mặt", "Chuyển khoản", "Thẻ"],
                key="pos3_pttt_radio",
                horizontal=True,
                label_visibility="collapsed",
            )

        return {
            "tien_mat":     khach_can_tra if pttt_chon == "Tiền mặt" else 0,
            "chuyen_khoan": khach_can_tra if pttt_chon == "Chuyển khoản" else 0,
            "the":          khach_can_tra if pttt_chon == "Thẻ" else 0,
        }

    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "💵 Tiền mặt:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-pos3-tm"):
        tm = st.number_input(
            "Tiền mặt", min_value=0, value=0, step=10000,
            key="pos3_tm", label_visibility="collapsed"
        )
    if tm > 0:
        st.caption(f"= {fmt_vnd(tm)}")

    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "🏦 Chuyển khoản:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-pos3-ck"):
        ck = st.number_input(
            "Chuyển khoản", min_value=0, value=0, step=10000,
            key="pos3_ck", label_visibility="collapsed"
        )
    if ck > 0:
        st.caption(f"= {fmt_vnd(ck)}")

    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "💳 Thẻ:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-pos3-the"):
        the = st.number_input(
            "Thẻ", min_value=0, value=0, step=10000,
            key="pos3_the", label_visibility="collapsed"
        )
    if the > 0:
        st.caption(f"= {fmt_vnd(the)}")

    tong_pttt = int(tm) + int(ck) + int(the)
    if tong_pttt > 0 or khach_can_tra > 0:
        lech = tong_pttt - khach_can_tra
        if lech == 0:
            st.success(f"✓ Đủ tiền: {fmt_vnd(tong_pttt)}")
        elif lech > 0:
            st.info(f"Khách trả: {fmt_vnd(tong_pttt)} · "
                    f"Tiền thừa: **{fmt_vnd(lech)}**")
        else:
            st.warning(f"Khách trả: {fmt_vnd(tong_pttt)} · "
                       f"Còn thiếu: **{fmt_vnd(-lech)}**")

    return {"tien_mat": int(tm), "chuyen_khoan": int(ck), "the": int(the)}


def _render_footer_thanh_toan(cart: list[dict], giam_gia_don: int,
                                khach_can_tra: int, pttt: dict):
    st.markdown("<hr style='margin:14px 0 8px;'>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='background:#fff8f8;border:2px solid #e63946;"
        f"border-radius:10px;padding:12px 14px;margin-bottom:12px;'>"
        f"<div style='font-size:0.82rem;color:#888;'>Khách cần trả:</div>"
        f"<div style='font-size:1.5rem;font-weight:700;color:#e63946;'>"
        f"{fmt_vnd(khach_can_tra)}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    # ── Validate trước khi enable nút ──
    is_khach_le = bool(st.session_state.get("pos3_khach_le", False))
    kh_data = st.session_state.get("pos3_kh_data", {})
    tong_pttt = pttt["tien_mat"] + pttt["chuyen_khoan"] + pttt["the"]

    error_msgs = []

    # FIX: bắt buộc 1 trong 2 — tick "Khách lẻ" HOẶC nhập SĐT
    if not is_khach_le:
        sdt_clean = (kh_data.get("sdt") or "").strip()
        if not sdt_clean:
            error_msgs.append("Tick 'Khách lẻ' hoặc nhập SĐT khách")
        elif kh_data.get("is_new") and not kh_data.get("ten_kh"):
            error_msgs.append("Nhập tên khách mới")

    if tong_pttt < khach_can_tra:
        error_msgs.append(f"Cần thêm {fmt_vnd(khach_can_tra - tong_pttt)}")

    can_submit = len(error_msgs) == 0

    if st.button(
        "✓ XÁC NHẬN HÓA ĐƠN",
        type="primary",
        use_container_width=True,
        disabled=not can_submit,
        key="pos3_submit",
        help=" · ".join(error_msgs) if error_msgs else None,
    ):
        _xu_ly_xac_nhan(cart, giam_gia_don, pttt, kh_data)


def _xu_ly_xac_nhan(cart: list[dict], giam_gia_don: int,
                     pttt: dict, kh_data: dict):
    from utils.db import upsert_khach_hang, tao_hoa_don_pos_rpc
    from utils.auth import get_user, get_active_branch

    user      = get_user() or {}
    chi_nhanh = get_active_branch()

    with st.spinner("Đang tạo hóa đơn..."):
        ma_kh = kh_data.get("ma_kh") or None
        if kh_data.get("is_new") and kh_data.get("sdt"):
            new_ma_kh = upsert_khach_hang(
                kh_data.get("ten_kh", ""),
                kh_data.get("sdt", ""),
                chi_nhanh,
            )
            if new_ma_kh:
                ma_kh = new_ma_kh

        items_payload = []
        for line in cart:
            items_payload.append({
                "ma_hang":       line["ma_hang"],
                "ten_hang":      line["ten_hang"],
                "so_luong":      int(line["so_luong"]),
                "don_gia":       int(line["don_gia"]),
                "giam_gia_dong": int(line["giam_gia_dong"]),
            })

        payload = {
            "chi_nhanh":    chi_nhanh,
            "ma_kh":        ma_kh,
            "ten_khach":    kh_data.get("ten_kh", ""),
            "sdt_khach":    kh_data.get("sdt", ""),
            "giam_gia_don": int(giam_gia_don),
            "tien_mat":     int(pttt.get("tien_mat", 0)),
            "chuyen_khoan": int(pttt.get("chuyen_khoan", 0)),
            "the":          int(pttt.get("the", 0)),
            "nguoi_ban":    user.get("ho_ten", ""),
            "nguoi_ban_id": str(user.get("id", "")),
            "items":        items_payload,
        }

        result = tao_hoa_don_pos_rpc(payload)

    if not result.get("ok"):
        st.error(f"Lỗi tạo hóa đơn: {result.get('error', 'Lỗi không xác định')}")
        return

    # ── Auto enqueue print ──
    ma_hd = result.get("ma_hd", "")
    try:
        from utils.print_queue import enqueue_hoa_don
        pr = enqueue_hoa_don(ma_hd, user.get("ho_ten", ""))
        if pr.get("ok"):
            st.toast("Đã gửi lệnh in", icon="🖨")
        else:
            st.toast("HĐ tạo OK · chưa gửi được lệnh in", icon="⚠️")
    except Exception:
        st.toast("HĐ tạo OK · chưa gửi được lệnh in", icon="⚠️")

    st.session_state["pos_last_invoice"] = {
        "ma_hd":         ma_hd,
        "tien_thua":     int(result.get("tien_thua", 0)),
        "khach_can_tra": int(sum(_calc_thanh_tien(l) for l in cart)) - giam_gia_don,
        "ten_khach":     kh_data.get("ten_kh", ""),
        "sdt_khach":     kh_data.get("sdt", ""),
        "items":         items_payload,
        "pttt":          pttt,
    }
    _clear_cart()
    _clear_step3_state()
    st.session_state["pos_step"] = "success"
    from utils.db import load_hang_hoa_pos
    load_hang_hoa_pos.clear()
    st.rerun()


def _clear_step3_state():
    keys = [
        "pos3_kh_data", "pos3_last_lookup_sdt", "pos3_lookup_result",
        "pos3_khach_le", "pos3_sdt_input", "pos3_ten_moi",
        "pos3_gg_mode", "pos3_gg_tien", "pos3_gg_pct",
        "pos3_chia_nhieu", "pos3_pttt_radio", "pos3_pttt_pick",
        "pos3_tm", "pos3_ck", "pos3_the",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    # Cleanup snapshot luôn — đảm bảo HĐ mới không bị nạp data cũ
    st.session_state.pop(SNAPSHOT_KEY, None)


# ════════════════════════════════════════════════════════════════
# MÀN SUCCESS — sau khi tạo HĐ thành công
# ════════════════════════════════════════════════════════════════

def _render_man_success():
    inv = st.session_state.get("pos_last_invoice")
    if not inv:
        st.session_state.pop("pos_step", None)
        st.rerun()
        return

    st.markdown(
        "<div style='text-align:center;padding:20px 0 10px;'>"
        "<div style='font-size:4rem;'>✓</div>"
        "<div style='font-size:1.3rem;font-weight:700;color:#1a7f37;"
        "margin-top:6px;'>Tạo hóa đơn thành công</div>"
        f"<div style='font-size:1rem;font-family:monospace;color:#555;"
        f"margin-top:8px;'>{inv['ma_hd']}</div>"
        "</div>",
        unsafe_allow_html=True
    )

    rows = [
        ("Khách hàng", inv.get("ten_khach") or "Khách lẻ"),
    ]
    if inv.get("sdt_khach"):
        rows.append(("SĐT", inv["sdt_khach"]))
    rows.append(("Khách cần trả", fmt_vnd(inv["khach_can_tra"])))

    pttt = inv.get("pttt", {})
    if pttt.get("tien_mat", 0) > 0:
        rows.append(("💵 Tiền mặt", fmt_vnd(pttt["tien_mat"])))
    if pttt.get("chuyen_khoan", 0) > 0:
        rows.append(("🏦 Chuyển khoản", fmt_vnd(pttt["chuyen_khoan"])))
    if pttt.get("the", 0) > 0:
        rows.append(("💳 Thẻ", fmt_vnd(pttt["the"])))

    summary_html = "<div style='background:#fff;border:1px solid #e8e8e8;" \
                   "border-radius:10px;padding:12px 14px;margin:14px 0;'>"
    for lbl, val in rows:
        summary_html += (
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:4px 0;font-size:0.92rem;'>"
            f"<span style='color:#777;'>{lbl}:</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{val}</span>"
            f"</div>"
        )
    summary_html += "</div>"
    st.markdown(summary_html, unsafe_allow_html=True)

    if inv.get("tien_thua", 0) > 0:
        st.markdown(
            f"<div style='background:#fff8e0;border:2px solid #f0c36d;"
            f"border-radius:10px;padding:12px 14px;margin:10px 0;'>"
            f"<div style='font-size:0.82rem;color:#856404;'>💰 Tiền thừa cần trả lại khách:</div>"
            f"<div style='font-size:1.5rem;font-weight:700;color:#856404;'>"
            f"{fmt_vnd(inv['tien_thua'])}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)

    col_in, col_new = st.columns(2)
    with col_in:
        if st.button("🖨 In lại", use_container_width=True,
                     key="pos_success_print"):
            try:
                from utils.print_queue import enqueue_hoa_don
                from utils.auth import get_user
                user = get_user() or {}
                pr = enqueue_hoa_don(inv["ma_hd"], user.get("ho_ten", ""))
                if pr.get("ok"):
                    st.toast("Đã gửi lệnh in", icon="🖨")
                else:
                    st.toast(f"Lỗi: {pr.get('error', '')}", icon="⚠️")
            except Exception as e:
                st.toast(f"Lỗi: {e}", icon="⚠️")

    with col_new:
        if st.button("➕ Hóa đơn mới", type="primary",
                     use_container_width=True,
                     key="pos_success_new"):
            st.session_state.pop("pos_step", None)
            st.session_state.pop("pos_last_invoice", None)
            st.rerun()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_ban_hang():
    step = st.session_state.get("pos_step")

    if step == "thanh_toan":
        _render_man_thanh_toan()
        return

    if step == "success":
        _render_man_success()
        return

    with st.container(key="pos1-section-khach-hang"):
        _render_section_khach_hang()
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    _render_search_section()
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    _render_cart_section()
    _render_footer()

