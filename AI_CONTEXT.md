# AI_CONTEXT.md — DL Watch POS App

**Cập nhật:** 01/05/2026  
**Mục đích:** Bàn giao context đầy đủ cho Claude session mới khi làm Bước 7 (Đổi/Trả) và Bước 8 (Đặt hàng theo yêu cầu).

---

## QUAN TRỌNG — ĐỌC ĐẦU TIÊN

Đây là dự án **POS app riêng** cho cửa hàng đồng hồ DL Watch, **chia sẻ database** với app quản lý cũ. Đã hoàn thành và deploy production qua **Bước 1 → Bước 6**.

User dùng tiếng Việt. Tuân theo `CLAUDE.md` (đã upload lên project knowledge): think before coding, simplicity first, surgical changes, goal-driven execution. **Luôn hỏi clarifying questions trước khi implement, không pick interpretation silently.**

---

## TỔNG QUAN DỰ ÁN

### 2 app riêng biệt, 1 database

| App | Path | Mục đích | Trạng thái |
|-----|------|----------|------------|
| **App quản lý cũ** (legacy) | `web_app/` | Quản trị: hàng hóa, sửa chữa, kiểm kê, báo cáo | Production, đang chạy |
| **POS app mới** | `pos_app/` | Bán hàng tại quầy trên mobile | Production, đang chạy |

Cả 2 deploy lên **Streamlit Cloud** từ 2 GitHub repo riêng. Cùng dùng **Supabase project** (cùng `SUPABASE_URL` + `SUPABASE_KEY`).

### Stack

- **Frontend:** Streamlit (Python) — POS mobile-first max-width 480px, app cũ desktop max-width 1350px
- **Backend:** Supabase PostgreSQL + RPC functions
- **Deploy:** Streamlit Cloud (private repos, GitHub-linked)
- **3 chi nhánh:** `100 Lê Quý Đôn` · `Coop Vũng Tàu` · `GO BÀ RỊA`

### Người dùng & quyền

| Role | Quyền POS | Quyền app cũ |
|------|-----------|--------------|
| `admin` | Tất cả + hủy HĐ | Tất cả modules |
| `ke_toan` | Bán hàng + lịch sử | Báo cáo + xem (không hủy/xóa) |
| `nhan_vien` | Bán hàng + xem lịch sử CN | Hạn chế: hóa đơn, hàng hóa, sửa chữa, chuyển hàng |

---

## ROADMAP

```
[✓] Bước 1: Auth PIN — chọn NV, PIN 4 số bcrypt, session 23:59:59 VN
[✓] Bước 2A: Bán hàng (search + giỏ + dialog sửa dòng)
[✓] Bước 3: Thanh toán + RPC tạo hóa đơn atomic
[✓] Bước 4: Lịch sử hóa đơn + hủy (admin only, hoàn tồn kho)
[✓] Bước 5: Polish + deploy guide (banner cảnh báo session, validation)
[✓] Bước 6: Liên kết app cũ với HĐ POS (adapter load_hoa_don_unified)

[✓] Bước 7: Đổi/Trả hàng đã bán       — đã code, chờ user test
[ ] Bước 8: Đặt hàng theo yêu cầu     ← KẾ TIẾP — user đã có câu trả lời nghiệp vụ
[ ] Bước 7B: Update adapter app cũ — phản ánh phiếu đổi/trả vào báo cáo (sau khi 7 stable)

[Roadmap kỹ thuật - làm khi có thời gian]
[ ] Local Daemon + in K80 (Xprinter XP-365B static IP, port 9100)
[ ] Webhook xác nhận chuyển khoản (Casso/SePay)
[ ] localStorage session token (Add to Home Screen)
[ ] Quản lý số dư khách hàng (tiền thừa)
[ ] Quét mã vạch (Phase 2B)
```

User sẽ **bỏ KiotViet trong <1 tuần** — adapter ở Bước 6 đã handle sẵn, không cần sửa gì khi đó.

---

## CẤU TRÚC POS APP (`pos_app/`)

