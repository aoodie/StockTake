from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import secrets
from .database import init_db, ensure_default_rows, DATA_DIR, STATIC_DIR
from .database import get_db
from .auth import admin_password
from .routers import sync, admin, ai

app = FastAPI(title="StockTake Backend")

@app.middleware("http")
async def operational_headers(request, call_next):
    request_id = request.headers.get("x-request-id") or secrets.token_hex(12)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response

# Register routers
app.include_router(sync.router)
app.include_router(admin.router)
app.include_router(ai.router)

@app.on_event("startup")
def startup() -> None:
    # 1. Initialize SQLite Database
    init_db()
    # 2. Add default locations and sessions if missing
    ensure_default_rows()
    # 3. Load admin password (validates strength and fails startup if weak!)
    _ = admin_password()

IMAGE_DIR = DATA_DIR / "product-images"

if IMAGE_DIR.exists() or True:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/product-images", StaticFiles(directory=IMAGE_DIR), name="product-images")

# Admin page fallback direct endpoint
@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")

@app.get("/mapping")
def mapping_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "mapping.html")

@app.get("/health")
def health() -> dict:
    with get_db() as db:
        db.execute("SELECT 1").fetchone()
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    return {"status": "ok", "database": "ok", "journal_mode": journal_mode}

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
