"""
Module Đổi/Trả hàng — Bước 7.

UI flow (full-screen state, vào từ tab Lịch sử):
- Header: ← Quay lại  |  ↔ Đổi/Trả từ AHD000123
- Section A: HĐ gốc — chọn các món khách trả lại + chỉnh SL
- Section B: Khách mua mới — search + thêm (giống màn bán hàng)
- Section C: Tóm tắt + chênh lệch + PTTT (chỉ khi khách bù)
- Footer: nút XÁC NHẬN

State:
- st.session_state["doi_tra_active"] = ma_hd_goc | None
- st.session_state["doi_tra_tra_map"]  = {ma_hang_idx: sl_tra}   # idx vì có thể trùng mã
- st.session_state["doi_tra_moi_cart"] = [{ma_hang, ten_hang, so_luong, don_gia, ton, loai_sp}]
"""

import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from utils.auth import get_active_branch, get_user, is_admin
from utils.db import (
    load_hoa_don_pos_by_ma,
    load_hang_hoa_pos,
    get_sl_da_tra_map,
    tao_phieu_doi_tra_pos_rpc,
    load_phieu_doi_tra_pos_history,
)
from utils.helpers import fmt_vnd

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


# ════════════════════════════════════════════════════════════════
# STATE HELPERS
# ════════════════════════════════════════════════════════════════

def open_doi_tra(ma_hd_goc: str):
    """Mở màn Đổi/Trả cho 1 HĐ gốc — gọi từ tab Lịch sử."""
    st.session_state["doi_tra_active"]   = ma_hd_goc
    st.session_state["doi_tra_tra_map"]  = {}
    st.session_state["doi_tra_moi_cart"] = []


def is_doi_tra_active() -> bool:
    return bool(st.session_state.get("doi_tra_active"))


def _close_doi_tra():
    for k in ("doi_tra_active", "doi_tra_tra_map", "doi_tra_moi_cart",
              "doi_tra_search_reset_cnt"):
        st.session_state.pop(k, None)


def _get_tra_map() -> dict[int, int]:
    return st.session_state.setdefault("doi_tra_tra_map", {})


def _get_moi_cart() -> list[dict]:
    return st.session_state.setdefault("doi_tra_moi_cart", [])


# ════════════════════════════════════════════════════════════════
# SEARCH (re-use logic màn bán hàng — viết lại gọn)
# ════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    import re
    return re.sub(r"[\s\-_./]", "", str(text or "")).lower()


def _search_hang_hoa(keyword: str, hh_list: list[dict],
                     max_results: int = 3) -> list[dict]:
    if not keyword.strip():
        return []
    kw = _normalize(keyword)
    matches = []
    for hh in hh_list:
        ma_n   = _normalize(hh["ma_hang"])
        vach_n = _normalize(hh.get("ma_vach", ""))
        ten_n  = _normalize(hh["ten_hang"])
        score = 0
        if ma_n.startswith(kw):
            score = 100
        elif vach_n and vach_n.startswith(kw):
            score = 95
        elif ten_n.startswith(kw):
            score = 80
        elif kw in ma_n:
            score = 60
        elif kw in vach_n:
            score = 50
        elif kw in ten_n:
            score = 40
        if score > 0:
            if hh["ton"] > 0:
                score += 1000
            matches.append((score, hh))
    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches[:max_results]]


# ════════════════════════════════════════════════════════════════
# SECTION A — HĐ gốc + chọn món trả
# ════════════════════════════════════════════════════════════════

