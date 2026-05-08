# PLAN — DL Watch Open-Price Refactor

> **Mục đích file:** Plan đầy đủ để execute trong session Claude Code mới. Đã chốt mọi decisions, không cần hỏi user lại trừ khi gặp tình huống ngoài plan.
>
> **Generated:** 2026-05-08, từ Phase A planning session.
> **Owner:** Kevin (DL Watch).
> **Repos:** `KevinTruong34/DLW_APP` (web app), `KevinTruong34/dl-watch-pos` (POS).
> **DB:** Supabase (Postgres).

---

## 0. CONTEXT

### 0.1 Vấn đề
Master data `hang_hoa` chứa **170 mã rác** đa-giá (LD100/200/.../1000, KSA150/.../1000, v.v.) — workaround do KiotViet không cho sửa giá khi bán. Mỗi nhóm dịch vụ đáng ra chỉ cần **1 mã chuẩn** với `gia_ban=0` + cờ "open-price" cho phép NV nhập giá tự do khi bán.

Session trước đã làm xong cho **2 nhóm** (SPK + DVPS) bằng convention-based (check `loai_hang`/`thuong_hieu`). Plan này refactor sang **flag `is_open_price` riêng** + migrate **24 nhóm còn lại**.

### 0.2 Architecture đã chốt

| Decision | Value |
|---|---|
| Open-price detection | Flag `hang_hoa.is_open_price BOOLEAN` |
| Helper SQL | `is_open_price_sql()` đọc thẳng cột flag |
| Helper Python | `is_open_price_item()` đọc field `is_open` từ enriched dict |
| Naming mã chuẩn | Mã mới rõ ràng (vd `LAUDAU`, `KINHSAPPHIRE`) |
| Bảo hành Group C | Đặt = "Không" cho master, BH thực tế quyết tại quầy |
| Bảng `hoa_don` (KiotViet legacy) | **SKIP migrate FK** — chấp nhận orphan ma_hang text |
| DVPS thuong_hieu | Đổi từ "Chi phí sửa chữa phát sinh" → "Dịch vụ phát sinh" |
| E7 (BMD - Bán mắt dây) | Merge vào SPK (UPDATE FK + DELETE) |
| E8 (OTD - Ổ tự động) | Tạo mã `OTUDONG` loại Hàng hóa, `loai_hang = "Sản phẩm khác"` |
| Pin (TPBG, PV, PDH, PDHKBH) | **KHÔNG đụng** (cần track tồn để chuyển hàng) |
| Thay máy treo tường (MDHTT) | **KHÔNG đụng** (master data thực, không phải open-price) |

### 0.3 Order migrate (risk-first)

Bắt đầu nhóm nhỏ (3 mã) để test pattern, scale dần lên nhóm lớn:

```
1.  VESINH       (3)
2.  NHATRANG     (3)
3.  HIEUCHUAN    (3)
4.  THAYDAYCOTGIO(3)
5.  THAYDAYTHIEU (3)
6.  THAYCANGCUA  (3)
7.  OTUDONG      (3)  [HÀNG HÓA]
8.  THAYMAYDHDUNG(3)
9.  THAYCHOT     (5)
10. THAYDAYDONG  (5)
11. THAYTYNUT    (5)
12. KIEMTRAMAY   (6)
13. CATMATDAY    (6)
14. THAYRON      (6)
15. LAUDAU       (7)
16. LAMCHONGNUOC (7)
17. THAYBANHXE   (7)
18. GANKIMCOC    (9)
19. THAYMAYAUTO  (9)
20. DANHBONG     (10)
21. THAYIC       (10)
22. THAYMAYPIN   (10)
23. KINHTHUONG   (13 = KTH 6 + KTHM 7)
24. KINHSAPPHIRE (27 = KSA 17 + KSAM 10)
25. E7 BMD → SPK (special case, làm CUỐI)
```

---

## 1. PRE-FLIGHT CHECKS

### 1.1 Backup verify

Backup từ 2026-04-25 đã có sẵn (xác nhận từ Phase A):
- `_backup_20260425_phieu_sua_chua`
- `_backup_20260425_phieu_sua_chua_chi_tiet`
- `_backup_20260425_hoa_don_apsc`
- `_backup_20260425_phieu_chuyen_app`

**Optional — Snapshot bổ sung trước khi chạy migration:**

```sql
-- Backup hang_hoa hiện tại (để rollback nhanh nếu cần)
CREATE TABLE _backup_20260508_hang_hoa AS
SELECT * FROM hang_hoa;

-- Backup hoa_don_pos_ct + phieu_sua_chua_chi_tiet + phieu_doi_tra_pos_ct + the_kho
CREATE TABLE _backup_20260508_hoa_don_pos_ct AS SELECT * FROM hoa_don_pos_ct;
CREATE TABLE _backup_20260508_phieu_sua_chua_chi_tiet AS SELECT * FROM phieu_sua_chua_chi_tiet;
CREATE TABLE _backup_20260508_phieu_doi_tra_pos_ct AS SELECT * FROM phieu_doi_tra_pos_ct;
CREATE TABLE _backup_20260508_the_kho AS SELECT * FROM the_kho;
```

### 1.2 Baseline counts (chạy + log)

