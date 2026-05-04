# AI_CONTEXT.md — DL Watch POS App

**Cập nhật:** 04/05/2026
**Mục đích:** Bàn giao context đầy đủ cho Claude session mới. POS app đã qua **Bước 1 → Bước 8 + LINE notification + URL session token** — đang ở giai đoạn polish và làm thêm tính năng phụ.

---

## QUAN TRỌNG — ĐỌC ĐẦU TIÊN

Đây là dự án **POS app riêng** cho cửa hàng đồng hồ DL Watch, **chia sẻ database** với app quản lý cũ. Đã hoàn thành và deploy production qua **Bước 1 → Bước 8**.

User dùng tiếng Việt, xưng "mình/bạn". Tuân theo `CLAUDE.md` (đã upload lên project knowledge): think before coding, simplicity first, surgical changes, goal-driven execution. **Luôn hỏi clarifying questions trước khi implement, không pick interpretation silently.**

---

## TỔNG QUAN DỰ ÁN

### 2 app riêng biệt, 1 database

| App | Path | Mục đích | Trạng thái |
|-----|------|----------|------------|
| **App quản lý cũ** (legacy) | `web_app/` | Quản trị: hàng hóa, sửa chữa, kiểm kê, báo cáo | Production |
| **POS app mới** | `pos_app/` | Bán hàng tại quầy trên mobile | Production |

Cả 2 deploy lên **Streamlit Cloud** từ 2 GitHub repo riêng. Cùng dùng **Supabase project** (cùng `SUPABASE_URL` + `SUPABASE_KEY`).

### Stack

- **Frontend:** Streamlit (Python) — POS mobile-first max-width 480px, app cũ desktop max-width 1350px
- **Backend:** Supabase PostgreSQL + RPC functions + **Edge Function (Deno/TypeScript)** cho LINE
- **Deploy:** Streamlit Cloud (private repos, GitHub-linked)
- **3 chi nhánh:** `100 Lê Quý Đôn` · `Coop Vũng Tàu` · `GO BÀ RỊA`

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
[✓] LINE Notification: Edge Function + Database Webhook định tuyến CN
[✓] Session token: URL params (?t=xxx) — sau khi cookie thất bại 3 vòng

[Pending — kỹ thuật phụ]
[ ] Phương án B (nhớ NV qua localStorage thuần) — UX skip bước chọn tài khoản
[ ] Casso/SePay webhook xác nhận chuyển khoản (B9-1..B9-5 đã chốt nghiệp vụ, paused)
[ ] Local Daemon + in K80 (Xprinter XP-365B static IP, port 9100)
[ ] Quản lý số dư khách hàng (tiền thừa)
[ ] Quét mã vạch (Phase 2B)
[ ] Logs thao tác POS app vào action_logs (web app)
[ ] LINE notification mở rộng (đổi/trả + phiếu đặt hoàn thành)
[ ] Cache/spinner perf — tech debt
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
│   ├── db.py                           # supabase client + load + RPC + validators
│   ├── auth.py                         # PIN flow, session URL token, banner
│   └── helpers.py                      # now_vn, today_vn, fmt_vnd, end_of_today_vn_iso
└── modules/
    ├── __init__.py
    ├── ban_hang.py                     # Màn 1 → 2 → 3 + hỗ trợ tạo HĐ từ phiếu đặt
    ├── lich_su.py                      # List HĐ + AHDD merge + modal chi tiết + hủy
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
| `the_kho` | Tồn kho theo CN. Cột `Mã hàng`, `Chi nhánh`, `Tồn cuối kì` |
| `khach_hang` | Unique key `sdt`. `tong_ban` cộng dồn KiotViet + POS + AHDD chenh_lech |
| `sessions` | Session token (đã mở rộng — xem Session Token Architecture) |
| `hoa_don` | HĐ KiotViet legacy (denormalized) |
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
    ma_kh            text,
    ten_khach        text,
    sdt_khach        text,
    tong_tien_hang   integer,
    giam_gia_don     integer,
    khach_can_tra    integer,
    tien_mat         integer,
    chuyen_khoan     integer,
    the              integer,
    tien_thua        integer,
    tien_coc_da_thu  integer,                  -- BƯỚC 8: cọc đã thu từ phiếu đặt
    trang_thai       text,                     -- "Hoàn thành" | "Đã hủy"
    nguoi_ban        text,
    nguoi_ban_id     bigint,
    ghi_chu          text,
    created_at       timestamptz,
    cancelled_by     text,
    cancelled_at     timestamptz,
    ma_pdh           text                      -- BƯỚC 8: link tới phieu_dat_hang nếu có
)

