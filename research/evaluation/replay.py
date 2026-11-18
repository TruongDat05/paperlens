"""Nạp artifacts để chạy lại pipeline ở chế độ offline.

Kiểm tra manifest và checksum, nạp tokenizer E5 đã pin trên máy rồi cấp
adapter đọc embeddings, scores và phản hồi LLM đã lưu.

Khớp record theo input, cấu hình và snapshot của run. Báo lỗi khi record
thiếu hoặc sai phiên bản và gắn mode replay vào kết quả.
"""
