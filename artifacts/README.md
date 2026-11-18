# Artifacts đánh giá PaperLens

Mỗi lần chạy QASPER có thư mục theo `run_id` và một manifest ghi dataset revision/checksum, split, sample IDs, cấu hình và phiên bản prompt, tools, models. Lưu retrieval results, traces hợp lệ, usage và metric output với định danh tương ứng. Đánh dấu lần chạy live hoặc replay ngay trong manifest.

Replay sử dụng bằng chứng đã lưu từ benchmark với quyền sử dụng phù hợp. Artifact chia sẻ có checksum, cách lấy dữ liệu và trạng thái của từng record. Dữ liệu người dùng dùng namespace sản phẩm và các quy tắc retention của backend.
