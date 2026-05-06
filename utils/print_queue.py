"""
Print queue — insert lệnh in vào bảng print_queue cho daemon laptop pick lên.

Flow:
- POS gọi enqueue_*() sau khi tạo HĐ/phiếu thành công
- Hàm tự load data từ DB → build text 42 cols → insert print_queue
- Daemon poll, gửi raw text qua TCP 9100 → máy in nhiệt Xprinter

Format text:
- ESC @ (init printer) ở đầu
- Nội dung UTF-8 thuần (Xprinter mode "Modern" hỗ trợ tiếng Việt)
- 4 line feed cuối để đẩy giấy ra ngoài rãnh xé tay (máy không có dao cắt)

3 doc_type:
- 'hoa_don'        — HĐ POS (AHD)
- 'phieu_dat_hang' — phiếu đặt (AHDC)
- 'phieu_doi_tra'  — phiếu đổi/trả (AHDD)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from utils.db import (
    supabase,
    load_hoa_don_pos_by_ma,
    load_phieu_dat_hang_by_ma,
)
from utils.helpers import fmt_vnd

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════

LINE_WIDTH = 42
RESET = "\x1b\x40"          # ESC @ — init printer (clear buffer)
TAIL = "\n\n\n\n"           # 4 line feed cuối để xé giấy

SEP_THIN  = "-" * LINE_WIDTH
SEP_THICK = "=" * LINE_WIDTH

# ── Whitelist CN có máy in ──
# Chỉ các CN trong list này mới enqueue print job. CN ngoài list → skip silent.
# Khi CN khác setup máy in, thêm tên vào set này (giống chính xác giá trị ở
# bảng cau_hinh_chi_nhanh).
PRINT_ENABLED_BRANCHES = {
    "100 Lê Quý Đôn",
}

# Địa chỉ ngắn theo CN (in dòng dưới "DL Watch")
_CN_ADDR_SHORT = {
    "100 Lê Quý Đôn": "100 Lê Quý Đôn, Bà Rịa",
    "Coop Vũng Tàu":  "Coop Vũng Tàu - 36 Nguyễn Thái Học",
    "GO BÀ RỊA":      "Siêu thị GO, Bà Rịa",
}


# ════════════════════════════════════════════════════════════════
# LAYOUT HELPERS
# ════════════════════════════════════════════════════════════════

def _center(s: str, width: int = LINE_WIDTH) -> str:
    s = s.strip()
    if len(s) >= width:
        return s[:width]
    pad = (width - len(s)) // 2
    return " " * pad + s


def _two_cols(left: str, right: str, width: int = LINE_WIDTH) -> str:
    """Trái căn trái, phải căn phải, padding space giữa."""
    left = str(left)
    right = str(right)
    space = width - len(left) - len(right)
    if space < 1:
        # Truncate left nếu không đủ chỗ
        left = left[: max(0, width - len(right) - 1)]
        space = width - len(left) - len(right)
    return left + " " * space + right


def _wrap(text: str, width: int = LINE_WIDTH) -> list[str]:
    """Wrap text giữ word boundary. Trả về list dòng."""
    text = (text or "").strip()
    if not text:
        return [""]
    out = []
    line = ""
    for word in text.split():
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    # Truncate word quá dài
    final = []
    for ln in out:
        while len(ln) > width:
            final.append(ln[:width])
            ln = ln[width:]
        final.append(ln)
    return final or [""]


def _fmt_dt_vn(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(_TZ_VN).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


def _fmt_date_vn(date_str: str) -> str:
    """date_str dạng 'YYYY-MM-DD' → 'DD/MM/YYYY'. Trống → ''."""
    if not date_str:
        return ""
    try:
        s = str(date_str).strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(date_str)


def _header(chi_nhanh: str) -> list[str]:
    """Header chung 3 loại: tên shop + địa chỉ ngắn."""
    addr = _CN_ADDR_SHORT.get(chi_nhanh, chi_nhanh)
    return [
        _center("DL Watch"),
        _center(addr),
    ]


# ════════════════════════════════════════════════════════════════
# BUILDER — HÓA ĐƠN
# ════════════════════════════════════════════════════════════════

def _build_text_hoa_don(hd: dict) -> str:
    chi_nhanh = hd.get("chi_nhanh", "")
    items = hd.get("items", []) or []

    lines = []
    lines.extend(_header(chi_nhanh))
    lines.append(SEP_THICK)
    lines.append("HÓA ĐƠN BÁN HÀNG")
    lines.append(_two_cols("Mã HĐ:",  hd.get("ma_hd", "")))
    lines.append(_two_cols("Ngày:",   _fmt_dt_vn(hd.get("created_at", ""))))
    lines.append(_two_cols("NV bán:", hd.get("nguoi_ban", "—")))
    lines.append(SEP_THIN)

    ten_kh = hd.get("ten_khach") or "Khách lẻ"
    lines.append(_two_cols("Khách:", ten_kh))
    if hd.get("sdt_khach"):
        lines.append(_two_cols("SĐT:", hd["sdt_khach"]))

    lines.append(SEP_THICK)

    # Items
    for ct in items:
        ten = ct.get("ten_hang", "")
        sl  = int(ct.get("so_luong", 0) or 0)
        dg  = int(ct.get("don_gia", 0) or 0)
        gg  = int(ct.get("giam_gia_dong", 0) or 0)
        tt  = int(ct.get("thanh_tien", 0) or 0)

        # Tên hàng wrap
        for w in _wrap(ten):
            lines.append(w)

        # SL x đơn giá ... thành tiền
        left = f"  {sl} x {fmt_vnd(dg)}"
        lines.append(_two_cols(left, fmt_vnd(tt)))

        if gg > 0:
            lines.append(_two_cols("  Giảm:", "-" + fmt_vnd(gg)))

    lines.append(SEP_THIN)

    # Totals
    tong_hang = int(hd.get("tong_tien_hang", 0) or 0)
    gg_don    = int(hd.get("giam_gia_don", 0) or 0)
    can_tra   = int(hd.get("khach_can_tra", 0) or 0)
    tien_coc  = int(hd.get("tien_coc_da_thu", 0) or 0)
    tm        = int(hd.get("tien_mat", 0) or 0)
    ck        = int(hd.get("chuyen_khoan", 0) or 0)
    the       = int(hd.get("the", 0) or 0)
    tien_thua = int(hd.get("tien_thua", 0) or 0)

    lines.append(_two_cols("Tổng tiền hàng:", fmt_vnd(tong_hang)))
    if gg_don > 0:
        lines.append(_two_cols("Giảm giá:", "-" + fmt_vnd(gg_don)))
    lines.append(_two_cols("Khách cần trả:", fmt_vnd(can_tra)))

    lines.append(SEP_THIN)

    if tien_coc > 0:
        lines.append(_two_cols("Tiền cọc đã thu:", fmt_vnd(tien_coc)))
    if tm > 0:
        lines.append(_two_cols("Tiền mặt:", fmt_vnd(tm)))
    if ck > 0:
        lines.append(_two_cols("Chuyển khoản:", fmt_vnd(ck)))
    if the > 0:
        lines.append(_two_cols("Thẻ:", fmt_vnd(the)))
    if tien_thua > 0:
        lines.append(_two_cols("Tiền thừa:", fmt_vnd(tien_thua)))

    lines.append(SEP_THICK)
    lines.append(_center("Cảm ơn quý khách!"))

    return RESET + "\n".join(lines) + TAIL


# ════════════════════════════════════════════════════════════════
# BUILDER — PHIẾU ĐẶT HÀNG
# ════════════════════════════════════════════════════════════════

def _build_text_phieu_dat(p: dict) -> str:
    chi_nhanh = p.get("chi_nhanh", "")

    lines = []
    lines.extend(_header(chi_nhanh))
    lines.append(SEP_THICK)
    lines.append(_center("PHIẾU ĐẶT HÀNG"))
    lines.append(SEP_THICK)
    lines.append("")

    # Mã + ngày hẹn nổi bật ở giữa
    lines.append(_center(f"Mã phiếu: {p.get('ma_phieu', '')}"))
    hen = _fmt_date_vn(p.get("ngay_du_kien_co") or p.get("ngay_hen_tra"))
    if hen:
        lines.append(_center(f"Hẹn trả: {hen}"))
    lines.append("")

    lines.append(SEP_THIN)

    ten_kh = p.get("ten_khach") or "Khách lẻ"
    lines.append(_two_cols("Khách:", ten_kh))
    if p.get("sdt_khach"):
        lines.append(_two_cols("SĐT:", p["sdt_khach"]))
    if p.get("nguoi_tao"):
        lines.append(_two_cols("NV:", p["nguoi_tao"]))
    lines.append(_two_cols("Ngày:", _fmt_dt_vn(p.get("created_at", ""))))

    lines.append(SEP_THICK)
    lines.append("Mặt hàng đặt:")

    ten_hang = p.get("ten_hang") or p.get("ten_hang_yeu_cau") or ""
    for w in _wrap(ten_hang):
        lines.append(w)

    mo_ta = p.get("mo_ta") or ""
    if mo_ta:
        for w in _wrap(mo_ta):
            lines.append("  " + w)

    sl = int(p.get("so_luong", 1) or 1)
    dg = int(p.get("don_gia", 0) or p.get("gia_du_kien", 0) or 0)
    tong = sl * dg

    lines.append(f"SL: {sl}")
    lines.append(_two_cols("Đơn giá dự kiến:", fmt_vnd(dg)))
    if sl > 1:
        lines.append(_two_cols("Tổng dự kiến:", fmt_vnd(tong)))

    lines.append(SEP_THICK)

    coc = int(p.get("tien_coc", 0) or 0)
    coc_tm = int(p.get("coc_tien_mat", 0) or 0)
    coc_ck = int(p.get("coc_chuyen_khoan", 0) or 0)
    coc_the = int(p.get("coc_the", 0) or 0)

    if coc > 0:
        lines.append(_two_cols("Tiền cọc:", fmt_vnd(coc)))
        if coc_tm > 0:
            lines.append(_two_cols("  Tiền mặt:", fmt_vnd(coc_tm)))
        if coc_ck > 0:
            lines.append(_two_cols("  Chuyển khoản:", fmt_vnd(coc_ck)))
        if coc_the > 0:
            lines.append(_two_cols("  Thẻ:", fmt_vnd(coc_the)))
        con_lai = max(0, tong - coc)
        lines.append(_two_cols("Còn lại khi nhận:", fmt_vnd(con_lai)))
    else:
        lines.append("Chưa đặt cọc")

    if p.get("ghi_chu"):
        lines.append(SEP_THIN)
        lines.append("Ghi chú:")
        for w in _wrap(p["ghi_chu"]):
            lines.append("  " + w)

    lines.append(SEP_THICK)
    lines.append(_center("Vui lòng giữ phiếu này"))
    lines.append(_center("khi đến lấy hàng"))

    return RESET + "\n".join(lines) + TAIL


# ════════════════════════════════════════════════════════════════
# BUILDER — PHIẾU ĐỔI/TRẢ
# ════════════════════════════════════════════════════════════════

def _build_text_phieu_doi_tra(pdt: dict) -> str:
    chi_nhanh = pdt.get("chi_nhanh", "")
    items = pdt.get("items", []) or []
    items_tra = [it for it in items if it.get("kieu") == "tra"]
    items_moi = [it for it in items if it.get("kieu") == "moi"]

    lines = []
    lines.extend(_header(chi_nhanh))
    lines.append(SEP_THICK)
    lines.append("PHIẾU ĐỔI/TRẢ HÀNG")
    lines.append(_two_cols("Mã phiếu:", pdt.get("ma_pdt", "")))
    lines.append(_two_cols("HĐ gốc:",   pdt.get("ma_hd_goc", "")))
    lines.append(_two_cols("Loại:",     pdt.get("loai_phieu", "")))
    lines.append(_two_cols("Ngày:",     _fmt_dt_vn(pdt.get("created_at", ""))))
    lines.append(_two_cols("NV:",       pdt.get("nguoi_tao", "—")))

    lines.append(SEP_THIN)
    lines.append(_two_cols("Khách:", pdt.get("ten_khach") or "Khách lẻ"))
    if pdt.get("sdt_khach"):
        lines.append(_two_cols("SĐT:", pdt["sdt_khach"]))

    # Items trả
    if items_tra:
        lines.append(SEP_THICK)
        lines.append("KHÁCH TRẢ LẠI:")
        for ct in items_tra:
            ten = ct.get("ten_hang", "")
            sl = int(ct.get("so_luong", 0) or 0)
            dg = int(ct.get("don_gia", 0) or 0)
            tt = int(ct.get("thanh_tien", 0) or 0)
            for w in _wrap(ten):
                lines.append(w)
            left = f"  {sl} x {fmt_vnd(dg)}"
            lines.append(_two_cols(left, "-" + fmt_vnd(tt)))

    # Items mới
    if items_moi:
        lines.append(SEP_THIN)
        lines.append("KHÁCH MUA MỚI:")
        for ct in items_moi:
            ten = ct.get("ten_hang", "")
            sl = int(ct.get("so_luong", 0) or 0)
            dg = int(ct.get("don_gia", 0) or 0)
            tt = int(ct.get("thanh_tien", 0) or 0)
            for w in _wrap(ten):
                lines.append(w)
            left = f"  {sl} x {fmt_vnd(dg)}"
            lines.append(_two_cols(left, fmt_vnd(tt)))

    lines.append(SEP_THICK)

    tien_tra = int(pdt.get("tien_hang_tra", 0) or 0)
    tien_moi = int(pdt.get("tien_hang_moi", 0) or 0)
    cl       = int(pdt.get("chenh_lech", 0) or 0)

    lines.append(_two_cols("Tiền hàng trả:", "-" + fmt_vnd(tien_tra)))
    if tien_moi > 0:
        lines.append(_two_cols("Tiền hàng mới:", fmt_vnd(tien_moi)))

    if cl > 0:
        lines.append(_two_cols("Khách bù thêm:", fmt_vnd(cl)))
    elif cl < 0:
        lines.append(_two_cols("Cửa hàng hoàn:", fmt_vnd(-cl)))
    else:
        lines.append(_two_cols("Đổi ngang:", "0đ"))

    # PTTT
    tm  = int(pdt.get("tien_mat", 0) or 0)
    ck  = int(pdt.get("chuyen_khoan", 0) or 0)
    the = int(pdt.get("the", 0) or 0)

    if tm != 0 or ck > 0 or the > 0:
        lines.append(SEP_THIN)
        if tm > 0:
            lines.append(_two_cols("Tiền mặt thu:", fmt_vnd(tm)))
        elif tm < 0:
            lines.append(_two_cols("Tiền mặt hoàn:", fmt_vnd(-tm)))
        if ck > 0:
            lines.append(_two_cols("Chuyển khoản:", fmt_vnd(ck)))
        if the > 0:
            lines.append(_two_cols("Thẻ:", fmt_vnd(the)))

    lines.append(SEP_THICK)
    lines.append(_center("Cảm ơn quý khách!"))

    return RESET + "\n".join(lines) + TAIL


# ════════════════════════════════════════════════════════════════
# INSERT print_queue
# ════════════════════════════════════════════════════════════════

def _insert_print_job(doc_type: str, doc_id: str, chi_nhanh: str,
                      text: str, data: dict, created_by: str = "") -> dict:
    """Insert 1 job vào print_queue. Trả về {ok, id?, error?}."""
    if not text or not text.strip():
        return {"ok": False, "error": "Nội dung in rỗng"}
    try:
        payload = {
            "text":  text,
            "title": doc_id,
            "data":  data or {},
        }
        row = {
            "doc_type":     doc_type,
            "doc_id":       doc_id,
            "chi_nhanh":    chi_nhanh,
            "payload_json": payload,
            "created_by":   created_by or "",
        }
        res = supabase.table("print_queue").insert(row).execute()
        if res.data:
            return {"ok": True, "id": res.data[0].get("id")}
        return {"ok": False, "error": "Insert không trả về data"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════

def enqueue_hoa_don(ma_hd: str, created_by: str = "") -> dict:
    """Enqueue lệnh in HĐ POS. Load HĐ qua mã, build text, insert queue."""
    if not ma_hd:
        return {"ok": False, "error": "Thiếu mã HĐ"}
    hd = load_hoa_don_pos_by_ma(ma_hd)
    if not hd:
        return {"ok": False, "error": f"Không tìm thấy HĐ {ma_hd}"}

    chi_nhanh = hd.get("chi_nhanh", "")
    if chi_nhanh not in PRINT_ENABLED_BRANCHES:
        return {"ok": False, "error": "Chi nhánh chưa có máy in"}

    text = _build_text_hoa_don(hd)
    return _insert_print_job(
        doc_type="hoa_don",
        doc_id=ma_hd,
        chi_nhanh=chi_nhanh,
        text=text,
        data={"ma_hd": ma_hd},
        created_by=created_by,
    )


def enqueue_phieu_dat(ma_pdh: str, created_by: str = "") -> dict:
    """Enqueue lệnh in phiếu đặt hàng."""
    if not ma_pdh:
        return {"ok": False, "error": "Thiếu mã phiếu"}
    p = load_phieu_dat_hang_by_ma(ma_pdh)
    if not p:
        return {"ok": False, "error": f"Không tìm thấy phiếu {ma_pdh}"}

    chi_nhanh = p.get("chi_nhanh", "")
    if chi_nhanh not in PRINT_ENABLED_BRANCHES:
        return {"ok": False, "error": "Chi nhánh chưa có máy in"}

    text = _build_text_phieu_dat(p)
    return _insert_print_job(
        doc_type="phieu_dat_hang",
        doc_id=ma_pdh,
        chi_nhanh=chi_nhanh,
        text=text,
        data={"ma_pdh": ma_pdh},
        created_by=created_by,
    )


def enqueue_phieu_doi_tra(ma_pdt: str, created_by: str = "") -> dict:
    """Enqueue lệnh in phiếu đổi/trả. Load + items qua 2 query."""
    if not ma_pdt:
        return {"ok": False, "error": "Thiếu mã phiếu"}
    try:
        res = supabase.table("phieu_doi_tra_pos").select("*") \
            .eq("ma_pdt", ma_pdt).limit(1).execute()
        if not res.data:
            return {"ok": False, "error": f"Không tìm thấy phiếu {ma_pdt}"}
        pdt = res.data[0]

        res_ct = supabase.table("phieu_doi_tra_pos_ct").select("*") \
            .eq("ma_pdt", ma_pdt).execute()
        pdt["items"] = res_ct.data or []
    except Exception as e:
        return {"ok": False, "error": f"Lỗi load phiếu: {e}"}

    chi_nhanh = pdt.get("chi_nhanh", "")
    if chi_nhanh not in PRINT_ENABLED_BRANCHES:
        return {"ok": False, "error": "Chi nhánh chưa có máy in"}

    text = _build_text_phieu_doi_tra(pdt)
    return _insert_print_job(
        doc_type="phieu_doi_tra",
        doc_id=ma_pdt,
        chi_nhanh=chi_nhanh,
        text=text,
        data={"ma_pdt": ma_pdt},
        created_by=created_by,
    )
