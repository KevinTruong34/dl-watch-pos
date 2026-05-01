"""
Module lịch sử hóa đơn POS.

UI flow:
- Mặc định load HĐ hôm nay của CN đang chọn
- Search SĐT / mã HĐ / tên KH → filter client-side
- Bấm "Xem cũ hơn" → load thêm 1 ngày (mỗi click)
- Bấm vào card HĐ → mở modal chi tiết
- Modal có nút "🚫 Hủy hóa đơn" (chỉ admin) → confirm 2 bước → gọi RPC
- HĐ đã hủy hiện xám với badge "Đã hủy"
"""

import streamlit as st
from datetime import datetime, timedelta

from utils.auth import (
    get_active_branch, get_accessible_branches, get_user, is_admin,
)
from utils.db import (
    load_hoa_don_pos_history, huy_hoa_don_pos_rpc,
    search_hoa_don_pos, load_phieu_doi_tra_by_hd,
)
from utils.helpers import fmt_vnd, today_vn
from modules.doi_tra import (
    open_doi_tra, is_doi_tra_active, render_man_doi_tra,
    dialog_chi_tiet_pdt, dialog_confirm_huy_pdt,
)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _get_days_back() -> int:
    """Số ngày lùi về quá khứ — mặc định 0 (chỉ hôm nay)."""
    return st.session_state.get("lichsu_days_back", 0)


def _get_from_date_iso() -> str:
    """ISO timestamp đầu của khoảng load (UTC+7)."""
    days_back = _get_days_back()
    today = today_vn()
    from_date = today - timedelta(days=days_back)
    # Format đầu ngày VN: 2026-04-30T00:00:00+07:00
    return from_date.strftime("%Y-%m-%dT00:00:00+07:00")


def _format_invoice_time(iso_str: str) -> str:
    """'2026-04-30T14:23:45+07:00' → '14:23 · 30/04'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M · %d/%m")
    except Exception:
        return iso_str[:16]


def _format_invoice_date(iso_str: str) -> str:
    """'2026-04-30T...' → '30/04/2026 14:23'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


def _filter_invoices(invoices: list[dict], keyword: str) -> list[dict]:
    """Filter HĐ theo SĐT / mã HĐ / tên KH (case-insensitive, contains)."""
    kw = keyword.strip().lower()
    if not kw:
        return invoices
    out = []
    for inv in invoices:
        ma_hd  = (inv.get("ma_hd") or "").lower()
        sdt    = (inv.get("sdt_khach") or "").lower()
        ten_kh = (inv.get("ten_khach") or "").lower()
        if kw in ma_hd or kw in sdt or kw in ten_kh:
            out.append(inv)
    return out


# ════════════════════════════════════════════════════════════════
# MODAL — Chi tiết HĐ
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết hóa đơn")
def _dialog_chi_tiet(inv: dict):
    is_cancelled = inv.get("trang_thai") == "Đã hủy"

    # Header
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

    # Khách hàng + người bán
    sdt_text = (" · " + inv["sdt_khach"]) if inv.get("sdt_khach") else ""
    st.markdown(
        f"<div style='font-size:0.88rem;color:#555;'>"
        f"<b>Khách:</b> {inv.get('ten_khach') or 'Khách lẻ'}{sdt_text}<br>"
        f"<b>NV bán:</b> {inv.get('nguoi_ban') or '—'}"
        f"</div>",
        unsafe_allow_html=True
    )

    # Items
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

    # Tổng tiền
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

    # Section "Đã đổi/trả" — chỉ render nếu HĐ chưa hủy
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

    # Actions — không show nếu HĐ đã hủy
    if is_cancelled:
        if st.button("🖨 In lại", use_container_width=True,
                     key=f"ls_in_{inv['ma_hd']}",
                     help="Sẽ kích hoạt khi setup máy in xong"):
            st.toast("Tính năng in đang chờ setup máy in", icon="🛠")
        return

    # 2 nút: Đổi/Trả (mọi NV) + Hủy (admin)
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
    """1 dòng phiếu đổi/trả trong modal HĐ gốc — bấm vào → mở modal chi tiết phiếu."""
    is_cancelled = pdt.get("trang_thai") == "Đã hủy"
    ma_pdt = pdt.get("ma_pdt", "")
    loai   = pdt.get("loai_phieu", "")
    cl     = int(pdt.get("chenh_lech", 0) or 0)

    # Tóm tắt: tên các món trả + tên các món mới (chỉ tên gọn)
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
        if st.button(btn_label,
                     key=f"ls_pdt_btn_{ma_pdt}",
                     use_container_width=True):
            dialog_chi_tiet_pdt(pdt)


# ════════════════════════════════════════════════════════════════
# MODAL — Confirm hủy
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
                # Invalidate cache hàng hóa (vì tồn đã thay đổi)
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
# RENDER — Card 1 hóa đơn
# ════════════════════════════════════════════════════════════════

