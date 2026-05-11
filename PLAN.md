# PLAN.md — Quét mã vạch POS

**Feature:** Quét mã vạch bằng camera điện thoại trong POS app
**User:** Kevin · **Date:** 11/05/2026
**Pattern:** 2-phase A planning + B execute với Claude Code (proven trên SPK/DVPS, B1, B2a, B2b, APSC K80)

---

## OVERVIEW

Cho phép NV quét mã vạch trên tem dán hộp SP để add vào giỏ ở POS, thay vì search bằng text.

**Schema:** `hang_hoa.ma_vach TEXT` đã tồn tại, data đầy đủ. Chỉ cần thêm UNIQUE partial index.

**Phần cứng:** Camera điện thoại qua `st.camera_input` (built-in Streamlit), decode server-side bằng `pyzbar` + system lib `libzbar0`.

**Scope:**
- Phase 0: POC gate (verify camera + decode + lookup chạy ổn trên iPhone + Android)
- Phase 1: Migration schema (UNIQUE index)
- Phase 2: Helper `utils/barcode.py`
- Phase 3: Wire vào `pos_app/modules/ban_hang.py`
- Phase 4: Wire vào `pos_app/modules/doi_tra.py` (items_moi)
- Phase 5: Smoke test + cleanup POC code + deploy + update AI_CONTEXT.md

**Defer (Phase 2 sau khi prod ổn 1-2 tuần):**
- Wire vào `web_app/modules/chuyen_hang.py` DLW

---

## PRE-FLIGHT CHECKLIST (chạy trước Phase 0)

Claude Code BẮT BUỘC verify trước khi commit code:

```bash
# 1. Verify file pos_app/modules/ban_hang.py tồn tại + lấy hash
git rev-parse HEAD
cat pos_app/modules/ban_hang.py | wc -l   # ghi nhận line count baseline

# 2. Verify file pos_app/modules/doi_tra.py tồn tại
cat pos_app/modules/doi_tra.py | wc -l

# 3. Verify utils/db.py có get_supabase()
grep -n "def get_supabase" pos_app/utils/db.py

# 4. Verify packages.txt EXISTS at REPO ROOT (KHÔNG phải trong pos_app/)
ls -la packages.txt   # nếu không có → tạo mới ở root

# 5. Verify pyzbar chưa có trong requirements.txt
grep pyzbar pos_app/requirements.txt   # phải không có gì
```

Nếu pre-flight fail → STOP, hỏi user.

---

## PHASE 0 — POC SCAN (GATE)

**Mục tiêu:** Verify camera + decode + lookup chạy ổn TRƯỚC khi build production code.

### Scope

Thêm 1 đoạn code tạm vào CUỐI `pos_app/modules/ban_hang.py` (sau toàn bộ code production hiện có) — toggle qua `st.expander` ẩn dưới page Bán hàng, chỉ admin thấy.

**KHÔNG đụng:**
- Code production của `ban_hang.py` (search bar, giỏ, dialog, etc.)
- `doi_tra.py`, `lich_su.py`, `dat_hang.py`
- Schema DB
- Bất kỳ RPC nào

### Files thay đổi

**1. `packages.txt`** (ROOT của repo, tạo mới nếu chưa có)
```
libzbar0
```

**2. `pos_app/requirements.txt`** (append)
```
pyzbar==0.1.9
```

**3. `pos_app/modules/ban_hang.py`** (append vào cuối file, sau toàn bộ code hiện có)