```sql
-- Trước migrate: log để verify sau
SELECT 'hang_hoa total' AS metric, COUNT(*) AS val FROM hang_hoa
UNION ALL SELECT 'hang_hoa rac (regex)', COUNT(*) FROM hang_hoa
WHERE ma_hang ~ '^(LD|VS|PH|KTM|TIC|TDD|TRCN|TTNM|TMDHD|TDCG|TDT|TBX|TCC|KSA|KSAM|KTH|KTHM|TMP|TMA|NT|HCA|GKC|TC|LCN|CMD|BMD|OTD)[0-9]+$'
UNION ALL SELECT 'hoa_don_pos_ct total', COUNT(*) FROM hoa_don_pos_ct
UNION ALL SELECT 'phieu_sua_chua_chi_tiet total', COUNT(*) FROM phieu_sua_chua_chi_tiet
UNION ALL SELECT 'the_kho total', COUNT(*) FROM the_kho;
```

**Expected:**
- `hang_hoa rac (regex) = 170` (170 mã rác cần xóa, không tính 4 mã BMD)
  - Wait: BMD pattern ^BMD[0-9]+$ cũng match → tổng phải là 174.
  - Verify với Q-COUNT-FINAL từ Phase A: tổng all groups = 71 + 59 + 40 = 170 (incl BMD = 4). OK.

---

## 2. PHASE 1 — INFRASTRUCTURE

### 2.1 Schema change

```sql
ALTER TABLE hang_hoa
ADD COLUMN is_open_price BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_hang_hoa_is_open_price ON hang_hoa(is_open_price) WHERE is_open_price = true;
```

### 2.2 Refactor helper SQL

**Replace** function `is_open_price_sql` (đã tồn tại từ session trước):

```sql
CREATE OR REPLACE FUNCTION is_open_price_sql(p_ma_hang text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        (SELECT is_open_price FROM hang_hoa WHERE ma_hang = p_ma_hang),
        false
    )
$$;
```

**Note:** Tất cả 4 RPC từ session trước (`tao_hoa_don_pos`, `huy_hoa_don_pos`, `tao_phieu_doi_tra_pos`, `huy_phieu_doi_tra_pos`) đã gọi `is_open_price_sql()` — KHÔNG cần edit RPC.

### 2.3 Refactor helper Python

#### File `pos_app/utils/db.py`

**Find:**
```python
def is_open_price_item(item) -> bool:
    loai_hang = (item.get("loai_hang") or "").strip()
    thuong_hieu = (item.get("thuong_hieu") or "").strip()
    if loai_hang == "Sản phẩm khác":
        return True
    if loai_hang == "Sửa chữa" and thuong_hieu == "Chi phí sửa chữa phát sinh":
        return True
    return False
```

**Replace with:**
```python
def is_open_price_item(item) -> bool:
    """Open-price = sửa giá khi bán, không track tồn. Đọc thẳng flag is_open_price."""
    return bool(item.get("is_open_price", False))
```

**Find** trong `load_hang_hoa_pos` (search query SELECT):
```python
.select("ma_hang, ten_hang, gia_ban, ton, loai_sp, loai_hang, thuong_hieu")
```
*(hoặc tương đương — search current SELECT clause)*

**Replace with:**
```python
.select("ma_hang, ten_hang, gia_ban, ton, loai_sp, loai_hang, thuong_hieu, is_open_price")
```

**Find** chỗ enrich `is_open` flag (hiện đang gọi `is_open_price_item` với loai_hang/thuong_hieu):
```python
item["is_open"] = is_open_price_item(item)
```

→ Giữ nguyên — vì `is_open_price_item` mới chỉ đọc field `is_open_price` (đã được SELECT).

#### File `pos_app/modules/ban_hang.py`

Không cần đổi — đã import `is_open_price_item` từ utils/db.py, logic flow giữ nguyên.

#### File `pos_app/modules/doi_tra.py`

Không cần đổi vì cũng dùng helper.

#### File `web_app/modules/sua_chua.py`

**Find** helper inline (nếu có):
```python
def _is_open_price_row(row) -> bool:
    loai_hang = (row.get("loai_hang") or "").strip()
    thuong_hieu = (row.get("thuong_hieu") or "").strip()
    if loai_hang == "Sản phẩm khác":
        return True
    if loai_hang == "Sửa chữa" and thuong_hieu == "Chi phí sửa chữa phát sinh":
        return True
    return False
```

**Replace with:**
```python
def _is_open_price_row(row) -> bool:
    return bool(row.get("is_open_price", False))
```

**Cũng cần update SELECT query** trong `sua_chua.py` để fetch field `is_open_price` từ `hang_hoa`. Search current `.select(...)` chứa "ma_hang" và thêm `is_open_price`.

#### File `web_app/modules/bao_cao.py`

**Find** filter trong `_filter_chi_hang_hoa`:
```python
def _filter_chi_hang_hoa(df):
    """Loại trừ Sản phẩm khác (open-price) khỏi báo cáo XNT."""
    if "loai_hang" in df.columns:
        return df[df["loai_hang"] != "Sản phẩm khác"]
    return df
```

**Replace with:**
```python
def _filter_chi_hang_hoa(df):
    """Loại trừ open-price (SPK, dịch vụ giá biến đổi) khỏi báo cáo XNT.
    
    Báo cáo XNT chỉ track Hàng hóa CÓ tồn kho thực. Open-price luôn là
    'tồn ảo' nên loại trừ để tránh nhiễu.
    """
    if "is_open_price" in df.columns:
        return df[~df["is_open_price"].fillna(False)]
    # Fallback nếu chưa có column (data cũ)
    if "loai_hang" in df.columns:
        return df[df["loai_hang"] != "Sản phẩm khác"]
    return df
```

**Note:** Cần update SELECT trong query load `hang_hoa` để có `is_open_price` field. Search trong `bao_cao.py` các chỗ `.select(...)` từ `hang_hoa`.

### 2.4 Backfill flag cho mã chuẩn đã có (SPK + DVPS)

