"""
Module Thông tin — phiếu sửa chữa "Chờ giao khách" của CN đang chọn.

UI flow:
- Header card: tên CN + count phiếu sẵn giao
- Search 1 ô: SĐT / mã phiếu / tên khách
- List card: ngày tạo, mã phiếu, tên khách, hiệu đồng hồ, hẹn trả, trả trước
- Bấm vào card → dialog chi tiết (read-only)
"""

import streamlit as st
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_active_branch
from utils.db import supabase
from utils.helpers import fmt_vnd

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


_TT_CSS = """
<style>
/* Header card */
.st-key-tt-header-card {
    background: #fff;
    border: 1px solid #ececec;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
}

/* Search row */
.st-key-tt-search-row {
    margin-bottom: 8px;
}

/* Phieu card */
[class*="st-key-tt-card-"] {
    background: #fff;
    border: 1px solid #ececec;
    border-radius: 12px;
    padding: 10px 10px 8px;
    margin: 8px 0;
    overflow: hidden;
}

[class*="st-key-tt-card-"] div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 10px !important;
    align-items: center !important;
    width: 100% !important;
}
[class*="st-key-tt-card-"] div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;
}

/* Click overlay button */
[class*="st-key-tt-cardbtn-"] button {
    background: transparent !important;
    border: none !important;
    padding: 4px 4px !important;
    text-align: left !important;
    min-height: 0 !important;
    box-shadow: none !important;
}
[class*="st-key-tt-cardbtn-"] button p {
    text-align: left !important;
    margin: 0 !important;
}
[class*="st-key-tt-cardbtn-"] button:hover {
    background: #fafafa !important;
}

/* Empty state */
.tt-empty {
    background: #fafafa;
    border: 1px dashed #ddd;
    border-radius: 10px;
    padding: 28px 16px;
    text-align: center;
    color: #999;
    margin: 10px 0;
}
</style>
"""

_VN_MONTHS = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "10", 11: "11", 12: "12",
}


# ════════════════════════════════════════════════════════════════
# DATA
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def _load_phieu_sc_cho_giao(chi_nhanh: str) -> list[dict]:
    """Load phiếu sửa chữa 'Chờ giao khách' của 1 CN, sort newest-first."""
    try:
        res = supabase.table("phieu_sua_chua") \
            .select("*") \
            .eq("chi_nhanh", chi_nhanh) \
            .eq("trang_thai", "Chờ giao khách") \
            .order("created_at", desc=True) \
            .limit(200).execute()
        return res.data or []
    except Exception as e:
        st.error(f"Lỗi tải phiếu sửa chữa: {e}")
        return []


