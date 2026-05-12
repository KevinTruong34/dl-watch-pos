# AI_CONTEXT.md — DL Watch POS App

**Cập nhật:** 10/05/2026
**Mục đích:** Bàn giao context đầy đủ cho Claude session mới. POS app đã qua **Bước 1 → Bước 8 + LINE notification + URL session token + APSC display + SPK/DVPS open-price refactor**, đang ở giai đoạn polish và làm tính năng phụ.

---

## QUAN TRỌNG — ĐỌC ĐẦU TIÊN

Đây là dự án **POS app riêng** cho cửa hàng đồng hồ DL Watch, **chia sẻ database** với app quản lý cũ. Đã hoàn thành và deploy production qua **Bước 1 → Bước 8** + nhiều cải tiến tháng 5/2026.

User dùng tiếng Việt, xưng "mình/bạn". Tuân theo `CLAUDE.md` (đã upload lên project knowledge): think before coding, simplicity first, surgical changes, goal-driven execution. **Luôn hỏi clarifying questions trước khi implement, không pick interpretation silently.**

**★ Workflow mới đã proven (lưu trong memory):** 2-phase cho big features — Phase A planning trên Claude in app (front-load decisions → PLAN.md chi tiết), Phase B execute với Claude Code (pre-flight verify, commit từng phase, smoke tests trước INSERT thật). Pattern này thành công với SPK/DVPS refactor + bộ Admin Override (B1, B2a, B2b).

---

## TỔNG QUAN DỰ ÁN

### 2 app riêng biệt, 1 database

| App | Path | Mục đích | Trạng thái |
|-----|------|----------|------------|
| **App quản lý cũ** (legacy) | `web_app/` | Quản trị: hàng hóa, sửa chữa, kiểm kê, báo cáo, **admin override** | Production, đã migrate Hướng B + Admin features |
| **POS app mới** | `pos_app/` | Bán hàng tại quầy trên mobile | Production |

Cả 2 deploy lên **Streamlit Cloud** từ 2 GitHub repo riêng. Cùng dùng **Supabase project**.

Repo: `KevinTruong34/dl-watch-pos` (POS) · `KevinTruong34/DLW_APP` (web app)

### Stack

- **Frontend:** Streamlit (Python) — POS mobile-first max-width 480px, app cũ desktop max-width 1350px
- **Backend:** Supabase PostgreSQL + RPC functions + **Edge Function (Deno/TypeScript)** cho LINE
- **Deploy:** Streamlit Cloud (private repos, GitHub-linked)
- **3 chi nhánh:** `100 Lê Quý Đôn` · `Coop Vũng Tàu` · `GO BÀ RỊA`
- **Daemon in K80:** Windows laptop tại CN 100 LQĐ — Xprinter XP-365B static IP, port 9100, **đã raster bitmap mode** (in tiếng Việt OK)

### Người dùng & quyền

| Role | Quyền POS | Quyền app cũ |
|------|-----------|--------------|
| `admin` | Tất cả + hủy HĐ + hủy phiếu đổi/trả + hủy phiếu đặt | Tất cả modules + **Admin Override (tạo + sửa HĐ tự do)** |
| `ke_toan` | Bán hàng + lịch sử + đổi/trả + đặt hàng | Báo cáo + xem (không hủy/xóa) |
| `nhan_vien` | Bán hàng + xem lịch sử CN + đổi/trả (≤7 ngày) + đặt hàng | Hạn chế: hóa đơn, hàng hóa, sửa chữa, chuyển hàng |

---

## ROADMAP

