import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo

from utils.auth import get_user, get_active_branch
from utils.helpers import now_vn
from utils.attendance import (
    load_work_schedules,
    load_attendance_sessions,
    record_check_in,
    record_check_out,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def _fmt(dt):
    try:
        return dt.astimezone(TZ).strftime("%H:%M")
    except Exception:
        return "--:--"

# Compatibility for Streamlit dialog
if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog


@dialog_decorator("⏱️ Chấm công", width="medium")
def show_attendance_dialog():
    user = get_user()
    branch = get_active_branch()

    if not user or not branch:
        st.error("Không xác định được người dùng hoặc chi nhánh")
        return

    emp_id = int(user.get("id") or 0)
    today = now_vn().date()

    st.markdown(f"**Nhân viên:** {user.get('ho_ten') or user.get('username')}")
    st.markdown(f"**Chi nhánh:** {branch}")
    st.markdown(f"**Ngày:** {today.strftime('%d/%m/%Y')}")

    st.markdown("---")

    schedules = load_work_schedules(work_date=today, employee_id=emp_id, branch_name=branch)
    sessions = load_attendance_sessions(work_date=today, employee_id=emp_id, branch_name=branch)

    if schedules.empty:
        st.warning("Hôm nay không có lịch làm")
        if st.button("Đóng"):
            st.rerun()
        return

    for _, row in schedules.iterrows():
        shift_no = int(row.get("shift_no") or 0)
        start = row.get("scheduled_start_at")
        end = row.get("scheduled_end_at")
        schedule_id = int(row.get("id") or 0)

        st.markdown(f"### Ca {shift_no} ({_fmt(start)} - {_fmt(end)})")

        session = None
        if not sessions.empty:
            match = sessions[sessions["shift_no"] == shift_no]
            if not match.empty:
                session = match.iloc[0]

        col1, col2 = st.columns(2)

        if session is None or pd.isna(session.get("check_in_at")):
            if col1.button(f"Chấm vào ca {shift_no}", key=f"in_{shift_no}"):
                res = record_check_in(emp_id, branch, schedule_id=schedule_id)
                if res.get("ok"):
                    st.success("Chấm vào thành công")
                    st.rerun()
                else:
                    st.error(res.get("error"))
        elif pd.isna(session.get("check_out_at")):
            col1.success("Đã chấm vào")
            if col2.button(f"Chấm ra ca {shift_no}", key=f"out_{shift_no}"):
                res = record_check_out(emp_id, branch, schedule_id=schedule_id)
                if res.get("ok"):
                    st.success("Chấm ra thành công")
                    st.rerun()
                else:
                    st.error(res.get("error"))
        else:
            col1.success("Đã hoàn thành ca")

        st.markdown("---")

    if st.button("Đóng"):
        st.rerun()