def _render_section_hd_goc(hd_goc: dict, sl_da_tra: dict[str, int]):
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:6px 0 6px;'>📦 KHÁCH TRẢ LẠI (chọn từ HĐ gốc)</div>",
        unsafe_allow_html=True
    )

    items = hd_goc.get("items", [])
    if not items:
        st.caption("HĐ gốc không có chi tiết.")
        return

    tra_map = _get_tra_map()

    for idx, ct in enumerate(items):
        ma_hang  = ct.get("ma_hang", "")
        ten_hang = ct.get("ten_hang", "")
        sl_goc   = int(ct.get("so_luong", 0) or 0)
        don_gia  = int(ct.get("don_gia", 0) or 0)

        sl_con_lai = max(0, sl_goc - sl_da_tra.get(ma_hang, 0))

        if sl_con_lai == 0:
            st.markdown(
                f"<div style='background:#f4f4f4;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 10px;margin:6px 0;opacity:0.55;'>"
                f"<div style='font-weight:500;color:#888;font-size:0.88rem;'>"
                f"{ten_hang}</div>"
                f"<div style='font-size:0.78rem;color:#aaa;'>"
                f"Đã trả hết ({sl_goc}/{sl_goc})</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            continue

        st.markdown(
            f"<div style='font-size:0.88rem;color:#1a1a2e;font-weight:500;"
            f"margin:8px 0 2px;'>{ten_hang}</div>"
            f"<div style='font-size:0.78rem;color:#888;margin-bottom:4px;'>"
            f"{ma_hang} · Đơn giá {fmt_vnd(don_gia)} · Còn trả: {sl_con_lai}/{sl_goc}"
            f"</div>",
            unsafe_allow_html=True
        )

        with st.container(key=f"numkb-dt-tra-{idx}"):
            sl_tra = st.number_input(
                f"SL trả (món {idx+1})",
                min_value=0, max_value=sl_con_lai,
                value=int(tra_map.get(idx, 0)),
                step=1,
                key=f"dt_tra_sl_{idx}",
                label_visibility="collapsed",
            )
        tra_map[idx] = int(sl_tra)


def _calc_tong_tra(hd_goc: dict) -> int:
    tra_map = _get_tra_map()
    total = 0
    for idx, ct in enumerate(hd_goc.get("items", [])):
        sl = int(tra_map.get(idx, 0) or 0)
        total += sl * int(ct.get("don_gia", 0) or 0)
    return total


def _build_items_tra_payload(hd_goc: dict) -> list[dict]:
    tra_map = _get_tra_map()
    out = []
    for idx, ct in enumerate(hd_goc.get("items", [])):
        sl = int(tra_map.get(idx, 0) or 0)
        if sl <= 0:
            continue
        out.append({
            "ma_hang":  ct.get("ma_hang", ""),
            "ten_hang": ct.get("ten_hang", ""),
            "so_luong": sl,
            "don_gia":  int(ct.get("don_gia", 0) or 0),
        })
    # Gộp các dòng cùng ma_hang
    merged: dict[str, dict] = {}
    for it in out:
        m = it["ma_hang"]
        if m in merged:
            merged[m]["so_luong"] += it["so_luong"]
        else:
            merged[m] = it
    return list(merged.values())


# ════════════════════════════════════════════════════════════════
# SECTION B — Khách mua mới
# ════════════════════════════════════════════════════════════════

def _moi_add(item: dict):
    cart = _get_moi_cart()
    for line in cart:
        if line["ma_hang"] == item["ma_hang"]:
            line["so_luong"] += 1
            return
    cart.append({
        "ma_hang":  item["ma_hang"],
        "ten_hang": item["ten_hang"],
        "so_luong": 1,
        "don_gia":  int(item["gia_ban"]),
        "ton":      int(item["ton"]),
        "loai_sp":  item.get("loai_sp", "Hàng hóa"),
    })


def _moi_remove(ma_hang: str):
    cart = [x for x in _get_moi_cart() if x["ma_hang"] != ma_hang]
    st.session_state["doi_tra_moi_cart"] = cart


def _render_section_moi(chi_nhanh: str):
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:14px 0 6px;'>🛒 KHÁCH MUA MỚI (tùy chọn)</div>",
        unsafe_allow_html=True
    )

    hh_list = load_hang_hoa_pos(chi_nhanh)
    cart = _get_moi_cart()

    with st.expander("🔍 Tìm hàng hóa", expanded=(len(cart) == 0)):
        rk = st.session_state.get("doi_tra_search_reset_cnt", 0)
        keyword = st.text_input(
            "Search input",
            placeholder="Gõ mã hoặc tên hàng...",
            key=f"dt_search_kw_{rk}",
            label_visibility="collapsed",
        )
        if keyword.strip():
            results = _search_hang_hoa(keyword, hh_list, max_results=3)
            if not results:
                st.caption("Không tìm thấy sản phẩm.")
            else:
                for hh in results:
                    _render_search_card_moi(hh)

    if not cart:
        st.caption("Chưa có sản phẩm mua mới.")
        return

    for line in cart:
        col_info, col_sl, col_x = st.columns([5, 2, 1])
        with col_info:
            st.markdown(
                f"<div style='padding:6px 0;'>"
                f"<div style='font-size:0.88rem;color:#1a1a2e;font-weight:500;'>"
                f"{line['ten_hang']}</div>"
                f"<div style='font-size:0.78rem;color:#666;'>"
                f"Đơn giá {fmt_vnd(line['don_gia'])}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_sl:
            is_dv = line.get("loai_sp") == "Dịch vụ"
            sl_max = 99999 if is_dv else max(1, int(line["ton"]))
            with st.container(key=f"numkb-dt-moi-sl-{line['ma_hang']}"):
                new_sl = st.number_input(
                    "SL", min_value=1, max_value=sl_max,
                    value=int(line["so_luong"]), step=1,
                    key=f"dt_moi_sl_{line['ma_hang']}",
                    label_visibility="collapsed",
                )
            line["so_luong"] = int(new_sl)
        with col_x:
            if st.button("✕", key=f"dt_moi_del_{line['ma_hang']}",
                         use_container_width=True):
                _moi_remove(line["ma_hang"])
                st.rerun()


def _render_search_card_moi(hh: dict):
    is_dich_vu = hh.get("loai_sp") == "Dịch vụ"
    is_oos = (not is_dich_vu) and (hh["ton"] == 0)

    if is_oos:
        st.markdown(
            f"<div style='background:#f4f4f4;border:1px solid #e0e0e0;"
            f"border-radius:10px;padding:10px 12px;margin:6px 0;opacity:0.6;'>"
            f"<div style='font-weight:600;color:#888;'>{hh['ten_hang']}</div>"
            f"<div style='font-family:monospace;font-size:0.78rem;color:#aaa;'>"
            f"{hh['ma_hang']} · <b>Hết hàng</b></div>"
            f"</div>",
            unsafe_allow_html=True
        )
        return

    if is_dich_vu:
        info = f"{hh['ma_hang']} · 🛠 Dịch vụ · {fmt_vnd(hh['gia_ban'])}"
    else:
        info = f"{hh['ma_hang']} · Tồn: {hh['ton']} · {fmt_vnd(hh['gia_ban'])}"

    if st.button(
        f"{hh['ten_hang']}\n{info}",
        key=f"dt_search_add_{hh['ma_hang']}",
        use_container_width=True,
    ):
        _moi_add(hh)
        st.session_state["doi_tra_search_reset_cnt"] = \
            st.session_state.get("doi_tra_search_reset_cnt", 0) + 1
        st.rerun()


def _calc_tong_moi() -> int:
    return sum(int(l["so_luong"]) * int(l["don_gia"]) for l in _get_moi_cart())


def _build_items_moi_payload() -> list[dict]:
    out = []
    for l in _get_moi_cart():
        sl = int(l.get("so_luong") or 0)
        if sl <= 0:
            continue
        out.append({
            "ma_hang":  l["ma_hang"],
            "ten_hang": l["ten_hang"],
            "so_luong": sl,
            "don_gia":  int(l["don_gia"]),
        })
    return out


# ════════════════════════════════════════════════════════════════
# SECTION C — Tóm tắt + Chênh lệch + PTTT
# ════════════════════════════════════════════════════════════════

def _render_section_tom_tat(tong_tra: int, tong_moi: int) -> int:
    """Render tóm tắt + return chenh_lech."""
    chenh_lech = tong_moi - tong_tra

    st.markdown("<hr style='margin:14px 0 8px;'>", unsafe_allow_html=True)

    rows_html = (
        f"<div style='display:flex;justify-content:space-between;"
        f"padding:3px 0;font-size:0.88rem;'>"
        f"<span style='color:#777;'>Tổng tiền hàng trả lại:</span>"
        f"<span style='color:#1a1a2e;font-weight:600;'>"
        f"− {fmt_vnd(tong_tra)}</span></div>"
        f"<div style='display:flex;justify-content:space-between;"
        f"padding:3px 0;font-size:0.88rem;'>"
        f"<span style='color:#777;'>Tổng tiền hàng mua mới:</span>"
        f"<span style='color:#1a1a2e;font-weight:600;'>"
        f"+ {fmt_vnd(tong_moi)}</span></div>"
    )

    if chenh_lech > 0:
        cl_label = "Khách cần bù thêm:"
        cl_color = "#e63946"
        cl_text  = f"+ {fmt_vnd(chenh_lech)}"
    elif chenh_lech < 0:
        cl_label = "Cửa hàng hoàn lại khách:"
        cl_color = "#1a7f37"
        cl_text  = f"− {fmt_vnd(-chenh_lech)}"
    else:
        cl_label = "Đổi ngang giá:"
        cl_color = "#555"
        cl_text  = "0đ"

    rows_html += (
        f"<hr style='border:none;border-top:1px dashed #ddd;margin:6px 0;'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"padding:4px 0;font-size:0.95rem;'>"
        f"<span style='color:#555;font-weight:600;'>{cl_label}</span>"
        f"<span style='color:{cl_color};font-weight:700;'>{cl_text}</span>"
        f"</div>"
    )

    st.markdown(
        f"<div style='background:#fff;border:1px solid #e8e8e8;"
        f"border-radius:10px;padding:10px 12px;'>{rows_html}</div>",
        unsafe_allow_html=True
    )

    return chenh_lech


def _render_section_pttt(chenh_lech: int) -> dict:
    """
    Trả về dict {tien_mat, chuyen_khoan, the}.
    - chenh_lech > 0: khách bù — cho chọn PTTT
    - chenh_lech < 0: shop hoàn — chỉ tiền mặt, tự gán = chenh_lech
    - chenh_lech = 0: tất cả 0
    """
    if chenh_lech == 0:
        return {"tien_mat": 0, "chuyen_khoan": 0, "the": 0}

    if chenh_lech < 0:
        st.markdown(
            f"<div style='background:#e8f7ee;border:1px solid #a4d8b4;"
            f"border-radius:10px;padding:10px 12px;margin-top:10px;'>"
            f"<div style='font-size:0.85rem;color:#1a7f37;'>"
            f"💵 Cửa hàng hoàn lại khách <b>{fmt_vnd(-chenh_lech)}</b> tiền mặt"
            f"</div></div>",
            unsafe_allow_html=True
        )
        return {"tien_mat": int(chenh_lech), "chuyen_khoan": 0, "the": 0}

    # chenh_lech > 0 — khách bù
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:600;color:#1a1a2e;"
        "margin:14px 0 6px;'>💳 KHÁCH BÙ — PHƯƠNG THỨC</div>",
        unsafe_allow_html=True
    )

    chia_nhieu = st.checkbox(
        "Chia nhiều phương thức",
        key="dt_pttt_chia",
        value=False,
    )

    if not chia_nhieu:
        pttt = st.radio(
            "Chọn PTTT",
            ["💵 Tiền mặt", "🏦 Chuyển khoản", "💳 Thẻ"],
            horizontal=True,
            key="dt_pttt_radio",
            label_visibility="collapsed",
        )
        return {
            "tien_mat":     chenh_lech if pttt == "💵 Tiền mặt" else 0,
            "chuyen_khoan": chenh_lech if pttt == "🏦 Chuyển khoản" else 0,
            "the":          chenh_lech if pttt == "💳 Thẻ" else 0,
        }

    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "💵 Tiền mặt:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-dt-tm"):
        tm = st.number_input("Tiền mặt", min_value=0, value=0, step=10000,
                             key="dt_tm", label_visibility="collapsed")
    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "🏦 Chuyển khoản:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-dt-ck"):
        ck = st.number_input("CK", min_value=0, value=0, step=10000,
                             key="dt_ck", label_visibility="collapsed")
    st.markdown("<div style='font-size:0.82rem;color:#666;margin:4px 0;'>"
                "💳 Thẻ:</div>", unsafe_allow_html=True)
    with st.container(key="numkb-dt-the"):
        the = st.number_input("Thẻ", min_value=0, value=0, step=10000,
                              key="dt_the", label_visibility="collapsed")

    tong = int(tm) + int(ck) + int(the)
    if tong < chenh_lech:
        st.warning(f"Còn thiếu: {fmt_vnd(chenh_lech - tong)}")
    elif tong > chenh_lech:
        st.info(f"Thừa: {fmt_vnd(tong - chenh_lech)} (sẽ trả lại tiền mặt)")
    else:
        st.success(f"✓ Đủ: {fmt_vnd(tong)}")

    return {"tien_mat": int(tm), "chuyen_khoan": int(ck), "the": int(the)}


