"""Cung cấp POST /api/v1/retrieve cho Evidence Mode.

Xác thực owner và quyền trên paper_id. Kiểm tra câu hỏi, top-k và mức
sẵn sàng của chỉ mục trước khi chuyển paper và index đã nạp cho
retrieval engine.

Trả EvidenceResult với đoạn nguồn, thứ hạng, retrieval_mode và
fallback_reason nếu có. Trả trạng thái phù hợp khi paper còn đang lập
chỉ mục để side panel tiếp tục poll.
"""
