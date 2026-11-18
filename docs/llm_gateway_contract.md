# Hợp đồng API gateway cho agent

Trạng thái **chờ kiểm chứng**. `backend/app/providers/llm_gateway.py` chuẩn hóa giao tiếp với gateway. `backend/app/agent/model_router.py` áp chính sách chuyển model. Điểm kiểm chứng là `scripts/smoke_test_llm_gateway.py`.

| Vai trò | Alias cấu hình | Bằng chứng cần ghi |
| --- | --- | --- |
| Primary | `ag/gemini-3.8-flash-medium` | Generation, finish reason, structured output, tool round trip và usage |
| Fallback | `ag/claude-sonnet-4-6` | Cùng bộ kiểm chứng, thêm handoff từ Gemini với observations đã chuẩn hóa |

Ghi base URL, auth, giao thức theo từng alias, timeout/error taxonomy, token/usage fields, quota, billing và khả năng truy cập từ backend đã host. Mỗi alias cần lượt kiểm chứng tool action → observation → final answer và mapping tool call ID. Chọn native tool calls hoặc structured-action JSON theo khả năng thực nghiệm của alias. Handoff giữ lịch sử portable và evidence IDs của turn. Ghi chi phí có thể chưa xác định khi timeout và mẫu đã bỏ thông tin xác thực. [Kế hoạch v4.1, mục 6](../PaperLens_Research_Project_Plan.md#62-kiểm-chứng-fpt-retrieval-và-gateway-llm)