```sql
BEGIN;

-- Backfill 2 mã chuẩn đã tồn tại
UPDATE hang_hoa SET is_open_price = true WHERE ma_hang IN ('SPK', 'DVPS');

-- Đổi DVPS thuong_hieu cho thống nhất naming
UPDATE hang_hoa SET thuong_hieu = 'Dịch vụ phát sinh'
WHERE ma_hang = 'DVPS' AND thuong_hieu = 'Chi phí sửa chữa phát sinh';

-- Verify
SELECT ma_hang, thuong_hieu, is_open_price FROM hang_hoa
WHERE ma_hang IN ('SPK', 'DVPS');
-- Expected: cả 2 mã có is_open_price = true; DVPS có thuong_hieu = 'Dịch vụ phát sinh'

COMMIT;
```

### 2.5 Form UI — thêm checkbox "Cho phép sửa giá khi bán"

#### File `web_app/modules/hang_hoa.py`

Tìm function `_render_them_moi` và `_render_sua_hang_hoa`.

**Find** (trong cột 2 hoặc nơi có loai_sp/loai_hang):
```python
loai_sp = st.radio(
    "Loại sản phẩm",
    ["Hàng hóa", "Dịch vụ"],
    horizontal=True,
    key="..."
)
```

**Add ngay sau:**
```python
is_open_price = st.checkbox(
    "✏️ Cho phép sửa giá khi bán (open-price)",
    value=False,
    help="Khi bán, NV tự nhập giá. Không track tồn kho. Dùng cho dịch vụ giá biến đổi (Lau dầu, Vệ sinh, ...) hoặc sản phẩm khác (SPK).",
    key="..."
)
```

**Find** trong `insert_payload` (function `_render_them_moi`):
```python
payload = {
    "ma_hang": ma_hang,
    "ten_hang": ten_hang,
    ...
    "loai_sp": loai_sp,
    ...
}
```

**Add field:**
```python
payload = {
    ...
    "loai_sp": loai_sp,
    "is_open_price": is_open_price,
    ...
}
```

Lặp lại cho `_render_sua_hang_hoa` (function sửa).

**Cũng cần load `is_open_price` từ DB** khi render form sửa. Search query SELECT hang_hoa trong file này, thêm `is_open_price` vào.

### 2.6 Verify Phase 1

```sql
-- Schema OK
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'hang_hoa' AND column_name = 'is_open_price';
-- Expected: column tồn tại, type boolean, default false

-- Helper SQL works
SELECT is_open_price_sql('SPK');   -- Expected: true
SELECT is_open_price_sql('DVPS');  -- Expected: true
SELECT is_open_price_sql('LD100'); -- Expected: false (chưa migrate)

-- Backfill correct
SELECT ma_hang, is_open_price, thuong_hieu FROM hang_hoa
WHERE ma_hang IN ('SPK', 'DVPS');
```

**Manual test app:**
1. Mở POS bán hàng → thêm SPK vào cart → input giá editable hiện ra → bán ok
2. Mở web app sửa chữa → search SPK / DVPS → input giá editable
3. Mở form Thêm hàng hóa → thấy checkbox "✏️ Cho phép sửa giá khi bán"
4. Tạo 1 mã test (vd `TEST_OPEN`) với checkbox = true → save → query `is_open_price = true`
5. DELETE mã test sau verify

---

## 3. PHASE 2 — MIGRATION TEMPLATE

### 3.1 Generic per-group migration

Template áp dụng cho mọi nhóm. Thay placeholders trong dấu `{...}` cho từng nhóm cụ thể.

```sql
-- ==========================================
-- Group: {GROUP_ID} — {GROUP_NAME}
-- Mã chuẩn mới: {NEW_CODE}
-- Pattern mã rác: {REGEX_PATTERN}
-- Số mã rác kỳ vọng: {EXPECTED_COUNT}
-- ==========================================

BEGIN;

-- Step 1: Tạo mã chuẩn mới (nếu chưa có)
INSERT INTO hang_hoa (
    ma_hang, ten_hang, gia_ban, loai_sp, loai_hang, thuong_hieu, is_open_price
)
VALUES (
    '{NEW_CODE}',
    '{NEW_TEN_HANG}',
    0,
    '{NEW_LOAI_SP}',     -- 'Dịch vụ' hoặc 'Hàng hóa'
    '{NEW_LOAI_HANG}',   -- 'Sửa chữa' hoặc 'Sản phẩm khác'
    {NEW_THUONG_HIEU},   -- text hoặc NULL
    true                 -- open-price flag
)
ON CONFLICT (ma_hang) DO UPDATE
    SET is_open_price = true,
        gia_ban = 0;  -- bảo đảm gia_ban = 0 cho master

-- Step 2: Verify số mã rác match expected (defensive)
DO $$
DECLARE
    v_count int;
BEGIN
    SELECT COUNT(*) INTO v_count FROM hang_hoa
    WHERE ma_hang ~ '{REGEX_PATTERN}';
    
    IF v_count != {EXPECTED_COUNT} THEN
        RAISE EXCEPTION 'Mismatch: expect % mã rác, found %', {EXPECTED_COUNT}, v_count;
    END IF;
END $$;

-- Step 3: UPDATE FK trong 3 bảng (skip hoa_don legacy)
UPDATE hoa_don_pos_ct
SET ma_hang = '{NEW_CODE}'
WHERE ma_hang ~ '{REGEX_PATTERN}';

UPDATE phieu_sua_chua_chi_tiet
SET ma_hang = '{NEW_CODE}'
WHERE ma_hang ~ '{REGEX_PATTERN}';

UPDATE phieu_doi_tra_pos_ct
SET ma_hang = '{NEW_CODE}'
WHERE ma_hang ~ '{REGEX_PATTERN}';

-- Step 4: DELETE mã rác từ hang_hoa
DELETE FROM hang_hoa
WHERE ma_hang ~ '{REGEX_PATTERN}';

-- Step 5: Dọn the_kho ảo cho mã rác đã xóa
DELETE FROM the_kho
WHERE "Mã hàng" ~ '{REGEX_PATTERN}';

-- Step 6: Verify post-migrate
DO $$
DECLARE
    v_remaining int;
BEGIN
    SELECT COUNT(*) INTO v_remaining FROM hang_hoa
    WHERE ma_hang ~ '{REGEX_PATTERN}';
    
    IF v_remaining > 0 THEN
        RAISE EXCEPTION 'Mã rác còn sót: %', v_remaining;
    END IF;
END $$;

COMMIT;
```

