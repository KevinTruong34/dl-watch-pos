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

    Returns: list of dict {ma_hang, ma_vach, ten_hang, gia_ban, ton}
    """
    try:
        # 1. Load master hàng hóa active có giá > 0
        rows, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("hang_hoa") \
                .select("ma_hang,ma_vach,ten_hang,gia_ban") \
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

        # 2. Load tồn kho chi nhánh
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

        # 3. Merge tồn vào danh sách hàng hóa
        result = []
        for r in rows:
            ma = str(r.get("ma_hang", "")).strip()
            result.append({
                "ma_hang":  ma,
                "ma_vach":  str(r.get("ma_vach", "") or "").strip(),
                "ten_hang": str(r.get("ten_hang", "") or ""),
                "gia_ban":  int(r.get("gia_ban", 0) or 0),
                "ton":      ton_map.get(ma, 0),
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
