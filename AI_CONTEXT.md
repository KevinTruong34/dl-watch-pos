# AI_CONTEXT.md — DL Watch POS App

**Cập nhật:** 07/05/2026
**Mục đích:** Bàn giao context đầy đủ cho Claude session mới. POS app đã qua **Bước 1 → Bước 8 + LINE notification + URL session token + APSC display**, đang ở giai đoạn polish và làm thêm tính năng phụ.

---

## QUAN TRỌNG — ĐỌC ĐẦU TIÊN

Đây là dự án **POS app riêng** cho cửa hàng đồng hồ DL Watch, **chia sẻ database** với app quản lý cũ. Đã hoàn thành và deploy production qua **Bước 1 → Bước 8**.

User dùng tiếng Việt, xưng "mình/bạn". Tuân theo `CLAUDE.md` (đã upload lên project knowledge): think before coding, simplicity first, surgical changes, goal-driven execution. **Luôn hỏi clarifying questions trước khi implement, không pick interpretation silently.**

---

## TỔNG QUAN DỰ ÁN

### 2 app riêng biệt, 1 database

| App | Path | Mục đích | Trạng thái |
|-----|------|----------|------------|
| **App quản lý cũ** (legacy) | `web_app/` | Quản trị: hàng hóa, sửa chữa, kiểm kê, báo cáo | Production, đã migrate Hướng B |
| **POS app mới** | `pos_app/` | Bán hàng tại quầy trên mobile | Production |

Cả 2 deploy lên **Streamlit Cloud** từ 2 GitHub repo riêng. Cùng dùng **Supabase project** (cùng `SUPABASE_URL` + `SUPABASE_KEY`).

Repo: `KevinTruong34/dl-watch-pos` (POS) · `KevinTruong34/DLW_APP` (web app)

### Stack

- **Frontend:** Streamlit (Python) — POS mobile-first max-width 480px, app cũ desktop max-width 1350px
- **Backend:** Supabase PostgreSQL + RPC functions + **Edge Function (Deno/TypeScript)** cho LINE
- **Deploy:** Streamlit Cloud (private repos, GitHub-linked)
- **3 chi nhánh:** `100 Lê Quý Đôn` · `Coop Vũng Tàu` · `GO BÀ RỊA`
- **Daemon in K80:** Windows laptop tại CN 100 LQĐ — Xprinter XP-365B static IP, port 9100

### Người dùng & quyền

| Role | Quyền POS | Quyền app cũ |
|------|-----------|--------------|
| `admin` | Tất cả + hủy HĐ + hủy phiếu đổi/trả + hủy phiếu đặt | Tất cả modules |
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
[✓] LINE Notification mở rộng APSC: Branch 3 trên hoa_don table — DEPLOYED 07/05, đợi test
[✓] Session token: URL params (?t=xxx) — sau khi cookie thất bại 3 vòng
[✓] APSC display trong POS lich_su: load + search + render từ hoa_don table — TESTED OK
[✓] Migration Hướng B (web app side): the_kho = single-source-of-truth — POS thừa hưởng

[In Progress]
[~] Print K80 tiếng Việt: daemon ESC/POS, máy ra CJK → fix codepage
    - Pattern A: POS lưu UTF-8, daemon encode CP1258 + ESC commands
    - Issue: Xprinter XP-365B codepage 27 không phải CP1258 chuẩn
    - Test file test_vn_v2.py chưa chạy, gác lại
    - Whitelist: PRINT_ENABLED_BRANCHES = {"100 Lê Quý Đôn"} only

