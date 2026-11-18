"""Thực thi hạn mức đầu vào, quota và ngân sách inference.

Kiểm tra kích thước paper, câu hỏi và history. Áp rate limit, giới hạn
đồng thời và quota theo chính sách sản phẩm.

Giữ chỗ ngân sách bằng giao dịch trước khi gọi FPT hoặc gateway, kể cả
search trong agent. Đối soát theo usage từng attempt và giữ trạng thái
unknown khi chưa xác định chi phí.
"""
