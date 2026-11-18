/**
 * Xác minh đoạn nguồn và cuộn tới vị trí trích dẫn.
 *
 * Sở hữu quy tắc chuẩn hóa văn bản và tính fingerprint dùng chung khi parse
 * và Jump. Kiểm tra document/version và đối chiếu fingerprint khi giải
 * element ID hoặc selector do parser xác lập.
 *
 * Chỉ tô sáng đoạn đã xác minh. Khi vị trí không còn khớp hoặc mơ hồ, trả
 * link section đã xác nhận nếu có.
 */
