"""Khởi tạo ứng dụng FastAPI của PaperLens.

Cung cấp ASGI app tại backend.app.main:app, gắn các router dưới /api/v1
và phục vụ GET /api/v1/health.

Quản lý cấu hình, SQLite, kết nối provider và các tác vụ nền qua
lifespan của một process. Khi khởi động lại, gọi ingest và runs để khôi
phục trạng thái thuộc từng luồng.
"""