```python
# ============================================================
# === POC BARCODE SCAN — Phase 0 gate (sẽ xóa ở Phase 5) ===
# ============================================================
def _poc_barcode_scan():
    """POC test camera + pyzbar + lookup. Sẽ xóa sau Phase 0."""
    import time
    from PIL import Image
    
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError as e:
        st.error(f"❌ pyzbar chưa cài: {e}")
        return
    
    from utils.db import get_supabase
    
    st.markdown("### 🧪 POC: Test quét mã vạch")
    st.caption("Đoạn code tạm để verify camera + decode + lookup. Sẽ xóa sau khi POC pass.")
    
    img_file = st.camera_input("📸 Chụp tem mã vạch", key="poc_scan_camera")
    
    if img_file is None:
        return
    
    t_start = time.perf_counter()
    
    # 1. Load ảnh
    try:
        img = Image.open(img_file)
    except Exception as e:
        st.error(f"❌ Lỗi load ảnh: {e}")
        return
    
    # 2. Decode
    t_decode_start = time.perf_counter()
    try:
        decoded = pyzbar_decode(img)
    except Exception as e:
        st.error(f"❌ Lỗi decode: {e}")
        return
    t_decode_end = time.perf_counter()
    
    if not decoded:
        st.error("❌ Không decode được mã vạch. Thử lại — đảm bảo tem rõ nét, đủ ánh sáng.")
        st.caption(f"⏱ decode={1000*(t_decode_end - t_decode_start):.0f}ms")
        return
    
    # 3. Lấy result đầu tiên
    barcode_obj = decoded[0]
    code_text = barcode_obj.data.decode("utf-8").strip()
    code_type = barcode_obj.type
    
    st.success(f"✅ Decode: `{code_text}` (type: **{code_type}**)")
    
    # 4. Lookup
    t_query_start = time.perf_counter()
    try:
        sb = get_supabase()
        res = sb.table("hang_hoa") \
            .select("ma_hang, ma_vach, ten_hang, loai_sp, is_open_price, gia_ban, active") \
            .eq("ma_vach", code_text) \
            .eq("active", True) \
            .limit(2) \
            .execute()
    except Exception as e:
        st.error(f"❌ Lỗi query: {e}")
        return
    t_query_end = time.perf_counter()
    
    rows = res.data or []
    
    if not rows:
        st.warning(f"⚠️ Không tìm thấy SP có ma_vach = `{code_text}`")
    elif len(rows) > 1:
        st.error(f"❌ {len(rows)} SP cùng ma_vach — cần resolve duplicate trước UNIQUE:")
        st.json(rows)
    else:
        sp = rows[0]
        st.markdown(f"### 🎯 Tìm thấy SP")
        st.markdown(f"- **Mã hàng:** `{sp['ma_hang']}`")
        st.markdown(f"- **Tên:** {sp['ten_hang']}")
        st.markdown(f"- **Loại:** {sp.get('loai_sp') or '-'}")
        st.markdown(f"- **Giá:** {(sp.get('gia_ban') or 0):,}đ")
        st.markdown(f"- **Open-price:** {'✅' if sp.get('is_open_price') else '❌'}")
    
    # 5. Timing
    t_total = time.perf_counter() - t_start
    st.divider()
    st.caption(
        f"⏱ decode={1000*(t_decode_end - t_decode_start):.0f}ms · "
        f"query={1000*(t_query_end - t_query_start):.0f}ms · "
        f"total={1000*t_total:.0f}ms"
    )


# === POC TOGGLE — chỉ admin thấy, sẽ xóa Phase 5 ===
def _render_poc_section():
    user = st.session_state.get("user") or {}
    if user.get("role") != "admin":
        return
    
    with st.expander("🧪 POC: Test quét mã vạch (admin only)", expanded=False):
        _poc_barcode_scan()
```

**Gọi `_render_poc_section()` ở cuối hàm chính của `ban_hang.py`** (tìm hàm `render()` hoặc tương đương, gọi cuối hàm — trước khi return).

### Branch & Deploy
```bash
git checkout -b feat/barcode-scan
git add packages.txt pos_app/requirements.txt pos_app/modules/ban_hang.py
git commit -m "Phase 0: POC barcode scan (camera + pyzbar)"
git push origin feat/barcode-scan
```

User Kevin:
1. Vào Streamlit Cloud POS settings → đổi branch sang `feat/barcode-scan`
2. Chờ deploy (~2 phút) — check log không có lỗi import
3. Mở app trên iPhone Safari + Android Chrome
4. Vào tab Bán hàng → scroll xuống → expand "🧪 POC: Test quét mã vạch"
5. Test theo 8 bước success criteria bên dưới
6. Báo lại số liệu cho mình

### Success Criteria (gate cho Phase 1)

