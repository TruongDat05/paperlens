"""Đặc tả kiểm thử tính đúng của các cấu hình B1 đến B4.

Dùng câu hỏi, passages, vector và score xác định để kiểm tra thứ hạng
RRF, rerank, định vị nguồn và gộp subchunks theo đoạn gốc.

Kiểm tra top-k theo cấu hình, BM25 fallback khi provider lỗi và mode
được báo trong EvidenceResult.
"""