### 3.2 Test plan template (per group)

Sau mỗi nhóm migrate xong:

```sql
-- a. Mã chuẩn tồn tại + flag đúng
SELECT ma_hang, ten_hang, gia_ban, loai_sp, loai_hang, thuong_hieu, is_open_price
FROM hang_hoa WHERE ma_hang = '{NEW_CODE}';
-- Expected: 1 row, gia_ban=0, is_open_price=true

-- b. Mã rác đã sạch
SELECT COUNT(*) FROM hang_hoa WHERE ma_hang ~ '{REGEX_PATTERN}';
-- Expected: 0

-- c. FK migrate xong
SELECT COUNT(*) FROM hoa_don_pos_ct WHERE ma_hang ~ '{REGEX_PATTERN}';
SELECT COUNT(*) FROM phieu_sua_chua_chi_tiet WHERE ma_hang ~ '{REGEX_PATTERN}';
SELECT COUNT(*) FROM phieu_doi_tra_pos_ct WHERE ma_hang ~ '{REGEX_PATTERN}';
-- All expected: 0

-- d. the_kho sạch
SELECT COUNT(*) FROM the_kho WHERE "Mã hàng" ~ '{REGEX_PATTERN}';
-- Expected: 0
```

**Manual app test (sau nhóm đầu tiên VESINH):**
1. POS bán hàng → search "VESINH" → thấy ✏️ "giá tự nhập" → thêm vào cart → nhập giá 80000 → tạo HĐ ok
2. Web app sửa chữa → tạo phiếu mới → search "VESINH" → input giá → ➕ thêm
3. Báo cáo XNT → mã `VESINH` không xuất hiện trong danh sách (đã filter)

---

## 4. PHASE 3 — EXECUTE PER-GROUP

### Format: 1 block code SQL cho mỗi nhóm — copy-paste vào Supabase SQL Editor.

**Note:** Mỗi block là transaction độc lập. Lỗi 1 nhóm KHÔNG ảnh hưởng nhóm khác. Chạy theo thứ tự rồi test trước khi sang nhóm tiếp.

---

### Group 1 — VESINH (3 mã: VS50, VS100, VS150)

```sql
BEGIN;

INSERT INTO hang_hoa (ma_hang, ten_hang, gia_ban, loai_sp, loai_hang, thuong_hieu, is_open_price)
VALUES ('VESINH', 'Vệ sinh', 0, 'Dịch vụ', 'Sửa chữa', 'Vệ sinh', true)
ON CONFLICT (ma_hang) DO UPDATE SET is_open_price = true, gia_ban = 0;

DO $$
DECLARE v_count int;
BEGIN
    SELECT COUNT(*) INTO v_count FROM hang_hoa WHERE ma_hang ~ '^VS[0-9]+$';
    IF v_count != 3 THEN RAISE EXCEPTION 'Mismatch: expect 3, found %', v_count; END IF;
END $$;

UPDATE hoa_don_pos_ct SET ma_hang = 'VESINH' WHERE ma_hang ~ '^VS[0-9]+$';
UPDATE phieu_sua_chua_chi_tiet SET ma_hang = 'VESINH' WHERE ma_hang ~ '^VS[0-9]+$';
UPDATE phieu_doi_tra_pos_ct SET ma_hang = 'VESINH' WHERE ma_hang ~ '^VS[0-9]+$';

DELETE FROM hang_hoa WHERE ma_hang ~ '^VS[0-9]+$';
DELETE FROM the_kho WHERE "Mã hàng" ~ '^VS[0-9]+$';

COMMIT;
```

**Test app sau nhóm này** (manual). Nếu OK → tiếp nhóm 2.

---

### Group 2 — NHATRANG (3: NT400, NT500, NT600)

```sql
BEGIN;
INSERT INTO hang_hoa VALUES (...) ON CONFLICT (ma_hang) DO UPDATE SET is_open_price = true, gia_ban = 0;
-- ... template với:
--   NEW_CODE = 'NHATRANG'
--   NEW_TEN_HANG = 'Nhả trắng'
--   NEW_LOAI_SP = 'Dịch vụ'
--   NEW_LOAI_HANG = 'Sửa chữa'
--   NEW_THUONG_HIEU = 'Nhả trắng'
--   REGEX = '^NT[0-9]+$'
--   EXPECTED = 3
COMMIT;
```

**Compact format cho các nhóm còn lại** — Claude Code có thể tự build SQL từ template + params:

