from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .database import init_db, ensure_default_rows, DATA_DIR, STATIC_DIR
from .auth import admin_password
from .routers import sync, admin

app = FastAPI(title="StockTake Backend")

# Register routers
app.include_router(sync.router)
app.include_router(admin.router)

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

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
