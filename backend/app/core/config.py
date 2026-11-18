"""Nạp và kiểm tra cấu hình backend và benchmark.

Tạo settings khi khởi động FastAPI hoặc CLI. Đọc cấu hình sản phẩm từ
configs/product_mvp.yaml. Ở local, nạp thông tin kết nối từ .env ở thư mục
gốc theo các tên biến trong .env.example. Trên host, lấy các biến tương
ứng từ môi trường server. Kiểm tra credentials của provider được bật.

CLI nạp cấu hình benchmark được chọn và chế độ live hoặc replay. Truyền
settings của từng lần chạy vào pipeline và adapter để giữ cùng hành vi ở
các điểm gọi.
"""
