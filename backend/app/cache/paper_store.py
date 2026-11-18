"""Lưu paper, đoạn văn, chỉ mục và tiến độ ingest theo owner.

Cấp dữ liệu nhất quán theo paper/version cho retrieval và agent. Gắn
cache vector với owner, content hash, phiên bản parser/chunking và cấu
hình embedding gồm model, snapshot và tiền tố.

Lưu thời điểm truy cập và dọn paper/index hết hạn theo cấu hình. Phối
hợp xóa dữ liệu dẫn xuất khi owner yêu cầu.
"""
