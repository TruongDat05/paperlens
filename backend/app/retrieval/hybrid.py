"""Điều phối các cấu hình truy xuất B1 đến B4.

Nhận câu hỏi, chỉ mục của một paper và cấu hình. B1 dùng BM25, B2 dùng
E5, B3 hợp nhất hai thứ hạng bằng RRF và B4 rerank ứng viên RRF bằng
BGE.

Giữ thứ hạng trước rerank để đo Candidate Recall@20. Giữ hit tốt nhất
cho mỗi parent_passage_id rồi lấy top-k đoạn gốc. Trả EvidenceResult
cùng retrieval_mode và lý do fallback BM25 khi cấu hình sản phẩm cho
phép.
"""
