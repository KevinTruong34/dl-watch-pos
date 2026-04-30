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
    Mỗi item: {id, username, ho_ten, role, chi_nhanh_list}
    """
    try:
        res = supabase.table("nhan_vien").select("id,username,ho_ten,role") \
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
    sdt_clean = sdt.strip().replace(" ", "")
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
            "ten_kh":        ten.strip(),
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