# ════════════════════════════════════════════════════════════════
# CONFIRM
# ════════════════════════════════════════════════════════════════

def _xu_ly_xac_nhan(hd_goc: dict, items_tra: list[dict],
                    items_moi: list[dict], pttt: dict, chenh_lech: int):
    user = get_user() or {}

    payload = {
        "ma_hd_goc":    hd_goc["ma_hd"],
        "is_admin":     bool(is_admin()),
        "items_tra":    items_tra,
        "items_moi":    items_moi,
        "tien_mat":     int(pttt.get("tien_mat", 0)),
        "chuyen_khoan": int(pttt.get("chuyen_khoan", 0)),
        "the":          int(pttt.get("the", 0)),
        "nguoi_tao":    user.get("ho_ten", ""),
        "nguoi_tao_id": str(user.get("id", "")),
    }

    with st.spinner("Đang tạo phiếu đổi/trả..."):
        result = tao_phieu_doi_tra_pos_rpc(payload)

    if not result.get("ok"):
        st.error(f"Lỗi: {result.get('error', 'Không xác định')}")
        return

    # Invalidate cache
    load_hang_hoa_pos.clear()
    load_phieu_doi_tra_pos_history.clear()

    ma_pdt = result.get("ma_pdt", "")
    st.toast(f"Đã tạo {ma_pdt}", icon="✅")

    _close_doi_tra()
    st.rerun()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT — render màn Đổi/Trả