hoa_don_pos_ct (
    id              bigserial PRIMARY KEY,
    ma_hd           text REFERENCES hoa_don_pos(ma_hd) ON DELETE CASCADE,
    ma_hang         text,
    ten_hang        text,
    so_luong        integer,
    don_gia         integer,
    giam_gia_dong   integer,
    thanh_tien      integer
)

-- BƯỚC 7: đổi/trả
phieu_doi_tra_pos (
    ma_pdt           text PRIMARY KEY,         -- AHDD000001
    ma_hd_goc        text REFERENCES hoa_don_pos(ma_hd),
    chi_nhanh        text,
    ma_kh, ten_khach, sdt_khach,
    loai_phieu       text,                     -- "Trả" | "Đổi ngang" | "Đổi có chênh lệch"
    tien_hang_tra    integer,
    tien_hang_moi    integer,
    chenh_lech       integer,                  -- = moi - tra (>0 khách bù; <0 shop hoàn)
    tien_mat         integer,
    chuyen_khoan     integer,
    the              integer,
    trang_thai       text,                     -- "Hoàn thành" | "Đã hủy"
    nguoi_tao, nguoi_tao_id, ghi_chu,
    created_at, cancelled_by, cancelled_at
)

phieu_doi_tra_pos_ct (
    id              bigserial PRIMARY KEY,
    ma_pdt          text REFERENCES ... ON DELETE CASCADE,
    kieu            text,                      -- "tra" (cộng kho) | "moi" (trừ kho)
    ma_hang, ten_hang, so_luong, don_gia, thanh_tien
)

-- BƯỚC 8: đặt hàng theo yêu cầu
phieu_dat_hang (
    ma_pdh           text PRIMARY KEY,         -- AHDC000001
    chi_nhanh        text,
    ma_kh, ten_khach, sdt_khach,
    ten_hang_yeu_cau text,                     -- free-text mô tả
    so_luong         integer,
    gia_du_kien      integer,
    tien_coc         integer,                  -- cọc đã thu
    pttt_coc_tien_mat, pttt_coc_chuyen_khoan, pttt_coc_the integer,  -- chi tiết PTTT cọc
    trang_thai       text,                     -- "Chờ đặt" | "Chờ lấy" | "Hoàn thành" | "Đã hủy"
    ngay_du_kien_co  date,
    ghi_chu          text,
    nguoi_tao, nguoi_tao_id,
    created_at, updated_at,
    cancelled_by, cancelled_at,
    ly_do_huy        text,                     -- "Trả cọc" | "Giữ cọc"
    ma_hd            text                      -- link tới hoa_don_pos khi Hoàn thành
)

