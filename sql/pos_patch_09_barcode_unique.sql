-- ════════════════════════════════════════════════════════════════
-- Patch 09 — UNIQUE partial index cho hang_hoa.ma_vach
-- ════════════════════════════════════════════════════════════════
-- Mục đích: enforce ma_vach unique (chỉ cho row active + non-null),
-- để barcode lookup ở POS chắc chắn ra ≤1 SP.
-- Pattern: giống hang_hoa_open_price_idx (partial index).
-- Refs: PLAN_v2.md mục Phase 1.
-- ════════════════════════════════════════════════════════════════

-- ── PRE-CHECK (chạy TRƯỚC khi ALTER) ──
-- Xác nhận không còn ma_vach trùng trong scope (active + non-null).
-- Expected: 0 rows. Nếu có rows → resolve duplicate trước khi chạy migration.
SELECT ma_vach, COUNT(*) AS n
FROM hang_hoa
WHERE active = true AND ma_vach IS NOT NULL
GROUP BY ma_vach
HAVING COUNT(*) > 1;


-- ── MIGRATION ──
-- 1. Drop index btree cũ (không unique) nếu có.
DROP INDEX IF EXISTS idx_hang_hoa_ma_vach;

-- 2. Tạo UNIQUE partial index mới.
-- Partial scope: chỉ enforce unique cho ma_vach NOT NULL AND active=true.
-- → Hàng đã ẩn (active=false) hoặc chưa gán ma_vach (NULL) không bị constraint.
CREATE UNIQUE INDEX hang_hoa_ma_vach_idx ON hang_hoa(ma_vach)
    WHERE ma_vach IS NOT NULL AND active = true;


-- ── VERIFY ──
-- Expected: 1 row, is_unique = true, index_definition chứa "UNIQUE INDEX ... WHERE ...".
SELECT
    i.relname AS index_name,
    ix.indisunique AS is_unique,
    pg_get_indexdef(ix.indexrelid) AS index_definition
FROM pg_class t
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
WHERE t.relname = 'hang_hoa' AND a.attname = 'ma_vach';


-- ── ROLLBACK (nếu cần) ──
-- DROP INDEX hang_hoa_ma_vach_idx;
-- CREATE INDEX idx_hang_hoa_ma_vach ON hang_hoa(ma_vach);