```
[✓] Bước 1: Auth PIN — chọn NV, PIN 4 số bcrypt, session 23:59:59 VN
[✓] Bước 2A: Bán hàng (search + giỏ + dialog sửa dòng)
[✓] Bước 3: Thanh toán + RPC tạo hóa đơn atomic
[✓] Bước 4: Lịch sử hóa đơn + hủy (admin only, hoàn tồn kho)
[✓] Bước 5: Polish + deploy guide
[✓] Bước 6: Liên kết app cũ với HĐ POS (adapter load_hoa_don_unified)
[✓] Bước 7: Đổi/Trả hàng đã bán (AHDD prefix, RPC atomic)
[✓] Bước 7B: Adapter app cũ phản ánh phiếu đổi/trả (AHDD merge)
[✓] Bước 8: Đặt hàng theo yêu cầu (4 trạng thái + cọc + free-text)
[✓] LINE Notification: Edge Function + Database Webhook định tuyến CN (POS)
[✓] LINE APSC mở rộng: Branch 3 trên hoa_don table — DEPLOYED 07/05
[✓] Session token: URL params (?t=xxx) — sau khi cookie thất bại 3 vòng
[✓] APSC display trong POS lich_su: load + search + render từ hoa_don table
[✓] Migration Hướng B (web app side): the_kho = single-source-of-truth
[✓] Print K80 tiếng Việt: daemon raster bitmap mode (07/05/2026) — solve codepage
[✓] SPK/DVPS Refactor (08/05/2026): is_open_price flag — POS RPC patched
[✓] Admin Override (DLW side, 08-09/05/2026): B1 (tạo) + B2a (sửa HĐ POS) + B2b (sửa PDT/SC)
[✓] APSC K80 + Cancel (10/05/2026): in K80 từ DLW + RPC huy_hoa_don_apsc

[Pending — kỹ thuật phụ]
[ ] Phương án B (nhớ NV qua localStorage thuần) — UX skip bước chọn tài khoản
[ ] Casso/SePay webhook xác nhận chuyển khoản (B9-1..B9-5 đã chốt nghiệp vụ, paused)
[ ] Quản lý số dư khách hàng (tiền thừa)
[✓] Quét mã vạch live (11-12/05/2026) — html5-qrcode + st.components.v2
    POS: ban_hang + doi_tra (items_moi); DLW: chuyen_hang (Tạo/Sửa phiếu)
    2 file shared: utils/scanner_component.py + utils/barcode.py — sync 2 repo khi fix bug
[ ] Logs thao tác POS app vào action_logs (web app)
[ ] LINE notification mở rộng (đổi/trả + phiếu đặt hoàn thành)
[ ] Cache/spinner perf — tech debt
[ ] use_container_width deprecated sau 2025-12-31 → đổi width='stretch' toàn codebase
[ ] Daemon Windows Service thay vì run.bat
```

User đã **bỏ KiotViet** — adapter ở Bước 6 handle sẵn.

---

## ★ SPK/DVPS OPEN-PRICE REFACTOR (08/05/2026)

### Vấn đề cũ

24 nhóm dịch vụ cửa hàng dùng nhiều mã rác (vd `SPK001..SPK022`, `DVPS001..DVPS018`) cho cùng 1 dịch vụ chỉ khác giá. Tổng 170 mã rác. NV phải scroll list dài, dễ chọn nhầm.

### Giải pháp — flag `is_open_price`

- Thêm cột `hang_hoa.is_open_price BOOLEAN` (default false, partial index)
- Mã chuẩn: 25 mã (vd SPK, DVPS, LAUDAU, KSA, DANHBONG, KIEMTRAMAY, THAYIC, THAYDAYDONG, THAYRON, THAYTYNUT, THAYMAYDHDUNG, THAYDAYCOTGIO, THAYDAYTHIEU, THAYBANHXE, THAYCANGCUA, KINHSAPPHIRE, KINHTHUONG, THAYMAYPIN, THAYMAYAUTO, NHATRANG, HIEUCHUAN, GANKIMCOC, THAYCHOT, LAMCHONGNUOC, CATMATDAY, OTUDONG, BMD)
- Mã có `is_open_price=true` → NV nhập giá tự do tại UI bán hàng
- Mã có `is_open_price=false` (hàng thường) → giá cố định từ `gia_ban`
- KHÔNG đụng PIN (TPBG/PV/PDH — cần track tồn) và MDHTT (Thay máy treo tường — master data thực)