| # | Criteria | Verify |
|---|----------|--------|
| 1 | iPhone Safari mở camera được, không lỗi permission | User test |
| 2 | Android Chrome mở camera được | User test |
| 3 | pyzbar decode được **3 tem cửa hàng khác nhau** trong ánh sáng thường | User chụp 3 SP, đọc đúng `ma_vach` |
| 4 | Latency end-to-end ≤ 3s | Timing report tự hiển thị |
| 5 | Lookup `hang_hoa.ma_vach` ra đúng SP | Match SP đã chụp |
| 6 | Tem không decode được → error rõ ràng | Chụp tem mờ, app báo lỗi |
| 7 | Mã không có trong DB → "Không tìm thấy" | Chụp barcode hộp sữa, app báo warning |
| 8 | Code type thực tế là gì? | Ghi nhận: Code128? EAN-13? |

**Pass ALL → Phase 1.**
**Fail bất kỳ → STOP, báo user, pivot strategy (xem mục Pivot bên dưới).**

### Pivot strategy nếu Phase 0 fail

| Fail mode | Pivot |
|-----------|-------|
| Camera permission lỗi iPhone | Thử với `accept_multiple_files=False` + reload page guide |
| pyzbar decode 0/3 tem | Test thử ánh sáng + khoảng cách. Vẫn fail → swap qua `zxing-cpp` (Python binding) |
| Latency >5s consistently | Consider `html5-qrcode` JS component cho live scan |
| Mọi thứ OK nhưng UX kém | Vẫn pass Phase 0, cải thiện UX ở Phase 3 |

---

## PHASE 1 — SCHEMA MIGRATION

**Mục tiêu:** Thêm UNIQUE partial index cho `hang_hoa.ma_vach`.

### Pre-check trên Supabase SQL editor

```sql
-- Re-verify không có trùng (đã verify trước, nhưng check lại right before ALTER)
SELECT ma_vach, COUNT(*) FROM hang_hoa
WHERE active = true AND ma_vach IS NOT NULL
GROUP BY ma_vach HAVING COUNT(*) > 1;
-- Expected: 0 rows
```

### Migration SQL

```sql
-- ============================================
-- MIGRATION: UNIQUE partial index cho ma_vach
-- Pattern: giống hang_hoa_open_price_idx
-- ============================================

-- 1. Drop index btree cũ (không unique)
DROP INDEX IF EXISTS idx_hang_hoa_ma_vach;

-- 2. Tạo UNIQUE partial index mới
CREATE UNIQUE INDEX hang_hoa_ma_vach_idx ON hang_hoa(ma_vach)
    WHERE ma_vach IS NOT NULL AND active = true;

-- 3. Verify
SELECT 
    i.relname AS index_name,
    ix.indisunique AS is_unique,
    pg_get_indexdef(ix.indexrelid) AS index_definition
FROM pg_class t
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
WHERE t.relname = 'hang_hoa' AND a.attname = 'ma_vach';
-- Expected: 1 row, is_unique=true
```

### Save SQL file

File: `pos_app/sql/pos_patch_09_barcode_unique.sql`

(Lý do save vào `pos_app/sql/`: pattern consistent với `pos_patch_07_session.sql`, `pos_patch_08_open_price.sql` — dễ trace lịch sử migration.)

### Verify
- Query verify trả 1 row với `is_unique=true`
- Insert thử SP test với ma_vach trùng → DB phải reject (test trong Supabase SQL editor, rồi rollback)

### Success Criteria
- ✅ Index `hang_hoa_ma_vach_idx` tồn tại, UNIQUE
- ✅ Index cũ `idx_hang_hoa_ma_vach` không còn
- ✅ Constraint hoạt động: thử INSERT duplicate → reject

---

## PHASE 2 — HELPER `utils/barcode.py`

**Mục tiêu:** Tách logic decode + lookup ra module riêng để reuse giữa ban_hang.py và doi_tra.py.

### File mới: `pos_app/utils/barcode.py`

