"""
Module Đặt hàng theo yêu cầu — Bước 8.

UI flow:
- Tab 1: Danh sách phiếu (filter trạng thái)
- Tab 2: Tạo phiếu mới
- Modal chi tiết phiếu → actions theo trạng thái
  · Chờ đặt  → [→ Chờ lấy] [→ Hoàn thành] [Hủy (admin)]
  · Chờ lấy  → [→ Hoàn thành] [Hủy (admin)]
  · Hoàn thành → hiện HĐ POS link
  · Đã hủy   → readonly
"""

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_active_branch, get_user, is_admin
from utils.db import (
    load_phieu_dat_hang,
    load_hang_hoa_pos,
    lookup_khach_hang_by_sdt,
    tao_phieu_dat_hang_rpc,
    chuyen_cho_lay_rpc,
    hoan_thanh_dat_hang_rpc,
    huy_phieu_dat_hang_rpc,
)
from utils.helpers import fmt_vnd

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# CSS scoped giữ cột ngang trên mobile + reskin cards / filter
_DAT_HANG_CSS = """
<style>
.st-key-dh-pttt-zone div[data-testid="stHorizontalBlock"],
.st-key-dh-coc-pttt-zone div[data-testid="stHorizontalBlock"],
.st-key-dh-actions-zone div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 8px !important;
    width: 100% !important;
}
.st-key-dh-pttt-zone div[data-testid="stHorizontalBlock"] > div,
.st-key-dh-coc-pttt-zone div[data-testid="stHorizontalBlock"] > div,
.st-key-dh-actions-zone div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;
}

/* Filter selectbox — red outline kiểu mockup */
.st-key-dh-filter-zone [data-baseweb="select"] > div {
    border: 1px solid #ffc6ca !important;
    border-radius: 12px !important;
    min-height: 48px !important;
    background: #fff !important;
}
.st-key-dh-filter-zone [data-baseweb="select"] > div:hover {
    border-color: #e63946 !important;
}

/* Caption "N phiếu" */
.dh-count-caption {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #888;
    font-size: 0.88rem;
    margin: 8px 2px 4px;
}
.dh-count-caption b { color: #555; }

/* Card frame */
[class*="st-key-dh-card-"] {
    background: #fff;
    border: 1px solid #ececec;
    border-radius: 14px;
    padding: 12px 12px 10px;
    margin: 10px 0;
}
[class*="st-key-dh-card-cancelled-"] { opacity: 0.78; }

/* Force horizontal columns inside cards */
[class*="st-key-dh-card-"] div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 10px !important;
    align-items: center !important;
    width: 100% !important;
}
[class*="st-key-dh-card-"] div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;
}

/* Click overlay button — flat, full width */
[class*="st-key-dh-cardbtn-"] button {
    background: transparent !important;
    border: none !important;
    padding: 6px 4px !important;
    text-align: left !important;
    min-height: 0 !important;
    box-shadow: none !important;
    color: #888 !important;
    font-size: 0.78rem !important;
}
[class*="st-key-dh-cardbtn-"] button p {
    text-align: left !important;
    margin: 0 !important;
}
[class*="st-key-dh-cardbtn-"] button:hover { background: #fafafa !important; }

/* Empty state */
.dh-empty {
    background: #fafafa;
    border: 1px dashed #ddd;
    border-radius: 12px;
    padding: 28px 16px;
    text-align: center;
    color: #999;
    margin: 10px 0;
}

/* Floating crown FAB (decorative, parity với mockup) */
.dh-fab-crown {
    position: fixed;
    right: 16px;
    bottom: calc(16px + env(safe-area-inset-bottom));
    width: 52px;
    height: 52px;
    border-radius: 14px;
    background: #e63946;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 1.5rem;
    box-shadow: 0 4px 14px rgba(230,57,70,0.35);
    z-index: 25;
    pointer-events: none;
}
</style>
"""

