"""Database client + load functions dùng cho POS app."""

import streamlit as st
from supabase import create_client, Client


# ── Supabase client ──
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("⚠️ Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()


# ── Load nhân viên active (cho màn login) ──
@st.cache_data(ttl=300)
def load_nhan_vien_active() -> list[dict]:
    """
    Trả về list nhân viên active để hiển thị ở màn login.
    Mỗi item: {id, username, ho_ten, role, avatar_url, chi_nhanh_list}
    """
    try:
        res = supabase.table("nhan_vien").select("id,username,ho_ten,role,avatar_url") \
            .eq("active", True).order("ho_ten").execute()
        if not res.data:
            return []

        nv_list = res.data

        # Lấy chi nhánh phân quyền cho từng NV
        cn_res = supabase.table("nhan_vien_chi_nhanh") \
            .select("nhan_vien_id,chi_nhanh(ten)").execute()
        cn_map = {}
        for r in (cn_res.data or []):
            nv_id = r.get("nhan_vien_id")
            cn_name = (r.get("chi_nhanh") or {}).get("ten")
            if nv_id and cn_name:
                cn_map.setdefault(nv_id, []).append(cn_name)

        for nv in nv_list:
            nv["chi_nhanh_list"] = cn_map.get(nv["id"], [])
        return nv_list
    except Exception as e:
        st.error(f"Lỗi tải nhân viên: {e}")
        return []


# ── Load PIN của 1 nhân viên ──
def load_pin(nhan_vien_id: int) -> str | None:
    """
    Trả về pin_hash nếu NV đã set PIN, None nếu chưa.
    """
    try:
        res = supabase.table("pin_code").select("pin_hash") \
            .eq("nhan_vien_id", nhan_vien_id).limit(1).execute()
        if res.data:
            return res.data[0].get("pin_hash")
        return None
    except Exception:
        return None


# ── Load danh sách hàng hóa + tồn kho cho POS ──
@st.cache_data(ttl=300)
def load_hang_hoa_pos(chi_nhanh: str) -> list[dict]:
    """
    Load tất cả hàng hóa active có giá > 0, kèm tồn kho tại chi_nhanh.
    Cache 5 phút.

    Phân biệt loai_sp:
      - "Hàng hóa" → tồn lấy từ the_kho thực tế
      - "Dịch vụ"  → tồn = 999999 (vô hạn, không cần check)

    Returns: list of dict {ma_hang, ma_vach, ten_hang, gia_ban, ton, loai_sp}
    """
    try:
        # 1. Load master: hàng hóa + dịch vụ active có giá > 0
        rows, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("hang_hoa") \
                .select("ma_hang,ma_vach,ten_hang,gia_ban,loai_sp") \
                .neq("active", False) \
                .gt("gia_ban", 0) \
                .range(offset, offset + batch - 1).execute()
            if not res.data:
                break
            rows.extend(res.data)
            if len(res.data) < batch:
                break
            offset += batch

        if not rows:
            return []

        # 2. Load tồn kho chi nhánh (chỉ cần cho hàng hóa)
        ton_rows, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("the_kho") \
                .select('"Mã hàng","Tồn cuối kì"') \
                .eq("Chi nhánh", chi_nhanh) \
                .range(offset, offset + batch - 1).execute()
            if not res.data:
                break
            ton_rows.extend(res.data)
            if len(res.data) < batch:
                break
            offset += batch

        # Map: ma_hang -> tồn (cộng dồn nếu có nhiều dòng)
        ton_map = {}
        for r in ton_rows:
            mh = str(r.get("Mã hàng", "")).strip()
            ton = int(r.get("Tồn cuối kì", 0) or 0)
            ton_map[mh] = ton_map.get(mh, 0) + ton

        # 3. Merge — phân biệt theo loai_sp
        result = []
        for r in rows:
            ma = str(r.get("ma_hang", "")).strip()
            loai_sp = str(r.get("loai_sp", "") or "Hàng hóa").strip()
            # Dịch vụ → tồn vô hạn; Hàng hóa → lấy từ the_kho
            if loai_sp == "Dịch vụ":
                ton = 999999
            else:
                ton = ton_map.get(ma, 0)
            result.append({
                "ma_hang":  ma,
                "ma_vach":  str(r.get("ma_vach", "") or "").strip(),
                "ten_hang": str(r.get("ten_hang", "") or ""),
                "gia_ban":  int(r.get("gia_ban", 0) or 0),
                "ton":      ton,
                "loai_sp":  loai_sp,
            })
        return result
    except Exception as e:
        st.error(f"Lỗi tải hàng hóa: {e}")
        return []


# ── Set PIN lần đầu ──
def set_pin(nhan_vien_id: int, pin_hash: str) -> bool:
    """Insert hoặc update pin_code cho NV."""
    try:
        from utils.helpers import now_vn_iso
        supabase.table("pin_code").upsert({
            "nhan_vien_id": nhan_vien_id,
            "pin_hash":     pin_hash,
            "updated_at":   now_vn_iso(),
        }, on_conflict="nhan_vien_id").execute()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu PIN: {e}")
        return False


# ════════════════════════════════════════════════════════════════
# KHÁCH HÀNG — lookup + tạo mới
# ════════════════════════════════════════════════════════════════

def lookup_khach_hang_by_sdt(sdt: str) -> dict | None:
    """
    Tra cứu khách hàng theo SĐT.
    Trả về dict {ma_kh, ten_kh, sdt, ...} hoặc None nếu không tìm thấy.
    """
    if not sdt or not sdt.strip():
        return None
    try:
        sdt_clean = sdt.strip().replace(" ", "")
        res = supabase.table("khach_hang").select("*") \
            .eq("sdt", sdt_clean).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def _gen_ma_akh() -> str:
    """Sinh mã AKH kế tiếp qua Postgres function."""
    try:
        from utils.helpers import now_vn
        res = supabase.rpc("get_next_akh_num", {}).execute()
        data = res.data
        if isinstance(data, list):
            num = int(data[0]) if data else 1
        elif data is not None:
            num = int(data)
        else:
            num = 1
        return f"AKH{num:06d}"
    except Exception:
        from utils.helpers import now_vn
        return f"AKH{now_vn().strftime('%y%m%d%H%M')}"


def upsert_khach_hang(ten: str, sdt: str, chi_nhanh: str = "") -> str:
    """
    Thêm mới khách nếu SĐT chưa có, hoặc trả về ma_kh nếu đã có.
    Trả về ma_kh (string), hoặc "" nếu lỗi.
    """
    sdt_clean = clean_phone(sdt)
    ten_clean = clean_name(ten)
    if not sdt_clean:
        return ""
    existing = lookup_khach_hang_by_sdt(sdt_clean)
    if existing:
        return existing.get("ma_kh", "")
    try:
        from utils.helpers import now_vn_iso
        ma = _gen_ma_akh()
        supabase.table("khach_hang").insert({
            "ma_kh":         ma,
            "ten_kh":        ten_clean,
            "sdt":           sdt_clean,
            "chi_nhanh_tao": chi_nhanh,
            "created_at":    now_vn_iso(),
            "updated_at":    now_vn_iso(),
        }).execute()
        return ma
    except Exception as e:
        st.error(f"Lỗi tạo khách hàng: {e}")
        return ""


# ════════════════════════════════════════════════════════════════
# RPC — Tạo hóa đơn POS (atomic)
# ════════════════════════════════════════════════════════════════

def tao_hoa_don_pos_rpc(payload: dict) -> dict:
    """
    Gọi RPC tao_hoa_don_pos.
    Returns dict: {ok: bool, ma_hd?: str, tien_thua?: int, error?: str}
    """
    try:
        res = supabase.rpc("tao_hoa_don_pos", {"payload": payload}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════
# LỊCH SỬ HÓA ĐƠN POS
# ════════════════════════════════════════════════════════════════

def load_hoa_don_pos_history(chi_nhanh: str, from_date_iso: str) -> list[dict]:
    """
    Load HĐ POS của 1 chi nhánh từ from_date_iso (>=) tới hiện tại.
    from_date_iso: 'YYYY-MM-DDT00:00:00+07:00' (tính theo VN time)
    Trả về list HĐ đã sort newest-first, kèm chi tiết items mỗi HĐ.
    """
    try:
        # 1. Load header
        res = supabase.table("hoa_don_pos") \
            .select("*") \
            .eq("chi_nhanh", chi_nhanh) \
            .gte("created_at", from_date_iso) \
            .order("created_at", desc=True) \
            .limit(500) \
            .execute()

        headers = res.data or []
        if not headers:
            return []

        # 2. Load chi tiết tất cả HĐ này trong 1 query
        ma_hd_list = [h["ma_hd"] for h in headers]
        res_ct = supabase.table("hoa_don_pos_ct") \
            .select("*") \
            .in_("ma_hd", ma_hd_list) \
            .execute()

        # Map ma_hd -> list items
        items_map: dict[str, list] = {}
        for ct in (res_ct.data or []):
            items_map.setdefault(ct["ma_hd"], []).append(ct)

        # 3. Merge items vào header
        for h in headers:
            h["items"] = items_map.get(h["ma_hd"], [])

        return headers
    except Exception as e:
        st.error(f"Lỗi tải lịch sử hóa đơn: {e}")
        return []


def huy_hoa_don_pos_rpc(ma_hd: str, cancelled_by: str = "") -> dict:
    """
    Gọi RPC huy_hoa_don_pos — hoàn lại tồn kho + đổi trạng thái sang 'Đã hủy'.
    Returns dict: {ok: bool, error?: str}
    """
    try:
        res = supabase.rpc("huy_hoa_don_pos", {
            "p_ma_hd":        ma_hd,
            "p_cancelled_by": cancelled_by or "",
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════
# ĐỔI / TRẢ HÀNG (Bước 7)
# ════════════════════════════════════════════════════════════════

def search_hoa_don_pos(keyword: str, chi_nhanh_list: list[str],
                       limit: int = 30) -> list[dict]:
    """
    Tìm HĐ POS theo SĐT hoặc mã HĐ (full hoặc partial), trong các CN cho phép.
    Trả về list HĐ kèm items, sort newest-first.
    """
    kw = (keyword or "").strip()
    if not kw or not chi_nhanh_list:
        return []
    try:
        q = supabase.table("hoa_don_pos").select("*").in_("chi_nhanh", chi_nhanh_list)
        q = q.or_(f"ma_hd.ilike.%{kw}%,sdt_khach.ilike.%{kw}%")
        res = q.order("created_at", desc=True).limit(limit).execute()
        headers = res.data or []
        if not headers:
            return []

        ma_hd_list = [h["ma_hd"] for h in headers]
        res_ct = supabase.table("hoa_don_pos_ct").select("*") \
            .in_("ma_hd", ma_hd_list).execute()
        items_map: dict[str, list] = {}
        for ct in (res_ct.data or []):
            items_map.setdefault(ct["ma_hd"], []).append(ct)
        for h in headers:
            h["items"] = items_map.get(h["ma_hd"], [])
        return headers
    except Exception as e:
        st.error(f"Lỗi tìm hóa đơn: {e}")
        return []


def load_hoa_don_pos_by_ma(ma_hd: str) -> dict | None:
    """Load 1 HĐ POS theo mã (kèm items + loai_sp). Trả về None nếu không có."""
    if not ma_hd:
        return None
    try:
        res = supabase.table("hoa_don_pos").select("*") \
            .eq("ma_hd", ma_hd).limit(1).execute()
        if not res.data:
            return None
        h = res.data[0]
        res_ct = supabase.table("hoa_don_pos_ct").select("*") \
            .eq("ma_hd", ma_hd).execute()
        items = res_ct.data or []

        # Enrich với loai_sp từ hang_hoa (cần để UI đổi/trả biết skip Dịch vụ)
        if items:
            ma_hang_list = list({ct["ma_hang"] for ct in items if ct.get("ma_hang")})
            res_hh = supabase.table("hang_hoa") \
                .select("ma_hang,loai_sp") \
                .in_("ma_hang", ma_hang_list).execute()
            loai_map = {r["ma_hang"]: (r.get("loai_sp") or "Hàng hóa")
                        for r in (res_hh.data or [])}
            for ct in items:
                ct["loai_sp"] = loai_map.get(ct.get("ma_hang", ""), "Hàng hóa")

        h["items"] = items
        return h
    except Exception:
        return None


def load_phieu_doi_tra_by_hd(ma_hd_goc: str) -> list[dict]:
    """
    Load tất cả phiếu đổi/trả của 1 HĐ gốc, kèm items, sort newest-first.
    Bao gồm cả phiếu Đã hủy (UI sẽ hiện xám).
    """
    if not ma_hd_goc:
        return []
    try:
        res = supabase.table("phieu_doi_tra_pos").select("*") \
            .eq("ma_hd_goc", ma_hd_goc) \
            .order("created_at", desc=True).execute()
        headers = res.data or []
        if not headers:
            return []
        ma_pdt_list = [h["ma_pdt"] for h in headers]
        res_ct = supabase.table("phieu_doi_tra_pos_ct").select("*") \
            .in_("ma_pdt", ma_pdt_list).execute()
        items_map: dict[str, list] = {}
        for ct in (res_ct.data or []):
            items_map.setdefault(ct["ma_pdt"], []).append(ct)
        for h in headers:
            h["items"] = items_map.get(h["ma_pdt"], [])
        return headers
    except Exception as e:
        st.error(f"Lỗi tải phiếu đổi/trả: {e}")
        return []


def get_sl_da_tra_map(ma_hd_goc: str) -> dict[str, int]:
    """
    Trả về map {ma_hang: tổng SL đã trả} từ các phiếu đổi/trả Hoàn thành
    của 1 HĐ gốc. Dùng để client validate SL còn lại có thể trả.
    """
    out: dict[str, int] = {}
    if not ma_hd_goc:
        return out
    try:
        res_h = supabase.table("phieu_doi_tra_pos").select("ma_pdt") \
            .eq("ma_hd_goc", ma_hd_goc) \
            .eq("trang_thai", "Hoàn thành").execute()
        ma_pdt_list = [r["ma_pdt"] for r in (res_h.data or [])]
        if not ma_pdt_list:
            return out
        res = supabase.table("phieu_doi_tra_pos_ct") \
            .select("ma_hang,so_luong,kieu") \
            .in_("ma_pdt", ma_pdt_list).execute()
        for r in (res.data or []):
            if r.get("kieu") != "tra":
                continue
            mh = r.get("ma_hang", "")
            out[mh] = out.get(mh, 0) + int(r.get("so_luong") or 0)
        return out
    except Exception:
        return out


def tao_phieu_doi_tra_pos_rpc(payload: dict) -> dict:
    """
    Gọi RPC tao_phieu_doi_tra_pos.
    Returns dict: {ok, ma_pdt, loai_phieu, tien_hang_tra, tien_hang_moi, chenh_lech}
                  hoặc {ok: false, error}
    """
    try:
        res = supabase.rpc("tao_phieu_doi_tra_pos", {"payload": payload}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def huy_phieu_doi_tra_pos_rpc(ma_pdt: str, cancelled_by: str = "") -> dict:
    """
    Gọi RPC huy_phieu_doi_tra_pos — đảo lại stock + set Đã hủy.
    """
    try:
        res = supabase.rpc("huy_phieu_doi_tra_pos", {
            "p_ma_pdt":       ma_pdt,
            "p_cancelled_by": cancelled_by or "",
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@st.cache_data(ttl=60)
def load_phieu_doi_tra_pos_history(chi_nhanh: str, from_date_iso: str) -> list[dict]:
    """
    Load phiếu đổi/trả POS của 1 chi nhánh từ from_date_iso, sort newest-first.
    TTL 60s (ngắn hơn HĐ vì thay đổi thường xuyên hơn).
    """
    try:
        res = supabase.table("phieu_doi_tra_pos") \
            .select("*") \
            .eq("chi_nhanh", chi_nhanh) \
            .gte("created_at", from_date_iso) \
            .order("created_at", desc=True) \
            .limit(200).execute()
        headers = res.data or []
        if not headers:
            return []
        ma_pdt_list = [h["ma_pdt"] for h in headers]
        res_ct = supabase.table("phieu_doi_tra_pos_ct").select("*") \
            .in_("ma_pdt", ma_pdt_list).execute()
        items_map: dict[str, list] = {}
        for ct in (res_ct.data or []):
            items_map.setdefault(ct["ma_pdt"], []).append(ct)
        for h in headers:
            h["items"] = items_map.get(h["ma_pdt"], [])
        return headers
    except Exception as e:
        st.error(f"Lỗi tải phiếu đổi/trả: {e}")
        return []



# ════════════════════════════════════════════════════════════════
# ĐẶT HÀNG THEO YÊU CẦU (Bước 8)
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def load_phieu_dat_hang(chi_nhanh: str,
                        trang_thai_filter: list | None = None) -> list:
    """
    Load phiếu đặt hàng của 1 chi nhánh, sort newest-first.
    trang_thai_filter=None → tất cả. Thường truyền ['Chờ đặt', 'Chờ lấy'].
    """
    try:
        q = supabase.table("phieu_dat_hang").select("*") \
            .eq("chi_nhanh", chi_nhanh) \
            .order("created_at", desc=True) \
            .limit(300)
        if trang_thai_filter:
            q = q.in_("trang_thai", trang_thai_filter)
        res = q.execute()
        return res.data or []
    except Exception as e:
        st.error(f"Lỗi tải phiếu đặt hàng: {e}")
        return []


def load_phieu_dat_hang_by_ma(ma_phieu: str) -> dict | None:
    """Load 1 phiếu đặt hàng theo mã."""
    if not ma_phieu:
        return None
    try:
        res = supabase.table("phieu_dat_hang").select("*") \
            .eq("ma_phieu", ma_phieu).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def tao_phieu_dat_hang_rpc(payload: dict) -> dict:
    """Tạo phiếu đặt hàng mới. Returns {ok, ma_phieu} hoặc {ok: false, error}."""
    try:
        res = supabase.rpc("tao_phieu_dat_hang", {"payload": payload}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def chuyen_cho_lay_rpc(ma_phieu: str) -> dict:
    """Chuyển trạng thái Chờ đặt → Chờ lấy."""
    try:
        res = supabase.rpc("chuyen_cho_lay_dat_hang",
                           {"p_ma_phieu": ma_phieu}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def hoan_thanh_dat_hang_rpc(payload: dict) -> dict:
    """
    Hoàn thành phiếu đặt — auto tạo HĐ POS (bypass stock check).
    Returns {ok, ma_phieu, ma_hd} hoặc {ok: false, error}.
    """
    try:
        res = supabase.rpc("hoan_thanh_dat_hang", {"payload": payload}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def huy_phieu_dat_hang_rpc(ma_phieu: str, cancelled_by: str,
                            coc_xu_ly: str | None = None) -> dict:
    """Hủy phiếu đặt hàng. coc_xu_ly: 'Trả cọc' | 'Giữ cọc' | None."""
    try:
        res = supabase.rpc("huy_phieu_dat_hang", {
            "p_ma_phieu":     ma_phieu,
            "p_cancelled_by": cancelled_by or "",
            "p_coc_xu_ly":    coc_xu_ly or "",
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return {"ok": False, "error": "RPC trả về kết quả không hợp lệ"}
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ════════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ════════════════════════════════════════════════════════════════

def clean_phone(s: str) -> str:
    """Chuẩn hoá SĐT: chỉ giữ chữ số, max 15 ký tự."""
    if not s:
        return ""
    return "".join(c for c in str(s) if c.isdigit())[:15]


def clean_name(s: str) -> str:
    """Trim + thu gọn whitespace liên tiếp + max 100 ký tự."""
    if not s:
        return ""
    return " ".join(str(s).split())[:100]


# ════════════════════════════════════════════════════════════════
# APSC (Hóa đơn sửa chữa) — đọc từ hoa_don table (web app insert vào)
# Schema khác hoa_don_pos: cột tiếng Việt, denormalized (mỗi item 1 row)
# ════════════════════════════════════════════════════════════════
from datetime import datetime as _dt_apsc
from zoneinfo import ZoneInfo as _ZI_apsc
from collections import defaultdict as _dd_apsc


def _build_apsc_dict(ma_hd: str, rows: list) -> dict:
    """Build APSC dict từ list rows denormalized — schema khớp hoa_don_pos."""
    head = rows[0]
    thoi_gian_str = head.get("Thời gian") or head.get("Thời gian tạo") or ""
    created_iso = ""
    try:
        dt = _dt_apsc.strptime(thoi_gian_str, "%d/%m/%Y %H:%M:%S")
        dt = dt.replace(tzinfo=_ZI_apsc("Asia/Ho_Chi_Minh"))
        created_iso = dt.isoformat()
    except Exception:
        pass

    items = []
    for r in rows:
        ten = (r.get("Tên hàng") or "").strip()
        if not ten:
            continue  # skip rows trống (edge case)
        items.append({
            "ma_hang":       (r.get("Mã hàng") or "").strip(),
            "ten_hang":      ten,
            "so_luong":      int(r.get("Số lượng", 0) or 0),
            "don_gia":       int(r.get("Đơn giá", 0) or 0),
            "thanh_tien":    int(r.get("Thành tiền", 0) or 0),
            "giam_gia_dong": int(r.get("Giảm giá", 0) or 0),
        })

    return {
        "ma_hd":           ma_hd,
        "chi_nhanh":       head.get("Chi nhánh", "") or "",
        "ten_khach":       head.get("Tên khách hàng") or "Khách lẻ",
        "sdt_khach":       (head.get("Điện thoại") or "").strip(),
        "tong_tien_hang":  int(head.get("Tổng tiền hàng", 0) or 0),
        "giam_gia_don":    int(head.get("Giảm giá hóa đơn", 0) or 0),
        "khach_can_tra":   int(head.get("Khách cần trả", 0) or 0),
        "tien_mat":        int(head.get("Tiền mặt", 0) or 0),
        "chuyen_khoan":    int(head.get("Chuyển khoản", 0) or 0),
        "the":             int(head.get("Thẻ", 0) or 0),
        "tien_thua":       0,
        "tien_coc_da_thu": 0,
        "trang_thai":      head.get("Trạng thái") or "Hoàn thành",
        "nguoi_ban":       head.get("Người bán") or head.get("Người tạo") or "—",
        "ma_ycsc":         head.get("Mã YCSC", "") or "",
        "ghi_chu":         head.get("Ghi chú", "") or "",
        "created_at":      created_iso,
        "items":           items,
        "_apsc":           True,
    }


def load_apsc_history(chi_nhanh: str, from_date_iso: str = None,
                      limit: int = 100) -> list:
    """Load APSC invoices từ hoa_don table cho 1 chi nhánh."""
    try:
        res = supabase.table("hoa_don") \
            .select("*") \
            .eq("Chi nhánh", chi_nhanh) \
            .like("Mã hóa đơn", "APSC%") \
            .limit(limit * 15) \
            .execute()
        if not res.data:
            return []

        groups = _dd_apsc(list)
        for r in res.data:
            ma_hd = r.get("Mã hóa đơn", "")
            if ma_hd and ma_hd.startswith("APSC"):
                groups[ma_hd].append(r)

        from_dt = None
        if from_date_iso:
            try:
                from_dt = _dt_apsc.fromisoformat(
                    from_date_iso.replace("Z", "+00:00"))
            except Exception:
                pass

        results = []
        for ma_hd, rows in groups.items():
            apsc = _build_apsc_dict(ma_hd, rows)
            if from_dt and apsc["created_at"]:
                try:
                    apsc_dt = _dt_apsc.fromisoformat(apsc["created_at"])
                    if apsc_dt < from_dt:
                        continue
                except Exception:
                    pass
            results.append(apsc)

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]
    except Exception as e:
        try:
            _logger.warning(f"load_apsc_history error: {e}")
        except Exception:
            pass
        return []


def search_apsc(keyword: str, branches: list, limit: int = 30) -> list:
    """Search APSC theo ma_hd, sdt, hoặc ten_khach (in-Python filter)."""
    try:
        kw = (keyword or "").strip().lower()
        if not kw:
            return []
        res = supabase.table("hoa_don") \
            .select("*") \
            .in_("Chi nhánh", list(branches)) \
            .like("Mã hóa đơn", "APSC%") \
            .limit(500) \
            .execute()
        if not res.data:
            return []
        groups = _dd_apsc(list)
        for r in res.data:
            ma_hd = r.get("Mã hóa đơn", "")
            if ma_hd and ma_hd.startswith("APSC"):
                groups[ma_hd].append(r)
        results = []
        for ma_hd, rows in groups.items():
            head = rows[0]
            ten_kh = (head.get("Tên khách hàng") or "").lower()
            sdt    = (head.get("Điện thoại") or "").lower().replace(" ", "")
            ma_lower = ma_hd.lower()
            if kw in ma_lower or kw in sdt or kw in ten_kh:
                results.append(_build_apsc_dict(ma_hd, rows))
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]
    except Exception as e:
        try:
            _logger.warning(f"search_apsc error: {e}")
        except Exception:
            pass
        return []