```python
"""
Helpers cho quét mã vạch qua camera + lookup hang_hoa.

Pattern: decode pyzbar → strip whitespace → lookup ma_vach → trả về dict standard.
"""
from typing import Optional
from PIL import Image
from .db import get_supabase


def decode_barcode_from_image(img) -> Optional[dict]:
    """
    Decode 1 ảnh PIL.Image hoặc file-like (st.camera_input).
    
    Returns:
        {"code": str, "type": str}  nếu decode được
        None                          nếu không decode được
    """
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        return None
    
    try:
        if not isinstance(img, Image.Image):
            img = Image.open(img)
        decoded = pyzbar_decode(img)
    except Exception:
        return None
    
    if not decoded:
        return None
    
    # Lấy result đầu tiên (POS không expect multi-barcode trong 1 ảnh)
    obj = decoded[0]
    return {
        "code": obj.data.decode("utf-8").strip(),
        "type": obj.type,
    }


def lookup_hang_by_ma_vach(code: str, chi_nhanh: str) -> dict:
    """
    Lookup SP theo ma_vach, kèm tồn tại chi nhánh.
    
    Returns standard dict:
        {"ok": True, "item": {...}}                — found
        {"ok": False, "error": "not_found", ...}    — không có trong DB
        {"ok": False, "error": "duplicate", ...}    — DB có duplicate (shouldn't happen nếu UNIQUE đã có)
        {"ok": False, "error": "db_error", ...}     — Supabase error
    
    `item` schema match với row của `load_hang_hoa_pos` để wire vào cart pattern hiện tại:
        ma_hang, ten_hang, loai_sp, is_open_price, gia_ban, ton (số lượng tồn ở chi_nhanh)
    """
    code = (code or "").strip()
    if not code:
        return {"ok": False, "error": "empty"}
    
    try:
        sb = get_supabase()
        res = sb.table("hang_hoa") \
            .select("ma_hang, ten_hang, loai_sp, is_open_price, gia_ban") \
            .eq("ma_vach", code) \
            .eq("active", True) \
            .limit(2) \
            .execute()
    except Exception as e:
        return {"ok": False, "error": "db_error", "detail": str(e)}
    
    rows = res.data or []
    
    if not rows:
        return {"ok": False, "error": "not_found", "code": code}
    
    if len(rows) > 1:
        # Không nên xảy ra sau UNIQUE index. Defensive.
        return {
            "ok": False,
            "error": "duplicate",
            "code": code,
            "ma_hang_list": [r["ma_hang"] for r in rows],
        }
    
    sp = rows[0]
    ma_hang = sp["ma_hang"]
    
    # Fetch tồn ở chi_nhanh
    try:
        ton_res = sb.table("the_kho") \
            .select('"Tồn cuối kì"') \
            .eq('"Mã hàng"', ma_hang) \
            .eq('"Chi nhánh"', chi_nhanh) \
            .limit(1) \
            .execute()
        ton = (ton_res.data or [{}])[0].get("Tồn cuối kì", 0) or 0
    except Exception:
        ton = 0
    
    # Dịch vụ + open-price: tồn = vô hạn theo pattern hiện tại
    if sp.get("loai_sp") == "Dịch vụ" or sp.get("is_open_price"):
        ton = 999999
    
    return {
        "ok": True,
        "item": {
            "ma_hang": ma_hang,
            "ten_hang": sp.get("ten_hang") or "",
            "loai_sp": sp.get("loai_sp") or "",
            "is_open_price": bool(sp.get("is_open_price")),
            "gia_ban": sp.get("gia_ban") or 0,
            "ton": ton,
        },
    }
```

### Verify
```bash
python3 -c "import ast; ast.parse(open('pos_app/utils/barcode.py').read())"
# Expected: no error
```

### Success Criteria
- ✅ File tồn tại, syntax OK
- ✅ Import được từ `from utils.barcode import decode_barcode_from_image, lookup_hang_by_ma_vach`
- ✅ Schema return của `lookup_hang_by_ma_vach` match với row của `load_hang_hoa_pos` (item key: `ma_hang`, `ten_hang`, `loai_sp`, `is_open_price`, `gia_ban`, `ton`)

---

## PHASE 3 — WIRE VÀO `ban_hang.py`

**Mục tiêu:** Thêm UI quét mã vạch vào màn search hàng (Màn 1) của Bán hàng.

### ⚠️ Pre-flight check trước khi sửa

User PHẢI gửi file `pos_app/modules/ban_hang.py` hiện tại trước khi Claude Code đụng vào. Lý do: theo CLAUDE.md style guide, user "đôi khi tự fix code mà không báo" → tránh override.

### Vị trí thêm UI

Trong hàm render Màn 1 (tìm hàng), gần search input text hiện có. Thêm 1 expander "📷 Quét mã vạch" gập lại mặc định (tiết kiệm vertical space cho mobile).