_BADGE_COLOR = {
    "Chờ đặt":    ("#fff8e0", "#856404"),
    "Chờ lấy":    ("#e8f7ee", "#1a7f37"),
    "Hoàn thành": ("#e8f0ff", "#1a4fba"),
    "Đã hủy":     ("#ffe5e5", "#c1121f"),
}


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _fmt_dt(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo as _Z
            dt = dt.replace(tzinfo=_Z("UTC"))
        return dt.astimezone(_TZ_VN).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


def _badge_html(trang_thai: str) -> str:
    bg, fg = _BADGE_COLOR.get(trang_thai, ("#f0f0f0", "#555"))
    return (f"<span style='background:{bg};color:{fg};"
            f"padding:2px 10px;border-radius:6px;"
            f"font-size:0.78rem;font-weight:600;'>{trang_thai}</span>")


def _clear_dat_hang_cache():
    try:
        load_phieu_dat_hang.clear()
    except Exception:
        pass


def _reset_form_tao_moi():
    """Reset toàn bộ form Tạo mới bằng cách tăng counter → tất cả widget re-render."""
    cnt = st.session_state.get("dh_form_reset_cnt", 0) + 1
    st.session_state["dh_form_reset_cnt"] = cnt
    # Clear các state phụ
    for k in ["dh_last_sdt", "dh_kh_result", "dh_confirm_hoan_thanh", "dh_confirm_huy"]:
        st.session_state.pop(k, None)


# ════════════════════════════════════════════════════════════════
# MODAL — Chi tiết phiếu
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết phiếu đặt hàng")
def _dialog_chi_tiet(phieu: dict):
    st.markdown(_DAT_HANG_CSS, unsafe_allow_html=True)

    ma     = phieu.get("ma_phieu", "")
    tt     = phieu.get("trang_thai", "")
    bg, fg = _BADGE_COLOR.get(tt, ("#f0f0f0", "#555"))

    st.markdown(
        f"<div style='font-family:monospace;font-size:1.05rem;font-weight:700;"
        f"color:#1a1a2e;'>{ma}</div>"
        f"<div style='margin-top:4px;'>{_badge_html(tt)}</div>"
        f"<div style='font-size:0.8rem;color:#888;margin-top:4px;'>"
        f"Tạo: {_fmt_dt(phieu.get('created_at',''))}"
        f"{' · NV: ' + phieu['nguoi_tao'] if phieu.get('nguoi_tao') else ''}"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown("<hr style='margin:10px 0 8px;'>", unsafe_allow_html=True)

    # Thông tin khách
    ten_kh = phieu.get("ten_khach") or "Khách lẻ"
    sdt    = phieu.get("sdt_khach") or ""
    st.markdown(
        f"<div style='font-size:0.88rem;color:#555;'>"
        f"<b>Khách:</b> {ten_kh}{' · ' + sdt if sdt else ''}</div>",
        unsafe_allow_html=True
    )

    # Thông tin hàng
    tong_gia = int(phieu.get("don_gia", 0) or 0) * int(phieu.get("so_luong", 1) or 1)
    mo_ta_html = ""
    if phieu.get("mo_ta"):
        mo_ta_html = (f"<br><span style='color:#666;'>"
                      f"{phieu['mo_ta']}</span>")
    st.markdown(
        f"<div style='background:#f7f7fa;border:1px solid #e8e8ee;"
        f"border-radius:8px;padding:10px 12px;margin:10px 0;font-size:0.88rem;'>"
        f"<b>{phieu.get('ten_hang', '')}</b>"
        f"{mo_ta_html}"
        f"<br>SL: {phieu.get('so_luong', 1)} · "
        f"Đơn giá: {fmt_vnd(phieu.get('don_gia', 0))} · "
        f"Tổng: <b>{fmt_vnd(tong_gia)}</b>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Cọc
    tien_coc = int(phieu.get("tien_coc", 0) or 0)
    if tien_coc > 0:
        coc_pttt = []
        if phieu.get("coc_tien_mat", 0):
            coc_pttt.append(f"💵 {fmt_vnd(phieu['coc_tien_mat'])}")
        if phieu.get("coc_chuyen_khoan", 0):
            coc_pttt.append(f"🏦 {fmt_vnd(phieu['coc_chuyen_khoan'])}")
        if phieu.get("coc_the", 0):
            coc_pttt.append(f"💳 {fmt_vnd(phieu['coc_the'])}")
        st.markdown(
            f"<div style='background:#fff8e0;border:1px solid #f0c36d;"
            f"border-radius:8px;padding:8px 12px;font-size:0.85rem;color:#856404;'>"
            f"💰 Đã cọc: <b>{fmt_vnd(tien_coc)}</b>"
            f"{' (' + ' · '.join(coc_pttt) + ')' if coc_pttt else ''}"
            f"<br>Còn lại: <b>{fmt_vnd(tong_gia - tien_coc)}</b>"
            f"</div>",
            unsafe_allow_html=True
        )

    if phieu.get("ghi_chu"):
        st.caption(f"📝 {phieu['ghi_chu']}")

    # Hoàn thành → link HĐ POS
    if tt == "Hoàn thành":
        ma_hd = phieu.get("ma_hd_pos", "")
        st.markdown(
            f"<div style='background:#e8f7ee;border:1px solid #a4d8b4;"
            f"border-radius:8px;padding:8px 12px;margin-top:8px;font-size:0.85rem;'>"
            f"✓ Hoàn thành lúc {_fmt_dt(phieu.get('completed_at',''))}<br>"
            f"HĐ POS: <b style='font-family:monospace;'>{ma_hd}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
        return

    # Đã hủy
    if tt == "Đã hủy":
        cb  = phieu.get("cancelled_by") or ""
        cxl = phieu.get("coc_xu_ly") or ""
        st.markdown(
            f"<div style='font-size:0.78rem;color:#c1121f;margin-top:6px;'>"
            f"Hủy lúc: {_fmt_dt(phieu.get('cancelled_at',''))}"
            f"{' bởi ' + cb if cb else ''}"
            f"{' · ' + cxl if cxl else ''}"
            f"</div>",
            unsafe_allow_html=True
        )
        return

    # ── Actions ──
    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    user = get_user() or {}
    nguoi_ban    = user.get("ho_ten", "")
    nguoi_ban_id = str(user.get("id", ""))

    # Chờ đặt: → Chờ lấy + → Hoàn thành
    if tt == "Chờ đặt":
        with st.container(key="dh-actions-zone"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📦 → Chờ lấy", use_container_width=True,
                             key=f"dh_chlay_{ma}"):
                    with st.spinner("Đang cập nhật..."):
                        r = chuyen_cho_lay_rpc(ma)
                    if r.get("ok"):
                        _clear_dat_hang_cache()
                        st.toast(f"{ma} → Chờ lấy", icon="✅")
                        st.rerun()
                    else:
                        st.error(r.get("error", "Lỗi"))
            with col2:
                if st.button("✓ Hoàn thành ngay", use_container_width=True,
                             key=f"dh_ht_now_{ma}",
                             help="Khách lấy hàng luôn"):
                    st.session_state["dh_confirm_hoan_thanh"] = phieu
                    st.rerun()

    # Chờ lấy: → Hoàn thành
    elif tt == "Chờ lấy":
        if st.button("✓ Hoàn thành — Khách lấy hàng",
                     type="primary", use_container_width=True,
                     key=f"dh_ht_{ma}"):
            st.session_state["dh_confirm_hoan_thanh"] = phieu
            st.rerun()

    # Nút Hủy — admin only, mọi trạng thái active
    if is_admin():
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        if st.button("🚫 Hủy phiếu", use_container_width=True,
                     key=f"dh_huy_{ma}"):
            st.session_state["dh_confirm_huy"] = phieu
            st.rerun()


# ════════════════════════════════════════════════════════════════
# DIALOG — Hoàn thành (form PTTT + sửa giá)
# ════════════════════════════════════════════════════════════════

@st.dialog("Xác nhận hoàn thành đơn")
def _dialog_hoan_thanh(phieu: dict):
    st.markdown(_DAT_HANG_CSS, unsafe_allow_html=True)

    ma       = phieu.get("ma_phieu", "")
    tien_coc = int(phieu.get("tien_coc", 0) or 0)
    sl       = int(phieu.get("so_luong", 1) or 1)
    don_gia  = int(phieu.get("don_gia", 0) or 0)

    st.markdown(
        f"<div style='font-weight:600;color:#1a1a2e;margin-bottom:8px;'>"
        f"Phiếu {ma} — {phieu.get('ten_hang', '')}</div>",
        unsafe_allow_html=True
    )

    # Sửa đơn giá
    st.markdown("**Đơn giá thực tế (có thể sửa):**")
    with st.container(key="numkb-dh-don-gia"):
        don_gia_moi = st.number_input(
            "Đơn giá", min_value=0, value=don_gia, step=10000,
            key="dh_ht_don_gia", label_visibility="collapsed"
        )
    st.caption(f"Tổng: {fmt_vnd(don_gia_moi * sl)}")

    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    con_lai = max(0, don_gia_moi * sl - tien_coc)

    if tien_coc > 0:
        st.markdown(
            f"<div style='background:#fff8e0;border-radius:6px;"
            f"padding:6px 10px;font-size:0.85rem;color:#856404;margin-bottom:8px;'>"
            f"💰 Đã cọc: {fmt_vnd(tien_coc)} · Còn lại: <b>{fmt_vnd(con_lai)}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(f"**Khách cần trả: {fmt_vnd(con_lai)}**")

    st.markdown("**Phương thức thanh toán phần còn lại:**")

    chia_nhieu = st.checkbox("Chia nhiều phương thức", key="dh_ht_chia", value=False)

    if not chia_nhieu:
        pttt = st.radio(
            "PTTT", ["💵 Tiền mặt", "🏦 Chuyển khoản", "💳 Thẻ"],
            horizontal=True, key="dh_ht_radio", label_visibility="collapsed"
        )
        tm = con_lai if pttt == "💵 Tiền mặt" else 0
        ck = con_lai if pttt == "🏦 Chuyển khoản" else 0
        the = con_lai if pttt == "💳 Thẻ" else 0
    else:
        with st.container(key="dh-pttt-zone"):
            col_tm, col_ck, col_the = st.columns(3)
            with col_tm:
                st.caption("💵 Tiền mặt")
                with st.container(key="numkb-dh-tm"):
                    tm = st.number_input("TM", min_value=0, value=0,
                                         step=10000, key="dh_ht_tm",
                                         label_visibility="collapsed")
            with col_ck:
                st.caption("🏦 Chuyển khoản")
                with st.container(key="numkb-dh-ck"):
                    ck = st.number_input("CK", min_value=0, value=0,
                                         step=10000, key="dh_ht_ck",
                                         label_visibility="collapsed")
            with col_the:
                st.caption("💳 Thẻ")
                with st.container(key="numkb-dh-the"):
                    the = st.number_input("The", min_value=0, value=0,
                                          step=10000, key="dh_ht_the",
                                          label_visibility="collapsed")

        tong = int(tm) + int(ck) + int(the)
        if tong < con_lai:
            st.warning(f"Còn thiếu: {fmt_vnd(con_lai - tong)}")
        elif tong > con_lai:
            st.info(f"Tiền thừa: {fmt_vnd(tong - con_lai)}")
        else:
            st.success(f"✓ Đủ: {fmt_vnd(tong)}")

    # Validate
    tong_pttt_voi_coc = int(tm) + int(ck) + int(the) + tien_coc
    tong_can_tra = don_gia_moi * sl
    can_submit = tong_pttt_voi_coc >= tong_can_tra

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✓ Xác nhận", type="primary", use_container_width=True,
                     key=f"dh_ht_confirm_{ma}", disabled=not can_submit):
            user = get_user() or {}
            payload = {
                "ma_phieu":     ma,
                "don_gia_moi":  int(don_gia_moi),
                "tien_mat":     int(tm),
                "chuyen_khoan": int(ck),
                "the":          int(the),
                "nguoi_ban":    user.get("ho_ten", ""),
                "nguoi_ban_id": str(user.get("id", "")),
            }
            with st.spinner("Đang xử lý..."):
                r = hoan_thanh_dat_hang_rpc(payload)
            if r.get("ok"):
                _clear_dat_hang_cache()
                from utils.db import load_hang_hoa_pos
                load_hang_hoa_pos.clear()
                st.session_state.pop("dh_confirm_hoan_thanh", None)
                st.toast(f"Hoàn thành {ma} · HĐ {r.get('ma_hd', '')}", icon="✅")
                st.rerun()
            else:
                st.error(r.get("error", "Lỗi không xác định"))
    with col2:
        if st.button("Hủy bỏ", use_container_width=True, key=f"dh_ht_cancel_{ma}"):
            st.session_state.pop("dh_confirm_hoan_thanh", None)
            st.rerun()


# ════════════════════════════════════════════════════════════════
# DIALOG — Hủy phiếu
# ════════════════════════════════════════════════════════════════

@st.dialog("Xác nhận hủy phiếu đặt?")
def _dialog_huy(phieu: dict):
    ma       = phieu.get("ma_phieu", "")
    tien_coc = int(phieu.get("tien_coc", 0) or 0)

    st.markdown(
        f"<div style='font-size:1rem;color:#1a1a2e;margin-bottom:6px;'>"
        f"Hủy phiếu <b>{ma}</b>?</div>"
        f"<div style='font-size:0.88rem;color:#666;margin-bottom:10px;'>"
        f"Hàng: {phieu.get('ten_hang', '')} · "
        f"Khách: {phieu.get('ten_khach') or 'Khách lẻ'}"
        f"</div>",
        unsafe_allow_html=True
    )

    coc_xu_ly = None
    if tien_coc > 0:
        st.markdown(
            f"<div style='background:#fff8e0;border-radius:6px;"
            f"padding:8px 12px;font-size:0.88rem;color:#856404;margin-bottom:10px;'>"
            f"⚠️ Phiếu có cọc <b>{fmt_vnd(tien_coc)}</b> — chọn xử lý:</div>",
            unsafe_allow_html=True
        )
        coc_xu_ly = st.radio(
            "Xử lý cọc",
            ["Trả cọc cho khách", "Giữ cọc (phạt)"],
            key=f"dh_huy_coc_{ma}",
            label_visibility="collapsed",
        )
        coc_xu_ly = "Trả cọc" if coc_xu_ly == "Trả cọc cho khách" else "Giữ cọc"

    col1, col2 = st.columns(2)
    with col1:
        can_submit = (tien_coc == 0) or (coc_xu_ly is not None)
        if st.button("✓ Xác nhận hủy", type="primary",
                     use_container_width=True,
                     key=f"dh_huy_confirm_{ma}",
                     disabled=not can_submit):
            user = get_user() or {}
            with st.spinner("Đang hủy..."):
                r = huy_phieu_dat_hang_rpc(ma, user.get("ho_ten", ""), coc_xu_ly)
            if r.get("ok"):
                _clear_dat_hang_cache()
                st.session_state.pop("dh_confirm_huy", None)
                st.toast(f"Đã hủy {ma}", icon="✅")
                st.rerun()
            else:
                st.error(r.get("error", "Lỗi"))
    with col2:
        if st.button("Quay lại", use_container_width=True,
                     key=f"dh_huy_cancel_{ma}"):
            st.session_state.pop("dh_confirm_huy", None)
            st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Card 1 phiếu trong danh sách
# ════════════════════════════════════════════════════════════════

_TT_VISUAL = {
    # trang_thai → (icon_emoji, circle_bg, circle_fg, pill_label, pill_bg, pill_fg)
    "Chờ đặt":    ("📋", "#fff8e0", "#856404", "Chờ đặt",    "#fff8e0", "#856404"),
    "Chờ lấy":    ("📦", "#e8f0ff", "#1a4fba", "Chờ lấy",    "#e8f0ff", "#1a4fba"),
    "Hoàn thành": ("📋", "#e8f7ee", "#1a7f37", "Hoàn thành", "#e8f7ee", "#1a7f37"),
    "Đã hủy":     ("✕",  "#ffe5e5", "#c1121f", "Đã hủy",     "#ffe5e5", "#c1121f"),
}


def _render_phieu_card(phieu: dict):
    ma      = phieu.get("ma_phieu", "")
    tt      = phieu.get("trang_thai", "")
    ten_kh  = phieu.get("ten_khach") or "Khách lẻ"
    sdt     = phieu.get("sdt_khach") or ""
    ten_hg  = phieu.get("ten_hang", "")
    sl      = int(phieu.get("so_luong", 1) or 1)
    don_gia = int(phieu.get("don_gia", 0) or 0)
    coc     = int(phieu.get("tien_coc", 0) or 0)
    tong_gia = don_gia * sl
    thoigian = _fmt_dt(phieu.get("created_at", ""))
    is_cancelled = (tt == "Đã hủy")

    icon, c_bg, c_fg, pill_lbl, p_bg, p_fg = _TT_VISUAL.get(
        tt, ("📋", "#f0f0f0", "#555", tt, "#f0f0f0", "#555")
    )

    state = "cancelled" if is_cancelled else "active"
    container_key = f"dh-card-{state}-{ma}"
    btn_key = f"dh-cardbtn-{ma}"

    pill_inline = (
        f"<span style='background:{p_bg};color:{p_fg};border-radius:999px;"
        f"padding:2px 9px;font-size:0.72rem;font-weight:600;"
        f"white-space:nowrap;'>{pill_lbl}</span>"
    )
    pill_under = (
        f"<div style='background:{p_bg};color:{p_fg};border-radius:999px;"
        f"padding:2px 10px;font-size:0.72rem;font-weight:600;margin-top:6px;"
        f"text-align:center;'>{pill_lbl}</div>"
    )
    icon_circle = (
        f"<div style='width:54px;height:54px;border-radius:50%;"
        f"background:{c_bg};color:{c_fg};display:flex;align-items:center;"
        f"justify-content:center;font-size:1.6rem;margin:0 auto;'>{icon}</div>"
    )

    sdt_html = (f"<span style='color:#888;'>📞 {sdt}</span>" if sdt else "")
    coc_html = (f" · <span>Cọc: <b style='color:#1a1a2e;'>{fmt_vnd(coc)}</b></span>"
                if coc > 0 else "")

    with st.container(key=container_key):
        col_icon, col_body, col_price = st.columns([1, 4, 2])

        with col_icon:
            st.markdown(icon_circle + pill_under, unsafe_allow_html=True)

        with col_body:
            sep_html = ""
            if sdt:
                sep_html = "<span style='color:#ddd;'>|</span>" + sdt_html
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;"
                f"flex-wrap:wrap;'>"
                f"<span style='font-family:monospace;font-size:0.98rem;"
                f"font-weight:800;color:#1a1a2e;'>{ma}</span>"
                f"{pill_inline}"
                f"</div>"
                f"<div style='font-size:0.92rem;color:#1a1a2e;margin-top:2px;'>"
                f"{ten_hg}</div>"
                f"<div style='font-size:0.78rem;color:#666;margin-top:6px;"
                f"display:flex;flex-wrap:wrap;gap:4px 6px;'>"
                f"<span>📅 {thoigian}</span>"
                f"<span>·</span><span>SL: {sl}</span>"
                f"{coc_html}"
                f"</div>"
                f"<div style='font-size:0.78rem;color:#888;margin-top:4px;"
                f"display:flex;flex-wrap:wrap;gap:6px;align-items:center;'>"
                f"<span>👤 {ten_kh}</span>"
                f"{sep_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_price:
            price_color = "#888" if is_cancelled else "#e63946"
            st.markdown(
                f"<div style='display:flex;align-items:center;justify-content:flex-end;"
                f"gap:4px;'>"
                f"<div style='font-size:1.05rem;font-weight:800;color:{price_color};"
                f"white-space:nowrap;'>{fmt_vnd(tong_gia) if not is_cancelled else '0đ'}</div>"
                f"<span style='color:#bbb;font-size:1.1rem;'>›</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with st.container(key=btn_key):
            if st.button("Xem chi tiết", key=f"dh_card_{ma}",
                         use_container_width=True):
                _dialog_chi_tiet(phieu)


# ════════════════════════════════════════════════════════════════
# TAB 1 — Danh sách phiếu
# ════════════════════════════════════════════════════════════════

def _render_tab_danh_sach():
    chi_nhanh = get_active_branch()

    # Pending dialogs
    pending_ht = st.session_state.pop("dh_confirm_hoan_thanh", None)
    if pending_ht:
        _dialog_hoan_thanh(pending_ht)

    pending_huy = st.session_state.pop("dh_confirm_huy", None)
    if pending_huy:
        _dialog_huy(pending_huy)

    # Filter trạng thái
    filter_options = {
        "Tất cả": None,
        "Đang mở (Chờ đặt + Chờ lấy)": ["Chờ đặt", "Chờ lấy"],
        "Chờ đặt": ["Chờ đặt"],
        "Chờ lấy": ["Chờ lấy"],
        "Hoàn thành": ["Hoàn thành"],
        "Đã hủy": ["Đã hủy"],
    }

    with st.container(key="dh-filter-zone"):
        filter_chon = st.selectbox(
            "Trạng thái:", list(filter_options.keys()),
            key="dh_filter_tt", label_visibility="collapsed"
        )

    tt_filter = filter_options[filter_chon]

    with st.spinner("Đang tải..."):
        phieu_list = load_phieu_dat_hang(chi_nhanh, tt_filter)

    st.markdown(
        f"<div class='dh-count-caption'>"
        f"<span style='font-size:1rem;'>📦</span>"
        f"<span><b>{len(phieu_list)}</b> phiếu</span></div>",
        unsafe_allow_html=True,
    )

    if not phieu_list:
        st.markdown(
            "<div class='dh-empty'>Không có phiếu nào</div>",
            unsafe_allow_html=True,
        )
    else:
        for phieu in phieu_list:
            _render_phieu_card(phieu)

    # FAB crown — trang trí kiểu mockup
    st.markdown("<div class='dh-fab-crown'>♛</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# TAB 2 — Tạo phiếu mới
# ════════════════════════════════════════════════════════════════

def _render_tab_tao_moi():
    st.markdown(_DAT_HANG_CSS, unsafe_allow_html=True)
    chi_nhanh = get_active_branch()
    user = get_user() or {}
    # Reset counter — tăng mỗi lần submit thành công → tất cả key widget thay đổi
    rk = st.session_state.get("dh_form_reset_cnt", 0)

    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin-bottom:10px;'>📝 Tạo phiếu đặt hàng mới</div>",
        unsafe_allow_html=True
    )

    # ── Khách hàng ──
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin:4px 0 6px;'>👤 Khách hàng</div>",
        unsafe_allow_html=True
    )
    is_khach_le = st.checkbox("Khách lẻ (không cần SĐT)", key=f"dh_khach_le_{rk}")

    ma_kh = ten_kh = sdt_kh = ""

    if not is_khach_le:
        with st.container(key=f"numkb-tel-dh-sdt-{rk}"):
            sdt_input = st.text_input(
                "SĐT:", placeholder="0xxx xxx xxx",
                key=f"dh_sdt_{rk}", max_chars=15, label_visibility="collapsed"
            )

        from utils.db import clean_phone
        sdt_clean = clean_phone(sdt_input)

        if sdt_clean:
            last = st.session_state.get("dh_last_sdt", "")
            if sdt_clean != last:
                kh = lookup_khach_hang_by_sdt(sdt_clean)
                st.session_state["dh_last_sdt"]    = sdt_clean
                st.session_state["dh_kh_result"]   = kh
            kh = st.session_state.get("dh_kh_result")
            if kh:
                st.success(f"✓ {kh.get('ten_kh', '')}")
                ma_kh  = kh.get("ma_kh", "")
                ten_kh = kh.get("ten_kh", "")
                sdt_kh = sdt_clean
            else:
                st.caption("⚠️ Chưa có — nhập tên")
                ten_input = st.text_input(
                    "Tên khách:", key=f"dh_ten_moi_{rk}",
                    label_visibility="collapsed",
                    placeholder="Tên khách hàng"
                )
                ten_kh = ten_input.strip()
                sdt_kh = sdt_clean
    else:
        ten_kh = "Khách lẻ"

    # ── Hàng hoá ──
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin:14px 0 6px;'>📦 Mặt hàng đặt</div>",
        unsafe_allow_html=True
    )
    ten_hang = st.text_input(
        "Tên hàng *", placeholder="Tên hàng cần đặt...",
        key=f"dh_ten_hang_{rk}", label_visibility="collapsed"
    )
    mo_ta = st.text_input(
        "Mô tả thêm", placeholder="Màu sắc, model, kích thước...",
        key=f"dh_mo_ta_{rk}", label_visibility="collapsed"
    )

    col_sl, col_gia = st.columns(2)
    with col_sl:
        st.caption("Số lượng:")
        with st.container(key=f"numkb-dh-sl-{rk}"):
            so_luong = st.number_input(
                "SL", min_value=1, max_value=99, value=1,
                key=f"dh_sl_{rk}", label_visibility="collapsed"
            )
    with col_gia:
        st.caption("Đơn giá dự kiến:")
        with st.container(key=f"numkb-dh-gia-{rk}"):
            don_gia = st.number_input(
                "Giá", min_value=0, value=0, step=10000,
                key=f"dh_don_gia_{rk}", label_visibility="collapsed"
            )
    if don_gia > 0:
        st.caption(f"Tổng dự kiến: {fmt_vnd(don_gia * so_luong)}")

    # ── Đặt cọc ──
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin:14px 0 6px;'>💰 Đặt cọc (tùy chọn)</div>",
        unsafe_allow_html=True
    )
    co_coc = st.checkbox("Có đặt cọc", key=f"dh_co_coc_{rk}")

    tien_coc = coc_tm = coc_ck = coc_the = 0

    if co_coc:
        with st.container(key=f"numkb-dh-coc-{rk}"):
            tien_coc = st.number_input(
                "Số tiền cọc:", min_value=0, value=0, step=10000,
                key=f"dh_tien_coc_{rk}", label_visibility="collapsed"
            )
        if tien_coc > 0:
            st.caption(f"= {fmt_vnd(tien_coc)}")
            st.markdown("**PTTT cọc:**")
            chia_coc = st.checkbox("Chia nhiều PTTT", key=f"dh_coc_chia_{rk}")

            if not chia_coc:
                pttt_coc = st.radio(
                    "PTTT cọc", ["💵 Tiền mặt", "🏦 Chuyển khoản", "💳 Thẻ"],
                    horizontal=True, key=f"dh_coc_radio_{rk}",
                    label_visibility="collapsed"
                )
                coc_tm  = tien_coc if pttt_coc == "💵 Tiền mặt" else 0
                coc_ck  = tien_coc if pttt_coc == "🏦 Chuyển khoản" else 0
                coc_the = tien_coc if pttt_coc == "💳 Thẻ" else 0
            else:
                with st.container(key=f"dh-coc-pttt-zone-{rk}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.caption("💵 Tiền mặt")
                        with st.container(key=f"numkb-dh-coc-tm-{rk}"):
                            coc_tm = st.number_input(
                                "TM", min_value=0, value=0, step=10000,
                                key=f"dh_coc_tm_{rk}", label_visibility="collapsed")
                    with c2:
                        st.caption("🏦 Chuyển khoản")
                        with st.container(key=f"numkb-dh-coc-ck-{rk}"):
                            coc_ck = st.number_input(
                                "CK", min_value=0, value=0, step=10000,
                                key=f"dh_coc_ck_{rk}", label_visibility="collapsed")
                    with c3:
                        st.caption("💳 Thẻ")
                        with st.container(key=f"numkb-dh-coc-the-{rk}"):
                            coc_the = st.number_input(
                                "The", min_value=0, value=0, step=10000,
                                key=f"dh_coc_the_{rk}", label_visibility="collapsed")
                tong_coc_pttt = int(coc_tm) + int(coc_ck) + int(coc_the)
                if tong_coc_pttt != tien_coc:
                    st.warning(
                        f"PTTT cọc ({fmt_vnd(tong_coc_pttt)}) "
                        f"≠ tiền cọc ({fmt_vnd(tien_coc)})"
                    )

    # ── Ghi chú ──
    ghi_chu = st.text_input(
        "Ghi chú:", placeholder="Ghi chú thêm...",
        key=f"dh_ghi_chu_{rk}", label_visibility="collapsed"
    )

    # ── Validate + Submit ──
    errors = []
    if not is_khach_le and not sdt_kh:
        errors.append("Tick 'Khách lẻ' hoặc nhập SĐT")
    if not is_khach_le and not ten_kh:
        errors.append("Nhập tên khách")
    if not ten_hang.strip():
        errors.append("Nhập tên hàng cần đặt")
    if co_coc and tien_coc > 0:
        tong_coc_check = int(coc_tm) + int(coc_ck) + int(coc_the)
        if tong_coc_check != tien_coc:
            errors.append("PTTT cọc không khớp số tiền cọc")

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    if st.button(
        "✓ TẠO PHIẾU ĐẶT HÀNG",
        type="primary", use_container_width=True,
        key=f"dh_submit_{rk}",
        disabled=bool(errors),
        help=" · ".join(errors) if errors else None,
    ):
        payload = {
            "chi_nhanh":        chi_nhanh,
            "ma_kh":            ma_kh,
            "ten_khach":        ten_kh,
            "sdt_khach":        sdt_kh,
            "ten_hang":         ten_hang.strip(),
            "mo_ta":            mo_ta.strip(),
            "so_luong":         int(so_luong),
            "don_gia":          int(don_gia),
            "tien_coc":         int(tien_coc) if co_coc else 0,
            "coc_tien_mat":     int(coc_tm) if co_coc else 0,
            "coc_chuyen_khoan": int(coc_ck) if co_coc else 0,
            "coc_the":          int(coc_the) if co_coc else 0,
            "ghi_chu":          ghi_chu.strip(),
            "nguoi_tao":        user.get("ho_ten", ""),
            "nguoi_tao_id":     str(user.get("id", "")),
        }
        with st.spinner("Đang tạo phiếu..."):
            r = tao_phieu_dat_hang_rpc(payload)

        if r.get("ok"):
            _clear_dat_hang_cache()
            ma_moi = r.get("ma_phieu", "")
            st.toast(f"Đã tạo {ma_moi}", icon="✅")
            # Reset form — tăng counter → tất cả widget re-render với key mới
            _reset_form_tao_moi()
            st.rerun()
        else:
            st.error(f"Lỗi: {r.get('error', 'Không xác định')}")


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_dat_hang():
    st.markdown(_DAT_HANG_CSS, unsafe_allow_html=True)

    tab_ds, tab_tao = st.tabs(["📋 Danh sách", "➕ Tạo mới"])

    with tab_ds:
        _render_tab_danh_sach()

    with tab_tao:
        _render_tab_tao_moi()
