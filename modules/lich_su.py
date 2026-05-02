"""
Module lịch sử hóa đơn POS.

UI flow:
- Mặc định load HĐ + phiếu đổi/trả hôm nay của CN đang chọn (merge, sort newest-first)
- Ô tìm SĐT/mã → tìm mọi ngày, tất cả CN có quyền
- Bấm "Xem cũ hơn" → load thêm 1 ngày (mỗi click)
- Bấm vào card HĐ → mở modal chi tiết
- Bấm vào card phiếu đổi/trả → mở modal chi tiết phiếu (top-level, tránh nested dialog)
- Modal HĐ có nút "🚫 Hủy hóa đơn" (chỉ admin) → confirm 2 bước → gọi RPC
- HĐ / phiếu đã hủy hiện xám với badge "Đã hủy"
"""

import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from utils.auth import (
    get_active_branch, get_accessible_branches, get_user, is_admin,
)
from utils.db import (
    load_hoa_don_pos_history, huy_hoa_don_pos_rpc,
    search_hoa_don_pos, load_phieu_doi_tra_by_hd,
    load_phieu_doi_tra_pos_history,
)
from utils.helpers import fmt_vnd, today_vn
from modules.doi_tra import (
    open_doi_tra, is_doi_tra_active, render_man_doi_tra,
    dialog_chi_tiet_pdt, dialog_confirm_huy_pdt,
)

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _get_days_back() -> int:
    return st.session_state.get("lichsu_days_back", 0)


def _get_from_date_iso() -> str:
    days_back = _get_days_back()
    today = today_vn()
    from_date = today - timedelta(days=days_back)
    return from_date.strftime("%Y-%m-%dT00:00:00+07:00")


def _parse_iso(s: str) -> datetime:
    """Parse ISO string → tz-aware datetime. Dùng để sort nhất quán."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=ZoneInfo("UTC"))


def _to_vn(iso_str: str) -> "datetime":
    """
    Parse ISO string từ Supabase → datetime giờ VN.
    Supabase trả naive datetime (không có tzinfo) → assume UTC → convert VN.
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_TZ_VN)


def _format_invoice_time(iso_str: str) -> str:
    """ISO string từ Supabase → '13:33 · 02/05' (giờ VN)."""
    try:
        return _to_vn(iso_str).strftime("%H:%M · %d/%m")
    except Exception:
        return iso_str[:16]


def _format_invoice_date(iso_str: str) -> str:
    """ISO string từ Supabase → '02/05/2026 13:33' (giờ VN)."""
    try:
        return _to_vn(iso_str).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