| # | Group | NEW_CODE | TEN_HANG | LOAI_SP | LOAI_HANG | THUONG_HIEU | REGEX | EXPECTED |
|---|---|---|---|---|---|---|---|---|
| 1 | VESINH | `VESINH` | Vệ sinh | Dịch vụ | Sửa chữa | Vệ sinh | `^VS[0-9]+$` | 3 |
| 2 | NHATRANG | `NHATRANG` | Nhả trắng | Dịch vụ | Sửa chữa | Nhả trắng | `^NT[0-9]+$` | 3 |
| 3 | HIEUCHUAN | `HIEUCHUAN` | Hiệu chuẩn auto | Dịch vụ | Sửa chữa | Hiệu chuẩn | `^HCA[0-9]+$` | 3 |
| 4 | THAYDAYCOTGIO | `THAYDAYCOTGIO` | Thay dây cót gió | Dịch vụ | Sửa chữa | Thay dây cót gió | `^TDCG[0-9]+$` | 3 |
| 5 | THAYDAYTHIEU | `THAYDAYTHIEU` | Thay dây thiều | Dịch vụ | Sửa chữa | Thay dây thiều | `^TDT[0-9]+$` | 3 |
| 6 | THAYCANGCUA | `THAYCANGCUA` | Thay bộ tự động (càng cua) | Dịch vụ | Sửa chữa | Thay bộ tự động (càng cua) | `^TCC[0-9]+$` | 3 |
| 7 | OTUDONG | `OTUDONG` | Ổ tự động | **Hàng hóa** | **Sản phẩm khác** | NULL | `^OTD[0-9]+$` | 3 |
| 8 | THAYMAYDHDUNG | `THAYMAYDHDUNG` | Thay máy đồng hồ đứng | Dịch vụ | Sửa chữa | Thay máy đồng hồ đứng | `^TMDHD[0-9]+$` | 3 |
| 9 | THAYCHOT | `THAYCHOT` | Thay chốt | Dịch vụ | Sửa chữa | Thay chốt | `^TC[0-9]+$` | 5 |
| 10 | THAYDAYDONG | `THAYDAYDONG` | Thay dây đồng | Dịch vụ | Sửa chữa | Thay dây đồng | `^TDD[0-9]+$` | 5 |
| 11 | THAYTYNUT | `THAYTYNUT` | Thay ty/nút máy | Dịch vụ | Sửa chữa | Thay ty/nút máy | `^TTNM[0-9]+$` | 5 |
| 12 | KIEMTRAMAY | `KIEMTRAMAY` | Kiểm tra máy | Dịch vụ | Sửa chữa | Kiểm tra máy | `^KTM[0-9]+$` | 6 |
| 13 | CATMATDAY | `CATMATDAY` | Cắt mắt dây | Dịch vụ | Sửa chữa | Cắt mắt dây | `^CMD[0-9]+$` | 6 |
| 14 | THAYRON | `THAYRON` | Thay ron chống nước | Dịch vụ | Sửa chữa | Thay ron | `^TRCN[0-9]+$` | 6 |
| 15 | LAUDAU | `LAUDAU` | Lau dầu | Dịch vụ | Sửa chữa | Lau dầu | `^LD[0-9]+$` | 7 |
| 16 | LAMCHONGNUOC | `LAMCHONGNUOC` | Làm chống nước | Dịch vụ | Sửa chữa | Làm chống nước | `^LCN[0-9]+$` | 7 |
| 17 | THAYBANHXE | `THAYBANHXE` | Thay bánh xe | Dịch vụ | Sửa chữa | Thay bánh xe | `^TBX[0-9]+$` | 7 |
| 18 | GANKIMCOC | `GANKIMCOC` | Gắn kim/cọc số | Dịch vụ | Sửa chữa | Gắn kim/cọc số | `^GKC[0-9]+$` | 9 |
| 19 | THAYMAYAUTO | `THAYMAYAUTO` | Thay máy auto | Dịch vụ | Sửa chữa | Thay máy auto | `^TMA[0-9]+$` | 9 |
| 20 | DANHBONG | `DANHBONG` | Đánh bóng | Dịch vụ | Sửa chữa | Đánh bóng | `^PH[0-9]+$` | 10 |
| 21 | THAYIC | `THAYIC` | Thay IC | Dịch vụ | Sửa chữa | Thay IC | `^TIC[0-9]+$` | 10 |
| 22 | THAYMAYPIN | `THAYMAYPIN` | Thay máy pin | Dịch vụ | Sửa chữa | Thay máy pin | `^TMP[0-9]+$` | 10 |
| 23 | KINHTHUONG | `KINHTHUONG` | Thay kính thường | Dịch vụ | Sửa chữa | Thay kính | `^(KTH\|KTHM)[0-9]+$` | 13 |
| 24 | KINHSAPPHIRE | `KINHSAPPHIRE` | Thay kính sapphire | Dịch vụ | Sửa chữa | Thay kính | `^(KSA\|KSAM)[0-9]+$` | 27 |

**⚠️ Cẩn thận với regex group 23, 24:**

PostgreSQL POSIX regex syntax:
```sql
-- KINHTHUONG: cả KTH và KTHM
WHERE ma_hang ~ '^(KTH|KTHM)[0-9]+$'

-- KINHSAPPHIRE: cả KSA và KSAM
WHERE ma_hang ~ '^(KSA|KSAM)[0-9]+$'
```

Note: `KTH150` match cả `^KTH[0-9]+$` lẫn `^(KTH|KTHM)[0-9]+$` → OK.
Note: `KTHM200` match `^(KTH|KTHM)[0-9]+$` nhưng KHÔNG match `^KTH[0-9]+$` (vì có M trước số) → cần regex alternative.

### Group 25 — E7 BMD (special: merge vào SPK, không tạo mã mới)