### Helpers mới

**SQL:**
```sql
CREATE FUNCTION is_open_price_sql(p_ma_hang text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT is_open_price FROM hang_hoa WHERE ma_hang = p_ma_hang), false);
$$;
```

**Python (POS `utils/db.py`):**
```python
def is_open_price_item(ma_hang: str, hang_hoa_dict: dict | None = None) -> bool:
    """Check 1 mã hàng có phải open-price không. Cache qua hang_hoa_dict optional."""
```

### POS RPC patches

4 RPCs đã update để skip stock check cho open-price (consistent pattern):
- `tao_hoa_don_pos`
- `huy_hoa_don_pos`
- `tao_phieu_doi_tra_pos`
- `huy_phieu_doi_tra_pos`

Pattern:
```sql
IF NOT is_open_price_sql(v_ma_hang) THEN
    -- check tồn kho + UPDATE the_kho
END IF;
```

### POS Module patches

- `pos_app/modules/ban_hang.py`: UI cho phép input giá khi `is_open_price=true`, skip stock check
- `pos_app/modules/doi_tra.py`: tương tự cho items_moi và items_tra

---

## CẤU TRÚC POS APP (`pos_app/`)

```
pos_app/
├── app.py                              # Entry, header, routing tab, MutationObserver inject inputmode
├── requirements.txt
├── README.md
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── docs/
│   ├── SETUP.md
│   └── ADMIN_GUIDE.md
├── sql/
│   ├── full_setup.sql                  # Schema cuối + RPC
│   ├── pos_setup.sql
│   ├── pos_patch_01_tien_thua.sql
│   ├── pos_patch_02_dich_vu.sql
│   ├── pos_patch_03_doi_tra.sql        # Bước 7
│   ├── pos_patch_04_huy_hd_check.sql   # Validate hủy HĐ khi đã có phiếu đổi/trả
│   ├── pos_patch_05_timezone_fix.sql   # Fix end-of-day VN trong RPC
│   ├── pos_patch_06_dat_hang.sql       # Bước 8
│   ├── pos_patch_07_session.sql        # Session token + RPC validate
│   └── pos_patch_08_open_price.sql     # ★ SPK/DVPS open-price (08/05/2026)
├── utils/
│   ├── __init__.py
│   ├── config.py                       # APP_NAME, ALL_BRANCHES, CN_SHORT, CN_INFO
│   ├── db.py                           # supabase client + load + RPC + validators + APSC loaders + is_open_price_item
│   ├── auth.py                         # PIN flow, session URL token, banner
│   ├── helpers.py                      # now_vn, today_vn, fmt_vnd, end_of_today_vn_iso
│   └── print_queue.py                  # Daemon enqueue cho HĐ POS + đổi/trả + đặt hàng
└── modules/
    ├── __init__.py
    ├── ban_hang.py                     # Màn 1 → 2 → 3 + open-price input UI + bypass stock cho open-price
    ├── lich_su.py                      # List HĐ + AHDD merge + APSC display + modal chi tiết + hủy
    ├── doi_tra.py                      # Bước 7: đổi/trả + open-price logic
    └── dat_hang.py                     # Bước 8: 4 trạng thái phiếu đặt
```

---

## DATABASE — TABLES SHARE GIỮA 2 APP

### Table chia sẻ (đã có từ app cũ)

