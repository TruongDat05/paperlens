"""Quản lý evidence registry và xác minh ID trích dẫn.

Đăng ký các đoạn đã cung cấp cho model trong run hiện tại. Kiểm tra từng
evidence_id theo registry, owner và paper/version trước khi công bố
answer block.

Lấy đoạn trích và locator từ passage nguồn đã đăng ký. Mức độ đoạn nguồn
hỗ trợ phát biểu được đánh giá trong research/evaluation/qa_audit.py.
"""
