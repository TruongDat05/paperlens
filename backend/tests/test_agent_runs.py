"""Đặc tả kiểm thử vòng đời và tính toàn vẹn của agent run.

Bao phủ quyền sở hữu, request_id trùng, yêu cầu hủy, deadline và
response đến muộn. Giả lập lỗi Gemini, chuyển model một lần, giữ Claude
đến hết lượt và lỗi cả hai model.

Kiểm tra usage chưa rõ, action ngoài phạm vi và citation IDs không thuộc
evidence registry.
"""
