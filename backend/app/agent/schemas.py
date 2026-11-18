"""Định nghĩa hợp đồng dữ liệu của agent và agent endpoints.

Mô tả action, observation, answer block gồm text và evidence_ids, trạng
thái run và response HTTP. Dùng cấu trúc message và observation chung
cho cả hai alias.

Ghi nhận metadata từng attempt, finish reason, lỗi và lý do dừng để
controller, router và evaluator hiểu cùng một kết quả.
"""
