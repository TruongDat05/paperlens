"""Đặc tả kiểm thử protocol QASPER và replay.

Dùng fixtures cho nhiều reference sets, duplicate parents, gold thiếu
hoặc chỉ có bảng/hình và abstention. Kiểm tra mẫu số của từng metric.

Xác minh replay từ artifact đúng hash, báo lỗi khi thiếu record và giữ
cấu hình primary_only cho đối chứng A1/A2 chính.
"""