```
pos_app/
├── app.py                          # Entry, header, routing tab, MutationObserver inject inputmode
├── requirements.txt
├── README.md
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── docs/
│   ├── SETUP.md                    # Setup Supabase + Streamlit Cloud + secrets
│   └── ADMIN_GUIDE.md              # Hướng dẫn admin: thêm NV, reset PIN, hủy HĐ
├── sql/
│   ├── full_setup.sql              # Schema cuối + RPC (cho fresh DB)
│   ├── pos_setup.sql               # Patch ban đầu (đã chạy)
│   ├── pos_patch_01_tien_thua.sql  # Đã chạy
│   ├── pos_patch_02_dich_vu.sql    # Đã chạy
│   └── pos_patch_03_doi_tra.sql    # Bước 7 — chờ user áp vào DB
├── utils/
│   ├── __init__.py
│   ├── config.py                   # APP_NAME, ALL_BRANCHES, CN_SHORT, CN_INFO
│   ├── db.py                       # supabase client + load + RPC + validators
│   ├── auth.py                     # PIN flow, session, branch, render_session_warning_banner
│   └── helpers.py                  # now_vn, today_vn, fmt_vnd, end_of_today_vn_iso
└── modules/
    ├── __init__.py
    ├── ban_hang.py                 # Màn 1 (search+giỏ) → Màn 2 (thanh toán) → Màn 3 (success)
    ├── lich_su.py                  # List HĐ POS + modal chi tiết + flow hủy + nút "↔ Đổi/Trả"
    └── doi_tra.py                  # Bước 7: màn Đổi/Trả + modal chi tiết phiếu AHDD
```

### POS — luồng chính

1. **Login:** Avatar NV → PIN numpad (có input native `inputmode=numeric`) → chọn CN
2. **Bán hàng:**
   - Search hàng (max 3 results, ưu tiên còn tồn, Dịch vụ luôn available)
   - Bấm vào kết quả → thêm giỏ (SL=1)
   - Bấm vào card giỏ → dialog sửa SL/đơn giá/giảm giá (với numpad số)
   - Bấm "Tiếp tục" → màn thanh toán
3. **Thanh toán:**
   - Section Khách: tick "Khách lẻ" hoặc nhập SĐT (lookup auto, khách mới yêu cầu nhập tên)
   - Tóm tắt giỏ
   - Giảm giá đơn (tiền/%)
   - PTTT: 3 nút radio đơn giản hoặc tick "Chia nhiều" → 3 ô input
   - Card "Khách cần trả" lớn đỏ
   - Validation: phải tick Khách lẻ HOẶC nhập SĐT, phải đủ tiền
   - Bấm "XÁC NHẬN" → call RPC atomic → màn success
4. **Success:**
   - ✓ to + mã HĐ AHD000001
   - Tóm tắt + tiền thừa (nếu có)
   - Nút "In hóa đơn" (placeholder, chờ Local Daemon)
   - Nút "Hóa đơn mới" → reset
5. **Lịch sử HĐ:**
   - Mặc định HĐ hôm nay của CN đang chọn
   - Tất cả NV thấy mọi HĐ trong CN (không filter theo người bán)
   - Search + filter
   - Nút "Xem cũ hơn (+1 ngày)"
   - Modal chi tiết: thông tin đầy đủ + nút Hủy (admin only)
   - Hủy: confirm "Hàng sẽ hoàn vào tồn kho" → RPC → toast → reload
   - HĐ đã hủy hiện xám với badge "[ĐÃ HỦY]"

---

## DATABASE — TABLES SHARE GIỮA 2 APP

### Table chia sẻ (đã có từ app cũ)

| Table | Mô tả |
|-------|-------|
| `nhan_vien` | Nhân viên: id, username, ho_ten, role, active |
| `nhan_vien_chi_nhanh` | Phân quyền CN cho NV |
| `chi_nhanh` | Danh sách 3 CN |
| `hang_hoa` | Master sản phẩm. **Cột `loai_sp`** = "Hàng hóa" hoặc "Dịch vụ" — POS dùng để skip stock check cho dịch vụ |
| `the_kho` | Tồn kho theo CN. Cột `Mã hàng`, `Chi nhánh`, `Tồn cuối kì` |
| `khach_hang` | Khách hàng. Unique key: `sdt`. `tong_ban` = tổng mua KiotViet (POS không sửa cột này) |
| `sessions` | Session token đăng nhập (cả 2 app dùng chung) |
| `hoa_don` | HĐ KiotViet legacy (denormalized, mỗi item 1 dòng) |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa |
| `phieu_chuyen_kho`, `phieu_nhap_hang`, `phieu_kiem_ke`, etc. | Các phiếu khác của app cũ |

### Table riêng của POS

