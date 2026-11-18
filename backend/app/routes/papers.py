"""Cung cấp các endpoint quản lý paper của người dùng.

Đăng ký POST /api/v1/papers/ingest, GET /api/v1/papers/{paper_id}/status
và DELETE /api/v1/papers/{paper_id}. Lấy owner từ phiên đã xác thực. Trả
HTTP 202 cùng paper_id và index_status khi ingest còn chạy.

Chuyển ingest và status sang module nghiệp vụ tương ứng. Khi xóa, phối
hợp thu hồi paper, chỉ mục, run liên quan và chặn tác vụ cũ ghi lại dữ
liệu.
"""