```sql
BEGIN;

-- Verify SPK đã backfill flag (Phase 1 đã làm)
DO $$
BEGIN
    IF NOT (SELECT is_open_price FROM hang_hoa WHERE ma_hang = 'SPK') THEN
        RAISE EXCEPTION 'SPK chưa có is_open_price = true. Chạy backfill Phase 1 trước.';
    END IF;
END $$;

-- Verify expected count
DO $$
DECLARE v_count int;
BEGIN
    SELECT COUNT(*) INTO v_count FROM hang_hoa WHERE ma_hang ~ '^BMD[0-9]+$';
    IF v_count != 4 THEN RAISE EXCEPTION 'BMD: expect 4, found %', v_count; END IF;
END $$;

-- UPDATE FK 3 bảng → trỏ về SPK
UPDATE hoa_don_pos_ct SET ma_hang = 'SPK' WHERE ma_hang ~ '^BMD[0-9]+$';
UPDATE phieu_sua_chua_chi_tiet SET ma_hang = 'SPK' WHERE ma_hang ~ '^BMD[0-9]+$';
UPDATE phieu_doi_tra_pos_ct SET ma_hang = 'SPK' WHERE ma_hang ~ '^BMD[0-9]+$';

-- DELETE 4 mã BMD từ hang_hoa
DELETE FROM hang_hoa WHERE ma_hang ~ '^BMD[0-9]+$';
DELETE FROM the_kho WHERE "Mã hàng" ~ '^BMD[0-9]+$';

COMMIT;
```

---

## 5. PHASE 4 — CLEANUP MÃ *BG CŨ

24 mã `*BG` cũ đã thấy trong Q1 (LDBG, VSBG, etc) là mã "báo giá" KiotViet legacy với gia_ban=0. Sau khi tạo mã chuẩn mới (LAUDAU, VESINH...), các *BG trở thành rác.

### Decision tree:

**Option A — Xóa hết 24 mã *BG** (recommended)
- Pro: Sạch master data
- Con: Nếu lịch sử HĐ có ref → orphan reference
- Cần verify trước:

```sql
-- Check ref *BG trong các bảng FK
SELECT 'hoa_don_pos_ct' AS bang, ma_hang, COUNT(*) AS so_dong
FROM hoa_don_pos_ct WHERE ma_hang LIKE '%BG' GROUP BY ma_hang
UNION ALL
SELECT 'phieu_sua_chua_chi_tiet', ma_hang, COUNT(*)
FROM phieu_sua_chua_chi_tiet WHERE ma_hang LIKE '%BG' GROUP BY ma_hang
UNION ALL
SELECT 'phieu_doi_tra_pos_ct', ma_hang, COUNT(*)
FROM phieu_doi_tra_pos_ct WHERE ma_hang LIKE '%BG' GROUP BY ma_hang;
```

- Nếu **0 rows** → DELETE thoải mái
- Nếu **có rows** → quyết định: UPDATE FK về mã chuẩn mới tương ứng (vd LDBG → LAUDAU), hoặc skip xóa

**Option B — Giữ lại để track** (skip)
- Để các *BG tồn tại như "marker" lịch sử
- Master data hơi rác hơn nhưng safer

→ **Recommend Option A nếu verify ref = 0.** Plan SQL:

```sql
BEGIN;

DELETE FROM hang_hoa WHERE ma_hang IN (
    'TPBG', 'LDBG', 'VSBG', 'DBBG', 'TKBG', 'KTMBG', 'TMBG',
    'TIBG', 'TDDBG', 'TRBG', 'TTTNBG', 'TDTBG', 'TTBXBG',
    'TMTTBG', 'TMDHDBG', 'TTCCBG', 'NTBG', 'HCABG', 'GKCBG',
    'TCBG', 'LCNBG', 'CMDBG', 'BMDBG', 'OTDBG'
);

COMMIT;
```

(24 mã — chính xác per Q1 phân nhóm "Mã *BG cha" = 14 + một số khác từ sheet không match Q1.)

**Note:** Q1 chỉ thấy **14 mã `*BG`**. Một số có thể chưa tồn tại trong DB. Dùng `DELETE ... WHERE ma_hang IN (...)` không error nếu không match.

---

## 6. PHASE 5 — FINAL VERIFICATION

```sql
-- 1. Tổng mã hang_hoa giảm như expected
SELECT COUNT(*) AS hang_hoa_total FROM hang_hoa;
-- Expected: original - 170 (mã rác) - 4 (BMD) - 14 (BG) = original - 188

-- 2. Mọi mã rác đã sạch
SELECT COUNT(*) FROM hang_hoa
WHERE ma_hang ~ '^(LD|VS|PH|KTM|TIC|TDD|TRCN|TTNM|TMDHD|TDCG|TDT|TBX|TCC|KSA|KSAM|KTH|KTHM|TMP|TMA|NT|HCA|GKC|TC|LCN|CMD|BMD|OTD)[0-9]+$';
-- Expected: 0

-- 3. 26 mã chuẩn (24 mới + SPK + DVPS) tồn tại
SELECT ma_hang, is_open_price FROM hang_hoa
WHERE is_open_price = true
ORDER BY ma_hang;
-- Expected: 26 rows

-- 4. FK consistency
SELECT 'hoa_don_pos_ct' AS bang, ma_hang, COUNT(*)
FROM hoa_don_pos_ct
WHERE ma_hang NOT IN (SELECT ma_hang FROM hang_hoa)
GROUP BY ma_hang;
-- Expected: 0 rows (mọi ma_hang đều có trong hang_hoa)

SELECT 'phieu_sua_chua_chi_tiet', ma_hang, COUNT(*)
FROM phieu_sua_chua_chi_tiet
WHERE ma_hang NOT IN (SELECT ma_hang FROM hang_hoa)
GROUP BY ma_hang;
-- Expected: 0 rows

SELECT 'phieu_doi_tra_pos_ct', ma_hang, COUNT(*)
FROM phieu_doi_tra_pos_ct
WHERE ma_hang NOT IN (SELECT ma_hang FROM hang_hoa)
GROUP BY ma_hang;
-- Expected: 0 rows

-- 5. the_kho sạch
SELECT COUNT(*) FROM the_kho
WHERE "Mã hàng" NOT IN (SELECT ma_hang FROM hang_hoa);
-- Expected: 0 (everything references valid hang_hoa)

-- 6. helper SQL works cho mã chuẩn mới
SELECT ma_hang, is_open_price_sql(ma_hang) AS is_op
FROM hang_hoa
WHERE is_open_price = true
ORDER BY ma_hang;
-- Expected: tất cả is_op = true
```

