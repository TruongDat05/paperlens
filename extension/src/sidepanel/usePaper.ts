/**
 * Quản lý paper đang mở và trạng thái lập chỉ mục.
 *
 * Theo dõi tab và document. Sau consent, yêu cầu content script parse, gửi
 * ingest qua API client rồi poll index_status để theo dõi lexical_ready và
 * semantic_ready.
 *
 * Chỉ áp kết quả khớp tab, document, version và thao tác hiện tại. Gửi yêu
 * cầu Jump đến đúng document đã phân tích.
 */
