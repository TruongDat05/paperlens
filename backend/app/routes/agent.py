"""Cung cấp giao diện HTTP để bắt đầu, đọc và hủy agent run.

Đăng ký POST /api/v1/agent/runs, GET /api/v1/agent/runs/{run_id} và POST
/api/v1/agent/runs/{run_id}/cancel. Xác thực owner và kiểm tra paper,
question, history và request_id trước khi chuyển cho runs.py.

Trả HTTP 202 và run_id khi bắt đầu. Poll trả tiến trình hoặc kết quả đã
kiểm tra citation, cùng model phục vụ và thông tin fallback nếu có.
"""