# ════════════════════════════════════════════════════════════════

def render_man_doi_tra():
    """Render màn Đổi/Trả full-screen."""
    ma_hd_goc = st.session_state.get("doi_tra_active")
    if not ma_hd_goc:
        return

    chi_nhanh = get_active_branch()

    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("←", key="dt_back", use_container_width=True,
                     help="Quay lại Lịch sử"):
            _close_doi_tra()
            st.rerun()
    with col_title:
        st.markdown(
            f"<div style='font-size:1.05rem;font-weight:700;color:#1a1a2e;"
            f"padding-top:10px;'>↔ Đổi/Trả từ "
            f"<span style='font-family:monospace;'>{ma_hd_goc}</span></div>",
            unsafe_allow_html=True
        )

    hd_goc = load_hoa_don_pos_by_ma(ma_hd_goc)
    if not hd_goc:
        st.error("Không tìm thấy hóa đơn gốc.")
        if st.button("← Quay lại", key="dt_back_err"):
            _close_doi_tra()
            st.rerun()
        return

    if hd_goc.get("trang_thai") == "Đã hủy":
        st.error("Hóa đơn gốc đã bị hủy — không thể đổi/trả.")
        if st.button("← Quay lại", key="dt_back_cancelled"):
            _close_doi_tra()
            st.rerun()
        return

    age_days = _hd_age_days(hd_goc.get("created_at", ""))
    over_7_days = age_days > 7
    if over_7_days and not is_admin():
        st.error(
            f"Hóa đơn đã {age_days} ngày — chỉ admin mới được tạo phiếu đổi/trả."
        )
        if st.button("← Quay lại", key="dt_back_overage"):
            _close_doi_tra()
            st.rerun()
        return

    sdt_text = (" · " + hd_goc["sdt_khach"]) if hd_goc.get("sdt_khach") else ""
    st.markdown(
        f"<div style='background:#f7f7fa;border:1px solid #e8e8ee;"
        f"border-radius:8px;padding:8px 12px;margin-top:10px;font-size:0.85rem;'>"
        f"<b>Khách:</b> {hd_goc.get('ten_khach') or 'Khách lẻ'}{sdt_text}<br>"
        f"<b>Ngày HĐ:</b> {_fmt_dt(hd_goc.get('created_at',''))} "
        f"({age_days} ngày trước)"
        f"</div>",
        unsafe_allow_html=True
    )
    if over_7_days:
        st.warning(f"⚠ Quá 7 ngày — admin override.")

    sl_da_tra = get_sl_da_tra_map(ma_hd_goc)

    _render_section_hd_goc(hd_goc, sl_da_tra)
    _render_section_moi(chi_nhanh)

    tong_tra = _calc_tong_tra(hd_goc)
    tong_moi = _calc_tong_moi()
    chenh_lech = _render_section_tom_tat(tong_tra, tong_moi)
    pttt = _render_section_pttt(chenh_lech)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    items_tra = _build_items_tra_payload(hd_goc)
    items_moi = _build_items_moi_payload()

    errors = []
    if not items_tra:
        errors.append("Phải chọn ít nhất 1 món trả lại")
    if chenh_lech > 0:
        tong_pttt = pttt["tien_mat"] + pttt["chuyen_khoan"] + pttt["the"]
        if tong_pttt < chenh_lech:
            errors.append(f"Cần thêm {fmt_vnd(chenh_lech - tong_pttt)}")

    can_submit = len(errors) == 0

    if st.button(
        "✓ XÁC NHẬN ĐỔI/TRẢ",
        type="primary",
        use_container_width=True,
        disabled=not can_submit,
        key="dt_submit",
        help=" · ".join(errors) if errors else None,
    ):
        _xu_ly_xac_nhan(hd_goc, items_tra, items_moi, pttt, chenh_lech)


