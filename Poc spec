# POC_SPEC.md — Quét mã vạch POS (Proof of Concept)

**Mục tiêu:** De-risk camera + decode + lookup trước khi commit full feature. POC này KHÔNG đụng code production, chạy độc lập 1 file để user test trên điện thoại tại cửa hàng.

**Time budget:** 30 phút build + 30 phút test tại cửa hàng.

---

## 1. Scope POC

### Trong scope (must)
- 1 file Python standalone `pos_app/poc_scan.py`
- Streamlit page: chụp ảnh tem → decode barcode → lookup `hang_hoa.ma_vach` → hiển thị thông tin SP
- Test trên iPhone Safari + Android Chrome tại cửa hàng (điều kiện ánh sáng thật)
- Đo latency end-to-end (chụp → result)
- Test với tem cửa hàng thật (không phải barcode in màn hình)

### Ngoài scope (KHÔNG làm)
- KHÔNG đụng `modules/ban_hang.py`, `modules/doi_tra.py`
- KHÔNG migration schema (UNIQUE index chưa cần cho POC)
- KHÔNG add vào giỏ, KHÔNG ghi DB
- KHÔNG UI polish (CSS, mobile fix, etc.)
- KHÔNG handle multi-barcode trong 1 ảnh (chỉ lấy cái đầu tiên)

---

## 2. Success criteria (gate cho Phase 1)

POC pass nếu **TẤT CẢ** điều kiện sau đạt:

| # | Criteria | Cách verify |
|---|----------|-------------|
| 1 | iPhone Safari mở camera được, không lỗi permission | User test mở app, bấm "Take photo" |
| 2 | Android Chrome mở camera được | Tương tự |
| 3 | pyzbar decode được ít nhất **3 tem cửa hàng khác nhau** trong điều kiện ánh sáng thường | User chụp 3 SP khác nhau, đọc đúng `ma_vach` |
| 4 | Latency e2e ≤ 3s (chụp → decode → result) | Đếm thời gian thủ công |
| 5 | Lookup `hang_hoa.ma_vach` ra đúng SP | Kết quả match SP đã chụp |
| 6 | Tem KHÔNG decode được hiển thị error rõ ràng | User chụp tem mờ/xa, app báo "Không decode được" |

POC fail nếu **bất kỳ** criteria nào không đạt → pivot:
- Camera lỗi → consider html5-qrcode JS component
- pyzbar không decode → consider zxing-cpp hoặc pyzbar config khác
- Latency >5s → consider live scan (html5-qrcode)
- Tem không decode được consistently → check format barcode hiện tại

---

## 3. Dependencies

### Cần thêm vào `pos_app/requirements.txt`
```
pyzbar==0.1.9
Pillow>=9.0.0  # đã có sẵn cho streamlit
```

### Cần thêm vào `pos_app/packages.txt` (Streamlit Cloud system deps)
```
libzbar0
```

**Lưu ý quan trọng:** `packages.txt` phải ở **root của repo** (cùng level `requirements.txt`). Streamlit Cloud auto-install lib này khi deploy. Local dev cần `apt-get install libzbar0` (Linux) hoặc `brew install zbar` (macOS).

---

## 4. File spec — `pos_app/poc_scan.py`

### Structure
```python
"""
POC quét mã vạch bằng camera điện thoại.
Standalone — không touch modules production.

Cách chạy:
    streamlit run pos_app/poc_scan.py

Cách test trên điện thoại:
    1. Deploy lên Streamlit Cloud branch riêng (vd `feat/barcode-poc`)
    2. Mở URL trên iPhone Safari + Android Chrome
    3. Grant camera permission
    4. Chụp tem SP thật tại cửa hàng
    5. Verify decode đúng, lookup ra đúng SP
"""
import streamlit as st
from PIL import Image
from pyzbar.pyzbar import decode
import time
from utils.db import get_supabase  # reuse client có sẵn

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
    sb = get_supabase()
    res = sb.table("hang_hoa") \
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
        st.markdown(f"### 🎯 Tìm thấy SP")
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
```

