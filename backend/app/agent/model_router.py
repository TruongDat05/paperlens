"""Chọn model cho từng bước LLM và quản lý failover.

Ưu tiên ag/gemini-3.8-flash-medium. Ở chế độ primary_then_fallback,
chuyển tối đa một lần sang ag/claude-sonnet-4-6 khi lỗi đủ điều kiện,
hợp đồng fallback đã qua kiểm chứng và vẫn còn ngân sách.

Giữ Claude đến hết lượt với cùng deadline và observations đã xác thực.
Giới hạn timeout mỗi attempt theo thời gian còn lại. Benchmark
primary_only dùng Gemini. Tắt retry của SDK và ghi model, usage, lỗi
theo từng attempt.

Dùng lỗi đã chuẩn hóa và kết quả kiểm tra output từ pipeline để xét
failover. Hủy lượt, lỗi xác thực chung và hết ngân sách là điều kiện
dừng.
"""