### Patch dạng search-replace

User sẽ gửi file → Claude Code identify chỗ search input hiện tại → patch bằng pattern:

```python
# TÌM (anchor — chính xác đoạn search input hiện tại, sẽ verify khi có file):
keyword = st.text_input("🔍 Tìm hàng...", key="search_hang")

# THAY BẰNG:
keyword = st.text_input("🔍 Tìm hàng...", key="search_hang")

# === BARCODE SCAN ===
with st.expander("📷 Quét mã vạch", expanded=False):
    _scan_and_add_to_cart_ban_hang()
# === END BARCODE SCAN ===
```

### Helper function trong cùng file

```python
def _scan_and_add_to_cart_ban_hang():
    """Scan barcode → lookup → auto-add 1 cái vào giỏ."""
    from utils.barcode import decode_barcode_from_image, lookup_hang_by_ma_vach
    
    img_file = st.camera_input("📸 Chụp tem", key="scan_ban_hang_cam")
    
    if img_file is None:
        return
    
    # Reset key sau scan thành công để cho phép scan tiếp
    decoded = decode_barcode_from_image(img_file)
    
    if decoded is None:
        st.error("❌ Không decode được. Thử lại — tem rõ nét, đủ ánh sáng.")
        return
    
    chi_nhanh = st.session_state.get("chi_nhanh", "")
    result = lookup_hang_by_ma_vach(decoded["code"], chi_nhanh)
    
    if not result["ok"]:
        err = result.get("error")
        if err == "not_found":
            st.warning(f"⚠️ Không tìm thấy SP có mã vạch `{decoded['code']}`")
        elif err == "duplicate":
            st.error(f"❌ Nhiều SP cùng mã vạch — báo admin kiểm tra: {result.get('ma_hang_list')}")
        else:
            st.error(f"❌ Lỗi: {result.get('error')} {result.get('detail', '')}")
        return
    
    item = result["item"]
    
    # Add vào cart — REUSE pattern add hiện có
    # (Claude Code sẽ identify hàm/logic add cart hiện tại của ban_hang.py)
    _add_to_cart_pattern(item, so_luong=1)
    
    st.success(f"✅ Đã thêm: {item['ten_hang']} ({item['ma_hang']})")
    
    # st.rerun() để clear camera widget + refresh cart
    st.rerun()
```

⚠️ **`_add_to_cart_pattern()` là placeholder** — Claude Code MUST identify logic add cart hiện tại của `ban_hang.py` (sau khi user gửi file) và reuse đúng pattern đó. Không tạo logic add cart mới.

### Edge cases handle

| Case | Behavior |
|------|----------|
| `is_open_price=true` SP có ma_vach | Add với `gia_ban` default, NV chỉnh giá ở dialog sửa dòng như flow hiện tại |
| SP đã có trong giỏ | Reuse logic hiện tại — tăng SL hay add row mới (theo behavior `ban_hang.py` hiện có) |
| Tồn = 0 (hàng thường) | Show warning nhưng vẫn add (để NV thấy + xử lý), HOẶC block — theo behavior hiện tại của `ban_hang.py` (consistent) |
| Dịch vụ (loai_sp="Dịch vụ") | Add bình thường, ton=999999 |

### Success Criteria
- ✅ Module load không lỗi import
- ✅ Expander "📷 Quét mã vạch" hiện ra trong Màn 1
- ✅ Scan tem thật → SP add vào giỏ đúng
- ✅ Mã không có → warning, không crash
- ✅ Code production cũ (search bằng text) vẫn chạy y nguyên
- ✅ `python3 -c "import ast; ast.parse(open('pos_app/modules/ban_hang.py').read())"` pass

---

## PHASE 4 — WIRE VÀO `doi_tra.py` (items_moi)

**Mục tiêu:** Tương tự Phase 3, nhưng chỉ cho items_moi (hàng khách mua thay thế). KHÔNG đụng items_tra.

### ⚠️ Pre-flight check

User PHẢI gửi file `pos_app/modules/doi_tra.py` hiện tại trước khi sửa.

### Vị trí thêm UI

Trong section "Hàng mua mới" / "items_moi" của doi_tra.py. KHÔNG thêm vào section "Hàng trả" / "items_tra".