# ════════════════════════════════════════════════════════════════
# Helpers ngày giờ
# ════════════════════════════════════════════════════════════════

def _hd_age_days(iso_str: str) -> int:
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_vn = dt.astimezone(_TZ_VN)
        now_vn = datetime.now(_TZ_VN)
        delta = now_vn - dt_vn
        return max(0, delta.days)
    except Exception:
        return 0


def _fmt_dt(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_TZ_VN).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


# ════════════════════════════════════════════════════════════════
# MODAL — Chi tiết phiếu đổi/trả (gọi từ tab Lịch sử)
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết phiếu đổi/trả")
def dialog_chi_tiet_pdt(pdt: dict):
    is_cancelled = pdt.get("trang_thai") == "Đã hủy"

    badge = ""
    if is_cancelled:
        badge = ("<span style='background:#ffe5e5;color:#c1121f;"
                 "padding:2px 8px;border-radius:6px;font-size:0.78rem;"
                 "font-weight:600;margin-left:6px;'>Đã hủy</span>")

    st.markdown(
        f"<div style='font-family:monospace;font-size:1.1rem;font-weight:700;"
        f"color:#1a1a2e;'>{pdt['ma_pdt']}{badge}</div>"
        f"<div style='font-size:0.82rem;color:#888;margin-top:2px;'>"
        f"{_fmt_dt(pdt.get('created_at',''))} · {pdt.get('loai_phieu','')}"
        f"</div>"
        f"<div style='font-size:0.82rem;color:#666;margin-top:2px;'>"
        f"HĐ gốc: <b>{pdt.get('ma_hd_goc','')}</b></div>",
        unsafe_allow_html=True
    )

    if is_cancelled and pdt.get("cancelled_at"):
        cb = pdt.get("cancelled_by") or ""
        by = f" bởi {cb}" if cb else ""
        st.markdown(
            f"<div style='font-size:0.78rem;color:#c1121f;margin-top:2px;'>"
            f"Hủy lúc: {_fmt_dt(pdt['cancelled_at'])}{by}</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin:10px 0 8px;'>", unsafe_allow_html=True)

    items = pdt.get("items", [])
    items_tra = [it for it in items if it.get("kieu") == "tra"]
    items_moi = [it for it in items if it.get("kieu") == "moi"]

    if items_tra:
        st.markdown(
            "<div style='font-size:0.85rem;font-weight:600;color:#c1121f;"
            "margin:8px 0 4px;'>📦 Khách trả lại:</div>",
            unsafe_allow_html=True
        )
        _render_pdt_items_html(items_tra)

    if items_moi:
        st.markdown(
            "<div style='font-size:0.85rem;font-weight:600;color:#1a7f37;"
            "margin:10px 0 4px;'>🛒 Khách mua mới:</div>",
            unsafe_allow_html=True
        )
        _render_pdt_items_html(items_moi)

    rows = [
        ("Tổng tiền hàng trả lại", "− " + fmt_vnd(pdt.get("tien_hang_tra", 0))),
        ("Tổng tiền hàng mua mới", "+ " + fmt_vnd(pdt.get("tien_hang_moi", 0))),
    ]
    cl = int(pdt.get("chenh_lech", 0) or 0)
    if cl > 0:
        rows.append(("Khách bù thêm", fmt_vnd(cl)))
    elif cl < 0:
        rows.append(("Cửa hàng hoàn lại", fmt_vnd(-cl)))
    else:
        rows.append(("Đổi ngang giá", "0đ"))

    if pdt.get("tien_mat", 0):
        rows.append(("💵 Tiền mặt", fmt_vnd(pdt["tien_mat"])))
    if pdt.get("chuyen_khoan", 0):
        rows.append(("🏦 Chuyển khoản", fmt_vnd(pdt["chuyen_khoan"])))
    if pdt.get("the", 0):
        rows.append(("💳 Thẻ", fmt_vnd(pdt["the"])))

    summary = "<div style='background:#fff;border:1px solid #e8e8e8;" \
              "border-radius:8px;padding:8px 12px;margin-top:10px;'>"
    for lbl, val in rows:
        summary += (
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:3px 0;font-size:0.86rem;'>"
            f"<span style='color:#777;'>{lbl}:</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{val}</span>"
            f"</div>"
        )
    summary += "</div>"
    st.markdown(summary, unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size:0.78rem;color:#888;margin-top:8px;'>"
        f"NV tạo: {pdt.get('nguoi_tao','—')}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    if is_admin() and not is_cancelled:
        if st.button("🚫 Hủy phiếu đổi/trả", use_container_width=True,
                     key=f"pdt_huy_{pdt['ma_pdt']}"):
            st.session_state["pdt_confirm_huy"] = pdt
            st.rerun()


def _render_pdt_items_html(items: list[dict]):
    html = "<div style='background:#fafafa;border:1px solid #eee;" \
           "border-radius:8px;padding:8px 10px;'>"
    for ct in items:
        sl = ct.get("so_luong", 0)
        dg = ct.get("don_gia", 0)
        tt = ct.get("thanh_tien", 0)
        html += (
            f"<div style='padding:4px 0;border-bottom:1px dashed #e8e8e8;'>"
            f"<div style='font-size:0.85rem;color:#1a1a2e;font-weight:500;'>"
            f"{ct.get('ten_hang','')}</div>"
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:0.78rem;color:#666;margin-top:2px;'>"
            f"<span>SL {sl} × {fmt_vnd(dg)}</span>"
            f"<span style='color:#1a1a2e;font-weight:600;'>{fmt_vnd(tt)}</span>"
            f"</div></div>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


@st.dialog("Xác nhận hủy phiếu?")
def dialog_confirm_huy_pdt(pdt: dict):
    from utils.db import huy_phieu_doi_tra_pos_rpc

    st.markdown(
        f"<div style='font-size:1rem;color:#1a1a2e;margin-bottom:6px;'>"
        f"Hủy phiếu <b>{pdt['ma_pdt']}</b>?</div>"
        f"<div style='font-size:0.88rem;color:#666;margin-bottom:14px;'>"
        f"Mọi ảnh hưởng tồn kho sẽ được hoàn tác. Hành động không thể đảo ngược."
        f"</div>",
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✓ Xác nhận hủy", type="primary",
                     use_container_width=True,
                     key=f"pdt_huy_confirm_{pdt['ma_pdt']}"):
            user = get_user() or {}
            with st.spinner("Đang hủy..."):
                result = huy_phieu_doi_tra_pos_rpc(
                    pdt["ma_pdt"], user.get("ho_ten", "")
                )
            if result.get("ok"):
                load_hang_hoa_pos.clear()
                load_phieu_doi_tra_pos_history.clear()
                st.session_state.pop("pdt_confirm_huy", None)
                st.toast(f"Đã hủy {pdt['ma_pdt']}", icon="✅")
                st.rerun()
            else:
                st.error(f"Lỗi: {result.get('error', 'Không xác định')}")
    with col2:
        if st.button("Quay lại", use_container_width=True,
                     key=f"pdt_huy_cancel_{pdt['ma_pdt']}"):
            st.session_state.pop("pdt_confirm_huy", None)
            st.rerun()
