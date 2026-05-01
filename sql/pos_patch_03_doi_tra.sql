-- ════════════════════════════════════════════════════════════════
-- Bước 7 — Đổi/Trả hàng đã bán (POS)
-- ════════════════════════════════════════════════════════════════
-- Mã phiếu: AHDD000001 (sequence ahdd_seq)
-- Liên kết HĐ gốc qua ma_hd_goc REFERENCES hoa_don_pos(ma_hd)
-- Kiểu chi tiết: "tra" (cộng kho) | "moi" (trừ kho)
-- 1 HĐ gốc có thể có NHIỀU phiếu đổi/trả, miễn tổng SL trả ≤ SL gốc
-- ════════════════════════════════════════════════════════════════

-- 1. Sequence cho mã phiếu AHDD
CREATE SEQUENCE IF NOT EXISTS ahdd_seq START 1;

-- 2. Bảng header phiếu đổi/trả
CREATE TABLE IF NOT EXISTS phieu_doi_tra_pos (
    ma_pdt           text PRIMARY KEY,
    ma_hd_goc        text NOT NULL REFERENCES hoa_don_pos(ma_hd),
    chi_nhanh        text NOT NULL,
    ma_kh            text,
    ten_khach        text,
    sdt_khach        text,
    loai_phieu       text NOT NULL,         -- "Trả" | "Đổi ngang" | "Đổi có chênh lệch"
    tien_hang_tra    integer NOT NULL DEFAULT 0,
    tien_hang_moi    integer NOT NULL DEFAULT 0,
    chenh_lech       integer NOT NULL DEFAULT 0,    -- = moi - tra
    tien_mat         integer NOT NULL DEFAULT 0,    -- >0 nếu khách bù; <0 nếu shop hoàn
    chuyen_khoan     integer NOT NULL DEFAULT 0,
    the              integer NOT NULL DEFAULT 0,
    trang_thai       text NOT NULL DEFAULT 'Hoàn thành',  -- "Hoàn thành" | "Đã hủy"
    nguoi_tao        text,
    nguoi_tao_id     bigint,
    ghi_chu          text,
    created_at       timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh'),
    cancelled_by     text,
    cancelled_at     timestamptz
);

CREATE INDEX IF NOT EXISTS idx_pdt_ma_hd_goc  ON phieu_doi_tra_pos(ma_hd_goc);
CREATE INDEX IF NOT EXISTS idx_pdt_chi_nhanh  ON phieu_doi_tra_pos(chi_nhanh);
CREATE INDEX IF NOT EXISTS idx_pdt_created_at ON phieu_doi_tra_pos(created_at DESC);