-- Sequences
CREATE SEQUENCE ahd_seq START 1;     -- AHD HĐ POS
CREATE SEQUENCE ahdd_seq START 1;    -- AHDD phiếu đổi/trả
CREATE SEQUENCE ahdc_seq START 1;    -- AHDC phiếu đặt hàng (BƯỚC 8)
```

### RPC functions của POS

**HĐ POS (Bước 3-4):**
- `tao_hoa_don_pos(payload jsonb) → jsonb` — atomic create với `bypass_stock_check` cho HĐ từ phiếu đặt (Bước 8)
- `huy_hoa_don_pos(p_ma_hd, p_cancelled_by) → jsonb` — atomic cancel, hoàn tồn kho, **block nếu HĐ đã có phiếu đổi/trả Hoàn thành** (patch 04)
- `get_next_ahd_num() → bigint`

**Đổi/Trả (Bước 7):**
- `tao_phieu_doi_tra_pos(payload) → jsonb` — atomic, validate cumulative SL trả ≤ SL gốc, gate 7 ngày trừ admin
- `huy_phieu_doi_tra_pos(p_ma_pdt, p_cancelled_by) → jsonb` — atomic, đảo ngược kho

**Đặt hàng (Bước 8):**
- `tao_phieu_dat_hang(payload) → jsonb` — tạo phiếu Chờ đặt + cọc
- `cap_nhat_trang_thai_phieu_dat(p_ma_pdh, p_trang_thai_moi, ...) → jsonb` — chuyển Chờ đặt → Chờ lấy
- `hoan_thanh_phieu_dat_hang(payload) → jsonb` — tạo HĐ POS có `tien_coc_da_thu` + link `ma_pdh`, cho sửa giá lúc này, **bypass_stock_check=true**
- `huy_phieu_dat_hang(p_ma_pdh, p_cancelled_by, p_ly_do_huy) → jsonb` — Trả cọc hoặc Giữ cọc

**Session token (URL session):**
- `create_session(p_nv_id, p_user_agent) → jsonb` — token UUID, expires cuối ngày VN qua `date_trunc + Asia/Ho_Chi_Minh`
- `validate_session(p_token) → jsonb` — return user info nếu hợp lệ
- `revoke_user_sessions(p_nv_id) → jsonb` — revoke ALL sessions của 1 NV
- `revoke_session_by_token(p_token) → jsonb` — revoke 1 token cụ thể

---

## QUYẾT ĐỊNH NGHIỆP VỤ ĐÃ CHỐT

### Bước 7 — Đổi/Trả (B7-1 .. B7-16)

| # | Quyết định |
|---|------------|
| B7-1 | Hỗ trợ Trả, Đổi ngang, Đổi có chênh lệch, Trả 1 phần |
| B7-2 | Giới hạn 7 ngày cho NV; admin override |
| B7-3 | Không loại trừ sản phẩm nào |
| B7-4 | Tra HĐ qua SĐT hoặc mã HĐ |
| B7-5 | NV thường tự xử lý, không cần admin duyệt |
| B7-6 | Hàng trả tự cộng `the_kho` ngay |
| B7-7 | Phiếu link HĐ gốc qua `ma_hd_goc` |
| B7-8 | Chỉ admin được hủy phiếu đổi/trả |
| B7-9 | 1 HĐ → nhiều phiếu OK, miễn tổng SL trả ≤ SL gốc |
| B7-10 | Shop hoàn tiền chỉ tiền mặt |
| B7-11 | `khach_hang.tong_ban` GIỮ NGUYÊN khi đổi/trả (Phase 1) → Bước 7B đổi: cộng `chenh_lech` AHDD |
| B7-12 | UI nhúng vào tab Lịch sử |
| B7-13 | Mã prefix `AHDD`, sequence `ahdd_seq` |
| B7-14 | 1 bảng `_ct` chung cho cả "tra" và "moi" (cột `kieu`) |
| B7-15 | Block hủy HĐ gốc khi đã có phiếu đổi/trả Hoàn thành (patch 04) |
| B7-16 | Sau hoàn thành phiếu, clear cache `load_phieu_doi_tra_pos_history` + `load_hang_hoa_pos` |

### Bước 7B — Adapter web app (4 quyết định)

1. Doanh thu gộp: cộng `chenh_lech` AHDD vào doanh thu (chenh_lech > 0 = thu thêm; < 0 = hoàn)
2. Bán hàng theo nhóm: tính **net items** (items mới trừ items trả) cho XNT chính xác
3. `khach_hang.tong_ban`: cộng dồn `chenh_lech` AHDD theo SĐT (chỉ "Hoàn thành")
4. Tab "Tra cứu hóa đơn" web app: merge AHDD vào danh sách, hiển thị badge "Đổi/Trả"

### Bước 8 — Đặt hàng (B8-1 .. B8-9)

| # | Quyết định |
|---|------------|
| B8-1 | 4 trạng thái: **Chờ đặt → Chờ lấy → Hoàn thành** + Đã hủy. Có thể skip Chờ lấy (đi thẳng từ Chờ đặt → Hoàn thành) khi cần |
| B8-2 | Cọc lưu chi tiết PTTT (tiền mặt + CK + thẻ) |
| B8-3 | Tên hàng yêu cầu = **free-text**, không đụng `hang_hoa` / `the_kho` |
| B8-4 | RPC `bypass_stock_check=true` khi tạo HĐ từ phiếu đặt (vì hàng yêu cầu có thể chưa có trong DB) |
| B8-5 | Cho sửa giá lúc Hoàn thành (giá lúc đặt là dự kiến, giá thực tế có thể khác) |
| B8-6 | Admin được hủy phiếu bất kỳ trạng thái với option "Trả cọc" hoặc "Giữ cọc" |
| B8-7 | Mã prefix `AHDC`, sequence `ahdc_seq` |
| B8-8 | UI: tab riêng "Đặt hàng" trong POS app |
| B8-9 | Khi Hoàn thành → tạo `hoa_don_pos` link qua `ma_pdh`, cọc thành `tien_coc_da_thu` trên HĐ |

### LINE Notification

- **Trigger:** Database Webhook trên `hoa_don_pos` INSERT
- **Edge Function:** `line-notify` (Deno/TypeScript) — `setTimeout(1500)` chờ ghi xong `hoa_don_pos_ct` rồi mới fetch chi tiết → push LINE
- **Định tuyến CN:** Cấu hình cứng trong code TS:
  - `100 LQĐ` + `GO BÀ RỊA` → cùng group `LINE_GROUP_BARIA`
  - `Coop Vũng Tàu` → return 200, skip (chưa có group)
- **Group ID:** lấy bằng webhook.site sniff payload
- **Auto-response messages** trên LINE Manager đã **tắt** (tránh bot spam khi NV chat trong nhóm)

### Session Token Architecture (URL params)

**Lịch sử thử nghiệm:**

1. **streamlit-local-storage** (initial) → **leak singleton** giữa users trên Streamlit Cloud (module-level `_LS = LocalStorage()` share)
2. **streamlit-cookies-controller** (option B) → Pass isolation, **FAIL persist** (cookie session-only, không expose `expires` argument)
3. **extra-streamlit-components** option 1 (cache trong `st.session_state`) → Pass isolation, **FAIL persist** (instance bị stale)
4. **extra-streamlit-components** option 2 (`@st.cache_resource`) → Pass persist, **FAIL isolation** (instance share giữa users → leak NV này thành NV khác) + **CachedWidgetWarning vàng**
5. **URL query params** (final) → Pass isolation + Pass logout + **FAIL persist** (URL không nhớ khi đóng tab)

**Quyết định cuối:** URL params `?t=xxx&b=xxx`. NV phải nhập PIN mỗi sáng (~5 giây). An toàn 100%, không leak. Trade-off này hợp lý cho shop 3 CN với NV cố định.

**SQL Patch 07 (`pos_patch_07_session.sql`):** ALTER `sessions` thêm `last_used_at`, `user_agent`, `revoked_at`, indexes; 4 RPC trên.

**Quyết định LS-1 .. LS-5:**
- LS-1: Token expire cuối ngày VN
- LS-2: Logout = revoke ALL sessions cross-device (cùng NV)
- LS-3: Admin web app xem session active (chưa làm UI, chỉ có DB schema)
- LS-4: Cho phép nhiều thiết bị cùng login 1 NV
- LS-5: ~~localStorage~~ → URL params

**Test results final (URL params):**
- Test 1 isolation: PASS ✓
- Test 2 persist: FAIL (chấp nhận trade-off)
- Test 3 logout cross-device: PASS ✓ (do nv reload phải qua validate_session)
- Test 4 hết ngày: chưa đủ điều kiện test

**Phương án B (để dành làm sau):** Lưu `last_nv_id` vào localStorage browser thuần (qua `st.components.v1.html` JS injection). Mở app → bấm tên NV (skip bước chọn) → chỉ nhập PIN 4 số. Không lưu credential, chỉ "gợi ý" UX. Risk thấp.

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
| D10 | In K80: kiến trúc Cloud-to-LAN spooler | Pending |
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
| D23 | Logs thao tác POS chưa ghi vào `action_logs` | Pending |

---

## CÁC FILE QUAN TRỌNG VÀ NỘI DUNG CHÍNH

### `utils/db.py` (POS)

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
```