```sql
-- pin_code: PIN bcrypt cho mỗi NV
pin_code (
    nhan_vien_id  bigint PRIMARY KEY,
    pin_hash      text NOT NULL,
    updated_at    timestamptz
)

-- hoa_don_pos: header HĐ POS (1 dòng/HĐ — KHÁC KiotViet denormalized)
hoa_don_pos (
    ma_hd            text PRIMARY KEY,         -- AHD000001
    chi_nhanh        text,
    ma_kh            text,                      -- nullable (Khách lẻ)
    ten_khach        text,
    sdt_khach        text,
    tong_tien_hang   integer,                   -- chưa giảm giá đơn
    giam_gia_don     integer,
    khach_can_tra    integer,                   -- cuối cùng
    tien_mat         integer,
    chuyen_khoan     integer,
    the              integer,
    tien_thua        integer,                   -- khách trả dư
    trang_thai       text,                      -- "Hoàn thành" | "Đã hủy"
    nguoi_ban        text,                      -- snapshot tên NV
    nguoi_ban_id     bigint,
    ghi_chu          text,
    created_at       timestamptz,
    cancelled_by     text,                      -- ai hủy
    cancelled_at     timestamptz                -- lúc nào
)

-- hoa_don_pos_ct: chi tiết items
hoa_don_pos_ct (
    id              bigserial PRIMARY KEY,
    ma_hd           text REFERENCES hoa_don_pos(ma_hd) ON DELETE CASCADE,
    ma_hang         text,
    ten_hang        text,
    so_luong        integer,
    don_gia         integer,
    giam_gia_dong   integer,                   -- giảm giá theo dòng
    thanh_tien      integer
)

-- ahd_seq: sequence cho mã AHD
CREATE SEQUENCE ahd_seq START 1;
```

### RPC functions của POS

**1. `tao_hoa_don_pos(payload jsonb) → jsonb`** — atomic create
- Input: chi_nhanh, ma_kh (nullable), ten_khach, sdt_khach, giam_gia_don, tien_mat, chuyen_khoan, the, nguoi_ban, nguoi_ban_id, items[]
- Logic: check tồn (chỉ Hàng hóa) → check tổng PTTT đủ → trừ tồn (chỉ Hàng hóa) → insert header + chi tiết
- Output: `{ok: true, ma_hd, tien_thua}` hoặc `{ok: false, error}`
- Tien_thua = (tien_mat + chuyen_khoan + the) - khach_can_tra (≥ 0)

**2. `huy_hoa_don_pos(p_ma_hd text, p_cancelled_by text) → jsonb`** — atomic cancel
- Cộng tồn lại (chỉ Hàng hóa) → set trang_thai="Đã hủy" + cancelled_by + cancelled_at
- Không reversible

**3. `get_next_ahd_num() → bigint`** — sequence helper

### RPC khác (từ app cũ, POS có dùng)

- `get_next_akh_num()` — sinh mã AKH cho khách mới

### Bước 7 — Bảng + RPC Đổi/Trả

```sql
phieu_doi_tra_pos (
    ma_pdt           text PRIMARY KEY,         -- AHDD000001
    ma_hd_goc        text REFERENCES hoa_don_pos(ma_hd),  -- bắt buộc
    chi_nhanh        text,
    ma_kh, ten_khach, sdt_khach,                -- snapshot từ HĐ gốc
    loai_phieu       text,                      -- "Trả" | "Đổi ngang" | "Đổi có chênh lệch"
    tien_hang_tra    integer,                   -- tổng món khách trả lại
    tien_hang_moi    integer,                   -- tổng món mua mới
    chenh_lech       integer,                   -- = moi - tra (>0 khách bù; <0 shop hoàn)
    tien_mat         integer,                   -- âm nếu shop hoàn
    chuyen_khoan     integer,
    the              integer,
    trang_thai       text,                      -- "Hoàn thành" | "Đã hủy"
    nguoi_tao, nguoi_tao_id, ghi_chu,
    created_at, cancelled_by, cancelled_at
)

phieu_doi_tra_pos_ct (
    id              bigserial PRIMARY KEY,
    ma_pdt          text REFERENCES ... ON DELETE CASCADE,
    kieu            text,                       -- "tra" (cộng kho) | "moi" (trừ kho)
    ma_hang, ten_hang, so_luong, don_gia, thanh_tien
)

CREATE SEQUENCE ahdd_seq START 1;
```

**RPC: `tao_phieu_doi_tra_pos(payload)`** — atomic
- Validate HĐ gốc tồn tại + không hủy
- Validate ngày: > 7 ngày → cần `is_admin=true` từ payload
- Validate items_tra: SL ≤ (SL gốc - SL đã trả ở phiếu trước Hoàn thành)
- Validate items_moi: check tồn (chỉ Hàng hóa)
- Cộng kho "tra", trừ kho "moi" (chỉ Hàng hóa)
- Tự suy ra `loai_phieu` từ tổng tra/mới
- PTTT: nếu chenh_lech < 0 (shop hoàn) → chỉ cho tiền mặt (auto correct = chenh_lech, CK + Thẻ phải = 0)
- Sinh mã `AHDD{seq:06d}`