def _render_invoice_card(inv: dict):
    is_cancelled = inv.get("trang_thai") == "Đã hủy"

    ma_hd  = inv.get("ma_hd", "")
    ten_kh = inv.get("ten_khach") or "Khách lẻ"
    sdt    = inv.get("sdt_khach") or ""
    tien   = inv.get("khach_can_tra", 0)
    thoi_gian = _format_invoice_time(inv.get("created_at", ""))
    nguoi_ban = inv.get("nguoi_ban") or ""

    sub_kh = ten_kh
    if sdt:
        sub_kh += f" · {sdt}"

    # Badge "Đã hủy" trên label nút (Streamlit button không nhận HTML)
    cancel_tag = " [ĐÃ HỦY]" if is_cancelled else ""

    btn_label = (
        f"{ma_hd}{cancel_tag} — {fmt_vnd(tien)}\n"
        f"{thoi_gian}  ·  {sub_kh}\n"
        f"NV: {nguoi_ban}"
    )

    # Wrap container để áp opacity nếu đã hủy
    container_key = f"ls-card-zone-{'cancelled' if is_cancelled else 'active'}-{ma_hd}"
    if is_cancelled:
        st.markdown(
            f"<style>.st-key-{container_key} button {{ opacity: 0.55 !important; }}</style>",
            unsafe_allow_html=True
        )

    with st.container(key=container_key):
        if st.button(
            btn_label,
            key=f"ls_card_{ma_hd}",
            use_container_width=True,
        ):
            _dialog_chi_tiet(inv)


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_lich_su():
    """Tab Lịch sử hóa đơn — list HĐ của CN đang chọn."""

    # Nếu đang ở màn Đổi/Trả → render full-screen, bỏ qua phần list
    if is_doi_tra_active():
        render_man_doi_tra()
        return

    chi_nhanh = get_active_branch()

    # Pending confirm dialogs (priority cao hơn render)
    pending_huy = st.session_state.get("lichsu_confirm_huy")
    if pending_huy:
        _dialog_confirm_huy(pending_huy)
    pending_huy_pdt = st.session_state.get("pdt_confirm_huy")
    if pending_huy_pdt:
        dialog_confirm_huy_pdt(pending_huy_pdt)

    # Header: tiêu đề
    st.markdown(
        f"<div style='font-size:1rem;font-weight:700;color:#1a1a2e;"
        f"margin-bottom:8px;'>📋 Lịch sử hóa đơn — {chi_nhanh}</div>",
        unsafe_allow_html=True
    )

    # ── Ô tìm HĐ theo SĐT/Mã (across all CN có quyền, mọi ngày) ──
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

    # Search input (filter trong list hiện tại)
    keyword = st.text_input(
        "Tìm kiếm",
        placeholder="Lọc trong danh sách bên dưới...",
        key="lichsu_search_kw",
        label_visibility="collapsed",
    )

    # Load HĐ
    from_date_iso = _get_from_date_iso()
    days_back = _get_days_back()

    with st.spinner("Đang tải hóa đơn..."):
        invoices = load_hoa_don_pos_history(chi_nhanh, from_date_iso)

    # Range info
    range_label = "hôm nay" if days_back == 0 else f"{days_back + 1} ngày gần nhất"
    st.caption(f"📅 Hiển thị HĐ {range_label} · Tổng: {len(invoices)} HĐ")

    # Filter theo keyword
    filtered = _filter_invoices(invoices, keyword)
    if keyword and len(filtered) != len(invoices):
        st.caption(f"🔍 Lọc còn: {len(filtered)} HĐ")

    # Render list
    if not filtered:
        if keyword:
            st.markdown(
                "<div style='background:#fafafa;border:1px dashed #ddd;"
                "border-radius:10px;padding:24px 16px;text-align:center;"
                "color:#999;margin:8px 0;'>"
                "Không tìm thấy hóa đơn nào khớp"
                "</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='background:#fafafa;border:1px dashed #ddd;"
                "border-radius:10px;padding:24px 16px;text-align:center;"
                f"color:#999;margin:8px 0;'>"
                f"Chưa có hóa đơn {range_label}"
                "</div>",
                unsafe_allow_html=True
            )
    else:
        for inv in filtered:
            _render_invoice_card(inv)

    # Nút "Xem cũ hơn" + "Quay về hôm nay" cùng hàng
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
# RENDER — Kết quả tìm SĐT/Mã (mọi ngày, các CN có quyền)
# ════════════════════════════════════════════════════════════════

def _render_find_results(keyword: str):
    cn_list = get_accessible_branches() or [get_active_branch()]

    with st.spinner("Đang tìm hóa đơn..."):
        results = search_hoa_don_pos(keyword, cn_list, limit=30)

    st.caption(f"🔎 Kết quả tìm '{keyword}' (mọi ngày): {len(results)} HĐ")

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
    if st.button("✕ Xóa tìm kiếm", use_container_width=True,
                 key="lichsu_clear_find"):
        st.session_state["lichsu_find_kw"] = ""
        st.rerun()
