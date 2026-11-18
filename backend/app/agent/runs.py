"""Quản lý vòng đời và kết quả của agent run qua FastAPI.

Lưu run theo owner, paper/version và request_id. Retry cùng nội dung trả
run hiện có. Cùng request_id với nội dung khác trả lỗi xung đột.

Nạp paper và index trước khi chạy A1 hoặc A2. Ghi tiến trình cho polling
và truyền yêu cầu hủy cùng deadline vào pipeline. Chỉ công bố kết quả
nếu trạng thái hiện tại của run cho phép.

Khi khởi động lại, kết thúc run bị gián đoạn và giữ usage chưa đối soát.
Áp thời hạn lưu tối đa 24 giờ cho dữ liệu run theo cấu hình sản phẩm.
"""