[Pending — kỹ thuật phụ]
[ ] Phương án B (nhớ NV qua localStorage thuần) — UX skip bước chọn tài khoản
[ ] Casso/SePay webhook xác nhận chuyển khoản (B9-1..B9-5 đã chốt nghiệp vụ, paused)
[ ] Quản lý số dư khách hàng (tiền thừa)
[ ] Quét mã vạch (Phase 2B)
[ ] Logs thao tác POS app vào action_logs (web app)
[ ] LINE notification mở rộng (đổi/trả + phiếu đặt hoàn thành)
[ ] Cache/spinner perf — tech debt
[ ] use_container_width deprecated sau 2025-12-31 → đổi sang width='stretch' toàn codebase
[ ] Daemon Windows Service thay vì run.bat
```

User đã **bỏ KiotViet** — adapter ở Bước 6 handle sẵn.

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
│   └── pos_patch_07_session.sql        # Session token + RPC validate
├── utils/
│   ├── __init__.py
│   ├── config.py                       # APP_NAME, ALL_BRANCHES, CN_SHORT, CN_INFO
│   ├── db.py                           # supabase client + load + RPC + validators + APSC loaders
│   ├── auth.py                         # PIN flow, session URL token, banner
│   ├── helpers.py                      # now_vn, today_vn, fmt_vnd, end_of_today_vn_iso
│   └── print_queue.py                  # Daemon-side print enqueue (in dev)
└── modules/
    ├── __init__.py
    ├── ban_hang.py                     # Màn 1 → 2 → 3 + hỗ trợ tạo HĐ từ phiếu đặt
    ├── lich_su.py                      # List HĐ + AHDD merge + APSC display + modal chi tiết + hủy
    ├── doi_tra.py                      # Bước 7: đổi/trả full-screen + dialog AHDD
    └── dat_hang.py                     # Bước 8: 4 trạng thái phiếu đặt
```

---

## DATABASE — TABLES SHARE GIỮA 2 APP

### Table chia sẻ (đã có từ app cũ)

| Table | Mô tả |
|-------|-------|
| `nhan_vien` | id, username, ho_ten, role, active |
| `nhan_vien_chi_nhanh` | Phân quyền CN |
| `chi_nhanh` | 3 CN |
| `hang_hoa` | Master sản phẩm. Cột `loai_sp` ("Hàng hóa"/"Dịch vụ") + `active` |
| `the_kho` | **Tồn kho LIVE (SSOT sau Hướng B)** — `Mã hàng`, `Chi nhánh`, `Tồn cuối kì` |
| `khach_hang` | Unique key `sdt`. `tong_ban` cộng dồn KiotViet + POS + AHDD chenh_lech |
| `sessions` | Session token (đã mở rộng — xem Session Token Architecture) |
| `hoa_don` | HĐ KiotViet legacy + **APSC sửa chữa từ web app** (denormalized) |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa |
| `phieu_chuyen_kho`, `phieu_nhap_hang`, `phieu_kiem_ke`, ... | App cũ |

### Table riêng của POS

```sql
-- pin_code: PIN bcrypt cho mỗi NV
pin_code (
    nhan_vien_id  bigint PRIMARY KEY,
    pin_hash      text NOT NULL,
    updated_at    timestamptz
)

-- hoa_don_pos: header HĐ POS (1 dòng/HĐ)
hoa_don_pos (
    ma_hd            text PRIMARY KEY,         -- AHD000001
    chi_nhanh        text,
    ma_kh, ten_khach, sdt_khach,
    tong_tien_hang, giam_gia_don, khach_can_tra,
    tien_mat, chuyen_khoan, the, tien_thua,
    tien_coc_da_thu  integer,                  -- BƯỚC 8: cọc đã thu từ phiếu đặt
    trang_thai       text,                     -- "Hoàn thành" | "Đã hủy"
    nguoi_ban, nguoi_ban_id, ghi_chu,
    created_at, cancelled_by, cancelled_at,
    ma_pdh           text                      -- BƯỚC 8: link tới phieu_dat_hang nếu có
)

hoa_don_pos_ct (...)

-- BƯỚC 7: đổi/trả
phieu_doi_tra_pos (
    ma_pdt           text PRIMARY KEY,         -- AHDD000001
    ma_hd_goc        text REFERENCES hoa_don_pos(ma_hd),
    ...
)
phieu_doi_tra_pos_ct (...)

-- BƯỚC 8: đặt hàng theo yêu cầu
phieu_dat_hang (
    ma_pdh           text PRIMARY KEY,         -- AHDC000001
    ten_hang_yeu_cau text,                     -- free-text mô tả
    so_luong, gia_du_kien, tien_coc,
    pttt_coc_tien_mat, pttt_coc_chuyen_khoan, pttt_coc_the integer,
    trang_thai       text,                     -- "Chờ đặt" | "Chờ lấy" | "Hoàn thành" | "Đã hủy"
    ngay_du_kien_co, ghi_chu,
    nguoi_tao, nguoi_tao_id,
    created_at, updated_at,
    cancelled_by, cancelled_at, ly_do_huy,
    ma_hd            text                      -- link tới hoa_don_pos khi Hoàn thành
)

-- Sequences
CREATE SEQUENCE ahd_seq START 1;     -- AHD HĐ POS
CREATE SEQUENCE ahdd_seq START 1;    -- AHDD phiếu đổi/trả
CREATE SEQUENCE ahdc_seq START 1;    -- AHDC phiếu đặt hàng
```