### Manual app smoke test

1. **POS bán hàng:**
   - Search "LAUDAU", "KINHSAPPHIRE", "OTUDONG", "THAYIC" → đều thấy với ✏️ "giá tự nhập"
   - Add LAUDAU → input giá 250000 → tạo HĐ → ok
   - Add OTUDONG (Hàng hóa) → input giá 350000 → tạo HĐ → ok

2. **POS đổi/trả:**
   - Mở HĐ vừa tạo → đổi/trả
   - Khách mua mới: search SPK → ok, search DVPS → KHÔNG hiện (đã chặn dịch vụ)

3. **Web app sửa chữa:**
   - Tạo phiếu mới → search "LAUDAU" → input giá → ➕
   - Save phiếu → ok

4. **Báo cáo:**
   - Tab XNT: không có mã chuẩn open-price (đã filter)
   - Tab Doanh thu theo nhóm: doanh thu vẫn ra số đúng
   - APSC vẫn được gộp như session trước

5. **Form Hàng hóa:**
   - Mở chi tiết SPK → checkbox "✏️ Cho phép sửa giá khi bán" được tick
   - Mở chi tiết LAUDAU mới → checkbox tick

---

## 7. ROLLBACK PLAN

Nếu có sự cố nghiêm trọng (vd report sai, FK vỡ, app không bán được):

### 7.1 Rollback nhanh (toàn bộ data)

```sql
-- Restore từ backup snapshot 2026-05-08
BEGIN;
TRUNCATE hang_hoa;
INSERT INTO hang_hoa SELECT * FROM _backup_20260508_hang_hoa;

TRUNCATE hoa_don_pos_ct;
INSERT INTO hoa_don_pos_ct SELECT * FROM _backup_20260508_hoa_don_pos_ct;

TRUNCATE phieu_sua_chua_chi_tiet;
INSERT INTO phieu_sua_chua_chi_tiet SELECT * FROM _backup_20260508_phieu_sua_chua_chi_tiet;

TRUNCATE phieu_doi_tra_pos_ct;
INSERT INTO phieu_doi_tra_pos_ct SELECT * FROM _backup_20260508_phieu_doi_tra_pos_ct;

TRUNCATE the_kho;
INSERT INTO the_kho SELECT * FROM _backup_20260508_the_kho;

-- Drop schema change
ALTER TABLE hang_hoa DROP COLUMN is_open_price;

-- Revert helper SQL về phiên bản cũ (convention-based)
CREATE OR REPLACE FUNCTION is_open_price_sql(p_ma_hang text)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM hang_hoa
        WHERE ma_hang = p_ma_hang
          AND (loai_hang = 'Sản phẩm khác'
               OR (loai_hang = 'Sửa chữa' AND thuong_hieu = 'Chi phí sửa chữa phát sinh'))
    )
$$;

COMMIT;
```

### 7.2 Rollback một nhóm cụ thể

Nếu chỉ 1 nhóm vỡ (vd LAUDAU), không cần restore toàn bộ:

```sql
-- Ví dụ: rollback LAUDAU
BEGIN;
-- Restore 7 mã LD từ backup
INSERT INTO hang_hoa
SELECT * FROM _backup_20260508_hang_hoa
WHERE ma_hang ~ '^LD[0-9]+$';

-- Revert FK trong 3 bảng (không thể tự revert vì đã LOST mã rác cũ)
-- → Phải copy từ backup hoa_don_pos_ct etc
-- (manual, hiếm khi cần)

-- Xóa mã chuẩn mới
DELETE FROM hang_hoa WHERE ma_hang = 'LAUDAU';
COMMIT;
```

### 7.3 Code revert (Python)

Git revert commit refactor `is_open_price_item` về phiên bản cũ. Web app + POS app deploy lại Streamlit Cloud.

---

## 8. POST-MIGRATION TODO

Sau khi 100% xong + verify:

1. **Cleanup backup:** Sau 1 tuần ổn định, có thể DROP các bảng `_backup_20260508_*` để tiết kiệm storage.

2. **Train NV:** Mỗi nhóm dịch vụ giờ chỉ cần gõ mã chuẩn (vd `LAUDAU`) và nhập giá. Không tạo mã mới kiểu `LAUDAU200` nữa.

3. **Update doc nội bộ:** Tài liệu hướng dẫn POS — cập nhật danh sách mã chuẩn open-price (26 mã).

4. **Future-proof:** Nếu phát sinh dịch vụ mới (vd "Đánh xi", "Khắc tên"), pattern là:
   - Tạo 1 mã chuẩn (vd `KHACTEN`) với `is_open_price = true`, `gia_ban = 0`
   - KHÔNG cần update helper SQL/Python (vì flag-based, không phải convention)
   - KHÔNG cần migrate gì khi NV tạo mã mới