### Patch tương tự Phase 3

```python
# === BARCODE SCAN (items_moi) ===
with st.expander("📷 Quét mã vạch", expanded=False):
    _scan_and_add_to_items_moi()
# === END BARCODE SCAN ===
```

```python
def _scan_and_add_to_items_moi():
    """Scan barcode → lookup → add vào items_moi của phiếu đổi/trả."""
    from utils.barcode import decode_barcode_from_image, lookup_hang_by_ma_vach
    
    img_file = st.camera_input("📸 Chụp tem", key="scan_doi_tra_cam")
    if img_file is None:
        return
    
    decoded = decode_barcode_from_image(img_file)
    if decoded is None:
        st.error("❌ Không decode được. Thử lại.")
        return
    
    chi_nhanh = st.session_state.get("chi_nhanh", "")
    result = lookup_hang_by_ma_vach(decoded["code"], chi_nhanh)
    
    if not result["ok"]:
        # ... same error handling as Phase 3
        return
    
    item = result["item"]
    # REUSE logic add items_moi hiện tại của doi_tra.py
    _add_to_items_moi_pattern(item, so_luong=1)
    st.success(f"✅ Đã thêm: {item['ten_hang']}")
    st.rerun()
```

### Success Criteria
- ✅ Module load không lỗi
- ✅ Scan trong tab Đổi/trả → item add vào items_moi đúng
- ✅ Section items_tra KHÔNG bị ảnh hưởng
- ✅ Logic chenh_lech recompute đúng sau add
- ✅ Syntax check pass

---

## PHASE 5 — SMOKE TEST + CLEANUP + DEPLOY

### Cleanup POC code

Xóa khỏi `pos_app/modules/ban_hang.py`:
- Hàm `_poc_barcode_scan()`
- Hàm `_render_poc_section()`
- Lời gọi `_render_poc_section()` ở cuối render

### Smoke test (chạy trên branch trước khi merge main)

Trên Streamlit Cloud branch `feat/barcode-scan`:

**Bán hàng:**
1. Login NV thường
2. Vào Bán hàng → expand "📷 Quét mã vạch"
3. Scan 1 SP có trong kho → verify add vào giỏ với SL=1, giá đúng
4. Scan SP `is_open_price=true` (nếu có ma_vach) → verify add với giá default
5. Scan barcode không có trong DB → verify warning
6. Tạo HĐ thử → verify lưu đúng, in K80 đúng (CN 100 LQĐ)

**Đổi/trả:**
1. Vào Đổi/trả → chọn HĐ gốc
2. Scan items_tra (CHỈ qua UI cũ — KHÔNG có scan section) → verify behavior cũ
3. Expand "📷 Quét mã vạch" trong section items_moi
4. Scan SP → verify add vào items_moi, chenh_lech recompute đúng
5. Tạo phiếu thử → verify lưu, AHDD đúng

**Regression:**
- Search bằng text vẫn OK ở Bán hàng + Đổi/trả
- Tạo HĐ không scan vẫn OK
- Hủy HĐ vẫn OK

### Deploy

```bash
git checkout main
git merge feat/barcode-scan
git push origin main
# Streamlit Cloud auto-deploy main
git branch -D feat/barcode-scan
git push origin --delete feat/barcode-scan
```

### Update AI_CONTEXT.md (POS)

Append vào roadmap:
```markdown
[✓] Barcode scan (11/05/2026): st.camera_input + pyzbar, lookup ma_vach
    - UNIQUE partial index hang_hoa_ma_vach_idx
    - Helper utils/barcode.py
    - Wire vào ban_hang.py + doi_tra.py (items_moi)
    - Defer: chuyen_hang.py DLW
```

Append vào DECISIONS:
```markdown
| D31 | ★ Barcode scan: st.camera_input + pyzbar (KHÔNG html5-qrcode, KHÔNG streamlit-webrtc) | Simplicity, built-in lib |
| D32 | ★ Barcode lookup chỉ ma_vach (single-tier), KHÔNG fallback ma_hang | ma_vach ≠ ma_hang ở dấu chấm/gạch, fallback vô ích |
| D33 | ★ Barcode scan chỉ items_moi của doi_tra, KHÔNG items_tra | items_tra từ HĐ gốc đã sẵn, không cần scan |
```

