"""Tạo vector E5 và truy xuất theo độ tương đồng trong paper.

Gắn tiền tố "passage: " khi tạo vector đoạn văn và "query: " khi tạo
vector câu hỏi. Dùng chung quy tắc này cho sản phẩm và benchmark.

Kiểm tra số chiều và model snapshot của vector. Xếp hạng theo cosine
hoặc tích vô hướng trên vector đã chuẩn hóa, rồi trả các ứng viên của
paper đã nạp.
"""