**RPC: `huy_phieu_doi_tra_pos(p_ma_pdt, p_cancelled_by)`** — atomic, đảo ngược kho

### Quyết định nghiệp vụ Bước 7 (chốt với user)

| # | Quyết định | Ghi chú |
|---|------------|---------|
| B7-1 | Hỗ trợ tất cả: Trả, Đổi ngang, Đổi có chênh lệch, Trả 1 phần | Phân loại tự động theo tổng tra vs mới |
| B7-2 | Giới hạn 7 ngày cho NV thường; admin override | Check ở RPC + UI |
| B7-3 | Không loại trừ sản phẩm nào | "Cho đổi/trả mọi mặt hàng" |
| B7-4 | Chỉ cần SĐT (hoặc mã HĐ) tra ra HĐ → đổi được | UI: ô tìm SĐT/Mã ở đầu tab Lịch sử |
| B7-5 | NV thường tự xử lý, không cần admin duyệt | RPC nhận `is_admin` chỉ để gate giới hạn 7 ngày |
| B7-6 | Hàng trả tự cộng `the_kho` ngay (không phân biệt nguyên vẹn/hỏng) | Phase 1 đơn giản |
| B7-7 | Phiếu link HĐ gốc qua `ma_hd_goc` (FK) | Modal HĐ gốc hiện list phiếu đổi/trả |
| B7-8 | Chỉ admin được hủy phiếu | RPC không gate role; UI gate |
| B7-9 | 1 HĐ gốc → nhiều phiếu đổi/trả OK, miễn tổng SL trả ≤ SL gốc | RPC tính cumulative `sl_da_tra` |
| B7-10 | Tiền hoàn (chenh_lech<0): chỉ tiền mặt | Q1 với user |
| B7-11 | `khach_hang.tong_ban` GIỮ NGUYÊN khi đổi/trả | Q4 — đơn giản |
| B7-12 | UI: nhúng vào tab Lịch sử (không tạo tab mới) | + ô tìm SĐT/Mã đầu tab |

### `utils/db.py` — thêm functions Bước 7

- `search_hoa_don_pos(keyword, chi_nhanh_list, limit=30)` — ilike SĐT/mã, mọi ngày
- `load_hoa_don_pos_by_ma(ma_hd)` — load 1 HĐ kèm items
- `load_phieu_doi_tra_by_hd(ma_hd_goc)` — list phiếu đổi/trả của 1 HĐ
- `get_sl_da_tra_map(ma_hd_goc)` — map {ma_hang: tổng SL đã trả ở các phiếu Hoàn thành}
- `tao_phieu_doi_tra_pos_rpc(payload)` / `huy_phieu_doi_tra_pos_rpc(ma_pdt, cancelled_by)`

### `modules/doi_tra.py` — màn Đổi/Trả

State:
- `st.session_state["doi_tra_active"]` = `ma_hd_goc` | None — gate render full-screen
- `st.session_state["doi_tra_tra_map"]` = `{idx_item_in_hd_goc: sl_tra}`
- `st.session_state["doi_tra_moi_cart"]` = list items mua mới

UI sections: HĐ gốc info → Section A (chọn món trả) → Section B (search + cart mua mới) → Section C (tóm tắt + chênh lệch + PTTT) → footer xác nhận. Sau RPC OK → `_close_doi_tra()` + `load_hang_hoa_pos.clear()` + rerun về Lịch sử.

Cũng export: `dialog_chi_tiet_pdt(pdt)` + `dialog_confirm_huy_pdt(pdt)` cho `lich_su.py` dùng.

---

## CÁC FILE QUAN TRỌNG VÀ NỘI DUNG CHÍNH

### `utils/db.py` (POS)

```python
# Helpers
load_nhan_vien_active()       # cache 5min
load_pin(nv_id)               # PIN hash của NV
set_pin(nv_id, pin_hash)
load_hang_hoa_pos(chi_nhanh)  # cache 5min, kèm tồn kho từ the_kho
                              # Dịch vụ: ton = 999999 (vô hạn)
                              # Hàng hóa: ton từ the_kho thực tế

# Khách hàng
lookup_khach_hang_by_sdt(sdt)
upsert_khach_hang(ten, sdt, chi_nhanh)  # tự sinh mã AKH nếu mới
clean_phone(s)                # validator: chỉ giữ chữ số, max 15
clean_name(s)                 # trim + collapse whitespace, max 100

# Lịch sử + RPC
load_hoa_don_pos_history(chi_nhanh, from_date_iso)
tao_hoa_don_pos_rpc(payload)
huy_hoa_don_pos_rpc(ma_hd, cancelled_by)
```