### RPC functions của POS

**HĐ POS:**
- `tao_hoa_don_pos(payload jsonb) → jsonb` — atomic create với `bypass_stock_check` cho HĐ từ phiếu đặt (Bước 8)
- `huy_hoa_don_pos(p_ma_hd, p_cancelled_by) → jsonb` — atomic cancel, hoàn tồn kho, **block nếu HĐ đã có phiếu đổi/trả Hoàn thành**
- `get_next_ahd_num() → bigint`

**Đổi/Trả:** `tao_phieu_doi_tra_pos`, `huy_phieu_doi_tra_pos`

**Đặt hàng:** `tao_phieu_dat_hang`, `cap_nhat_trang_thai_phieu_dat`, `hoan_thanh_phieu_dat_hang`, `huy_phieu_dat_hang`

**Session:** `create_session`, `validate_session`, `revoke_user_sessions`, `revoke_session_by_token`

**Stock writes (Hướng B - chia với web app):** `xac_nhan_chuyen_hang`, `nhan_hang`, `duyet_phieu_kiem_ke` — atomic, lock + validate + apply trực tiếp `the_kho`. Xem web app AI_CONTEXT.

---

## QUYẾT ĐỊNH NGHIỆP VỤ ĐÃ CHỐT (đã rút gọn — chi tiết xem session sử)

### Bước 7 — Đổi/Trả

Hỗ trợ Trả / Đổi ngang / Đổi có chênh lệch / Trả 1 phần · Giới hạn 7 ngày NV (admin override) · Hàng trả tự cộng `the_kho` ngay · Phiếu link HĐ gốc qua `ma_hd_goc` · Chỉ admin được hủy phiếu · 1 HĐ → nhiều phiếu OK miễn tổng SL trả ≤ SL gốc · Shop hoàn tiền chỉ tiền mặt · Mã `AHDD`, sequence `ahdd_seq` · 1 bảng `_ct` chung (cột `kieu`) · Block hủy HĐ gốc khi đã có phiếu đổi/trả Hoàn thành.

### Bước 7B — Adapter web app

(1) Doanh thu cộng `chenh_lech` AHDD; (2) Bán hàng theo nhóm tính net items; (3) `khach_hang.tong_ban` cộng dồn `chenh_lech`; (4) Tab tra cứu HĐ web app merge AHDD với badge "Đổi/Trả".

### Bước 8 — Đặt hàng

4 trạng thái Chờ đặt → Chờ lấy → Hoàn thành (+ Đã hủy), có thể skip Chờ lấy · Cọc lưu chi tiết PTTT 3 cột · Tên hàng free-text, không đụng `hang_hoa` · RPC `bypass_stock_check=true` khi tạo HĐ từ phiếu đặt · Cho sửa giá lúc Hoàn thành · Admin được hủy với option Trả cọc / Giữ cọc · Mã `AHDC`, sequence `ahdc_seq` · Khi Hoàn thành tạo `hoa_don_pos` link qua `ma_pdh`.

### LINE Notification (đã mở rộng 07/05/2026)

**Architecture:** Event-driven Edge Function (Deno/TypeScript) tên `line-notify`. **Python KHÔNG gọi LINE trực tiếp** — chỉ INSERT vào DB, webhook tự fire.