---

## 9. CONSTRAINTS & NOTES

### 9.1 PHẢI làm theo thứ tự
1. Phase 1 (infrastructure) hoàn tất + verify trước khi sang Phase 3
2. Phase 3: bắt đầu nhóm 1 (VESINH), test app rồi mới chạy nhóm 2
3. Sau nhóm 5-6 đã smooth → có thể batch chạy nhanh hơn (run 2-3 nhóm trước khi test app)

### 9.2 Tránh
- ❌ KHÔNG migrate `hoa_don` (KiotViet legacy) — accept orphan ma_hang text
- ❌ KHÔNG đụng Pin (TPBG, PV, PDH, PDHKBH) — cần track tồn
- ❌ KHÔNG đụng MDHTT (Thay máy treo tường) — master data thực
- ❌ KHÔNG dùng `LIKE 'XXX%'` — pattern dễ dính false positive (đã verify Phase A)
- ❌ KHÔNG xóa mã chuẩn `*BG` cho tới khi verify FK = 0

### 9.3 File code cần edit (Python)

| File | Lý do |
|---|---|
| `pos_app/utils/db.py` | Refactor `is_open_price_item`, update SELECT clause |
| `web_app/modules/sua_chua.py` | Refactor `_is_open_price_row` (nếu có), update SELECT |
| `web_app/modules/bao_cao.py` | Refactor `_filter_chi_hang_hoa` |
| `web_app/modules/hang_hoa.py` | Thêm checkbox `is_open_price` vào form |

KHÔNG cần edit:
- `pos_app/modules/ban_hang.py` (dùng helper từ utils/db)
- `pos_app/modules/doi_tra.py` (dùng helper từ utils/db)
- 4 RPC SQL (gọi `is_open_price_sql()` — function refactor trong DB, RPC tự dùng phiên bản mới)

### 9.4 Streamlit Cloud deploy

Sau khi code Python refactor xong + commit + push:
- Web app: tự redeploy (nếu auto-deploy ON)
- POS app: tự redeploy
- Verify cả 2 app load được trước khi chạy SQL Phase 3

Nếu deploy fail vì syntax error → fix trước khi chạy SQL.

### 9.5 Time budget kỳ vọng

| Phase | Time |
|---|---|
| Phase 1 (infrastructure) | 45-60 phút |
| Phase 3 nhóm 1-7 (test cẩn thận) | ~30 phút (3-4 phút/nhóm) |
| Phase 3 nhóm 8-25 (batch nhanh) | ~30 phút |
| Phase 4 cleanup *BG | 10 phút |
| Phase 5 verify + smoke test | 30 phút |
| **TỔNG** | **2.5 - 3 giờ** |

Nếu dùng Claude Code + MCP Supabase → có thể giảm 30-40%.

---

## 10. CHECKLIST THỰC HIỆN

```
[ ] 0. Backup snapshot 2026-05-08 (Phase 1.1)
[ ] 0. Baseline counts logged (Phase 1.2)

PHASE 1
[ ] 1.1 ALTER TABLE add is_open_price
[ ] 1.2 CREATE OR REPLACE is_open_price_sql (flag-based)
[ ] 1.3 Refactor pos_app/utils/db.py (helper + SELECT)
[ ] 1.4 Refactor web_app/modules/sua_chua.py (helper + SELECT)
[ ] 1.5 Refactor web_app/modules/bao_cao.py (filter)
[ ] 1.6 Add checkbox web_app/modules/hang_hoa.py (form)
[ ] 1.7 Backfill SPK + DVPS + đổi DVPS thuong_hieu
[ ] 1.8 Verify Phase 1 (SQL + manual app test)

PHASE 3 — Migrate (theo thứ tự)
[ ] G1  VESINH      (3)
[ ] G2  NHATRANG    (3)
[ ] G3  HIEUCHUAN   (3)
[ ] G4  THAYDAYCOTGIO (3)
[ ] G5  THAYDAYTHIEU (3)
[ ] G6  THAYCANGCUA (3)
[ ] G7  OTUDONG     (3)  -- Hàng hóa
[ ] G8  THAYMAYDHDUNG (3)
   ⏸️ Smoke test app
[ ] G9  THAYCHOT    (5)
[ ] G10 THAYDAYDONG (5)
[ ] G11 THAYTYNUT   (5)
[ ] G12 KIEMTRAMAY  (6)
[ ] G13 CATMATDAY   (6)
[ ] G14 THAYRON     (6)
[ ] G15 LAUDAU      (7)
[ ] G16 LAMCHONGNUOC (7)
[ ] G17 THAYBANHXE  (7)
   ⏸️ Smoke test app
[ ] G18 GANKIMCOC   (9)
[ ] G19 THAYMAYAUTO (9)
[ ] G20 DANHBONG    (10)
[ ] G21 THAYIC      (10)
[ ] G22 THAYMAYPIN  (10)
[ ] G23 KINHTHUONG  (13)
[ ] G24 KINHSAPPHIRE (27)
[ ] G25 BMD → SPK   (4, special merge)

PHASE 4
[ ] Verify *BG ref = 0
[ ] Cleanup 24 mã *BG

PHASE 5
[ ] Final SQL verification (Section 6)
[ ] Manual app smoke test (Section 6)

POST
[ ] Doc nội bộ cập nhật
[ ] Train NV pattern mã chuẩn
[ ] Backup cleanup sau 1 tuần
```

---

**END OF PLAN.md**