def _load_chi_tiet(ma_phieu: str) -> list[dict]:
    """Load chi tiết dịch vụ/linh kiện của 1 phiếu."""
    if not ma_phieu:
        return []
    try:
        res = supabase.table("phieu_sua_chua_chi_tiet") \
            .select("*") \
            .eq("ma_phieu", ma_phieu).execute()
        return res.data or []
    except Exception:
        return []


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _to_vn(iso_str: str) -> datetime | None:
    """Parse ISO → datetime giờ VN. None nếu invalid."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(_TZ_VN)
    except Exception:
        return None


def _date_strip_html(iso_str: str) -> str:
    """Tem ngày THG/DD đỏ ở góc trái card (giống tab Lịch sử)."""
    dt = _to_vn(iso_str)
    if dt is None:
        thg, dd = "—", "—"
    else:
        thg = _VN_MONTHS.get(dt.month, str(dt.month))
        dd = f"{dt.day:02d}"
    return (
        f"<div style='display:flex;flex-direction:column;align-items:center;"
        f"width:54px;'>"
        f"<div style='background:#e63946;color:#fff;font-size:0.62rem;"
        f"font-weight:700;letter-spacing:0.5px;padding:2px 0;width:100%;"
        f"text-align:center;border-top-left-radius:6px;"
        f"border-top-right-radius:6px;'>THG {thg}</div>"
        f"<div style='background:#fff;border:1px solid #f0f0f0;border-top:none;"
        f"font-size:1.4rem;font-weight:800;color:#1a1a2e;width:100%;"
        f"text-align:center;padding:2px 0;'>{dd}</div>"
        f"</div>"
    )


def _fmt_hen_tra(date_str: str) -> str:
    """date_str từ DB ISO date 'YYYY-MM-DD' → 'DD/MM'."""
    if not date_str:
        return "—"
    try:
        # Có thể là date hoặc datetime
        s = str(date_str).strip()
        if "T" in s or " " in s:
            dt = _to_vn(s)
            return dt.strftime("%d/%m") if dt else s
        # Plain date YYYY-MM-DD
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m")
    except Exception:
        return str(date_str)


def _fmt_dt_full(iso_str: str) -> str:
    dt = _to_vn(iso_str)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else (iso_str or "")


def _normalize_search(s: str) -> str:
    """Lower + strip + bỏ dấu space để fuzzy match."""
    return re.sub(r"\s+", "", str(s or "").lower())


def _filter_phieu(phieu_list: list[dict], keyword: str) -> list[dict]:
    """Filter client-side theo SĐT / mã phiếu / tên khách."""
    kw = (keyword or "").strip().lower()
    if not kw:
        return phieu_list

    out = []
    for p in phieu_list:
        ma = str(p.get("ma_phieu", "") or "").lower()
        sdt = str(p.get("sdt_khach", "") or "").lower()
        ten = str(p.get("ten_khach", "") or "").lower()
        # Match khi keyword nằm trong 1 trong 3 field, hoặc match phần số của mã
        # (vd "900" khớp "SC000900")
        if kw in ma or kw in sdt or kw in ten:
            out.append(p)
            continue
        # Nếu mã dạng "SC<digits>" thử match phần số
        if ma.startswith("sc"):
            num_part = ma[2:].lstrip("0") or "0"
            if num_part.endswith(kw):
                out.append(p)
    return out


# ════════════════════════════════════════════════════════════════
# DIALOG — chi tiết phiếu
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết phiếu sửa chữa")
def _dialog_chi_tiet(phieu: dict):
    ma = phieu.get("ma_phieu", "")

    st.markdown(
        f"<div style='font-family:monospace;font-size:1.1rem;font-weight:700;"
        f"color:#1a1a2e;'>{ma}</div>"
        f"<div style='font-size:0.82rem;color:#888;margin-top:2px;'>"
        f"Tạo: {_fmt_dt_full(phieu.get('created_at',''))}"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown("<hr style='margin:10px 0 8px;'>", unsafe_allow_html=True)

    # Thông tin tiếp nhận
    rows = [
        ("Khách hàng", phieu.get("ten_khach") or "—"),
        ("SĐT", phieu.get("sdt_khach") or "—"),
        ("Hiệu ĐH", phieu.get("hieu_dong_ho") or "—"),
        ("Đặc điểm", phieu.get("dac_diem") or "—"),
        ("Loại YC", phieu.get("loai_yeu_cau") or "—"),
        ("NV tiếp nhận", phieu.get("nguoi_tiep_nhan") or "—"),
        ("Hẹn trả", _fmt_hen_tra(phieu.get("ngay_hen_tra"))),
    ]
    info_html = "<div style='background:#f7f7fa;border:1px solid #e8e8ee;" \
                "border-radius:8px;padding:10px 12px;font-size:0.88rem;'>"
    for lbl, val in rows:
        info_html += (
            f"<div style='display:flex;padding:3px 0;'>"
            f"<span style='color:#777;min-width:100px;'>{lbl}:</span>"
            f"<span style='color:#1a1a2e;font-weight:500;flex:1;'>{val}</span>"
            f"</div>"
        )
    info_html += "</div>"
    st.markdown(info_html, unsafe_allow_html=True)

    # Mô tả lỗi
    if phieu.get("mo_ta_loi"):
        st.markdown(
            f"<div style='font-size:0.85rem;font-weight:600;color:#1a1a2e;"
            f"margin:12px 0 4px;'>📝 Mô tả lỗi:</div>"
            f"<div style='background:#fff;border:1px solid #e8e8e8;"
            f"border-radius:8px;padding:8px 12px;font-size:0.88rem;"
            f"color:#1a1a2e;line-height:1.5;'>{phieu['mo_ta_loi']}</div>",
            unsafe_allow_html=True
        )

    # Ghi chú nội bộ
    if phieu.get("ghi_chu_noi_bo"):
        st.markdown(
            f"<div style='font-size:0.85rem;font-weight:600;color:#1a1a2e;"
            f"margin:10px 0 4px;'>🔧 Ghi chú nội bộ:</div>"
            f"<div style='background:#fffbe6;border:1px solid #f0d97a;"
            f"border-radius:8px;padding:8px 12px;font-size:0.88rem;"
            f"color:#856404;line-height:1.5;'>{phieu['ghi_chu_noi_bo']}</div>",
            unsafe_allow_html=True
        )

    # Dịch vụ / linh kiện
    ct = _load_chi_tiet(ma)
    st.markdown(
        "<div style='font-size:0.85rem;font-weight:600;color:#1a1a2e;"
        "margin:12px 0 4px;'>🔧 Dịch vụ / Linh kiện:</div>",
        unsafe_allow_html=True
    )
    if not ct:
        st.caption("_(Chưa có)_")
    else:
        items_html = "<div style='background:#fafafa;border:1px solid #eee;" \
                     "border-radius:8px;padding:8px 10px;'>"
        tong = 0
        for r in ct:
            sl = int(r.get("so_luong") or 0)
            dg = int(r.get("don_gia") or 0)
            tt = sl * dg
            tong += tt
            ten = r.get("ten_hang", "") or ""
            loai = r.get("loai_dong", "") or ""
            items_html += (
                f"<div style='padding:4px 0;border-bottom:1px dashed #e8e8e8;'>"
                f"<div style='font-size:0.86rem;color:#1a1a2e;font-weight:500;'>"
                f"{ten}</div>"
                f"<div style='display:flex;justify-content:space-between;"
                f"font-size:0.78rem;color:#666;margin-top:2px;'>"
                f"<span>{loai} · SL {sl} × {fmt_vnd(dg)}</span>"
                f"<span style='color:#1a1a2e;font-weight:600;'>{fmt_vnd(tt)}</span>"
                f"</div></div>"
            )
        items_html += "</div>"
        st.markdown(items_html, unsafe_allow_html=True)

        # Tổng tiền
        tra_truoc = int(phieu.get("khach_tra_truoc") or 0)
        con_lai = max(0, tong - tra_truoc)
        summary_html = (
            "<div style='background:#fff;border:1px solid #e8e8e8;"
            "border-radius:8px;padding:8px 12px;margin-top:8px;'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:3px 0;font-size:0.86rem;'>"
            f"<span style='color:#777;'>Tổng cộng:</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{fmt_vnd(tong)}</span>"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:3px 0;font-size:0.86rem;'>"
            f"<span style='color:#777;'>Đã trả trước:</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{fmt_vnd(tra_truoc)}</span>"
            f"</div>"
            f"<hr style='border:none;border-top:1px dashed #ddd;margin:4px 0;'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:3px 0;font-size:0.92rem;'>"
            f"<span style='color:#555;font-weight:600;'>Khách cần trả:</span>"
            f"<span style='color:#e63946;font-weight:700;'>{fmt_vnd(con_lai)}</span>"
            f"</div>"
            "</div>"
        )
        st.markdown(summary_html, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# RENDER — card 1 phiếu
# ════════════════════════════════════════════════════════════════

def _render_phieu_card(phieu: dict):
    ma = phieu.get("ma_phieu", "")
    ten_kh = phieu.get("ten_khach") or "—"
    sdt = phieu.get("sdt_khach") or ""
    hieu = phieu.get("hieu_dong_ho") or "—"
    hen = _fmt_hen_tra(phieu.get("ngay_hen_tra"))
    tra_truoc = int(phieu.get("khach_tra_truoc") or 0)
    created = phieu.get("created_at", "")

    container_key = f"tt-card-{ma}"
    btn_key = f"tt-cardbtn-{ma}"

    sdt_html = (f"<span style='color:#888;'>📞 {sdt}</span>" if sdt else "")
    tra_html = (f"<span>Trả trước: <b style='color:#1a1a2e;'>"
                f"{fmt_vnd(tra_truoc)}</b></span>"
                if tra_truoc > 0 else "")

    meta_parts = [f"⌚ {hieu}", f"Hẹn {hen}"]
    if tra_html:
        meta_parts_html = " · ".join(meta_parts) + " · " + tra_html
    else:
        meta_parts_html = " · ".join(meta_parts)

    with st.container(key=container_key):
        col_date, col_body = st.columns([1, 5])
        with col_date:
            st.markdown(_date_strip_html(created), unsafe_allow_html=True)
        with col_body:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:flex-start;gap:8px;'>"
                f"<div style='font-family:monospace;font-size:1rem;"
                f"font-weight:800;color:#1a1a2e;'>{ma}</div>"
                f"</div>"
                f"<div style='font-size:0.88rem;color:#1a1a2e;margin-top:2px;"
                f"display:flex;gap:10px;flex-wrap:wrap;align-items:center;'>"
                f"<span>{ten_kh}</span>{sdt_html}</div>"
                f"<div style='font-size:0.78rem;color:#666;margin-top:6px;"
                f"display:flex;flex-wrap:wrap;gap:4px 6px;'>"
                f"{meta_parts_html}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with st.container(key=btn_key):
            if st.button("Xem chi tiết", key=f"tt_card_{ma}",
                         use_container_width=True):
                _dialog_chi_tiet(phieu)


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_thong_tin():
    st.markdown(_TT_CSS, unsafe_allow_html=True)

    chi_nhanh = get_active_branch()

    # Header card
    with st.container(key="tt-header-card"):
        with st.spinner("Đang tải..."):
            phieu_list = _load_phieu_sc_cho_giao(chi_nhanh)

        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;'>"
            f"<div style='width:38px;height:38px;border-radius:10px;"
            f"background:#fff5f5;display:flex;align-items:center;"
            f"justify-content:center;font-size:1.2rem;'>📢</div>"
            f"<div style='flex:1;min-width:0;'>"
            f"<div style='font-size:1.05rem;font-weight:800;color:#1a1a2e;'>"
            f"Phiếu sửa chữa sẵn giao</div>"
            f"<div style='font-size:0.85rem;color:#888;'>"
            f"{chi_nhanh} · <b>{len(phieu_list)}</b> phiếu chờ giao khách"
            f"</div>"
            f"</div></div>",
            unsafe_allow_html=True
        )

    # Search
    with st.container(key="tt-search-row"):
        with st.container(key="numkb-tel-tt-find"):
            kw = st.text_input(
                "Tìm phiếu",
                placeholder="🔎  Tìm theo mã phiếu, SĐT, tên khách...",
                key="tt_find_kw",
                label_visibility="collapsed",
            )

    filtered = _filter_phieu(phieu_list, kw)

    if not filtered:
        if kw and kw.strip():
            st.markdown(
                "<div class='tt-empty'>Không tìm thấy phiếu khớp</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div class='tt-empty'>Hiện không có phiếu sửa chữa nào "
                f"sẵn giao tại {chi_nhanh}.</div>",
                unsafe_allow_html=True
            )
        return

    if kw and kw.strip():
        st.caption(f"🔎 {len(filtered)} kết quả khớp '{kw}'")

    for phieu in filtered:
        _render_phieu_card(phieu)