-- 3. Bảng chi tiết
CREATE TABLE IF NOT EXISTS phieu_doi_tra_pos_ct (
    id          bigserial PRIMARY KEY,
    ma_pdt      text NOT NULL REFERENCES phieu_doi_tra_pos(ma_pdt) ON DELETE CASCADE,
    kieu        text NOT NULL,           -- "tra" | "moi"
    ma_hang     text NOT NULL,
    ten_hang    text,
    so_luong    integer NOT NULL,
    don_gia     integer NOT NULL,
    thanh_tien  integer NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pdt_ct_ma_pdt ON phieu_doi_tra_pos_ct(ma_pdt);


-- ════════════════════════════════════════════════════════════════
-- RPC: tao_phieu_doi_tra_pos(payload jsonb) → jsonb
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION tao_phieu_doi_tra_pos(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_ma_hd_goc      text;
    v_chi_nhanh      text;
    v_hd_goc         hoa_don_pos%ROWTYPE;
    v_is_admin       boolean;
    v_age_days       integer;
    v_items_tra      jsonb;
    v_items_moi      jsonb;
    v_item           jsonb;
    v_ma_hang        text;
    v_so_luong       integer;
    v_don_gia        integer;
    v_loai_sp        text;
    v_ton_hien_tai   integer;
    v_sl_da_ban      integer;
    v_sl_da_tra      integer;
    v_tong_tra       integer := 0;
    v_tong_moi       integer := 0;
    v_chenh_lech     integer;
    v_tien_mat       integer;
    v_chuyen_khoan   integer;
    v_the            integer;
    v_loai_phieu     text;
    v_seq            bigint;
    v_ma_pdt         text;
    v_now            timestamptz := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh');
BEGIN
    -- Đọc các field bắt buộc
    v_ma_hd_goc := payload->>'ma_hd_goc';
    v_is_admin  := COALESCE((payload->>'is_admin')::boolean, false);
    v_items_tra := COALESCE(payload->'items_tra', '[]'::jsonb);
    v_items_moi := COALESCE(payload->'items_moi', '[]'::jsonb);

    IF v_ma_hd_goc IS NULL OR v_ma_hd_goc = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu mã hóa đơn gốc');
    END IF;

    -- Lock + load HĐ gốc
    SELECT * INTO v_hd_goc FROM hoa_don_pos
    WHERE ma_hd = v_ma_hd_goc
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Không tìm thấy hóa đơn gốc');
    END IF;

    IF v_hd_goc.trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Hóa đơn gốc đã bị hủy, không thể đổi/trả');
    END IF;

    v_chi_nhanh := v_hd_goc.chi_nhanh;

    -- Validate ngày: > 7 ngày phải là admin
    v_age_days := GREATEST(0, EXTRACT(DAY FROM (v_now - v_hd_goc.created_at))::int);
    IF v_age_days > 7 AND NOT v_is_admin THEN
        RETURN jsonb_build_object(
            'ok', false,
            'error', format('Hóa đơn đã %s ngày — chỉ admin mới được tạo phiếu đổi/trả', v_age_days)
        );
    END IF;

    -- Phải có ít nhất 1 item trả
    IF jsonb_array_length(v_items_tra) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phải có ít nhất 1 sản phẩm trả lại');
    END IF;

    -- ── VALIDATE & XỬ LÝ ITEMS TRẢ ──
    -- Với mỗi item trả: check SL ≤ (SL trong HĐ gốc - SL đã trả ở các phiếu trước)
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_tra)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN
            CONTINUE;
        END IF;

        -- SL đã bán theo HĐ gốc
        SELECT COALESCE(SUM(so_luong), 0) INTO v_sl_da_ban
        FROM hoa_don_pos_ct
        WHERE ma_hd = v_ma_hd_goc AND ma_hang = v_ma_hang;

        IF v_sl_da_ban = 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Sản phẩm %s không có trong HĐ gốc', v_ma_hang));
        END IF;

        -- SL đã trả ở các phiếu đổi/trả trước (trạng thái Hoàn thành)
        SELECT COALESCE(SUM(ct.so_luong), 0) INTO v_sl_da_tra
        FROM phieu_doi_tra_pos_ct ct
        JOIN phieu_doi_tra_pos pdt ON pdt.ma_pdt = ct.ma_pdt
        WHERE pdt.ma_hd_goc = v_ma_hd_goc
          AND pdt.trang_thai = 'Hoàn thành'
          AND ct.kieu = 'tra'
          AND ct.ma_hang = v_ma_hang;

        IF v_so_luong > (v_sl_da_ban - v_sl_da_tra) THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Sản phẩm %s: chỉ còn %s có thể trả (đã bán %s, đã trả %s)',
                    v_ma_hang, v_sl_da_ban - v_sl_da_tra, v_sl_da_ban, v_sl_da_tra));
        END IF;

        v_tong_tra := v_tong_tra + (v_so_luong * v_don_gia);
    END LOOP;

    -- ── VALIDATE ITEMS MỚI: check tồn (chỉ Hàng hóa) ──
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_moi)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN
            CONTINUE;
        END IF;

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;

        IF v_loai_sp IS NULL THEN
            v_loai_sp := 'Hàng hóa';
        END IF;

        IF v_loai_sp = 'Hàng hóa' THEN
            SELECT COALESCE(SUM("Tồn cuối kì"), 0) INTO v_ton_hien_tai
            FROM the_kho
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;

            IF v_ton_hien_tai < v_so_luong THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('Sản phẩm %s không đủ tồn (có %s, cần %s)',
                        v_ma_hang, v_ton_hien_tai, v_so_luong));
            END IF;
        END IF;

        v_tong_moi := v_tong_moi + (v_so_luong * v_don_gia);
    END LOOP;

    -- ── TÍNH CHÊNH LỆCH + LOẠI PHIẾU ──
    v_chenh_lech := v_tong_moi - v_tong_tra;

    IF v_tong_moi = 0 THEN
        v_loai_phieu := 'Trả';
    ELSIF v_chenh_lech = 0 THEN
        v_loai_phieu := 'Đổi ngang';
    ELSE
        v_loai_phieu := 'Đổi có chênh lệch';
    END IF;

    -- PTTT: theo Q1 — chỉ cho phép tiền mặt
    v_tien_mat     := COALESCE((payload->>'tien_mat')::int, 0);
    v_chuyen_khoan := COALESCE((payload->>'chuyen_khoan')::int, 0);
    v_the          := COALESCE((payload->>'the')::int, 0);

    -- Nếu chenh_lech > 0 (khách bù): tổng PTTT phải >= chenh_lech
    -- Nếu chenh_lech < 0 (shop hoàn): tien_mat phải = chenh_lech (số âm) hoặc client gửi đúng
    -- Nếu chenh_lech = 0: PTTT = 0
    IF v_chenh_lech > 0 THEN
        IF (v_tien_mat + v_chuyen_khoan + v_the) < v_chenh_lech THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Khách cần bù %s, mới nhập %s',
                    v_chenh_lech, v_tien_mat + v_chuyen_khoan + v_the));
        END IF;
    ELSIF v_chenh_lech < 0 THEN
        -- Shop hoàn: bắt buộc tien_mat = chenh_lech (âm), CK + Thẻ = 0
        IF v_chuyen_khoan != 0 OR v_the != 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', 'Hoàn tiền cho khách: chỉ chấp nhận tiền mặt');
        END IF;
        IF v_tien_mat != v_chenh_lech THEN
            v_tien_mat := v_chenh_lech;  -- auto correct: shop hoàn = số âm
        END IF;
    ELSE
        v_tien_mat     := 0;
        v_chuyen_khoan := 0;
        v_the          := 0;
    END IF;

    -- ── SINH MÃ AHDD ──
    v_seq := nextval('ahdd_seq');
    v_ma_pdt := 'AHDD' || LPAD(v_seq::text, 6, '0');

    -- ── INSERT HEADER ──
    INSERT INTO phieu_doi_tra_pos (
        ma_pdt, ma_hd_goc, chi_nhanh,
        ma_kh, ten_khach, sdt_khach,
        loai_phieu,
        tien_hang_tra, tien_hang_moi, chenh_lech,
        tien_mat, chuyen_khoan, the,
        trang_thai, nguoi_tao, nguoi_tao_id, ghi_chu,
        created_at
    ) VALUES (
        v_ma_pdt, v_ma_hd_goc, v_chi_nhanh,
        v_hd_goc.ma_kh, v_hd_goc.ten_khach, v_hd_goc.sdt_khach,
        v_loai_phieu,
        v_tong_tra, v_tong_moi, v_chenh_lech,
        v_tien_mat, v_chuyen_khoan, v_the,
        'Hoàn thành',
        payload->>'nguoi_tao',
        NULLIF(payload->>'nguoi_tao_id', '')::bigint,
        payload->>'ghi_chu',
        v_now
    );

    -- ── INSERT CHI TIẾT + CỘNG/TRỪ KHO ──
    -- Items "tra": cộng kho (chỉ Hàng hóa)
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_tra)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN
            CONTINUE;
        END IF;

        INSERT INTO phieu_doi_tra_pos_ct (
            ma_pdt, kieu, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_pdt, 'tra', v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_so_luong * v_don_gia
        );

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;

        IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;

            -- Nếu chưa có dòng the_kho → tạo
            IF NOT FOUND THEN
                INSERT INTO the_kho ("Mã hàng", "Chi nhánh", "Tồn cuối kì")
                VALUES (v_ma_hang, v_chi_nhanh, v_so_luong);
            END IF;
        END IF;
    END LOOP;

    -- Items "moi": trừ kho (chỉ Hàng hóa)
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_moi)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN
            CONTINUE;
        END IF;

        INSERT INTO phieu_doi_tra_pos_ct (
            ma_pdt, kieu, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_pdt, 'moi', v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_so_luong * v_don_gia
        );

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;

        IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'ok', true,
        'ma_pdt', v_ma_pdt,
        'loai_phieu', v_loai_phieu,
        'tien_hang_tra', v_tong_tra,
        'tien_hang_moi', v_tong_moi,
        'chenh_lech', v_chenh_lech
    );
