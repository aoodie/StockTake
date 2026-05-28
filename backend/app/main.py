from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .exporter import build_stocktake_workbook

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "stocktake.db"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
IMAGE_DIR = DATA_DIR / "product-images"
ADMIN_PASSWORD_FILE = DATA_DIR / "admin_password.txt"
ADMIN_COOKIE = "stocktake_admin"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

app = FastAPI(title="StockTake Backend")


class SyncEvent(BaseModel):
    local_id: str
    device_id: str
    session_id: str
    location_id: str | None = None
    event_type: Literal[
        "scan",
        "quantity_edit",
        "draft_product",
        "photo_capture",
        "location_change",
        "session_change",
        "undo_scan",
        "delete_line",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    idempotency_key: str


class SyncRequest(BaseModel):
    events: list[SyncEvent]


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class BinUpdateRequest(BaseModel):
    bin: str = Field(min_length=1)


class ProductUpsertRequest(BaseModel):
    barcode: str = Field(min_length=1)
    bin: str | None = None
    name: str = Field(min_length=1)
    category: str = ""
    size: str = ""
    unit: str = "each"
    photo_url: str | None = None
    notes: str | None = None
    draft_status: str = "confirmed"


class ProductPatchRequest(BaseModel):
    barcode: str | None = None
    bin: str | None = None
    name: str | None = None
    category: str | None = None
    size: str | None = None
    unit: str | None = None
    photo_url: str | None = None
    notes: str | None = None
    draft_status: str | None = None


class SessionCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    period_date: str = Field(min_length=1)


class TaskPatchRequest(BaseModel):
    status: str | None = None
    suggested: dict[str, Any] | None = None
    error: str | None = None


class TaskApproveRequest(BaseModel):
    name: str = Field(min_length=1)
    bin: str = ""
    category: str = ""
    size: str = ""
    unit: str = "each"
    photo_url: str | None = None
    notes: str | None = None


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def normalize_identifier(value: Any) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def admin_password() -> str:
    configured = os.getenv("ADMIN_PASSWORD")
    if configured:
        return configured
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ADMIN_PASSWORD_FILE.exists():
        return ADMIN_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    generated = secrets.token_urlsafe(24)
    ADMIN_PASSWORD_FILE.write_text(f"{generated}\n", encoding="utf-8")
    ADMIN_PASSWORD_FILE.chmod(0o600)
    return generated


def admin_secret() -> str:
    return os.getenv("ADMIN_SECRET") or admin_password()


def admin_token() -> str:
    password = admin_password()
    digest = hmac.new(admin_secret().encode(), password.encode(), hashlib.sha256).hexdigest()
    return f"v1:{digest}"


def require_admin(stocktake_admin: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> None:
    if not stocktake_admin or not hmac.compare_digest(stocktake_admin, admin_token()):
        raise HTTPException(status_code=401, detail="Admin login required")


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def add_column_if_missing(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS synced_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                local_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                location_id TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                barcode TEXT UNIQUE,
                bin TEXT,
                name TEXT NOT NULL,
                category TEXT,
                size TEXT,
                unit TEXT DEFAULT 'each',
                photo_url TEXT,
                notes TEXT,
                draft_status TEXT NOT NULL DEFAULT 'confirmed',
                product_updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_tasks (
                id TEXT PRIMARY KEY,
                barcode TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'scanner',
                draft_product_id TEXT,
                suggested_json TEXT,
                confidence REAL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS locations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                period_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stocktake_lines (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                location_id TEXT,
                product_id TEXT,
                barcode_snapshot TEXT,
                bin_snapshot TEXT,
                product_name_snapshot TEXT,
                quantity_decimal TEXT NOT NULL,
                draft_status TEXT NOT NULL DEFAULT 'confirmed',
                counted_at TEXT NOT NULL,
                device_id TEXT NOT NULL,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS quantity_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_id TEXT NOT NULL,
                original_quantity TEXT NOT NULL,
                new_quantity TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                change_reason TEXT
            );
            """
        )
        add_column_if_missing(db, "products", "photo_source_url", "TEXT")
        add_column_if_missing(db, "products", "photo_source_name", "TEXT")
        add_column_if_missing(db, "products", "photo_saved_path", "TEXT")
        add_column_if_missing(db, "products", "photo_approved_at", "TEXT")
        db.commit()


def ensure_default_rows() -> None:
    today = datetime.now().date().isoformat()
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO locations (id, name) VALUES ('main-bar', 'Main Bar')")
        db.execute("INSERT OR IGNORE INTO locations (id, name) VALUES ('cellar', 'Cellar')")
        db.execute(
            "INSERT OR IGNORE INTO sessions (id, name, period_date) VALUES (?, ?, ?)",
            (f"session-{today}", today, today),
        )
        db.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_default_rows()


def product_select_sql() -> str:
    return """
        SELECT id, barcode, bin, name, category, size, unit, photo_url, notes,
               draft_status, product_updated_at, photo_source_url, photo_source_name,
               photo_saved_path, photo_approved_at
        FROM products
    """


def task_from_row(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["suggested"] = json.loads(task.pop("suggested_json") or "{}")
    return task


def upsert_product_task(
    db: sqlite3.Connection,
    barcode: str,
    draft_product_id: str | None,
    source: str = "scanner",
) -> None:
    if not barcode:
        return
    current = now_iso()
    db.execute(
        """
        INSERT INTO product_tasks (
            id, barcode, status, source, draft_product_id, created_at, updated_at
        )
        VALUES (?, ?, 'queued', ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            draft_product_id = COALESCE(excluded.draft_product_id, product_tasks.draft_product_id),
            status = CASE
                WHEN product_tasks.status IN ('approved', 'review_needed', 'enriching') THEN product_tasks.status
                ELSE 'queued'
            END,
            updated_at = excluded.updated_at
        """,
        (f"task-{barcode}", barcode, source, draft_product_id, current, current),
    )


def apply_event(db: sqlite3.Connection, event: SyncEvent, server_id: str) -> None:
    payload = event.payload
    created = event.created_at.isoformat()

    if event.event_type == "scan":
        product = payload.get("product") or {}
        product_id = product.get("id")
        barcode = normalize_identifier(payload.get("barcode") or product.get("barcode"))
        product["barcode"] = normalize_identifier(product.get("barcode") or barcode)
        if product_id:
            db.execute(
                """
                INSERT INTO products (
                    id, barcode, bin, name, category, size, unit, photo_url, notes,
                    draft_status, product_updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    barcode = excluded.barcode,
                    bin = CASE WHEN products.draft_status = 'draft' THEN excluded.bin ELSE products.bin END,
                    name = CASE WHEN products.draft_status = 'draft' THEN excluded.name ELSE products.name END,
                    category = CASE WHEN products.draft_status = 'draft' THEN excluded.category ELSE products.category END,
                    size = CASE WHEN products.draft_status = 'draft' THEN excluded.size ELSE products.size END,
                    unit = CASE WHEN products.draft_status = 'draft' THEN excluded.unit ELSE products.unit END,
                    photo_url = COALESCE(products.photo_url, excluded.photo_url),
                    notes = CASE WHEN products.draft_status = 'draft' THEN excluded.notes ELSE products.notes END,
                    product_updated_at = excluded.product_updated_at
                """,
                (
                    product_id,
                    product.get("barcode"),
                    product.get("bin"),
                    product.get("name", "Unknown Product"),
                    product.get("category", ""),
                    product.get("size", ""),
                    product.get("unit", "each"),
                    product.get("photo_url"),
                    product.get("notes"),
                    product.get("draft_status", "confirmed"),
                    created,
                ),
            )
            if product.get("draft_status") == "draft":
                upsert_product_task(db, barcode, product_id)

        db.execute(
            """
            INSERT OR REPLACE INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("line_id", server_id),
                event.session_id,
                event.location_id,
                product_id,
                barcode,
                product.get("bin"),
                product.get("name"),
                str(payload.get("quantity_decimal", "1")),
                product.get("draft_status", "confirmed"),
                created,
                event.device_id,
                payload.get("notes"),
            ),
        )

    elif event.event_type == "quantity_edit":
        line_id = payload.get("line_id")
        if not line_id:
            return
        current = db.execute(
            "SELECT quantity_decimal FROM stocktake_lines WHERE id = ?", (line_id,)
        ).fetchone()
        original = str(payload.get("original_quantity", current["quantity_decimal"] if current else "0"))
        new = str(payload.get("new_quantity", "0"))
        db.execute("UPDATE stocktake_lines SET quantity_decimal = ? WHERE id = ?", (new, line_id))
        db.execute(
            """
            INSERT INTO quantity_audit (
                line_id, original_quantity, new_quantity, changed_at, change_reason
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (line_id, original, new, created, payload.get("change_reason")),
        )

    elif event.event_type in ("undo_scan", "delete_line"):
        line_id = payload.get("line_id")
        if line_id:
            db.execute("DELETE FROM stocktake_lines WHERE id = ?", (line_id,))

    elif event.event_type == "draft_product":
        product_id = payload.get("product_id") or f"draft-{event.local_id}"
        barcode = normalize_identifier(payload.get("barcode"))
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, '', ?, '', '', 'each', ?, ?, 'draft', ?)
            ON CONFLICT(id) DO UPDATE SET
                barcode = excluded.barcode,
                photo_url = COALESCE(products.photo_url, excluded.photo_url),
                notes = excluded.notes,
                product_updated_at = excluded.product_updated_at
            """,
            (
                product_id,
                barcode,
                payload.get("placeholder_name", "Draft Product"),
                payload.get("photo_url"),
                payload.get("notes"),
                created,
            ),
        )
        upsert_product_task(db, barcode, product_id)


def parse_open_food_facts(product: dict[str, Any], barcode: str) -> dict[str, Any]:
    name = product.get("product_name") or product.get("generic_name") or f"Product {barcode}"
    quantity = product.get("quantity") or ""
    category = ""
    categories = product.get("categories_tags") or product.get("categories_hierarchy") or []
    if categories:
        category = str(categories[0]).split(":")[-1].replace("-", " ").title()
    image_url = product.get("image_front_url") or product.get("image_url") or ""
    brand = (product.get("brands") or "").split(",")[0].strip()
    return {
        "barcode": barcode,
        "name": " ".join([brand, name]).strip() if brand and brand.lower() not in name.lower() else name,
        "brand": brand,
        "category": category,
        "size": quantity,
        "unit": "bottle" if re.search(r"\b(cl|ml|l)\b", quantity, re.I) else "each",
        "image_url": image_url,
        "source_urls": [f"https://world.openfoodfacts.org/product/{barcode}"],
        "source_name": "Open Food Facts",
        "confidence": 0.72 if name else 0.4,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.I | re.M).strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def llm_refine_product(suggestion: dict[str, Any]) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        return suggestion
    prompt = (
        "Return only compact JSON for a stocktaking product record. "
        "Use the supplied online lookup data, do not invent facts, and leave unknown fields blank. "
        "Fields: barcode,name,brand,category,size,unit,image_url,source_urls,confidence."
    )
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "input": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(suggestion, separators=(",", ":"))},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        suggestion["llm_error"] = str(exc)
        return suggestion

    output = data.get("output_text", "")
    if not output:
        output_parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    output_parts.append(content.get("text", ""))
        output = "\n".join(output_parts)
    refined = extract_json_object(output)
    return {**suggestion, **{k: v for k, v in refined.items() if v not in (None, "")}}


def fetch_product_suggestion(barcode: str) -> dict[str, Any]:
    suggestion = {
        "barcode": barcode,
        "name": f"Product {barcode}",
        "brand": "",
        "category": "",
        "size": "",
        "unit": "each",
        "image_url": "",
        "source_urls": [],
        "source_name": "",
        "confidence": 0.25,
    }
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1:
                    suggestion = parse_open_food_facts(data.get("product") or {}, barcode)
    except Exception as exc:
        suggestion["lookup_error"] = str(exc)
    return llm_refine_product(suggestion)


def image_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def save_product_image(product_id: str, image_url: str) -> str | None:
    if not image_url:
        return None
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(image_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None
            ext = image_extension(image_url, content_type)
            safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", product_id)
            path = IMAGE_DIR / f"{safe_id}{ext}"
            path.write_bytes(response.content)
            return f"/product-images/{path.name}"
    except Exception:
        return None


@app.post("/sync/events")
def sync_events(request: SyncRequest) -> dict[str, Any]:
    init_db()
    results = []
    with get_db() as db:
        for event in request.events:
            existing = db.execute(
                "SELECT server_id FROM synced_events WHERE idempotency_key = ?",
                (event.idempotency_key,),
            ).fetchone()
            if existing:
                results.append(
                    {
                        "local_id": event.local_id,
                        "server_id": existing["server_id"],
                        "status": "duplicate_ignored",
                    }
                )
                continue

            server_id = f"srv_{event.local_id}"
            apply_event(db, event, server_id)
            db.execute(
                """
                INSERT INTO synced_events (
                    idempotency_key, local_id, server_id, device_id, session_id, location_id,
                    event_type, payload_json, created_at, received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.idempotency_key,
                    event.local_id,
                    server_id,
                    event.device_id,
                    event.session_id,
                    event.location_id,
                    event.event_type,
                    json.dumps(event.payload, separators=(",", ":")),
                    event.created_at.isoformat(),
                    now_iso(),
                ),
            )
            results.append({"local_id": event.local_id, "server_id": server_id, "status": "synced"})
        db.commit()
    return {"events": results}


@app.get("/catalog")
def catalog() -> dict[str, Any]:
    init_db()
    ensure_default_rows()
    with get_db() as db:
        products = db.execute(f"{product_select_sql()} ORDER BY name").fetchall()
        locations = db.execute("SELECT id, name FROM locations ORDER BY name").fetchall()
        sessions = db.execute(
            "SELECT id, name, period_date FROM sessions ORDER BY period_date DESC"
        ).fetchall()
    return {
        "catalog_version": now_iso(),
        "products": [dict(row) for row in products],
        "locations": [dict(row) for row in locations],
        "sessions": [dict(row) for row in sessions],
    }


@app.post("/products")
def upsert_product(request: ProductUpsertRequest) -> dict[str, Any]:
    init_db()
    barcode = normalize_identifier(request.barcode)
    product_id = f"product-{barcode}"
    current = now_iso()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO UPDATE SET
                bin = excluded.bin,
                name = excluded.name,
                category = excluded.category,
                size = excluded.size,
                unit = excluded.unit,
                photo_url = excluded.photo_url,
                notes = excluded.notes,
                draft_status = excluded.draft_status,
                product_updated_at = excluded.product_updated_at
            """,
            (
                product_id,
                barcode,
                request.bin or "",
                request.name,
                request.category,
                request.size,
                request.unit,
                request.photo_url,
                request.notes,
                request.draft_status,
                current,
            ),
        )
        db.commit()
    return {"product_id": product_id, "status": "saved"}


@app.post("/sessions")
def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    init_db()
    session_id = normalize_identifier(request.id)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO sessions (id, name, period_date)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, period_date = excluded.period_date
            """,
            (session_id, request.name, request.period_date),
        )
        db.commit()
    return {"id": session_id, "name": request.name, "period_date": request.period_date, "status": "saved"}


@app.get("/pre-export/{session_id}")
def pre_export(session_id: str) -> dict[str, Any]:
    init_db()
    with get_db() as db:
        stats = db.execute(
            """
            SELECT
                COUNT(*) AS line_count,
                SUM(CASE WHEN COALESCE(p.bin, sl.bin_snapshot, '') = '' THEN 1 ELSE 0 END) AS missing_bin_count,
                SUM(CASE WHEN COALESCE(p.draft_status, sl.draft_status, 'confirmed') = 'draft' THEN 1 ELSE 0 END) AS draft_count
            FROM stocktake_lines sl
            LEFT JOIN products p ON p.id = sl.product_id
            WHERE sl.session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return {
        "session_id": session_id,
        "line_count": stats["line_count"] or 0,
        "missing_bin_count": stats["missing_bin_count"] or 0,
        "draft_count": stats["draft_count"] or 0,
    }


@app.get("/pre-export/{session_id}/missing-bin")
def missing_bin_rows(session_id: str) -> dict[str, Any]:
    init_db()
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                sl.id AS line_id,
                sl.product_id,
                COALESCE(p.barcode, sl.barcode_snapshot, '') AS barcode,
                COALESCE(p.name, sl.product_name_snapshot, '') AS product_name,
                COALESCE(l.name, sl.location_id) AS location,
                sl.quantity_decimal,
                sl.counted_at
            FROM stocktake_lines sl
            LEFT JOIN products p ON p.id = sl.product_id
            LEFT JOIN locations l ON l.id = sl.location_id
            WHERE sl.session_id = ?
              AND COALESCE(p.bin, sl.bin_snapshot, '') = ''
            ORDER BY sl.counted_at DESC
            """,
            (session_id,),
        ).fetchall()
    return {"session_id": session_id, "rows": [dict(row) for row in rows]}


@app.patch("/products/{product_id}/bin")
def update_product_bin(product_id: str, request: BinUpdateRequest) -> dict[str, Any]:
    init_db()
    with get_db() as db:
        result = db.execute(
            """
            UPDATE products
            SET bin = ?, draft_status = CASE WHEN draft_status = 'draft' THEN 'confirmed' ELSE draft_status END,
                product_updated_at = ?
            WHERE id = ?
            """,
            (request.bin, now_iso(), product_id),
        )
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")
    return {"product_id": product_id, "bin": request.bin, "status": "updated"}


@app.get("/export/{session_id}")
def export_session(session_id: str) -> Response:
    init_db()
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS count FROM stocktake_lines WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"]
        if count == 0:
            raise HTTPException(status_code=404, detail="No stocktake lines for session")
        workbook = build_stocktake_workbook(db, session_id)
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stocktake-{session_id}.xlsx"'},
    )


@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.post("/admin/api/login")
def admin_login(request: Request, payload: LoginRequest) -> JSONResponse:
    if not hmac.compare_digest(payload.password, admin_password()):
        raise HTTPException(status_code=401, detail="Invalid password")
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        ADMIN_COOKIE,
        admin_token(),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@app.post("/admin/api/logout")
def admin_logout() -> JSONResponse:
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(ADMIN_COOKIE)
    return response


@app.get("/admin/api/me")
def admin_me(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    return {"authenticated": True}


@app.get("/admin/api/dashboard")
def admin_dashboard(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    init_db()
    with get_db() as db:
        counts = {
            "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
            "draft_products": db.execute("SELECT COUNT(*) AS c FROM products WHERE draft_status = 'draft'").fetchone()["c"],
            "tasks": db.execute("SELECT COUNT(*) AS c FROM product_tasks WHERE status != 'approved'").fetchone()["c"],
            "sessions": db.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"],
            "lines": db.execute("SELECT COUNT(*) AS c FROM stocktake_lines").fetchone()["c"],
        }
    return counts


@app.get("/admin/api/products")
def admin_products(search: str = "", _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    init_db()
    query = f"%{search.lower()}%"
    with get_db() as db:
        if search:
            rows = db.execute(
                f"""
                {product_select_sql()}
                WHERE lower(name || ' ' || barcode || ' ' || COALESCE(bin, '')) LIKE ?
                ORDER BY product_updated_at DESC
                LIMIT 250
                """,
                (query,),
            ).fetchall()
        else:
            rows = db.execute(f"{product_select_sql()} ORDER BY product_updated_at DESC LIMIT 250").fetchall()
    return {"products": [dict(row) for row in rows]}


@app.patch("/admin/api/products/{product_id}")
def admin_update_product(
    product_id: str,
    request: ProductPatchRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict[str, Any]:
    require_admin(_)
    init_db()
    values = request.model_dump(exclude_unset=True)
    if not values:
        return {"product_id": product_id, "status": "unchanged"}
    allowed = ["barcode", "bin", "name", "category", "size", "unit", "photo_url", "notes", "draft_status"]
    assignments = [f"{key} = ?" for key in allowed if key in values]
    args = [values[key] for key in allowed if key in values]
    assignments.append("product_updated_at = ?")
    args.append(now_iso())
    args.append(product_id)
    with get_db() as db:
        result = db.execute(
            f"UPDATE products SET {', '.join(assignments)} WHERE id = ?",
            args,
        )
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")
    return {"product_id": product_id, "status": "saved"}


@app.get("/admin/api/tasks")
def admin_tasks(status: str = "", _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    init_db()
    with get_db() as db:
        if status:
            rows = db.execute(
                """
                SELECT pt.*, p.name AS current_name, p.bin AS current_bin
                FROM product_tasks pt
                LEFT JOIN products p ON p.id = pt.draft_product_id
                WHERE pt.status = ?
                ORDER BY pt.updated_at DESC
                """,
                (status,),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT pt.*, p.name AS current_name, p.bin AS current_bin
                FROM product_tasks pt
                LEFT JOIN products p ON p.id = pt.draft_product_id
                ORDER BY CASE pt.status
                    WHEN 'queued' THEN 0
                    WHEN 'failed' THEN 1
                    WHEN 'review_needed' THEN 2
                    ELSE 3
                END, pt.updated_at DESC
                """
            ).fetchall()
    return {"tasks": [task_from_row(row) for row in rows]}


@app.patch("/admin/api/tasks/{task_id}")
def admin_patch_task(
    task_id: str,
    request: TaskPatchRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict[str, Any]:
    require_admin(_)
    init_db()
    values = request.model_dump(exclude_unset=True)
    assignments = []
    args: list[Any] = []
    if "status" in values:
        assignments.append("status = ?")
        args.append(values["status"])
    if "suggested" in values:
        assignments.append("suggested_json = ?")
        args.append(json.dumps(values["suggested"] or {}, separators=(",", ":")))
    if "error" in values:
        assignments.append("error = ?")
        args.append(values["error"])
    if not assignments:
        return {"task_id": task_id, "status": "unchanged"}
    assignments.append("updated_at = ?")
    args.extend([now_iso(), task_id])
    with get_db() as db:
        result = db.execute(f"UPDATE product_tasks SET {', '.join(assignments)} WHERE id = ?", args)
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "status": "saved"}


@app.post("/admin/api/tasks/{task_id}/enrich")
def admin_enrich_task(task_id: str, _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    init_db()
    with get_db() as db:
        task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        db.execute("UPDATE product_tasks SET status = 'enriching', updated_at = ? WHERE id = ?", (now_iso(), task_id))
        db.commit()
    suggestion = fetch_product_suggestion(task["barcode"])
    status = "review_needed" if suggestion.get("name") else "failed"
    with get_db() as db:
        db.execute(
            """
            UPDATE product_tasks
            SET status = ?, suggested_json = ?, confidence = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(suggestion, separators=(",", ":")),
                suggestion.get("confidence"),
                suggestion.get("lookup_error") or suggestion.get("llm_error"),
                now_iso(),
                task_id,
            ),
        )
        db.commit()
    return {"task_id": task_id, "status": status, "suggested": suggestion}


@app.post("/admin/api/tasks/{task_id}/approve")
def admin_approve_task(
    task_id: str,
    request: TaskApproveRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict[str, Any]:
    require_admin(_)
    init_db()
    with get_db() as db:
        task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        barcode = task["barcode"]
        product_id = task["draft_product_id"] or f"product-{barcode}"
        saved_photo = save_product_image(product_id, request.photo_url or "")
        photo_url = saved_photo or request.photo_url or ""
        current = now_iso()
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes, draft_status,
                product_updated_at, photo_source_url, photo_source_name, photo_saved_path, photo_approved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                barcode = excluded.barcode,
                bin = excluded.bin,
                name = excluded.name,
                category = excluded.category,
                size = excluded.size,
                unit = excluded.unit,
                photo_url = excluded.photo_url,
                notes = excluded.notes,
                draft_status = 'confirmed',
                product_updated_at = excluded.product_updated_at,
                photo_source_url = excluded.photo_source_url,
                photo_source_name = excluded.photo_source_name,
                photo_saved_path = excluded.photo_saved_path,
                photo_approved_at = excluded.photo_approved_at
            """,
            (
                product_id,
                barcode,
                request.bin,
                request.name,
                request.category,
                request.size,
                request.unit,
                photo_url,
                request.notes,
                current,
                request.photo_url,
                "Admin approved image" if request.photo_url else "",
                saved_photo,
                current if photo_url else None,
            ),
        )
        db.execute(
            """
            UPDATE product_tasks
            SET status = 'approved', approved_at = ?, updated_at = ?, draft_product_id = ?
            WHERE id = ?
            """,
            (current, current, product_id, task_id),
        )
        db.commit()
    return {"task_id": task_id, "product_id": product_id, "photo_url": photo_url, "status": "approved"}


@app.get("/admin/api/sessions")
def admin_sessions(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    init_db()
    ensure_default_rows()
    with get_db() as db:
        rows = db.execute(
            """
            SELECT s.id, s.name, s.period_date, COUNT(sl.id) AS line_count
            FROM sessions s
            LEFT JOIN stocktake_lines sl ON sl.session_id = s.id
            GROUP BY s.id, s.name, s.period_date
            ORDER BY s.period_date DESC
            """
        ).fetchall()
    return {"sessions": [dict(row) for row in rows]}


@app.get("/admin/api/export/{session_id}/review")
def admin_export_review(session_id: str, _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict[str, Any]:
    require_admin(_)
    review = pre_export(session_id)
    missing = missing_bin_rows(session_id)
    return {**review, "missing_bin_rows": missing["rows"]}


if IMAGE_DIR.exists() or True:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/product-images", StaticFiles(directory=IMAGE_DIR), name="product-images")

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