| Table | Mô tả |
|-------|-------|
| `nhan_vien` | id, username, ho_ten, role, active. **role='admin'** dùng cho admin override (DLW) |
| `nhan_vien_chi_nhanh` | Phân quyền CN |
| `chi_nhanh` | 3 CN |
| `hang_hoa` | Master sản phẩm. **★ Cột mới `is_open_price BOOLEAN`** + `loai_sp`, `active` |
| `the_kho` | **Tồn kho LIVE (SSOT sau Hướng B)** — `Mã hàng`, `Chi nhánh`, `Tồn cuối kì` |
| `khach_hang` | Unique key `sdt`. `tong_ban` cộng dồn KiotViet + POS + AHDD chenh_lech |
| `sessions` | Session token |
| `hoa_don` | HĐ KiotViet legacy + **APSC sửa chữa từ web app** (denormalized, cột tiếng Việt) |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa. **Cột mới: `is_admin_created`, `admin_note`, `created_by_id`** |
| `print_queue` | **Cột mới: `source_app` (default 'pos_app')** — DLW dùng `'dlw_app'` |
| `admin_edit_history` | **★ Bảng mới (B2a)** — snapshot before/after JSONB cho mọi edit của admin |
| `phieu_chuyen_kho`, `phieu_nhap_hang`, `phieu_kiem_ke`, ... | App cũ |

### Table riêng của POS (không đổi)

```sql
-- pin_code, hoa_don_pos, hoa_don_pos_ct, phieu_doi_tra_pos, phieu_doi_tra_pos_ct, phieu_dat_hang
-- Cột mới (từ B1 admin override): is_admin_created, admin_note ở 3 bảng
--   hoa_don_pos, phieu_doi_tra_pos, phieu_sua_chua
```

### Sequences POS (không đổi)

```sql
ahd_seq    -- AHD HĐ POS
ahdd_seq   -- AHDD phiếu đổi/trả
ahdc_seq   -- AHDC phiếu đặt hàng
sc_seq     -- ★ MỚI (B1): cho phiếu sửa chữa, race-safe (Python cũng dùng nextval)
```

### RPC functions của POS (đã update)

**HĐ POS (đã patch open-price 08/05):**
- `tao_hoa_don_pos(payload jsonb)` — skip stock check cho open-price
- `huy_hoa_don_pos(p_ma_hd, p_cancelled_by)` — chỉ hoàn kho hàng thường
- `get_next_ahd_num()`

**Đổi/Trả (đã patch open-price):** `tao_phieu_doi_tra_pos`, `huy_phieu_doi_tra_pos`

**Đặt hàng:** `tao_phieu_dat_hang`, `cap_nhat_trang_thai_phieu_dat`, `hoan_thanh_phieu_dat_hang`, `huy_phieu_dat_hang`

**Session:** `create_session`, `validate_session`, `revoke_user_sessions`, `revoke_session_by_token`

**Stock writes (Hướng B):** `xac_nhan_chuyen_hang`, `nhan_hang`, `duyet_phieu_kiem_ke`

**★ Helper RPCs mới (chia với DLW):**
- `is_open_price_sql(p_ma_hang)` — SQL helper cho open-price detection
- `next_sc_seq()` — wrapper Python dùng nextval('sc_seq')
- (Admin RPCs — xem AI_CONTEXT.md web app)

---

## QUYẾT ĐỊNH NGHIỆP VỤ ĐÃ CHỐT (rút gọn)

### Bước 7 — Đổi/Trả

Hỗ trợ Trả / Đổi ngang / Đổi có chênh lệch / Trả 1 phần · Giới hạn 7 ngày NV (admin override) · Hàng trả tự cộng `the_kho` ngay · Phiếu link HĐ gốc qua `ma_hd_goc` · Chỉ admin được hủy phiếu · 1 HĐ → nhiều phiếu OK miễn tổng SL trả ≤ SL gốc · Shop hoàn tiền chỉ tiền mặt · Mã `AHDD`, sequence `ahdd_seq` · 1 bảng `_ct` chung (cột `kieu`) · Block hủy HĐ gốc khi đã có phiếu đổi/trả Hoàn thành.

### Bước 7B — Adapter web app

(1) Doanh thu cộng `chenh_lech` AHDD; (2) Bán hàng theo nhóm tính net items; (3) `khach_hang.tong_ban` cộng dồn `chenh_lech`; (4) Tab tra cứu HĐ web app merge AHDD với badge "Đổi/Trả".