### `utils/auth.py` (POS)

```python
run_auth_gate()               # gate ở đầu app.py — không pass thì stop
get_user() / get_active_branch() / get_accessible_branches() / is_admin()
do_logout()
_render_numpad_input(prefix, max_len=4)  # PIN: input native + numpad button
                                          # Container key prefix "numkb-" → tự inputmode=numeric
                                          # Container key prefix "numkb-tel-" → inputmode=tel
render_session_warning_banner()  # banner vàng 30 phút trước expire 23:59:59 VN
                                  # Dùng ZoneInfo để format đúng giờ VN
```

### `app.py` (POS)

- Cấu trúc: `set_page_config` → MutationObserver inject (global, 1 lần) → CSS mobile → `run_auth_gate()` → header (logo + CN popover + avatar popover) → `render_session_warning_banner()` → tabs "Bán hàng" / "Lịch sử"
- **MutationObserver pattern:** Container `st.container(key="numkb-XXX")` → JS auto set `inputmode="numeric"` cho input bên trong. Fix vấn đề bàn phím chữ bật ở lần đầu vào.

### `modules/ban_hang.py` (POS)

State routing qua `st.session_state["pos_step"]`:
- `None` → màn 2 (search + giỏ)
- `"thanh_toan"` → màn 3 (thanh toán)
- `"success"` → màn success

Cart state: `st.session_state["pos_cart"]` = list of dicts với fields: ma_hang, ten_hang, so_luong, don_gia, giam_gia_dong, ton_kho, **loai_sp**

### `modules/lich_su.py` (POS)

State: `st.session_state["lichsu_days_back"]` (mặc định 0 = chỉ hôm nay)

Confirm hủy 2 bước:
1. Bấm nút "🚫 Hủy hóa đơn" trong modal chi tiết → set `st.session_state["lichsu_confirm_huy"] = inv` → rerun
2. Dialog `_dialog_confirm_huy` mở (vì state đã set) → user xác nhận → call RPC → toast → reload

---

## APP CŨ — BAO GỒM POS DATA (Bước 6)

### Adapter pattern

```python
# utils/db.py app cũ — đã thêm:

@st.cache_data(ttl=300, show_spinner=False)
def _load_hoa_don_pos_flat(branches_key):
    # Load hoa_don_pos + hoa_don_pos_ct
    # Flatten thành format giống hoa_don (KiotViet denormalized)
    # Mỗi item = 1 dòng, header lặp lại
    # Map columns: ma_hd → "Mã hóa đơn", created_at → "Thời gian" (dd/MM/yyyy HH:mm:ss)...

@st.cache_data(ttl=300, show_spinner=False)
def load_hoa_don_unified(branches_key):
    df_old = load_hoa_don(branches_key)
    df_pos = _load_hoa_don_pos_flat(branches_key)
    return pd.concat([df_old, df_pos], ignore_index=True, sort=False)

def invalidate_hoa_don_cache():  # clear khi có thay đổi
```

### Modules đã đổi `load_hoa_don()` → `load_hoa_don_unified()`

- `modules/hoa_don.py` (1 dòng)
- `modules/khach_hang.py` (1 dòng, trong tab_detail)
- `modules/tong_quan.py` (2 dòng: `module_tong_quan` + `hien_thi_dashboard`)
- `modules/bao_cao.py` — phức tạp hơn:

### Phân loại HĐ trong `bao_cao.py` (đã thêm)

```python
APSC_PREFIXES = ["APSC"]                      # Sửa chữa
POS_PREFIXES  = ["AHD"]                       # POS bán hàng
APP_INVOICE_PREFIXES = APSC_PREFIXES + POS_PREFIXES  # backward compat

_is_apsc_hd(ma)      # APSC riêng
_is_pos_hd(ma)       # POS riêng
_is_app_hd(ma)       # cả 2 (giữ lại để code cũ dùng)
_is_kiotviet_hd(ma)  # KiotViet legacy
```

### Báo cáo đã update