**3 nhánh hiện tại:**
- **Branch 1:** webhook trên `phieu_doi_tra_pos` INSERT → đổi/trả notification
- **Branch 2:** webhook trên `hoa_don_pos` INSERT → HĐ POS (kèm phân loại VIP ≥10M / hàng đặt AHDC / thường), `setTimeout(1500)` chờ ghi xong `hoa_don_pos_ct` rồi fetch chi tiết
- **Branch 3 (07/05/2026):** webhook trên `hoa_don` INSERT → APSC sửa chữa
  - Lọc `record["Mã hóa đơn"]` startsWith `'APSC'`, bỏ qua HĐ KiotViet khác
  - **Dedupe:** 1 APSC = N rows (mỗi item 1 row, denormalized KiotViet schema). Chỉ row có id thấp nhất gửi LINE. Race-free vì AFTER ROW trigger fire post-commit.
  - Code: `supabase.from('hoa_don').select('id').eq('Mã hóa đơn', maHd).lt('id', record.id).limit(1)` — nếu có row → skip
  - Đợi 1.5s rồi query toàn bộ rows cùng `ma_hd` để build danh sách dịch vụ
  - Đọc theo cột tiếng Việt có dấu (KiotViet schema): `record["Chi nhánh"]`, `record["Tổng tiền hàng"]`, etc.

**Định tuyến CN:** Cấu hình cứng trong code TS:
- `100 LQĐ` + `GO BÀ RỊA` → cùng group `LINE_GROUP_BARIA`
- `Coop Vũng Tàu` → return 200, skip (chưa có group)

**Auto-response messages** trên LINE Manager đã **tắt** (tránh bot spam).

### Session Token Architecture

Sau 4 vòng cookie thất bại → URL params `?t=xxx&b=xxx`. NV phải nhập PIN mỗi sáng (~5 giây).

- **LS-1:** Token expire cuối ngày VN
- **LS-2:** Logout = revoke ALL sessions cross-device (cùng NV)
- **LS-3:** Admin web app xem session active (chưa làm UI, chỉ có DB schema)
- **LS-4:** Cho phép nhiều thiết bị cùng login 1 NV
- **LS-5:** ~~localStorage~~ → URL params

**SQL Patch 07** (`pos_patch_07_session.sql`): ALTER `sessions` thêm `last_used_at`, `user_agent`, `revoked_at`, indexes; 4 RPC.

### APSC Display trong POS lich_su (07/05/2026 — TESTED OK)

**Yêu cầu:** Khách counter cần xem cả lịch sử mua hàng + lịch sử sửa chữa. APSC được web app `_tao_hoa_don_apsc` insert vào `hoa_don` table (không phải `hoa_don_pos`).

**Implementation:**
- POS `utils/db.py` thêm 3 hàm:
  - `_build_apsc_dict(ma_hd, rows)` — group N rows denormalized → 1 dict với schema khớp `hoa_don_pos`. Parse "Thời gian" "DD/MM/YYYY HH:MM:SS" → ISO + tzinfo VN.
  - `load_apsc_history(chi_nhanh, from_date_iso, limit=100)` — load APSC, group, filter date in-Python
  - `search_apsc(keyword, branches, limit=30)` — full-text search trên ma_hd + sdt + ten_khach
- POS `modules/lich_su.py`:
  - Import 2 hàm trên
  - `_render_apsc_card(apsc)` — badge cam "🔧 Sửa chữa", icon 🔧 trước mã HĐ, link "từ {ma_ycsc}"
  - `@st.dialog _dialog_chi_tiet_apsc(apsc)` — read-only, không có nút Đổi/Trả/Hủy/In
  - `module_lich_su()` merge APSC vào `all_items` với `_type="apsc"`, route renderer theo type
  - `_render_find_results()` cũng search APSC, merge với HĐ POS

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
| D10 | In K80: kiến trúc Cloud-to-LAN spooler | In progress (codepage issue) |
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
| D21 | LINE Edge Function: `setTimeout(1500)` chờ ghi `_ct` | Streamlit ghi tuần tự, header xong trước chi tiết |
| D22 | Session token URL params (sau 4 vòng cookie thất bại) | An toàn 100% > UX persist |
| D23 | LINE Branch 3 APSC: dedupe bằng `lt id` check | Race-free, no schema change |
| D24 | APSC display trong POS lich_su: read-only, không Hủy/In/Đổi | APSC sống ở web app, POS chỉ tham khảo |
| D25 | Hướng B (web app side): `the_kho` = SSOT | POS thừa hưởng — RPC POS đã ghi trực tiếp `the_kho` từ đầu |
| D26 | Logs thao tác POS chưa ghi vào `action_logs` | Pending |