### Bước 8 — Đặt hàng

4 trạng thái Chờ đặt → Chờ lấy → Hoàn thành (+ Đã hủy), có thể skip Chờ lấy · Cọc lưu chi tiết PTTT 3 cột · Tên hàng free-text, không đụng `hang_hoa` · RPC `bypass_stock_check=true` khi tạo HĐ từ phiếu đặt · Cho sửa giá lúc Hoàn thành · Admin được hủy với option Trả cọc / Giữ cọc · Mã `AHDC`, sequence `ahdc_seq` · Khi Hoàn thành tạo `hoa_don_pos` link qua `ma_pdh`.

### LINE Notification

**Architecture:** Event-driven Edge Function (Deno/TypeScript) tên `line-notify`. Python KHÔNG gọi LINE trực tiếp. Database webhook → Edge Function → LINE Push API.

**3 nhánh:**
- **Branch 1:** webhook trên `phieu_doi_tra_pos` INSERT → đổi/trả notification
- **Branch 2:** webhook trên `hoa_don_pos` INSERT → HĐ POS với phân loại VIP ≥10M / hàng đặt AHDC / thường
- **Branch 3:** webhook trên `hoa_don` INSERT → APSC sửa chữa (dedupe race-free qua `lt id`)

**Định tuyến CN:** `100 LQĐ` + `GO BÀ RỊA` → cùng group `LINE_GROUP_BARIA`. `Coop Vũng Tàu` skip.

### Session Token Architecture

URL params `?t=xxx&b=xxx`. NV nhập PIN mỗi sáng. Token expire cuối ngày VN. Logout = revoke ALL sessions cross-device.

### APSC Display trong POS lich_su

POS hiển thị HĐ APSC từ `hoa_don` table (read-only, không có nút Hủy/Đổi/In). 3 nguồn merged trong lich_su:
- `load_hoa_don_pos_history` → AHD
- `load_phieu_doi_tra_pos_history` → AHDD
- `load_apsc_history` → APSC

**★ Lưu ý sau APSC K80 (10/05/2026):** Nút "In lại" + "Hủy HĐ" cho APSC đặt trên **DLW** (không POS). POS chỉ hiển thị read-only.

---

## QUYẾT ĐỊNH KỸ THUẬT (DECISIONS)