- **Doanh thu (Cuối ngày + Tổng quan):** 4 cột (Tổng / Số HĐ / Bán hàng / Sửa chữa APSC) + chú thích "💡 Bán hàng — KiotViet: X · POS: Y" khi có cả 2
- **XNT:** "Bán hàng (KiotViet)" + "Bán hàng (POS)" + "Sửa chữa (APSC) — chỉ linh kiện" — 3 dòng riêng
- **Tra cứu mã hàng:** thêm query `hoa_don_pos_ct` cho dòng "Bán hàng (POS)"
- **`load_khach_hang_list`:** `tong_ban` = tổng KiotViet + tổng POS theo SĐT (chỉ "Hoàn thành")

---

## CÁC PATTERN KỸ THUẬT QUAN TRỌNG

### 1. Mobile column stacking fix (CSS scoped)

Streamlit ép `flex-direction: column` ở `@media (max-width: 640px)`. Ghi đè bằng:

```python
_CSS = """<style>
.st-key-{ZONE} div[data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    width: 100% !important;
}
.st-key-{ZONE} div[data-testid="stHorizontalBlock"] > div {
    min-width: 0 !important;  /* allow text shrink */
}
</style>"""

st.markdown(_CSS, unsafe_allow_html=True)
with st.container(key="ZONE"):
    cols = st.columns([3, 2])  # ratio điều chỉnh
```

Đã áp dụng ở: `cart-rows-zone`, `cart-header-zone`, `header-zone`, và các zone tương tự.

### 2. Numeric keyboard global (MutationObserver)

Trong `app.py` POS đã inject 1 lần:

```javascript
// Mọi input/textarea trong container có class chứa "st-key-numkb"
// → tự set inputmode="numeric" hoặc "tel"
var observer = new MutationObserver(function(mutations) {
    // áp khi DOM thay đổi
});
observer.observe(doc.body, {childList: true, subtree: true});
```

Pattern dùng: `st.container(key="numkb-XXX")` cho numeric, `st.container(key="numkb-tel-XXX")` cho phone.

### 3. Timezone

POS cùng app cũ dùng `ZoneInfo("Asia/Ho_Chi_Minh")` cho VN time. Quan trọng: Supabase lưu `timestamptz` ở UTC. Khi format hiển thị, **phải convert về VN** trước khi `strftime`:

```python
expires.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M")
```

### 4. Streamlit toast icon

`st.toast(msg, icon="✅")` — phải dùng emoji thật (✅), không được dùng ký tự Unicode "Check Mark" (✓ U+2713). Streamlit reject ký tự không phải emoji.

### 5. Dialog state pattern (cho hủy 2 bước)

```python
# Tab chính:
pending = st.session_state.get("lichsu_confirm_huy")
if pending:
    _dialog_confirm_huy(pending)  # Streamlit @st.dialog tự render

# Trong modal chi tiết, khi user bấm Hủy:
if st.button("🚫 Hủy"):
    st.session_state["lichsu_confirm_huy"] = inv
    st.rerun()  # close modal hiện tại, mở dialog confirm

# Trong dialog confirm, khi user bấm Quay lại:
st.session_state.pop("lichsu_confirm_huy", None)
st.rerun()
```

### 6. Cache invalidation sau ghi DB

Sau khi tạo/hủy HĐ POS:
```python
load_hang_hoa_pos.clear()      # tồn kho thay đổi
# App cũ tự thấy sau ≤5 phút (cache TTL của adapter)
```

---

## QUYẾT ĐỊNH KỸ THUẬT QUAN TRỌNG (DECISIONS)

