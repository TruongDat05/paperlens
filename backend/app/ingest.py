"""Tiếp nhận paper arXiv và điều phối lập chỉ mục.

Nhận các đoạn văn do người dùng đồng ý gửi. Kiểm tra nguồn arXiv, phiên
bản, cấu trúc và hạn mức đầu vào rồi tính content hash tại server. Cùng
owner, nội dung và cấu hình lập chỉ mục dùng lại cùng paper_id.

Chia đoạn qua chunking.py và dựng BM25 để đạt lexical_ready. Ghi tiến độ
embedding theo batch và chỉ đặt semantic_ready khi bộ vector tương ứng
đã được lưu đầy đủ.
"""
