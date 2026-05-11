# PROMPT GIAO VIỆC CHO CLAUDE CODE

---

Chào Claude Code,

Mình cần bạn implement feature **Quét mã vạch** cho POS app theo file `PLAN.md` đã được lên kế hoạch sẵn (đính kèm).

## Context

- Repo: `KevinTruong34/dl-watch-pos` (POS app)
- Stack: Streamlit + Supabase
- Pattern proven trên 4 feature trước (SPK/DVPS, B1, B2a, B2b, APSC K80): 2-phase A planning + B execute với commit từng phase
- Phase A planning đã xong → bạn làm Phase B execute

## Tài liệu tham khảo BẮT BUỘC đọc trước khi code

1. **`PLAN.md`** — kế hoạch chi tiết 6 phases (đính kèm)
2. **`CLAUDE.md`** — guidelines: think before coding, simplicity first, surgical changes, goal-driven execution
3. **`AI_CONTEXT.md`** (POS) — context dự án, conventions, patterns đã proven

## Cách làm việc

### 1. Bắt đầu với Pre-flight
- Đọc PLAN.md mục "PRE-FLIGHT CHECKLIST"
- Chạy đủ 5 verify commands
- Nếu bất kỳ check nào fail → **STOP, hỏi mình trước**, KHÔNG tự fix

### 2. Làm tuần tự từng phase
- **KHÔNG nhảy phase**, KHÔNG gộp commit nhiều phase
- Mỗi phase = 1 commit riêng với message rõ ràng:
  - `Phase 0: POC barcode scan (camera + pyzbar)`
  - `Phase 1: Schema migration - UNIQUE partial index ma_vach`
  - `Phase 2: Helper utils/barcode.py`
  - `Phase 3: Wire barcode scan vào ban_hang.py`
  - `Phase 4: Wire barcode scan vào doi_tra.py items_moi`
  - `Phase 5: Cleanup POC + deploy + update AI_CONTEXT.md`

### 3. Gate Phase 0 → DỪNG chờ mình test
Sau khi push Phase 0:
- Báo lại cho mình URL/branch để mình deploy + test trên điện thoại
- **KHÔNG tự ý qua Phase 1**
- Mình sẽ báo kết quả 8 success criteria → bạn mới tiếp tục

### 4. Gate Phase 3 + Phase 4 → DỪNG chờ mình gửi file
Trước khi đụng `ban_hang.py` và `doi_tra.py`:
- **DỪNG, yêu cầu mình gửi file hiện tại** (lý do: mình thỉnh thoảng tự fix code mà không báo, tránh override)
- Đọc kỹ pattern add cart hiện tại → reuse pattern đó, KHÔNG invent flow mới
- Placeholder `_add_to_cart_pattern()` trong PLAN.md cần thay bằng logic thật

### 5. Smoke test sau mỗi edit
- `python3 -c "import ast; ast.parse(open('path/to/file.py').read())"` sau mỗi edit `.py`
- Phase 1 SQL: chạy verify query, confirm `is_unique=true`
- Phase 5: chạy đủ checklist smoke test trong PLAN.md trước khi merge main

### 6. Style code
- Match style của codebase hiện tại (xem các module khác trong `pos_app/modules/`)
- KHÔNG refactor adjacent code (CLAUDE.md mục 3 — Surgical Changes)
- KHÔNG thêm error handling cho impossible scenarios (CLAUDE.md mục 2)
- Comment tiếng Việt OK, match với các file khác

### 7. Commit message convention
```
Phase X: <description>

- <chi tiết 1>
- <chi tiết 2>

Refs: PLAN.md mục Phase X
```

## Quy tắc QUAN TRỌNG

1. **Tiếng Việt khi giao tiếp với mình** (xưng "mình/bạn")
2. **Surface tradeoffs, không hide confusion** — gặp chỗ unclear thì hỏi, đừng tự assume
3. **KHÔNG đụng web_app/DLW repo** — feature này chỉ POS, DLW defer Phase 2 sau
4. **KHÔNG migrate data**, KHÔNG đụng RPC ngoài Phase 1 SQL
5. **KHÔNG xóa code cũ** trừ POC cleanup ở Phase 5 (chỉ xóa code POC mình tự thêm vào)
6. **`packages.txt` ở ROOT repo** (cùng level với `pos_app/`), KHÔNG phải bên trong `pos_app/`
7. **Rollback plan luôn rõ ràng** — Phase nào fail thì revert phase đó, không cascade

## Đầu ra mỗi phase

Báo lại cho mình theo format:

```
✅ Phase X — <tên phase> DONE

Files changed:
  - <file 1>
  - <file 2>

Commit: <hash> "<message>"

Smoke test:
  - <verify 1>: pass
  - <verify 2>: pass

Next step: <chờ user / qua phase Y / cần file Z>
```

## Bắt đầu

1. Đọc PLAN.md
2. Đọc CLAUDE.md + AI_CONTEXT.md
3. Confirm bạn đã hiểu plan và sẵn sàng
4. Bắt đầu Pre-flight checklist

Nếu có chỗ nào trong PLAN.md không rõ → hỏi mình TRƯỚC khi chạy bất kỳ lệnh nào.

Cảm ơn!