---

## CÁC FILE QUAN TRỌNG VÀ NỘI DUNG CHÍNH

### `utils/db.py` (POS) — đã thêm APSC functions

```python
# Helpers (cache 5min unless noted)
load_nhan_vien_active()
load_pin(nv_id) / set_pin(nv_id, pin_hash)
load_hang_hoa_pos(chi_nhanh)             # Dịch vụ: ton=999999 vô hạn

# Khách hàng
lookup_khach_hang_by_sdt(sdt)
upsert_khach_hang(ten, sdt, chi_nhanh)   # tự sinh AKH nếu mới
clean_phone(s) / clean_name(s)

# HĐ POS
load_hoa_don_pos_history(chi_nhanh, from_date_iso)
tao_hoa_don_pos_rpc(payload)
huy_hoa_don_pos_rpc(ma_hd, cancelled_by)

# Đổi/Trả (Bước 7)
search_hoa_don_pos(keyword, chi_nhanh_list, limit=30)
load_hoa_don_pos_by_ma(ma_hd)
load_phieu_doi_tra_by_hd(ma_hd_goc)
get_sl_da_tra_map(ma_hd_goc)
load_phieu_doi_tra_pos_history(chi_nhanh, from_date)
tao_phieu_doi_tra_pos_rpc(payload)
huy_phieu_doi_tra_pos_rpc(ma_pdt, cancelled_by)

# Đặt hàng (Bước 8)
load_phieu_dat_hang(chi_nhanh, trang_thai_filter=None)
tao_phieu_dat_hang_rpc(payload)
cap_nhat_trang_thai_phieu_dat_rpc(...)
hoan_thanh_phieu_dat_hang_rpc(payload)
huy_phieu_dat_hang_rpc(ma_pdh, cancelled_by, ly_do_huy)

# Session (URL token)
create_session_rpc(nv_id, user_agent)
validate_session_rpc(token)
revoke_user_sessions_rpc(nv_id)
revoke_session_by_token_rpc(token)

# APSC display (07/05/2026 - đọc từ hoa_don table KiotViet schema)
_build_apsc_dict(ma_hd, rows)            # Group N rows → 1 dict, parse "DD/MM/YYYY HH:MM:SS" → ISO
load_apsc_history(chi_nhanh, from_date_iso=None, limit=100)
search_apsc(keyword, branches, limit=30)
```

### `utils/auth.py` (POS) — URL session token

(không thay đổi — xem session sử)

### `app.py` (POS)

(không thay đổi — xem session sử)

### `modules/ban_hang.py`

(không thay đổi — xem session sử)

### `modules/lich_su.py` (07/05/2026 — đã mở rộng APSC)

State: `st.session_state["lichsu_days_back"]` (mặc định 0)

**Sources merged trong `module_lich_su`:**
- `load_hoa_don_pos_history` → AHD (HĐ POS)
- `load_phieu_doi_tra_pos_history` → AHDD (đổi/trả)
- `load_apsc_history` → APSC (sửa chữa, từ hoa_don table)

**Items list:** `[{"_type": "hd"|"pdt"|"apsc", **data}]`, sort newest-first by `_parse_iso(created_at)`. Ẩn HĐ + phiếu + APSC `trang_thai="Đã hủy"`.

**Renderers:**
- `_render_invoice_card(inv)` — HĐ POS, badge xanh "Hoàn thành"
- `_render_pdt_card(pdt)` — đổi/trả, badge tùy loại, hiển thị chenh_lech màu
- `_render_apsc_card(apsc)` — APSC, badge cam "🔧 Sửa chữa", link "từ {ma_ycsc}"

**Modals (top-level via session_state pattern):**
- `_dialog_chi_tiet(inv)` — HĐ POS, có nút Đổi/Trả + Hủy (admin) + In lại
- `dialog_chi_tiet_pdt(pdt)` — đổi/trả, từ module doi_tra
- `_dialog_chi_tiet_apsc(apsc)` — APSC, **read-only** (không Hủy/Đổi/In)

