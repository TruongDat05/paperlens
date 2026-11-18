"""Chia đoạn văn dài và giữ liên kết với đoạn nguồn.

Nhận các đoạn văn arXiv hoặc QASPER cùng tokenizer E5 đã pin. Áp ngân
sách khoảng 400 token tính cả tiền tố và chừa chỗ cho special tokens.

Tạo subchunk ID và text offsets xác định, đồng thời giữ
parent_passage_id để quy kết quả và nhãn đánh giá về cùng đoạn gốc. Khi
replay, dùng tài nguyên tokenizer đã có trên máy.
"""
