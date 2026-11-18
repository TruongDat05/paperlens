/**
 * Gửi các yêu cầu HTTP từ side panel tới FastAPI.
 *
 * Dùng backend origin của bản build và token phiên hiện tại. Hỗ trợ hủy fetch
 * và giữ request_id khi gửi lại cùng thao tác.
 *
 * Chuẩn hóa lỗi offline, xác thực, quota và provider để UI hiển thị đúng
 * trạng thái.
 */