| # | Quyết định | Lý do |
|---|------------|-------|
| D1 | POS tạo bảng riêng `hoa_don_pos` (normalized) | Schema sạch. Adapter Bước 6 lo gộp |
| D2 | Adapter trong Python ở Bước 6 | Surgical, code app cũ thay đổi 1-2 dòng/module |
| D3 | RPC atomic cho mọi thao tác ghi DB | Tránh race condition |
| D4 | Dịch vụ: `loai_sp = "Dịch vụ"` → skip stock check + skip trừ kho | Không phá kho |
| D5 | Tien thừa: ghi nhận `tien_thua` column nhưng không auto-credit | Phase 1 đơn giản |
| D6 | NV thường thấy mọi HĐ POS của CN | User chọn |
| D7 | Hủy HĐ: chỉ admin, bất kỳ lúc nào | User chọn |
| D8 | HĐ đã hủy: hiện xám trong list | User chọn |
| D9 | "Xem cũ hơn" lịch sử: +1 ngày/click | User chọn |
| D10 | In K80: kiến trúc Cloud-to-LAN spooler | ✅ Đã solve (raster bitmap 07/05) |
| D11 | Bước 6: tách prefix APSC / AHD / KiotViet | User chọn |
| D12 | Sau bỏ KiotViet: không cần code thay đổi | Adapter tự thích nghi |
| D13 | Bước 7 prefix `AHDD`, sequence riêng | Tách bạch HĐ POS |
| D14 | Bước 7: 1 bảng `_ct` chung (cột `kieu`) | Đơn giản hơn 2 bảng |
| D15 | Bước 7: shop hoàn tiền chỉ tiền mặt | User chọn |
| D16 | Bước 7B: tong_ban cộng `chenh_lech` AHDD | Sửa D11 cũ — chính xác hơn |
| D17 | Bước 8: prefix `AHDC`, sequence `ahdc_seq` | Tách bạch |
| D18 | Bước 8: free-text tên hàng, không đụng `hang_hoa` | Hàng yêu cầu thường chưa có trong DB |
| D19 | Bước 8: RPC `bypass_stock_check` cho HĐ từ phiếu đặt | Hàng free-text không có `the_kho` |
| D20 | Bước 8: cọc lưu chi tiết PTTT (3 cột) | Báo cáo chính xác |
| D21 | LINE Edge Function: `setTimeout(1500)` chờ ghi `_ct` | Streamlit ghi tuần tự |
| D22 | Session token URL params (sau 4 vòng cookie thất bại) | An toàn 100% > UX persist |
| D23 | LINE Branch 3 APSC: dedupe `lt id` check | Race-free, no schema change |
| D24 | APSC display trong POS lich_su: read-only, KHÔNG Hủy/In/Đổi | Action đặt trên DLW (10/05) |
| D25 | Hướng B: `the_kho` = SSOT | POS thừa hưởng |
| D26 | Logs thao tác POS chưa ghi vào `action_logs` | Pending |
| **D27** | **★ SPK/DVPS: flag `is_open_price` thay convention OR-list** | Future-proof, server-side check, scalable |
| **D28** | **★ Admin Override (DLW): `nhan_vien.role='admin'` server-side check** | Reuse cột sẵn có, không tạo permission table |
| **D29** | **★ APSC K80 + Cancel: in K80 + nút action đặt trên DLW (KHÔNG POS)** | Tránh duplicate code 2 repo, scope hẹp |
| **D30** | **★ `print_queue.source_app`: distinguish 'pos_app' vs 'dlw_app'** | Trace nguồn gốc job in |

---

## CÁC FILE QUAN TRỌNG VÀ NỘI DUNG CHÍNH

### `utils/db.py` (POS) — đã thêm helpers + APSC functions

```python
# Existing helpers
load_nhan_vien_active()
load_pin(nv_id) / set_pin(nv_id, pin_hash)
load_hang_hoa_pos(chi_nhanh)             # Dịch vụ: ton=999999 vô hạn

# Khách hàng
lookup_khach_hang_by_sdt(sdt)
upsert_khach_hang(ten, sdt, chi_nhanh)

# HĐ POS
load_hoa_don_pos_history(chi_nhanh, from_date_iso)
tao_hoa_don_pos_rpc(payload)
huy_hoa_don_pos_rpc(ma_hd, cancelled_by)

# Đổi/Trả
search_hoa_don_pos(keyword, chi_nhanh_list, limit=30)
load_hoa_don_pos_by_ma(ma_hd)
load_phieu_doi_tra_by_hd(ma_hd_goc)
get_sl_da_tra_map(ma_hd_goc)
load_phieu_doi_tra_pos_history(chi_nhanh, from_date)
tao_phieu_doi_tra_pos_rpc(payload)
huy_phieu_doi_tra_pos_rpc(ma_pdt, cancelled_by)

# Đặt hàng
load_phieu_dat_hang(chi_nhanh, trang_thai_filter=None)
tao_phieu_dat_hang_rpc(payload)
cap_nhat_trang_thai_phieu_dat_rpc(...)
hoan_thanh_phieu_dat_hang_rpc(payload)
huy_phieu_dat_hang_rpc(ma_pdh, cancelled_by, ly_do_huy)

# Session
create_session_rpc(nv_id, user_agent)
validate_session_rpc(token)
revoke_user_sessions_rpc(nv_id)
revoke_session_by_token_rpc(token)

# APSC display
_build_apsc_dict(ma_hd, rows)
load_apsc_history(chi_nhanh, from_date_iso=None, limit=100)
search_apsc(keyword, branches, limit=30)

# ★ MỚI: Open-price helper (08/05/2026)
is_open_price_item(ma_hang, hang_hoa_dict=None) -> bool
```