### `utils/auth.py` (POS) — URL session token

```python
# Constants
_URL_TOKEN_KEY  = "t"
_URL_BRANCH_KEY = "b"

# 5 helpers thay localStorage:
_ls_get_token() / _ls_set_token(token) / _ls_delete_token()
_ls_get_branch() / _save_branch_localstorage(branch)
# Tất cả dùng st.query_params

# Flow chính:
run_auth_gate()                  # gate ở đầu app.py — không pass thì stop
restore_session()                # đọc URL token → validate_session RPC → set st.session_state["user"]
get_user() / get_active_branch() / get_accessible_branches() / is_admin()
do_logout()                      # revoke_user_sessions + clear URL params
_render_numpad_input(prefix)     # input native + numpad
render_session_warning_banner()  # banner vàng 30 phút trước expire 23:59:59 VN
```

### `app.py` (POS)

- Cấu trúc: `set_page_config` → MutationObserver inject (1 lần) → CSS mobile → `run_auth_gate()` → header (logo + CN popover + avatar popover) → `render_session_warning_banner()` → tabs **"Bán hàng" / "Lịch sử" / "Đặt hàng"**

### `modules/ban_hang.py`

State routing qua `st.session_state["pos_step"]`:
- `None` → màn 2 (search + giỏ)
- `"thanh_toan"` → màn 3 (thanh toán)
- `"success"` → màn success

**Bước 8 mở rộng:** ban_hang.py có hỗ trợ tạo HĐ từ phiếu đặt — khi `st.session_state["from_pdh"]` có giá trị thì hiện cọc đã thu trong dialog thanh toán.

### `modules/lich_su.py`

