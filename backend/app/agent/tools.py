"""Thực thi các tool chỉ đọc trên paper đang được hỏi.

Cung cấp get_paper_outline, search_evidence và read_section. Nhận
paper/version đã được backend gắn với run, kiểm tra tên tool, arguments,
section ID, offset và giới hạn số đoạn.

Search dùng retrieval engine chung. Observation trả dữ liệu theo schema,
kèm passage IDs và thông tin nguồn cho các đoạn agent đã đọc.
"""