### Update AI_CONTEXT.md (DLW)

Pending roadmap:
```markdown
| 15 | Wire barcode scan vào web_app/modules/chuyen_hang.py | Pending | Defer sau POS ổn 1-2 tuần |
```

### Success Criteria toàn feature
- ✅ Tất cả smoke test pass
- ✅ Code POC đã xóa sạch khỏi ban_hang.py
- ✅ AI_CONTEXT.md cả 2 repo đã update
- ✅ Merge main, deploy prod thành công
- ✅ Test 1 HĐ thật ở cửa hàng pass

---

## ROLLBACK STRATEGY

| Phase fail | Rollback |
|-----------|----------|
| Phase 0 (POC) | Đổi branch Streamlit về `main`, branch test giữ để pivot |
| Phase 1 (Schema) | `DROP INDEX hang_hoa_ma_vach_idx; CREATE INDEX idx_hang_hoa_ma_vach ON hang_hoa(ma_vach);` |
| Phase 2/3/4 | Git revert commit của phase đó, push lại branch |
| Phase 5 deploy | `git revert` merge commit trên main, push, Streamlit auto-deploy lại |

DB rollback an toàn 100% vì không có data migration, chỉ thêm index.

---

## DEPENDENCIES & DECISIONS

| Decision | Choice | Lý do |
|----------|--------|-------|
| Camera library | `st.camera_input` (built-in) | Simplicity, không cần JS component |
| Decode library | `pyzbar 0.1.9` | Stable, support EAN/UPC/Code128/QR |
| System lib | `libzbar0` qua packages.txt | Streamlit Cloud auto-install |
| Lookup logic | Single-tier `ma_vach` only | ma_vach ≠ ma_hang ở dấu, fallback vô ích |
| UNIQUE constraint | Partial index (ma_vach NOT NULL AND active=true) | Pattern proven SPK/DVPS |
| Helper module | `utils/barcode.py` | Reuse giữa ban_hang + doi_tra |
| Cart add behavior | SL=1 auto, reuse logic hiện có | Consistency, không invent flow mới |
| Open-price SP | Add bình thường, NV chỉnh giá ở dialog | Không special-case |
| items_tra của doi_tra | KHÔNG support scan | Items_tra từ HĐ gốc, không cần scan |
| chuyen_hang DLW | Defer Phase 2 | Sau POS ổn 1-2 tuần |

---

## NOTES CHO CLAUDE CODE

1. **Pre-flight ALWAYS run** trước Phase 0 — kiểm tra file exists, hash, dependencies chưa có
2. **User MUST send file ban_hang.py + doi_tra.py** trước Phase 3/4 — KHÔNG đoán code hiện tại
3. **Reuse pattern add cart hiện có** — `_add_to_cart_pattern()` chỉ là placeholder, identify pattern thật trong code user gửi
4. **Commit từng phase** — không squash, để rollback từng phase độc lập
5. **`st.rerun()` sau scan success** — clear camera widget + refresh state
6. **Test syntax `ast.parse()`** sau mỗi phase edit `.py`
7. **KHÔNG migrate data, KHÔNG đụng RPC** — feature này chỉ thêm UI + 1 index
8. **packages.txt ở ROOT repo** (cùng level pos_app/), KHÔNG phải bên trong pos_app/
9. **Mỗi phase phải có smoke test cụ thể** trước khi push commit
10. **AI_CONTEXT.md update là phase cuối** (Phase 5), KHÔNG update giữa chừng

---

## TIMELINE ESTIMATE

| Phase | Effort | Gate |
|-------|--------|------|
| Phase 0 — POC | 30 phút build + 30 phút test | Pass 8 success criteria |
| Phase 1 — Schema | 5 phút | UNIQUE index verify |
| Phase 2 — Helper | 15 phút | Syntax + import OK |
| Phase 3 — ban_hang.py | 30 phút (cần user gửi file) | Smoke test |
| Phase 4 — doi_tra.py | 30 phút (cần user gửi file) | Smoke test |
| Phase 5 — Deploy | 30 phút | Tất cả smoke test pass |

**Total:** ~3 giờ end-to-end nếu Phase 0 pass smooth. Pivot có thể thêm 2-4 giờ.

---

## END OF PLAN.md
