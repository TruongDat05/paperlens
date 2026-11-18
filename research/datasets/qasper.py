"""Nạp QASPER v0.3 và ánh xạ evidence tới đoạn văn gốc.

Kiểm tra dataset revision, checksum và official splits từ manifest.
Chuyển mỗi paper sang Paper và Passage dùng chung với backend.

Giữ EvidenceLabel và từng reference set hợp lệ cho evaluator.
Ghi nhận evidence trùng, không ánh xạ được hoặc chỉ có bảng/hình.
Xác định các tập text evidence và abstention theo kế hoạch v4.1.
"""
