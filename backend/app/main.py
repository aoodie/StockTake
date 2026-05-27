from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .exporter import build_stocktake_workbook

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "stocktake.db"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

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
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    idempotency_key: str


class SyncRequest(BaseModel):
    events: list[SyncEvent]


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


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


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


def apply_event(db: sqlite3.Connection, event: SyncEvent, server_id: str) -> None:
    payload = event.payload
    now = event.created_at.isoformat()

    if event.event_type == "scan":
        product = payload.get("product") or {}
        product_id = product.get("id")
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
                    product.get("barcode"),
                    product.get("bin"),
                    product.get("name", "Unknown Product"),
                    product.get("category", ""),
                    product.get("size", ""),
                    product.get("unit", "each"),
                    product.get("photo_url"),
                    product.get("notes"),
                    product.get("draft_status", "confirmed"),
                    now,
                ),
            )

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
                payload.get("barcode"),
                product.get("bin"),
                product.get("name"),
                str(payload.get("quantity_decimal", "1")),
                product.get("draft_status", "confirmed"),
                now,
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
        db.execute(
            "UPDATE stocktake_lines SET quantity_decimal = ? WHERE id = ?",
            (new, line_id),
        )
        db.execute(
            """
            INSERT INTO quantity_audit (
                line_id, original_quantity, new_quantity, changed_at, change_reason
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (line_id, original, new, now, payload.get("change_reason")),
        )

    elif event.event_type == "draft_product":
        product_id = payload.get("product_id") or f"draft-{event.local_id}"
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, '', ?, '', '', 'each', ?, ?, 'draft', ?)
            ON CONFLICT(id) DO UPDATE SET
                barcode = excluded.barcode,
                name = excluded.name,
                photo_url = excluded.photo_url,
                notes = excluded.notes,
                draft_status = 'draft',
                product_updated_at = excluded.product_updated_at
            """,
            (
                product_id,
                payload.get("barcode"),
                payload.get("placeholder_name", "Draft Product"),
                payload.get("photo_url"),
                payload.get("notes"),
                now,
            ),
        )


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
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            results.append(
                {"local_id": event.local_id, "server_id": server_id, "status": "synced"}
            )
        db.commit()
    return {"events": results}


@app.get("/catalog")
def catalog() -> dict[str, Any]:
    init_db()
    ensure_default_rows()
    with get_db() as db:
        products = db.execute(
            """
            SELECT id, barcode, bin, name, category, size, unit, photo_url, notes,
                   draft_status, product_updated_at
            FROM products
            ORDER BY name
            """
        ).fetchall()
        locations = db.execute("SELECT id, name FROM locations ORDER BY name").fetchall()
        sessions = db.execute(
            "SELECT id, name, period_date FROM sessions ORDER BY period_date DESC"
        ).fetchall()
    return {
        "catalog_version": datetime.now(timezone.utc).isoformat(),
        "products": [dict(row) for row in products],
        "locations": [dict(row) for row in locations],
        "sessions": [dict(row) for row in sessions],
    }


@app.post("/products")
def upsert_product(request: ProductUpsertRequest) -> dict[str, Any]:
    init_db()
    product_id = f"product-{request.barcode}"
    now = datetime.now(timezone.utc).isoformat()
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
                request.barcode,
                request.bin or "",
                request.name,
                request.category,
                request.size,
                request.unit,
                request.photo_url,
                request.notes,
                request.draft_status,
                now,
            ),
        )
        db.commit()
    return {"product_id": product_id, "status": "saved"}


@app.get("/pre-export/{session_id}")
def pre_export(session_id: str) -> dict[str, Any]:
    init_db()
    with get_db() as db:
        missing = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM stocktake_lines sl
            LEFT JOIN products p ON p.id = sl.product_id
            WHERE sl.session_id = ?
              AND COALESCE(p.bin, sl.bin_snapshot, '') = ''
            """,
            (session_id,),
        ).fetchone()["count"]
    return {"session_id": session_id, "missing_bin_count": missing}


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
            (request.bin, datetime.now(timezone.utc).isoformat(), product_id),
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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
