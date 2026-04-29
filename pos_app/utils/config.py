"""Cấu hình chung cho POS app."""

APP_NAME = "DL Watch POS"

# 3 chi nhánh — phải khớp chính xác với app chính (utils/config.py)
ALL_BRANCHES = ["100 Lê Quý Đôn", "Coop Vũng Tàu", "GO BÀ RỊA"]

CN_SHORT = {
    "100 Lê Quý Đôn": "LQD",
    "Coop Vũng Tàu":  "Coop VT",
    "GO BÀ RỊA":      "GO Bà Rịa",
}

# Thông tin in trên hóa đơn K80
CN_INFO = {
    "100 Lê Quý Đôn": {
        "ten":    "DL Watch — 100 Lê Quý Đôn",
        "dia_chi":"100 Lê Quý Đôn, P. Phước Trung, TP. Bà Rịa",
        "sdt":    "0254 627 6786",
    },
    "Coop Vũng Tàu": {
        "ten":    "DL Watch — Coop Vũng Tàu",
        "dia_chi":"Siêu thị Coopmart, 36 Nguyễn Thái Học, P.7, TP. Vũng Tàu",
        "sdt":    "0702 014 334",
    },
    "GO BÀ RỊA": {
        "ten":    "DL Watch — GO Bà Rịa",
        "dia_chi":"Siêu thị GO, 2A Nguyễn Đình Chiểu, KP1, P. Phước Hiệp, TP. Bà Rịa",
        "sdt":    "0702 014 334",
    },
}

# Session POS — đến hết ngày 23:59:59 (giờ VN)
# Tính trong auth.py mỗi lần tạo session