**Pending dialog handlers ở đầu `module_lich_su`:** `lichsu_confirm_huy` (HĐ POS), `pdt_confirm_huy`, `lichsu_view_pdt`, `lichsu_view_apsc`.

**Search range:** ô tìm SĐT/Mã (mọi ngày) → `_render_find_results(kw)` chạy `search_hoa_don_pos` + `search_apsc`, merge sort.

**Bug history fix:** Form Tạo mới reset (counter pattern), HĐ POS từ phiếu đặt hiện cọc, `dict.DataFrame` (rename pd loop), IndentationError 681.

### `modules/doi_tra.py`, `modules/dat_hang.py`

(không thay đổi — xem session sử)

### `utils/print_queue.py` (in progress)

- `PRINT_ENABLED_BRANCHES = {"100 Lê Quý Đôn"}` — whitelist
- 3 builders trả text Vietnamese UTF-8 thuần (POS không encode, daemon lo encoding)
- Pattern A: POS lưu UTF-8, daemon Windows encode CP1258 + ESC/POS commands
- **Issue chưa giải quyết:** Xprinter XP-365B với `ESC t 27` (codepage Vietnam) không interpret CP1258 chuẩn — bytes 0xEA, 0xCC, 0xF2, 0xD0 ra ký tự Việt sai (precomposed thay vì combining)
- **Test pending:** test_vn_v2.py thử 6 combo codepage (27/30/32/16/52, có/không ESC R 0)
- **Backup phương án:** render text → bitmap PNG via PIL + Vietnamese font, gửi qua ESC/POS GS v 0 (raster) — tránh codepage hoàn toàn

---

## CÁC PATTERN KỸ THUẬT QUAN TRỌNG

### 1. Mobile column stacking fix (CSS scoped)

```python
_CSS = """<style>
.st-key-{ZONE} div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
}
.st-key-{ZONE} div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;
}
</style>"""
```

### 2. Numeric keyboard global (MutationObserver)

Inject 1 lần ở app.py: input/textarea trong container `st-key-numkb-*` → tự set inputmode="numeric" hoặc "tel". Pattern: `st.container(key="numkb-XXX")` hoặc `st.container(key="numkb-tel-XXX")`.

### 3. Timezone

`ZoneInfo("Asia/Ho_Chi_Minh")` cho VN time. Supabase lưu `timestamptz` UTC. **Phải convert về VN** trước `strftime`. `_to_vn()` helper handle naive datetime.

### 4. Streamlit toast icon

Phải emoji thật, không Unicode "Check Mark" (✓ ✗). Dùng ✅ ❌.

### 5. Dialog state pattern (top-level, tránh nested @st.dialog)

```python
pending = st.session_state.get("lichsu_confirm_huy")
if pending:
    _dialog_confirm_huy(pending)

# Trong modal khi user bấm Hủy:
st.session_state["lichsu_confirm_huy"] = inv
st.rerun()
```

### 6. Cache invalidation sau ghi DB

```python
load_hang_hoa_pos.clear()
load_phieu_doi_tra_pos_history.clear()
load_phieu_dat_hang.clear()
```

### 7. Reset counter pattern cho form

```python
rk = st.session_state.get("dh_form_reset_cnt", 0)
ten = st.text_input("Tên hàng", key=f"dh_ten_{rk}")
# Sau lưu OK:
st.session_state["dh_form_reset_cnt"] = rk + 1
st.rerun()
```

### 8. Sanity check syntax trước push

```bash
python3 -c "import ast; ast.parse(open('modules/X.py').read())"
```

### 9. APSC schema mapping (07/05/2026)

`hoa_don` table dùng cột tiếng Việt có dấu (KiotViet schema). Đọc qua subscript:
```python
head["Mã hóa đơn"]    # NOT head.ma_hd
head["Chi nhánh"]
head["Tổng tiền hàng"]
head["Người bán"]
head["Mã YCSC"]
```

Edge Function TypeScript cũng dùng cách này: `record["Chi nhánh"]`.

`_tao_hoa_don_apsc` insert N rows (1 row/item) → cần dedupe khi xử lý event-driven.

---

