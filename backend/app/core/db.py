"""Quản lý kết nối, schema và giao dịch SQLite.

Đặt cơ sở dữ liệu trên persistent volume. Khai báo khóa ngoại, ràng buộc
duy nhất theo owner và giao dịch cho các lần cập nhật trạng thái, chỉ
mục và ngân sách.

Giữ giao dịch quanh các thao tác đọc và ghi ngắn. Các lời gọi provider
diễn ra ngoài giao dịch, với kết quả được commit khi tài nguyên vẫn hợp
lệ.
"""
