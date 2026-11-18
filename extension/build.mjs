/**
 * Đóng gói Chrome Extension Manifest V3 bằng esbuild.
 *
 * Tạo dist/background.js từ background/index.ts, dist/content.js từ
 * content/index.ts và dist/sidepanel/main.js từ sidepanel/main.tsx. Đóng gói
 * content script thành một bundle tự chứa.
 *
 * Chép manifest, index.html và styles.css vào đường dẫn đã khai báo. Cấu hình
 * backend origin và quyền host tương ứng cho bản local hoặc public.
 */