### `modules/ban_hang.py` (★ patched 08/05)

UI cart: nếu item có `is_open_price=true` → render `st.number_input` cho đơn giá editable. Stock check skip cho open-price (consistent với RPC).

### `modules/doi_tra.py` (★ patched 08/05)

Tương tự `ban_hang.py` cho items_moi và items_tra. Open-price không cần check stock khi đổi.

### `modules/lich_su.py`

3 sources merged (HĐ POS + AHDD + APSC). APSC dialog **read-only** (không Hủy/Đổi/In). User in lại / hủy APSC qua DLW app.

### `utils/print_queue.py`

POS public API:
- `enqueue_hoa_don(ma_hd, created_by)` — doc_type='hoa_don', source_app='pos_app'
- `enqueue_phieu_dat(ma_pdh, created_by)` — doc_type='phieu_dat_hang'
- `enqueue_phieu_doi_tra(ma_pdt, created_by)` — doc_type='phieu_doi_tra'

**Note:** APSC được enqueue từ DLW (`web_app/utils/print_queue_apsc.py`), KHÔNG phải POS.

---

## CÁC PATTERN KỸ THUẬT QUAN TRỌNG

### 1. Mobile column stacking fix (CSS scoped)
(không đổi — xem session sử)

### 2. Numeric keyboard global (MutationObserver)
(không đổi)

### 3. Timezone
`ZoneInfo("Asia/Ho_Chi_Minh")` cho VN time. Supabase lưu `timestamptz` UTC. **Phải convert về VN** trước `strftime`.

### 4. Streamlit toast icon
Phải emoji thật (✅ ❌), không Unicode "Check Mark" (✓ ✗).

### 5. Dialog state pattern (top-level, tránh nested @st.dialog)
(không đổi)

### 6. Cache invalidation sau ghi DB
```python
load_hang_hoa_pos.clear()
load_phieu_doi_tra_pos_history.clear()
load_phieu_dat_hang.clear()
```

### 7. Reset counter pattern cho form
(không đổi)

### 8. Sanity check syntax trước push
```bash
python3 -c "import ast; ast.parse(open('modules/X.py').read())"
```

### 9. APSC schema mapping
`hoa_don` table dùng cột tiếng Việt có dấu (KiotViet schema):
```python
head["Mã hóa đơn"]    # NOT head.ma_hd
head["Chi nhánh"]
head["Tổng tiền hàng"]
head["Người bán"]
head["Mã YCSC"]
```

### 10. ★ Open-price detection pattern (mới)

```python
# Python
from utils.db import is_open_price_item
if is_open_price_item(ma_hang):
    # input giá tự do, skip stock check
```

```sql
-- SQL trong RPC
IF NOT is_open_price_sql(v_ma_hang) THEN
    -- check tồn kho + UPDATE the_kho
END IF;
```

---

## CONSTANTS & SECRETS
(không đổi — xem session sử)

---

## STYLE GUIDE KHI LÀM VIỆC VỚI USER

- Tiếng Việt, "mình/bạn", trả lời ngắn gọn rõ ràng
- User dùng thuật ngữ kỹ thuật chính xác — không cần đơn giản hóa
- User kỹ tính, hay phát hiện edge case
- User đôi khi tự fix code mà không báo → **luôn ask user gửi lại file trước khi code tiếp** nếu có nguy cơ override
- `CLAUDE.md`: think before coding, simplicity, surgical changes
- Khi đề xuất plan, **luôn list rõ scope rồi đợi approve**
- Khi có choice, **trình bày 2-3 lựa chọn, recommend 1, giải thích tại sao**
- Khi user hỏi clarification, dùng `ask_user_input_v0` cho options nhanh
- Patches dạng search-replace inline để user apply tay (file > 500 dòng không rewrite full)
- Recommend pattern atomic RPC + verify Supabase queries trước khi sửa
- **★ Workflow lớn: 2-phase A planning + B execute với Claude Code** (proven trên SPK/DVPS, B1, B2a, B2b)

