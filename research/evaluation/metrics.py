"""Tính chỉ số retrieval theo đoạn văn gốc.

Quy subchunk về parent trước khi tính Recall@5, Paragraph Evidence F1@5,
MRR@10 và Candidate Recall@20. Chỉ tính mẫu có text evidence hợp lệ
trong mẫu số retrieval.

Với Recall@5 và F1@5, lấy điểm cao nhất qua các reference sets hợp lệ
rồi macro-average theo query. Ước tính khoảng tin cậy chênh lệch bằng
paired bootstrap theo paper.
"""