State: `st.session_state["lichsu_days_back"]` (mặc định 0)

**Bước 7B merge:** danh sách hiển thị cả HĐ POS và phiếu đổi/trả AHDD (bằng cờ trong row). Modal chi tiết phân biệt theo prefix.

Search range: tab "Ngày tháng" có date range picker 3 cột (từ ngày, đến ngày, áp dụng).

**Bug đã fix:**
- Form Tạo mới không reset → counter pattern `dh_form_reset_cnt`
- HĐ POS từ phiếu đặt không hiện cọc → thêm `tien_coc_da_thu` vào dialog
- Web app HĐ thiếu cọc PTTT chi tiết → join `phieu_dat_hang` trong `_load_hoa_don_pos_flat`
- `'dict' object has no attribute 'DataFrame'` → rename loop var `pd` → `_pdat_row`
- IndentationError line 681 → indent body của `if not all_items` 8 spaces

### `modules/doi_tra.py`

Full-screen mode khi `st.session_state["doi_tra_active"]` = `ma_hd_goc`.

State:
- `doi_tra_tra_map` = `{idx_item_in_hd_goc: sl_tra}`
- `doi_tra_moi_cart` = list items mua mới

Sections: HĐ gốc info → A (chọn món trả) → B (search + cart mới) → C (tóm tắt + chênh lệch + PTTT) → footer.

Sau RPC OK → `_close_doi_tra()` + `load_hang_hoa_pos.clear()` + `load_phieu_doi_tra_pos_history.clear()` + rerun.

Cũng export: `dialog_chi_tiet_pdt(pdt)` + `dialog_confirm_huy_pdt(pdt)`.

### `modules/dat_hang.py` (Bước 8)

Tabs: **"Danh sách phiếu" / "Tạo mới"**

Tab Danh sách: filter theo trạng thái + search SĐT/mã. Modal chi tiết theo trạng thái:
- **Chờ đặt:** action "Chuyển sang Chờ lấy" hoặc "Skip → Hoàn thành"
- **Chờ lấy:** action "Hoàn thành" (mở dialog tạo HĐ POS, cho sửa giá)
- **Hoàn thành:** chỉ xem
- **Đã hủy:** chỉ xem + hiện lý do

Tab Tạo mới: form free-text tên hàng, SL, giá dự kiến, cọc PTTT chi tiết. Sau lưu OK → counter `dh_form_reset_cnt += 1` để reset widgets keys.

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

```javascript
// Inject 1 lần ở app.py: input/textarea trong container "st-key-numkb-*"
// → tự set inputmode="numeric" hoặc "tel"
```

Pattern: `st.container(key="numkb-XXX")` cho numeric, `st.container(key="numkb-tel-XXX")` cho phone.

### 3. Timezone

`ZoneInfo("Asia/Ho_Chi_Minh")` cho VN time. Supabase lưu `timestamptz` UTC. **Phải convert về VN** trước `strftime`:

```python
expires.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M")
```

`_to_vn()` helper handle naive datetime từ Supabase.

### 4. Streamlit toast icon

`st.toast(msg, icon="✅")` — phải emoji thật, không Unicode "Check Mark" (✓).

### 5. Dialog state pattern

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
LINE_ACCESS_TOKEN = "xxx"
LINE_GROUP_BARIA  = "Cxxxxxx"      # group cho 100 LQĐ + GO BR
SUPABASE_URL      = "..."
SUPABASE_SERVICE_ROLE_KEY = "..."
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

---

## CHECKLIST BÀN GIAO

Claude session mới nên:

1. ✅ Đọc `CLAUDE.md` trong project knowledge
2. ✅ Đọc file này (`AI_CONTEXT.md`) hết
3. ✅ Hỏi user gửi các file Python liên quan trước khi code (tránh override)
4. ✅ Đề xuất plan kỹ thuật, đợi approve
5. ✅ Code, deliver as patch hoặc full files
6. ✅ Sau test, cập nhật roadmap

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

---

## RESET POS DATA SQL

File `reset_pos_data.sql` (đã output): hoàn tồn kho cho HĐ Hoàn thành + đảo tồn từ phiếu đổi/trả + DELETE theo thứ tự FK + RESTART sequences về 1. Có sanity check cuối query.

Dùng khi cần reset toàn bộ dữ liệu POS để test lại từ đầu (KHÔNG dùng production trừ khi user yêu cầu rõ).

---

## CONTACT

User: **chủ cửa hàng đồng hồ DL Watch** ở Bà Rịa - Vũng Tàu (Kevin). Liên hệ qua chat Claude.
