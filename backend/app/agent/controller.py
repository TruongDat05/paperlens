"""Điều phối vòng lặp A2 cho một lượt hỏi trên paper.

Nhận câu hỏi, history hợp lệ và paper đã nạp. Gọi router để lấy action
hoặc answer, xác thực action trước khi gọi tool rồi đưa observation đã
kiểm tra vào evidence registry.

Áp giới hạn bước, tool calls, lần search, token và thời gian của cả lượt
theo settings. Chặn action trùng, dành bước cuối cho answer và kiểm tra
yêu cầu hủy giữa các bước.

Trả answer hợp lệ, partial hoặc evidence_only theo bằng chứng còn dùng
được và lý do dừng.
"""