### Notes về implementation
- **Reuse `utils.db.get_supabase()`** thay vì init client mới → consistent với codebase
- **`.strip()`** sau decode → pyzbar đôi khi trả `b'ABC\n'`
- **`.limit(2)`** thay vì `.limit(1)` → detect duplicate ngay trong POC, biết trước có cần resolve trước khi UNIQUE
- **Timing log** đo riêng decode vs query → biết bottleneck ở đâu
- **`code_type` print ra** → biết format thực tế (Code128, EAN13, CODE39...) → quan trọng cho Phase 1

---

## 5. Deploy POC

### Option A — Branch riêng (recommend)
```bash
git checkout -b feat/barcode-poc
git add pos_app/poc_scan.py pos_app/requirements.txt pos_app/packages.txt
git commit -m "POC: barcode scan with st.camera_input + pyzbar"
git push origin feat/barcode-poc
```

Trong Streamlit Cloud:
- Tạo app mới (hoặc đổi branch của app POS staging)
- Set main file = `pos_app/poc_scan.py`
- Wait deploy ~2 phút
- Mở URL trên điện thoại

### Option B — Test local trước (nhanh hơn nếu có máy)
```bash
cd pos_app
pip install pyzbar==0.1.9
# Linux: sudo apt-get install libzbar0
# macOS: brew install zbar
streamlit run poc_scan.py
```

→ Mở URL local trên laptop, hoặc dùng ngrok expose cho điện thoại test.

---

## 6. Test plan tại cửa hàng

User Kevin test với device thật:

| Step | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở URL POC trên **iPhone Safari** | App load, hiện nút "Take photo" |
| 2 | Bấm "Take photo" lần đầu | Browser hỏi permission camera, grant |
| 3 | Chụp tem SP 1 (vd Tophill `TE061LPZ2262`) | Decode đúng, lookup ra SP đúng, latency ≤3s |
| 4 | Chụp tem SP 2 (Bestdon `BD99310GB02`) | Tương tự |
| 5 | Chụp tem SP 3 (open-price item nếu có) | Tương tự, show `is_open_price=true` |
| 6 | Chụp tem mờ / xa / nghiêng | Báo lỗi "Không decode được" rõ ràng |
| 7 | Chụp barcode bất kỳ (vd hộp sữa) → mã không có trong DB | Báo "Không tìm thấy" rõ ràng |
| 8 | Lặp lại trên **Android Chrome** | Tương tự |

**Ghi nhận:**
- Latency trung bình bao nhiêu ms?
- Loại barcode thực tế là gì (Code128? EAN-13?)
- Có tem nào không decode được không? Tại sao?
- Camera có lag/crash gì không?

---

## 7. Sau POC

### Nếu POC pass → mình viết PLAN.md full với 5 phases:
1. **Phase 1** — Schema migration (drop btree, add UNIQUE partial)
2. **Phase 2** — Helper `utils/barcode.py` (decode + lookup) + add to `utils/db.py`
3. **Phase 3** — Wire vào `modules/ban_hang.py`
4. **Phase 4** — Wire vào `modules/doi_tra.py` (items_moi)
5. **Phase 5** — Smoke test + deploy + update AI_CONTEXT.md

### Nếu POC fail → pivot:
- Camera permission/UX kém → html5-qrcode JS component
- pyzbar không decode tem cụ thể → thử zxing-cpp
- Latency >5s ổn định → consider live scan instead of capture-then-decode

---

## 8. Rollback POC

POC chỉ là 1 file standalone + 2 lib mới. Rollback:
```bash
git checkout main
git branch -D feat/barcode-poc
# Streamlit Cloud: tắt app POC, KHÔNG đụng app production
```

Không có data migration, không có RPC mới, không có DB change → rollback 100% an toàn.

---

## CHECKLIST CHO USER TRƯỚC KHI TEST

- [ ] Branch `feat/barcode-poc` đã tạo
- [ ] `pos_app/poc_scan.py` đã có
- [ ] `pos_app/requirements.txt` đã thêm `pyzbar==0.1.9`
- [ ] `pos_app/packages.txt` đã có dòng `libzbar0` (file mới hoặc append)
- [ ] Streamlit Cloud deploy thành công (check log không có lỗi import)
- [ ] Có ít nhất 3 tem SP tại cửa hàng để test (đã in sẵn)
- [ ] Test trên cả iPhone Safari + Android Chrome
- [ ] Ghi nhận: latency, barcode type, % decode success rate
