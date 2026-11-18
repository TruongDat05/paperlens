"""Đặc tả kiểm thử ingest, trạng thái và xóa paper.

Dùng SQLite cục bộ và adapter giả lập để kiểm tra quyền sở hữu, giới hạn
đầu vào, ingest lặp và hai mốc lexical_ready, semantic_ready.

Bao phủ batch embedding bị gián đoạn khi restart và yêu cầu xóa paper
khi tác vụ còn chạy.
"""