# ════════════════════════════════════════════════════════════════
# MODAL — Chi tiết HĐ
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết hóa đơn")
def _dialog_chi_tiet(inv: dict):
    is_cancelled = inv.get("trang_thai") == "Đã hủy"

    badge = ""
    if is_cancelled:
        badge = ("<span style='background:#ffe5e5;color:#c1121f;"
                 "padding:2px 8px;border-radius:6px;font-size:0.78rem;"
                 "font-weight:600;margin-left:6px;'>Đã hủy</span>")

    st.markdown(
        f"<div style='font-family:monospace;font-size:1.1rem;font-weight:700;"
        f"color:#1a1a2e;'>{inv['ma_hd']}{badge}</div>"
        f"<div style='font-size:0.82rem;color:#888;margin-top:2px;'>"
        f"{_format_invoice_date(inv.get('created_at',''))}</div>",
        unsafe_allow_html=True
    )

    if is_cancelled and inv.get("cancelled_at"):
        cancelled_by = inv.get("cancelled_by") or ""
        by_text = f" bởi {cancelled_by}" if cancelled_by else ""
        st.markdown(
            f"<div style='font-size:0.78rem;color:#c1121f;margin-top:2px;'>"
            f"Hủy lúc: {_format_invoice_date(inv['cancelled_at'])}{by_text}"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin:10px 0 8px;'>", unsafe_allow_html=True)

    sdt_text = (" · " + inv["sdt_khach"]) if inv.get("sdt_khach") else ""
    st.markdown(
        f"<div style='font-size:0.88rem;color:#555;'>"
        f"<b>Khách:</b> {inv.get('ten_khach') or 'Khách lẻ'}{sdt_text}<br>"
        f"<b>NV bán:</b> {inv.get('nguoi_ban') or '—'}"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#1a1a2e;"
        "margin:12px 0 6px;'>Chi tiết:</div>",
        unsafe_allow_html=True
    )

    items_html = "<div style='background:#fafafa;border:1px solid #eee;" \
                 "border-radius:8px;padding:8px 10px;'>"
    for ct in inv.get("items", []):
        sl = ct.get("so_luong", 0)
        dg = ct.get("don_gia", 0)
        gg = ct.get("giam_gia_dong", 0)
        tt = ct.get("thanh_tien", 0)
        gg_str = (" · giảm " + fmt_vnd(gg)) if gg > 0 else ""
        items_html += (
            f"<div style='padding:4px 0;border-bottom:1px dashed #e8e8e8;'>"
            f"<div style='font-size:0.86rem;color:#1a1a2e;font-weight:500;'>"
            f"{ct.get('ten_hang','')}</div>"
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:0.78rem;color:#666;margin-top:2px;'>"
            f"<span>SL {sl} × {fmt_vnd(dg)}{gg_str}</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{fmt_vnd(tt)}</span>"
            f"</div></div>"
        )
    items_html += "</div>"
    st.markdown(items_html, unsafe_allow_html=True)

    rows = [("Tổng tiền hàng", fmt_vnd(inv.get("tong_tien_hang", 0)))]
    if inv.get("giam_gia_don", 0) > 0:
        rows.append(("Giảm giá đơn", "− " + fmt_vnd(inv["giam_gia_don"])))
    rows.append(("Khách cần trả", fmt_vnd(inv.get("khach_can_tra", 0))))
    if inv.get("tien_mat", 0) > 0:
        rows.append(("💵 Tiền mặt", fmt_vnd(inv["tien_mat"])))
    if inv.get("chuyen_khoan", 0) > 0:
        rows.append(("🏦 Chuyển khoản", fmt_vnd(inv["chuyen_khoan"])))
    if inv.get("the", 0) > 0:
        rows.append(("💳 Thẻ", fmt_vnd(inv["the"])))
    if inv.get("tien_thua", 0) > 0:
        rows.append(("Tiền thừa", fmt_vnd(inv["tien_thua"])))

    summary_html = "<div style='background:#fff;border:1px solid #e8e8e8;" \
                   "border-radius:8px;padding:8px 12px;margin-top:10px;'>"
    for lbl, val in rows:
        summary_html += (
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:3px 0;font-size:0.86rem;'>"
            f"<span style='color:#777;'>{lbl}:</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{val}</span>"
            f"</div>"
        )
    summary_html += "</div>"
    st.markdown(summary_html, unsafe_allow_html=True)

    if not is_cancelled:
        pdt_list = load_phieu_doi_tra_by_hd(inv["ma_hd"])
        if pdt_list:
            st.markdown(
                "<div style='font-size:0.88rem;font-weight:600;color:#1a1a2e;"
                "margin:14px 0 6px;'>↔ Đã đổi/trả:</div>",
                unsafe_allow_html=True
            )
            for pdt in pdt_list:
                _render_pdt_row_in_invoice(pdt)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    if is_cancelled:
        if st.button("🖨 In lại", use_container_width=True,
                     key=f"ls_in_{inv['ma_hd']}",
                     help="Sẽ kích hoạt khi setup máy in xong"):
            st.toast("Tính năng in đang chờ setup máy in", icon="🛠")
        return

    col_dt, col_huy = st.columns(2)
    with col_dt:
        if st.button("↔ Đổi/Trả", use_container_width=True,
                     key=f"ls_doitra_{inv['ma_hd']}"):
            open_doi_tra(inv["ma_hd"])
            st.rerun()
    with col_huy:
        if is_admin():
            if st.button("🚫 Hủy hóa đơn", use_container_width=True,
                         key=f"ls_huy_{inv['ma_hd']}"):
                st.session_state["lichsu_confirm_huy"] = inv
                st.rerun()
        else:
            if st.button("🖨 In lại", use_container_width=True,
                         key=f"ls_in_{inv['ma_hd']}",
                         help="Sẽ kích hoạt khi setup máy in xong"):
                st.toast("Tính năng in đang chờ setup máy in", icon="🛠")


def _render_pdt_row_in_invoice(pdt: dict):
    """
    1 dòng phiếu đổi/trả trong modal HĐ gốc.
    Set state → rerun ra top-level để tránh nested @st.dialog crash.
    """
    is_cancelled = pdt.get("trang_thai") == "Đã hủy"
    ma_pdt = pdt.get("ma_pdt", "")
    loai   = pdt.get("loai_phieu", "")
    cl     = int(pdt.get("chenh_lech", 0) or 0)

    items = pdt.get("items", [])
    tra_names = [it.get("ten_hang", "") for it in items if it.get("kieu") == "tra"]
    moi_names = [it.get("ten_hang", "") for it in items if it.get("kieu") == "moi"]
    parts = []
    if tra_names:
        parts.append("Trả: " + ", ".join(tra_names[:2])
                     + (f" +{len(tra_names)-2}" if len(tra_names) > 2 else ""))
    if moi_names:
        parts.append("Mới: " + ", ".join(moi_names[:2])
                     + (f" +{len(moi_names)-2}" if len(moi_names) > 2 else ""))
    sub = " · ".join(parts) if parts else loai

    cl_text = ""
    if cl > 0:
        cl_text = f"  ·  Khách bù {fmt_vnd(cl)}"
    elif cl < 0:
        cl_text = f"  ·  Hoàn {fmt_vnd(-cl)}"

    cancel_tag = " [ĐÃ HỦY]" if is_cancelled else ""
    btn_label = (
        f"{ma_pdt}{cancel_tag} — {loai}{cl_text}\n"
        f"{_format_invoice_time(pdt.get('created_at',''))}\n"
        f"{sub}"
    )

    container_key = f"ls-pdt-zone-{'cancelled' if is_cancelled else 'active'}-{ma_pdt}"
    if is_cancelled:
        st.markdown(
            f"<style>.st-key-{container_key} button {{ opacity: 0.55 !important; }}</style>",
            unsafe_allow_html=True
        )
    with st.container(key=container_key):
        if st.button(btn_label, key=f"ls_pdt_btn_{ma_pdt}", use_container_width=True):
            st.session_state["lichsu_view_pdt"] = pdt
            st.rerun()


# ════════════════════════════════════════════════════════════════
# MODAL — Confirm hủy HĐ
# ════════════════════════════════════════════════════════════════

@st.dialog("Xác nhận hủy hóa đơn?")
def _dialog_confirm_huy(inv: dict):
    st.markdown(
        f"<div style='font-size:1rem;color:#1a1a2e;margin-bottom:6px;'>"
        f"Hủy hóa đơn <b>{inv['ma_hd']}</b>?</div>"
        f"<div style='font-size:0.88rem;color:#666;margin-bottom:14px;'>"
        f"Hàng sẽ được hoàn lại vào tồn kho. Hành động này không thể đảo ngược."
        f"</div>",
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✓ Xác nhận hủy", type="primary",
                     use_container_width=True,
                     key=f"ls_huy_confirm_{inv['ma_hd']}"):
            user = get_user() or {}
            cancelled_by = user.get("ho_ten", "")
            with st.spinner("Đang hủy hóa đơn..."):
                result = huy_hoa_don_pos_rpc(inv["ma_hd"], cancelled_by)
            if result.get("ok"):
                st.session_state.pop("lichsu_confirm_huy", None)
                from utils.db import load_hang_hoa_pos
                load_hang_hoa_pos.clear()
                st.toast(f"Đã hủy {inv['ma_hd']}", icon="✅")
                st.rerun()
            else:
                st.error(f"Lỗi: {result.get('error', 'Không xác định')}")
    with col2:
        if st.button("Quay lại", use_container_width=True,
                     key=f"ls_huy_cancel_{inv['ma_hd']}"):
            st.session_state.pop("lichsu_confirm_huy", None)
            st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Card HĐ bán hàng
# ════════════════════════════════════════════════════════════════

def _render_invoice_card(inv: dict):
    is_cancelled = inv.get("trang_thai") == "Đã hủy"
    ma_hd     = inv.get("ma_hd", "")
    ten_kh    = inv.get("ten_khach") or "Khách lẻ"
    sdt       = inv.get("sdt_khach") or ""
    tien      = inv.get("khach_can_tra", 0)
    thoi_gian = _format_invoice_time(inv.get("created_at", ""))
    nguoi_ban = inv.get("nguoi_ban") or ""

    sub_kh = ten_kh + (f" · {sdt}" if sdt else "")
    cancel_tag = " [ĐÃ HỦY]" if is_cancelled else ""
    btn_label = (
        f"{ma_hd}{cancel_tag} — {fmt_vnd(tien)}\n"
        f"{thoi_gian}  ·  {sub_kh}\n"
        f"NV: {nguoi_ban}"
    )

    container_key = f"ls-card-zone-{'cancelled' if is_cancelled else 'active'}-{ma_hd}"
    if is_cancelled:
        st.markdown(
            f"<style>.st-key-{container_key} button {{ opacity: 0.55 !important; }}</style>",
            unsafe_allow_html=True
        )
    with st.container(key=container_key):
        if st.button(btn_label, key=f"ls_card_{ma_hd}", use_container_width=True):
            _dialog_chi_tiet(inv)


# ════════════════════════════════════════════════════════════════
# RENDER — Card phiếu đổi/trả
# ════════════════════════════════════════════════════════════════

def _render_pdt_card(pdt: dict):
    is_cancelled = pdt.get("trang_thai") == "Đã hủy"
    ma_pdt    = pdt.get("ma_pdt", "")
    loai      = pdt.get("loai_phieu", "")
    cl        = int(pdt.get("chenh_lech", 0) or 0)
    ten_kh    = pdt.get("ten_khach") or "Khách lẻ"
    sdt       = pdt.get("sdt_khach") or ""
    nguoi     = pdt.get("nguoi_tao") or ""
    thoi_gian = _format_invoice_time(pdt.get("created_at", ""))
    ma_hd_goc = pdt.get("ma_hd_goc", "")

    if cl > 0:
        tien_text = f"{fmt_vnd(cl)} (KH bù)"
    elif cl < 0:
        tien_text = f"{fmt_vnd(-cl)} (hoàn KH)"
    else:
        tien_text = "đổi ngang"

    sub_kh = ten_kh + (f" · {sdt}" if sdt else "")
    cancel_tag = " [ĐÃ HỦY]" if is_cancelled else ""
    btn_label = (
        f"↔ {ma_pdt}{cancel_tag} — {loai} · {tien_text}\n"
        f"{thoi_gian}  ·  {sub_kh}\n"
        f"Từ HĐ: {ma_hd_goc}  ·  NV: {nguoi}"
    )

    container_key = f"ls-pdt-card-{'cancelled' if is_cancelled else 'active'}-{ma_pdt}"
    if is_cancelled:
        st.markdown(
            f"<style>.st-key-{container_key} button {{ opacity: 0.55 !important; }}</style>",
            unsafe_allow_html=True
        )
    with st.container(key=container_key):
        if st.button(btn_label, key=f"ls_pdt_card_{ma_pdt}", use_container_width=True):
            st.session_state["lichsu_view_pdt"] = pdt
            st.rerun()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_lich_su():
    if is_doi_tra_active():
        render_man_doi_tra()
        return

    chi_nhanh = get_active_branch()

    # ── Pending dialogs — top-level ──
    pending_huy = st.session_state.get("lichsu_confirm_huy")
    if pending_huy:
        _dialog_confirm_huy(pending_huy)

    pending_huy_pdt = st.session_state.get("pdt_confirm_huy")
    if pending_huy_pdt:
        dialog_confirm_huy_pdt(pending_huy_pdt)

    pending_view_pdt = st.session_state.pop("lichsu_view_pdt", None)
    if pending_view_pdt:
        dialog_chi_tiet_pdt(pending_view_pdt)

    # ── Header ──
    st.markdown(
        f"<div style='font-size:1rem;font-weight:700;color:#1a1a2e;"
        f"margin-bottom:8px;'>📋 Lịch sử — {chi_nhanh}</div>",
        unsafe_allow_html=True
    )

    # ── Ô tìm HĐ theo SĐT/Mã (mọi ngày) ──
    with st.container(key="numkb-tel-lichsu-find"):
        find_kw = st.text_input(
            "Tìm HĐ theo SĐT hoặc mã",
            placeholder="🔎 Tìm HĐ theo SĐT hoặc mã (mọi ngày)...",
            key="lichsu_find_kw",
            label_visibility="collapsed",
        )

    if find_kw and find_kw.strip():
        _render_find_results(find_kw.strip())
        return

    # ── Load dữ liệu ──
    from_date_iso = _get_from_date_iso()
    days_back = _get_days_back()

    with st.spinner("Đang tải..."):
        invoices = load_hoa_don_pos_history(chi_nhanh, from_date_iso)
        pdts     = load_phieu_doi_tra_pos_history(chi_nhanh, from_date_iso)

    # Ẩn HĐ + phiếu đã hủy khỏi tab Lịch sử POS
    # (hiển thị bên web app là đủ để tra cứu)
    invoices = [h for h in invoices if h.get("trang_thai") != "Đã hủy"]
    pdts     = [p for p in pdts     if p.get("trang_thai") != "Đã hủy"]

    # Merge + sort newest-first bằng datetime thực (không sort string)
    all_items = (
        [{"_type": "hd",  **h} for h in invoices] +
        [{"_type": "pdt", **p} for p in pdts]
    )
    all_items.sort(key=lambda x: _parse_iso(x.get("created_at", "")), reverse=True)

    # Caption
    range_label = "hôm nay" if days_back == 0 else f"{days_back + 1} ngày gần nhất"
    pdt_note = f" · {len(pdts)} phiếu ĐT" if pdts else ""
    st.caption(f"📅 {range_label} · {len(invoices)} HĐ{pdt_note}")

    # Render list
    if not all_items:
        st.markdown(
            f"<div style='background:#fafafa;border:1px dashed #ddd;"
            f"border-radius:10px;padding:24px 16px;text-align:center;"
            f"color:#999;margin:8px 0;'>Chưa có giao dịch {range_label}</div>",
            unsafe_allow_html=True
        )
    else:
        for item in all_items:
            if item["_type"] == "hd":
                _render_invoice_card(item)
            else:
                _render_pdt_card(item)

    # ── Nút xem cũ hơn / quay về hôm nay ──
    st.markdown(
        """<style>
        .st-key-lichsu-actions-zone div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            width: 100% !important;
            gap: 8px !important;
        }
        .st-key-lichsu-actions-zone div[data-testid="stHorizontalBlock"] > div {
            min-width: 0 !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    with st.container(key="lichsu-actions-zone"):
        col_old, col_today = st.columns(2)
        with col_old:
            if st.button("📅 Xem cũ hơn (+1 ngày)",
                         use_container_width=True,
                         key="lichsu_xem_cu_hon"):
                st.session_state["lichsu_days_back"] = days_back + 1
                st.rerun()
        with col_today:
            if st.button("↻ Quay về hôm nay",
                         use_container_width=True,
                         key="lichsu_reset",
                         disabled=(days_back == 0)):
                st.session_state["lichsu_days_back"] = 0
                st.rerun()


# ════════════════════════════════════════════════════════════════
# RENDER — Kết quả tìm SĐT/Mã (mọi ngày)
# ════════════════════════════════════════════════════════════════

def _render_find_results(keyword: str):
    cn_list = get_accessible_branches() or [get_active_branch()]
    with st.spinner("Đang tìm hóa đơn..."):
        results = search_hoa_don_pos(keyword, cn_list, limit=30)
    # Ẩn HĐ đã hủy
    results = [r for r in results if r.get("trang_thai") != "Đã hủy"]
    st.caption(f"🔎 Kết quả tìm '{keyword}': {len(results)} HĐ")
    if not results:
        st.markdown(
            "<div style='background:#fafafa;border:1px dashed #ddd;"
            "border-radius:10px;padding:24px 16px;text-align:center;"
            "color:#999;margin:8px 0;'>"
            "Không tìm thấy hóa đơn khớp"
            "</div>",
            unsafe_allow_html=True
        )
        return
    for inv in results:
        _render_invoice_card(inv)
    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    if st.button("✕ Xóa tìm kiếm", use_container_width=True, key="lichsu_clear_find"):
        st.session_state["lichsu_find_kw"] = ""
        st.rerun()
