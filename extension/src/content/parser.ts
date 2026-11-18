/**
 * Đọc thông tin nguồn và đoạn văn từ DOM của arXiv.
 *
 * Phân loại trang HTML, abstract và trang chưa hỗ trợ. Với abstract, lấy link
 * HTML hiện diện trên trang. Báo rõ khi version chưa xác định.
 *
 * Khi Analyze, trích title, canonical URL, version, cây section và paragraphs
 * theo thứ tự tài liệu. Gắn parser version và locator theo quy tắc
 * fingerprint dùng chung với navigation.ts.
 */
