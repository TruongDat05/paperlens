/**
 * Quản lý lượt hỏi và Evidence Mode trong side panel.
 *
 * Gửi Ask hoặc follow-up với tối đa 3 lượt history của cùng paper/version.
 * Quản lý request_id, run_id, polling, hủy và phục hồi polling từ
 * chrome.storage.session trong phiên hiện tại.
 *
 * Chỉ áp response khớp owner, tab, document và lượt hỏi đang theo dõi. Dùng
 * retrieve endpoint cho luồng trả trực tiếp evidence.
 */