---

## CHECKLIST BÀN GIAO

Claude session mới nên:

1. ✅ Đọc `CLAUDE.md` trong project knowledge
2. ✅ Đọc cả 2 file `AI_CONTEXT.md` (POS + web app — bổ trợ lẫn nhau)
3. ✅ Hỏi user gửi các file Python liên quan trước khi code (tránh override)
4. ✅ Đề xuất plan kỹ thuật, đợi approve
5. ✅ Code, deliver as patch hoặc full files
6. ✅ Sau test, cập nhật roadmap

---

## OPEN ISSUES — CẦN LÀM Ở SESSION SAU

| # | Item | Trạng thái | Note |
|---|------|------------|------|
| 1 | LINE notification mở rộng | Pending | Đổi/trả + phiếu đặt hoàn thành |
| 2 | Performance perf | Pending | Web app side, ảnh hưởng cả 2 app |
| 3 | Logs thao tác POS app vào `action_logs` | Pending | Lower priority |
| 4 | UI admin xem session POS active | Pending | DB schema có sẵn (LS-3) |
| 5 | `use_container_width` deprecated | Pending | Cần đổi width='stretch' toàn codebase trước 31/12/2025 |
| 6 | Daemon Windows Service thay run.bat | Pending | Auto-start không cần manual |

---

## TROUBLESHOOTING REFERENCE

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `Chưa cấu hình SUPABASE_URL` | Streamlit secrets thiếu | Set Streamlit Cloud → Secrets |
| Bàn phím chữ thay vì số ở PIN | MutationObserver chưa inject | Hard refresh (Ctrl+Shift+R) |
| `Lỗi tạo hóa đơn: tồn không đủ` | Race / tồn = 0 | Refresh, check `the_kho` |
| Banner session sai giờ | Strftime trên UTC | Đã fix Bước 5 |
| `st.toast` báo lỗi icon | Unicode thay vì emoji | `✓` → `✅` |
| HĐ POS không hiện app cũ | Cache 5 phút | Bấm "↺ Tải lại" |
| LINE không nhận thông báo | Edge Function lỗi hoặc Group ID sai | Check Supabase logs > Edge Functions |
| Multi-NV cùng login do share URL | URL chứa `?t=...` cũ | Mở URL gốc → màn login |
| HĐ từ phiếu đặt báo "không đủ tồn" | RPC quên `bypass_stock_check=true` | Patch 06 đã fix |
| APSC LINE gửi 3 tin/HĐ | Dedupe lt id không match | Check `hoa_don` có cột `id` PK |
| In K80 ra CJK/lỗi tiếng Việt | Codepage không match | ✅ Đã solve qua raster bitmap (07/05) |
| **★ Open-price hàng vẫn check kho** | RPC chưa patch | Verify RPC có dùng `is_open_price_sql()` |
| **★ POS RPC fail "duplicate ma_phieu"** | Race với SC seq | Đã fix dùng `nextval('sc_seq')` (08/05) |

---

## RESET POS DATA SQL

File `reset_pos_data.sql`: hoàn tồn kho cho HĐ Hoàn thành + đảo tồn từ phiếu đổi/trả + DELETE theo thứ tự FK + RESTART sequences về 1. Có sanity check cuối query. Dùng khi cần reset toàn bộ dữ liệu POS để test lại từ đầu (KHÔNG dùng production trừ khi user yêu cầu rõ).

---

## CONTACT

User: **chủ cửa hàng đồng hồ DL Watch** ở Bà Rịa - Vũng Tàu (Kevin). Liên hệ qua chat Claude.