## CONSTANTS & SECRETS

### POS `utils/config.py`

```python
APP_NAME = "DL Watch POS"
ALL_BRANCHES = ["100 Lê Quý Đôn", "Coop Vũng Tàu", "GO BÀ RỊA"]
CN_SHORT = {
    "100 Lê Quý Đôn": "100 LQĐ",
    "Coop Vũng Tàu":  "Coop VT",
    "GO BÀ RỊA":      "GO BR",
}
CN_INFO = { ... }  # đầy đủ địa chỉ + SĐT
```

### Streamlit secrets

```toml
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "xxxxx"
```

### Supabase Edge Function secrets (LINE)

```
LINE_TOKEN        = "xxx"               # bearer token bot
LINE_GROUP_BARIA  = "Cxxxxxx"           # group cho 100 LQĐ + GO BR
SUPABASE_URL      = "..."
SUPABASE_ANON_KEY = "..."               # service role không cần — dùng anon
```

### Daemon `.env` (Windows laptop LQĐ)

```
SUPABASE_URL = "..."
SUPABASE_SERVICE_ROLE_KEY = "..."       # daemon dùng service role để poll print_queue
PRINTER_IP = "192.168.x.x"
PRINTER_PORT = 9100
```

### `requirements.txt`

```
streamlit>=1.36.0
supabase>=2.0.0
bcrypt>=4.0.0
pandas>=2.0.0
```

(Đã bỏ `streamlit-local-storage`, `streamlit-cookies-controller`, `extra-streamlit-components` sau khi switch về URL params.)

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
| 1 | LINE Branch 3 APSC notification | Đã deploy, chưa test | User: "đợi kết quả khi có hóa đơn phiếu sửa sau" |
| 2 | Print K80 tiếng Việt — tìm codepage đúng | In progress | Test test_vn_v2.py 6 combo, hoặc fallback raster PNG |
| 3 | Performance perf | Pending | Web app side, ảnh hưởng cả 2 app |
| 4 | LINE notification mở rộng | Pending | Đổi/trả + phiếu đặt hoàn thành (đã có Branch 1 đổi/trả, chỉ chưa nâng cao) |

---

## TROUBLESHOOTING REFERENCE

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `Chưa cấu hình SUPABASE_URL` | Streamlit secrets thiếu | Set Streamlit Cloud → Secrets |
| Bàn phím chữ thay vì số ở PIN | MutationObserver chưa inject | Hard refresh (Ctrl+Shift+R) |
| `Lỗi tạo hóa đơn: tồn không đủ` | Race / tồn = 0 | Refresh, check `the_kho` |
| Banner session sai giờ | Strftime trên UTC | Đã fix Bước 5: `.astimezone(...)` |
| `st.toast` báo lỗi icon | Unicode thay vì emoji | `✓` → `✅` |
| HĐ POS không hiện app cũ | Cache 5 phút | Bấm "↺ Tải lại" |
| LINE không nhận thông báo | Edge Function lỗi hoặc Group ID sai | Check Supabase logs > Edge Functions > line-notify |
| Multi-NV cùng login do share URL | URL chứa `?t=...` cũ | Mở URL gốc (không có query) → màn login |
| HĐ từ phiếu đặt báo "không đủ tồn" | RPC quên `bypass_stock_check=true` | Patch 06 đã fix |
| APSC LINE gửi 3 tin/HĐ | Dedupe lt id không match | Check `hoa_don` có cột `id` PK không |
| In K80 ra CJK | Máy in default Kanji mode | Sequence: ESC @ + FS . + ESC R 0 + ESC t 27 |

---

## RESET POS DATA SQL

File `reset_pos_data.sql`: hoàn tồn kho cho HĐ Hoàn thành + đảo tồn từ phiếu đổi/trả + DELETE theo thứ tự FK + RESTART sequences về 1. Có sanity check cuối query. Dùng khi cần reset toàn bộ dữ liệu POS để test lại từ đầu (KHÔNG dùng production trừ khi user yêu cầu rõ).

---

## CONTACT

User: **chủ cửa hàng đồng hồ DL Watch** ở Bà Rịa - Vũng Tàu (Kevin). Liên hệ qua chat Claude.
