"""Initialize the PaperLens FastAPI application.

Expose the ASGI app at backend.app.main:app, mount routers under
/api/v1, and serve GET /api/v1/health.

Manage configuration, SQLite, provider connections, and background tasks
through the lifespan of a single process. On restart, let ingest and
runs recover their respective state.
"""
