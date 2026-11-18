"""Kiểm tra trực tiếp hợp đồng embedding và reranking của FPT.

Nhận cấu hình server và mẫu nhỏ theo Model Catalog. Kiểm tra endpoint,
số vector, số chiều, ánh xạ score, batch và usage. Dùng fpt.py khi
adapter đã có.

Ghi mẫu đã bỏ thông tin xác thực vào docs/fpt_api_contract.md. Chỉ thực
hiện lời gọi live khi script được chạy tường minh.
"""
