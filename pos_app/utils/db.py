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
