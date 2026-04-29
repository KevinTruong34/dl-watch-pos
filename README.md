# DL Watch POS

App POS bán hàng — mobile-first, dùng chung Supabase DB với app quản lý chính.

---

## 📋 Yêu cầu trước khi deploy

1. ✅ Đã chạy 2 file SQL trên Supabase:
   - `pos_setup.sql` (tạo bảng + RPC)
   - `pos_patch_01_tien_thua.sql` (thêm cột tien_thua)
2. ✅ Có `SUPABASE_URL` và `SUPABASE_KEY` (giống app chính)
3. ✅ Có tài khoản GitHub
4. ✅ Có tài khoản Streamlit Cloud (https://share.streamlit.io)

---

## 🚀 Deploy lên Streamlit Cloud (khuyên dùng)

### Bước 1: Tạo repo GitHub mới

1. Vào https://github.com/new
2. Đặt tên repo: `dl-watch-pos` (hoặc tên khác tùy anh)
3. Để **Private** (đề xuất, vì chứa code business)
4. Bỏ tick "Add README" — vì mình đã có sẵn
5. Bấm **Create repository**

### Bước 2: Upload code lên GitHub

**Cách dễ nhất — qua web browser:**

1. Sau khi tạo repo xong, GitHub sẽ hiện trang trắng có dòng:
   *"…or upload an existing file"* — bấm vào đó
2. Kéo thả **toàn bộ files trong thư mục `pos_app/`** (trừ `.streamlit/secrets.toml` nếu có) vào trang upload
3. Hoặc bấm "choose your files" và chọn tất cả
4. Cuộn xuống dưới, gõ commit message: `Initial commit`
5. Bấm **Commit changes**

> ⚠️ **Lưu ý quan trọng:** KHÔNG upload file `.streamlit/secrets.toml` lên GitHub vì chứa key bí mật. File `.gitignore` đã loại trừ sẵn. Nếu lỡ upload, đổi key Supabase ngay.

### Bước 3: Deploy lên Streamlit Cloud

1. Vào https://share.streamlit.io
2. Đăng nhập bằng GitHub
3. Bấm **New app** (góc trên phải)
4. Chọn repo vừa tạo (`dl-watch-pos`)
5. Branch: `main`
6. Main file path: `app.py`
7. Bấm **Advanced settings** → tab **Secrets** → paste nội dung sau (thay giá trị thật):

   ```toml
   SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
   SUPABASE_KEY = "eyJxxxxxxxxx..."
   ```

8. Bấm **Deploy!**

App sẽ build và chạy trong 2–5 phút. Sau khi xong, anh sẽ có 1 link dạng:
`https://dl-watch-pos-xxxxx.streamlit.app`

### Bước 4: Test app

1. Mở link trên điện thoại
2. Chọn tên anh trong danh sách
3. Set PIN 4 số → xác nhận lại PIN
4. Chọn chi nhánh
5. Sẽ thấy trang xác nhận "Bước 1 hoàn tất" — login flow đã chạy đúng

### Bước 5 (tùy chọn): Add to Home Screen

Trên điện thoại:
- **iPhone (Safari):** Bấm nút Share → Add to Home Screen
- **Android (Chrome):** Bấm dấu 3 chấm → Install app / Add to home

---

## 🛠 Chạy local để test (tùy chọn)

Nếu anh muốn test trên máy tính trước khi deploy:

1. Cài Python 3.10+
2. Mở Terminal/CMD trong thư mục `pos_app/`
3. Cài thư viện:
   ```bash
   pip install -r requirements.txt
   ```
4. Tạo file `.streamlit/secrets.toml` với nội dung:
   ```toml
   SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
   SUPABASE_KEY = "eyJxxxxxxxxx..."
   ```
5. Chạy:
   ```bash
   streamlit run app.py
   ```
6. Browser tự mở `http://localhost:8501`

---

## 📁 Cấu trúc files

```
pos_app/
├── app.py                          # Entry point + CSS + header
├── requirements.txt                # Thư viện Python
├── .gitignore                      # Loại trừ secrets khi push GitHub
├── README.md                       # File này
├── .streamlit/
│   ├── config.toml                 # Theme mobile
│   └── secrets.toml.example        # Template secrets (KHÔNG dùng thật)
├── utils/
│   ├── __init__.py
│   ├── config.py                   # Hằng số: chi nhánh, branding
│   ├── db.py                       # Supabase client + load nhân viên/PIN
│   ├── auth.py                     # Login PIN + numpad + session
│   └── helpers.py                  # Timezone, format VND
├── modules/
│   ├── __init__.py
│   ├── ban_hang.py                 # [Bước 2-3] Bán hàng + thanh toán
│   └── lich_su.py                  # [Bước 4] Lịch sử hóa đơn
└── static/                         # Sẽ thêm favicon ở bước sau
```

---

## ❓ Sự cố thường gặp

**Q: Login xong báo lỗi "Lỗi khôi phục session"**
A: Kiểm tra Supabase secrets đã đúng chưa, và bảng `sessions` có tồn tại không.

**Q: Không thấy nhân viên nào trong danh sách**
A: Vào DB Supabase, kiểm tra bảng `nhan_vien` có dòng `active = true` không.

**Q: Set PIN xong vẫn báo Sai PIN**
A: Hiếm gặp. Vào Supabase → bảng `pin_code` → xóa dòng của NV đó → mở lại app set PIN mới.

**Q: Đổi chi nhánh không lưu sau khi tắt app**
A: Đây là tính năng `localStorage`. Nếu Add to Home Screen → tắt hẳn app → mở lại có thể bị reset, đây là giới hạn của Streamlit hiện tại (đã có trong roadmap).

---

## 🗺️ Roadmap

- [x] **Bước 1:** Auth (PIN 4 số) + Setup project
- [ ] **Bước 2:** Màn bán hàng (search + giỏ hàng)
- [ ] **Bước 3:** Màn thanh toán + RPC + in K80
- [ ] **Bước 4:** Lịch sử hóa đơn (xem + admin hủy)
- [ ] **Bước 5:** Polish + tối ưu

**Tương lai:**
- Lưu token vào `localStorage` thay vì URL params (giữ đăng nhập khi Add to Home Screen)
- Quản lý số dư khách hàng (tiền thừa dùng cho lần sau)
