import streamlit as st
import hmac
import hashlib
import time
from .db import (
    get_branches, 
    get_staff_by_branch, 
    verify_pin, 
    create_session_token, 
    verify_session_token,
    remove_session_token,
    log_action
)
from .config import PIN_SECRET_KEY, SESSION_EXPIRY_DAYS

def init_auth_state():
    """Khởi tạo các state cần thiết cho auth"""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "branch" not in st.session_state:
        st.session_state.branch = None
    if "session_token" not in st.session_state:
        st.session_state.session_token = None
    if "pre_selected_user_id" not in st.session_state:
        st.session_state.pre_selected_user_id = None

def check_auth():
    """Kiểm tra trạng thái đăng nhập từ session_state hoặc URL token"""
    init_auth_state()
    
    # 1. Kiểm tra URL params
    params = st.query_params
    
    # Lấy Branch từ URL
    if "b" in params and not st.session_state.branch:
        st.session_state.branch = params["b"]
        
    # Lấy User ID từ URL (Phương án B cho Auth)
    if "u" in params and not st.session_state.pre_selected_user_id:
        st.session_state.pre_selected_user_id = str(params["u"])
        
    # Lấy Token từ URL
    if "t" in params:
        token = params["t"]
        # Xác thực token với DB
        user_data = verify_session_token(token)
        if user_data:
            st.session_state.user = user_data
            st.session_state.session_token = token
            # Cập nhật lại URL params để dọn dẹp token (tuỳ chọn)
            # st.query_params.clear()
            return True
        else:
            # Token không hợp lệ hoặc hết hạn
            st.warning("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
            # Xoá token khỏi URL để tránh vòng lặp
            if "t" in st.query_params:
                del st.query_params["t"]
            
    # 2. Kiểm tra session_state hiện tại
    if st.session_state.user is not None:
        return True
        
    return False

def login_screen():
    """Hiển thị màn hình đăng nhập (Chọn chi nhánh -> Chọn nhân viên -> Nhập PIN)"""
    st.markdown("<h1 style='text-align: center; margin-bottom: 2rem;'>🛒 DL Watch POS</h1>", unsafe_allow_html=True)
    
    # Lấy danh sách chi nhánh
    branches = get_branches()
    if not branches:
        st.error("Không thể tải danh sách chi nhánh. Vui lòng kiểm tra kết nối DB.")
        return
        
    branch_names = [b['name'] for b in branches]
    
    # Card đăng nhập
    with st.container():
        st.markdown("""
        <style>
        .login-card {
            background-color: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            max-width: 400px;
            margin: 0 auto;
        }
        </style>
        <div class="login-card">
        """, unsafe_allow_html=True)
        
        # 1. Chọn chi nhánh
        default_branch_idx = 0
        if st.session_state.branch in branch_names:
            default_branch_idx = branch_names.index(st.session_state.branch)
            
        selected_branch = st.selectbox(
            "📍 Chọn chi nhánh", 
            options=branch_names,
            index=default_branch_idx
        )
        
        if selected_branch != st.session_state.branch:
            st.session_state.branch = selected_branch
            st.query_params["b"] = selected_branch
            st.rerun()
            
        # 2. Chọn nhân viên (khi đã có chi nhánh)
        if st.session_state.branch:
            staff_list = get_staff_by_branch(st.session_state.branch)
            
            if not staff_list:
                st.warning(f"Không có nhân viên nào đang hoạt động tại {st.session_state.branch}")
            else:
                # Xử lý pre-selected user từ URL
                staff_ids = [str(s['id']) for s in staff_list]
                default_staff_idx = 0
                
                if st.session_state.pre_selected_user_id in staff_ids:
                    default_staff_idx = staff_ids.index(st.session_state.pre_selected_user_id)
                
                # Format hiển thị: "Tên - Vai trò"
                staff_display = [f"{s['name']} ({s['role']})" for s in staff_list]
                
                selected_staff_str = st.selectbox(
                    "👤 Chọn nhân viên",
                    options=staff_display,
                    index=default_staff_idx
                )
                
                # Tìm lại dict nhân viên đã chọn
                selected_idx = staff_display.index(selected_staff_str)
                selected_staff = staff_list[selected_idx]
                
                # 3. Nhập mã PIN
                pin_input = st.text_input("🔑 Mã PIN", type="password", placeholder="Nhập mã PIN 4-6 số")
                
                if st.button("Đăng nhập", type="primary", use_container_width=True):
                    if not pin_input:
                        st.error("Vui lòng nhập mã PIN")
                    else:
                        with st.spinner("Đang xác thực..."):
                            is_valid = verify_pin(selected_staff['id'], pin_input)
                            
                            if is_valid:
                                # Tạo session token mới
                                token = create_session_token(selected_staff['id'], st.session_state.branch)
                                
                                if token:
                                    # Lưu vào state
                                    st.session_state.user = selected_staff
                                    st.session_state.session_token = token
                                    
                                    # Cập nhật URL với token (để F5 không mất)
                                    # Xóa u vì đã đăng nhập thành công
                                    st.query_params["t"] = token
                                    st.query_params["b"] = st.session_state.branch
                                    if "u" in st.query_params:
                                        del st.query_params["u"]
                                    
                                    # Ghi log đăng nhập
                                    log_action(
                                        user_id=selected_staff['id'],
                                        action_type="LOGIN",
                                        description="Đăng nhập hệ thống POS"
                                    )
                                    
                                    st.success("Đăng nhập thành công!")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("Lỗi hệ thống: Không thể tạo phiên đăng nhập")
                            else:
                                st.error("Mã PIN không chính xác!")
                                
        st.markdown("</div>", unsafe_allow_html=True)

def do_logout():
    """Xử lý đăng xuất"""
    # Giữ lại thông tin chi nhánh và user hiện tại
    current_b = st.session_state.get("branch", "")
    current_u = ""
    if st.session_state.get("user"):
        current_u = str(st.session_state.user.get("id", ""))
    
    # Xoá token trong DB nếu có
    if st.session_state.get("session_token"):
        remove_session_token(st.session_state.session_token)
        
    # Ghi log đăng xuất (nếu có user)
    if st.session_state.get("user"):
        log_action(
            user_id=st.session_state.user['id'],
            action_type="LOGOUT",
            description="Đăng xuất hệ thống POS"
        )
        
    # Xoá toàn bộ session state
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
    # Điều hướng lại trang login, giữ lại param b và u
    st.query_params.clear()
    if current_b:
        st.query_params["b"] = current_b
    if current_u:
        st.query_params["u"] = current_u
        
    st.rerun()
