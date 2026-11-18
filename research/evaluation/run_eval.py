"""Cung cấp CLI đánh giá retrieval và agent trên QASPER.

Chạy từ repo root qua python -m research.evaluation.run_eval với cấu
hình, split, pipeline B1–B4 hoặc A1/A2 và chế độ live hoặc replay được
chọn tường minh.

Nạp paper vào bộ nhớ rồi gọi trực tiếp chunking, retrieval và agent dùng
chung. Cấp adapter theo chế độ chạy. Với đối chứng A1/A2 chính, khóa
Gemini primary_only.

Ghi manifest, kết quả từng query, lỗi, usage và metric tables kèm thông
tin để tái lập.
"""