| # | Quyết định | Lý do |
|---|------------|-------|
| D1 | POS tạo bảng riêng `hoa_don_pos` (normalized), không dùng `hoa_don` | Schema sạch, dễ maintain. Adapter Bước 6 lo việc gộp |
| D2 | Phương án A — Adapter trong Python ở Bước 6 | Surgical, code app cũ thay đổi 1-2 dòng/module |
| D3 | RPC atomic cho tạo/hủy HĐ POS | Tránh race condition khi 2 NV bán cùng món cuối |
| D4 | Dịch vụ: `loai_sp = "Dịch vụ"` → skip stock check + skip trừ kho | Không phá kho, không cần the_kho cho dịch vụ |
| D5 | Tien thừa: ghi nhận trong `tien_thua` column nhưng KHÔNG auto-credit cho HĐ sau | Phase 1 đơn giản, làm sau khi có nhu cầu |
| D6 | NV thường thấy mọi HĐ POS của CN (không filter theo người bán) | User chọn — cần linh hoạt cho team nhỏ |
| D7 | Hủy HĐ: chỉ admin, hủy bất kỳ lúc nào (không giới hạn ngày) | User chọn — admin cần linh hoạt |
| D8 | HĐ đã hủy: hiện xám trong list (không ẩn) | User chọn — có dấu vết |
| D9 | "Xem cũ hơn" lịch sử HĐ: +1 ngày mỗi click | User chọn — đơn giản |
| D10 | In K80: kiến trúc Cloud-to-LAN spooler (POS INSERT print_queue → Local Daemon polls → TCP 9100) | User design |
| D11 | Bước 6: tách prefix APSC / POS / KiotViet, hiển thị doanh thu 4 cột + caption tách KiotViet/POS | User chọn |
| D12 | Sau khi bỏ KiotViet, không cần code thay đổi gì | Adapter tự thích nghi |
| D13 | Bước 7: prefix mới `AHDD` cho phiếu đổi/trả (sequence riêng `ahdd_seq`) | Tách bạch với HĐ POS |
| D14 | Bước 7: 1 phiếu đổi/trả lưu CẢ items trả + items mua mới trong 1 bảng `phieu_doi_tra_pos_ct` (cột `kieu`) | Đơn giản hơn 2 bảng |
| D15 | Bước 7: shop hoàn tiền chỉ tiền mặt (Phase 1) | User chọn |
| D16 | Bước 7: `khach_hang.tong_ban` không trừ khi đổi/trả | User chọn — đơn giản |

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
CN_INFO = {  # đầy đủ địa chỉ + SĐT cho in hóa đơn (chưa dùng)
    ...
}
```

### App cũ `utils/config.py`

```python
ALL_BRANCHES = [...]
CN_SHORT = {...}
IN_APP_MARKER   = "Chuyển hàng (App)"
ARCHIVED_MARKER = "Chuyển hàng (App - đã đồng bộ)"
APP_INVOICE_PREFIXES = ["APSC", "AHD"]  # đã update Bước 6
```

### Streamlit secrets (cả 2 app dùng cùng)

```toml
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "xxxxx"
```

---

## NHỮNG ĐIỂM CẦN LƯU Ý KHI LÀM BƯỚC 7 / 8

### Trước khi code

1. **Hỏi user các câu nghiệp vụ cụ thể** — user đã chuẩn bị câu trả lời sẵn cho cả 2 bước. Đừng giả định.
2. **Đọc CLAUDE.md** trước (trong project knowledge) — bias về caution, simplicity.
3. **Trình bày plan trước, code sau** — user sẽ approve plan rồi mới code.

### Bước 7 — Đổi/Trả hàng đã bán (câu hỏi đã hỏi user, user có sẵn câu trả lời)

Tôi đã hỏi user các câu sau (xem context lịch sử):

**A. Phạm vi:**
- Đổi (1↔1), Trả (refund), Đổi có chênh lệch, Trả 1 phần — hỗ trợ tất cả hay chỉ một số?

**B. Quy định cửa hàng:**
- Đổi/trả trong bao nhiêu ngày?
- Có loại trừ sản phẩm nào không (pin đã mở, dịch vụ đã thực hiện)?
- Bắt buộc HĐ gốc, hay chỉ cần SĐT?

**C. Ai được phép:**
- Chỉ admin, hay NV thường có nhưng cần admin duyệt?

**D. Tồn kho:**
- Hàng trả về tự cộng `the_kho`?
- Hay kiểm tra tình trạng (nguyên vẹn/hỏng) trước?

**E. Truy vết:**
- HĐ trả/đổi liên kết HĐ gốc?

**Liên quan database (theo D2 trong AI_CONTEXT của app cũ):** Sẽ tạo bảng riêng `phieu_doi_tra_pos` (KHÔNG dùng `phieu_tra_hang` — bảng đó là trả hàng NCC).

### Bước 8 — Đặt hàng theo yêu cầu (câu hỏi đã hỏi user)

Tôi đã hỏi user:

**A. Nghiệp vụ thực tế:**
- Khách → đặt hàng chưa có → đặt cọc → đặt NCC → hàng về → khách đến lấy + thanh toán còn lại — đúng flow?

**B. Tracking trạng thái:**
- "Chờ đặt" → "Đã đặt NCC" → "Hàng về" → "Khách đã lấy" — full flow?
- Hay đơn giản hơn: "Đang chờ" / "Hoàn thành" / "Hủy"?

**C. Đặt cọc:**
- Có ghi nhận đặt cọc? Bao nhiêu %?
- Tiền cọc lưu ở đâu? Phiếu thu cọc riêng?
- Hủy đơn → có hoàn cọc?

**D. Mã sản phẩm:**
- Có sẵn trong `hang_hoa` không?
- Hay nhập tay free-text?

**E. Khi hàng về:**
- NV tạo phiếu nhập kho thủ công?
- Hay bấm "Đã có hàng" → hệ thống tự cộng `the_kho`?

**F. Khi khách đến lấy:**
- Auto tạo HĐ POS trừ cọc?
- Hay manual tạo HĐ?

**G. Module nằm ở đâu:**
- App POS (cùng tab Bán hàng / Lịch sử)?
- Hay app cũ?

---

## CÁC SESSION CŨ ĐÃ LÀM GÌ

### Session 1 (cách đây): Bước 1-3
- Setup auth PIN, sales screen, payment + RPC
- Fix nhiều issues với Streamlit mobile (cột bị stack dọc, bàn phím chữ vs số)
- Pattern MutationObserver cho numeric keyboard

### Session 2 (cách đây): Bước 4-5
- Lịch sử HĐ + hủy
- Polish: validation strict, banner cảnh báo session, empty states đẹp hơn
- Documentation: README, SETUP, ADMIN_GUIDE, full_setup.sql

### Session hiện tại: Bước 6
- Adapter `load_hoa_don_unified` trong app cũ
- Tách prefix APSC / POS / KiotViet trong báo cáo
- Update `tong_ban` của khách hàng cộng dồn cả 2 nguồn
- 5 file patch cho user áp vào app cũ
- User đã test 8 trường hợp đều OK

---

## STYLE GUIDE KHI LÀM VIỆC VỚI USER

- User nói **tiếng Việt**, prefer trả lời ngắn gọn rõ ràng
- User dùng các thuật ngữ kỹ thuật chính xác (system architecture, RPC, atomic, etc.) — không cần giải thích đơn giản hóa
- User kỹ tính, hay phát hiện edge case (ví dụ: bug logic SĐT khi không tick Khách lẻ; bug timezone hiển thị 16:59 thay vì 23:59)
- User đôi khi tự fix code mà không báo (mobile column stacking) → **luôn ask user gửi lại file trước khi code tiếp** nếu có nguy cơ override
- User có sẵn `CLAUDE.md` rule: think before coding, simplicity first, surgical changes
- Khi đề xuất plan, **luôn list rõ scope rồi đợi approve** trước khi code
- Khi gặp choice, **trình bày 2-3 lựa chọn, recommend 1, và giải thích tại sao** — đừng pick silently

---

## CHECKLIST BÀN GIAO

Trước khi bắt đầu Bước 7/8, Claude session mới nên:

1. ✅ Đọc file `CLAUDE.md` trong project knowledge
2. ✅ Đọc file này (`AI_CONTEXT.md`) hết
3. ✅ Hỏi user gửi các file Python liên quan từ POS app (`utils/db.py`, `modules/lich_su.py`, `modules/ban_hang.py`) để có code hiện tại
4. ✅ Hỏi user các câu nghiệp vụ Bước 7 (5 câu A-E) — user đã có câu trả lời sẵn
5. ✅ Hỏi user các câu nghiệp vụ Bước 8 (7 câu A-G) — user đã có câu trả lời sẵn
6. ✅ Sau khi có câu trả lời, **đề xuất plan kỹ thuật**, đợi user approve
7. ✅ Code, deliver as patch hoặc full files, deliver SQL nếu cần
8. ✅ Sau test, cập nhật roadmap

---

## TROUBLESHOOTING REFERENCE

### Nếu user gặp lỗi sau deploy

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `Chưa cấu hình SUPABASE_URL` | Streamlit secrets thiếu | Set lại trong Streamlit Cloud → Secrets |
| Bàn phím chữ thay vì số ở PIN | MutationObserver chưa kịp inject | Hard refresh (Ctrl+Shift+R) |
| `Lỗi tạo hóa đơn: tồn không đủ` | Race condition / tồn = 0 | Refresh page, kiểm tra `the_kho` Supabase |
| Banner session sai giờ (16:59 thay 23:59) | Strftime trên UTC datetime không convert | Đã fix Bước 5: `.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))` |
| `st.toast` báo lỗi icon | Dùng ký tự Unicode không phải emoji | Đổi `✓` → `✅` |
| HĐ POS không hiện app cũ | Cache 5 phút | Bấm nút "↺ Tải lại" header app cũ |

### Nếu Streamlit Cloud rebuild fail

- Check `requirements.txt` có thiếu package mới không
- Check syntax error: `python3 -c "import ast; ast.parse(open('app.py').read())"`
- Roll back commit cuối cùng

---

## CONTACT

User là **chủ cửa hàng đồng hồ DL Watch** ở Bà Rịa - Vũng Tàu. Liên hệ qua chat Claude.
