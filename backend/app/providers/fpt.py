"""Kết nối FPT AI Factory cho embedding E5 và reranking BGE.

Dùng endpoint và schema xác nhận theo docs/fpt_api_contract.md. Nhận văn
bản đã gắn tiền tố để embedding và cặp câu hỏi–đoạn văn để rerank.

Trả vector hoặc score theo đúng input, cùng usage và lỗi chuẩn hóa. Áp
giới hạn batch, timeout và retry theo hợp đồng provider.
"""
