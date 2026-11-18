"""Ghi số liệu vận hành cho các giai đoạn và lần gọi provider.

Ghi thời gian theo stage, cache hit, model, lỗi, token và chi phí. Phân
biệt usage do provider báo, usage ước tính và usage chưa xác định của
attempt bị timeout hoặc hủy.

Ghi model phục vụ và lý do fallback theo run. Giới hạn log sản phẩm ở
metadata cần vận hành.
"""
