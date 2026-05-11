"""
POC quét mã vạch bằng camera điện thoại.
Standalone — không touch modules production.

Cách chạy:
    streamlit run poc_scan.py

Cách test trên điện thoại:
    1. Deploy lên Streamlit Cloud branch riêng (vd `feat/barcode-poc`)
    2. Mở URL trên iPhone Safari + Android Chrome
    3. Grant camera permission
    4. Chụp tem SP thật tại cửa hàng
    5. Verify decode đúng, lookup ra đúng SP

Source: Pocspec.md §4. Adapted: import `supabase` client trực tiếp
từ utils.db (codebase không có `get_supabase()` factory).
"""
import streamlit as st
from PIL import Image
from pyzbar.pyzbar import decode
import time

from utils.db import supabase

st.set_page_config(page_title="POC Quét mã vạch", layout="centered")
st.title("🔍 POC Quét mã vạch")

# Camera input
img_file = st.camera_input("📸 Chụp tem mã vạch trên SP")

if img_file is not None:
    t_start = time.perf_counter()

    # 1. Load ảnh
    img = Image.open(img_file)

    # 2. Decode bằng pyzbar
    t_decode_start = time.perf_counter()
    decoded = decode(img)
    t_decode_end = time.perf_counter()

    if not decoded:
        st.error("❌ Không decode được mã vạch. Thử lại — đảm bảo tem rõ nét, đủ ánh sáng.")
        st.caption(f"Thời gian decode: {(t_decode_end - t_decode_start)*1000:.0f}ms")
        st.stop()

    # 3. Lấy result đầu tiên
    barcode_obj = decoded[0]
    code_text = barcode_obj.data.decode("utf-8").strip()
    code_type = barcode_obj.type

    st.success(f"✅ Decode được: `{code_text}` (loại: {code_type})")

    # 4. Lookup trong hang_hoa
    t_query_start = time.perf_counter()
    res = supabase.table("hang_hoa") \
        .select("ma_hang, ma_vach, ten_hang, loai_sp, is_open_price, gia_ban, active") \
        .eq("ma_vach", code_text) \
        .eq("active", True) \
        .limit(2) \
        .execute()
    t_query_end = time.perf_counter()

    rows = res.data or []

    if not rows:
        st.warning(f"⚠️ Không tìm thấy SP có ma_vach = `{code_text}` trong DB")
    elif len(rows) > 1:
        st.error(f"❌ Có {len(rows)} SP cùng ma_vach — cần resolve duplicate trước khi add UNIQUE:")
        st.json(rows)
    else:
        sp = rows[0]
        st.markdown("### 🎯 Tìm thấy SP")
        st.markdown(f"- **Mã hàng:** `{sp['ma_hang']}`")
        st.markdown(f"- **Tên:** {sp['ten_hang']}")
        st.markdown(f"- **Loại:** {sp['loai_sp']}")
        st.markdown(f"- **Giá:** {sp.get('gia_ban') or 0:,}đ")
        st.markdown(f"- **Open-price:** {'✅' if sp.get('is_open_price') else '❌'}")

    # 5. Timing report
    t_total = time.perf_counter() - t_start
    st.divider()
    st.caption(
        f"⏱ **Timing:** "
        f"decode={1000*(t_decode_end - t_decode_start):.0f}ms · "
        f"query={1000*(t_query_end - t_query_start):.0f}ms · "
        f"total={1000*t_total:.0f}ms"
    )

# Reset hint
st.divider()
st.caption("💡 Chụp lại để test SP khác. Nếu fail nhiều lần → check ánh sáng + khoảng cách camera (10-20cm).")