END;
$$;


-- ════════════════════════════════════════════════════════════════
-- RPC: huy_phieu_doi_tra_pos(p_ma_pdt text, p_cancelled_by text) → jsonb
-- ════════════════════════════════════════════════════════════════
-- Đảo ngược: trừ lại "tra", cộng lại "moi", set Đã hủy
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION huy_phieu_doi_tra_pos(p_ma_pdt text, p_cancelled_by text)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_pdt       phieu_doi_tra_pos%ROWTYPE;
    v_ct        record;
    v_loai_sp   text;
    v_now       timestamptz := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh');
BEGIN
    SELECT * INTO v_pdt FROM phieu_doi_tra_pos
    WHERE ma_pdt = p_ma_pdt
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Không tìm thấy phiếu');
    END IF;

    IF v_pdt.trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phiếu đã bị hủy trước đó');
    END IF;

    -- Đảo kho cho từng dòng chi tiết
    FOR v_ct IN
        SELECT kieu, ma_hang, so_luong
        FROM phieu_doi_tra_pos_ct
        WHERE ma_pdt = p_ma_pdt
    LOOP
        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ct.ma_hang;

        IF COALESCE(v_loai_sp, 'Hàng hóa') != 'Hàng hóa' THEN
            CONTINUE;
        END IF;

        IF v_ct.kieu = 'tra' THEN
            -- "tra" lúc tạo cộng kho → hủy thì trừ lại
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_ct.so_luong
            WHERE "Mã hàng" = v_ct.ma_hang AND "Chi nhánh" = v_pdt.chi_nhanh;
        ELSIF v_ct.kieu = 'moi' THEN
            -- "moi" lúc tạo trừ kho → hủy thì cộng lại
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_ct.so_luong
            WHERE "Mã hàng" = v_ct.ma_hang AND "Chi nhánh" = v_pdt.chi_nhanh;

            IF NOT FOUND THEN
                INSERT INTO the_kho ("Mã hàng", "Chi nhánh", "Tồn cuối kì")
                VALUES (v_ct.ma_hang, v_pdt.chi_nhanh, v_ct.so_luong);
            END IF;
        END IF;
    END LOOP;

    UPDATE phieu_doi_tra_pos
    SET trang_thai   = 'Đã hủy',
        cancelled_by = COALESCE(p_cancelled_by, ''),
        cancelled_at = v_now
    WHERE ma_pdt = p_ma_pdt;

    RETURN jsonb_build_object('ok', true, 'ma_pdt', p_ma_pdt);
END;
$$;


-- ════════════════════════════════════════════════════════════════
-- Helper: get_next_ahdd_num()
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION get_next_ahdd_num()
RETURNS bigint
LANGUAGE sql
AS $$
    SELECT nextval('ahdd_seq');
$$;
