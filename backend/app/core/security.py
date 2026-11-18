"""Xác thực phiên và xác lập phạm vi dữ liệu của owner.

Đối chiếu token beta với hash lưu trên server hoặc xác minh access token
của dịch vụ đăng nhập khi tích hợp. Cấp owner từ danh tính đã xác thực.

Dùng owner do server cấp để kiểm tra quyền truy cập paper, cache và run.
Chính sách origin của extension thuộc cấu hình HTTP.
"""
