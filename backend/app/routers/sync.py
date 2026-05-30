import sqlite3
import json
import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from ..database import (
    get_db, now_iso, normalize_identifier, init_db, 
    ensure_default_rows, product_select_sql
)
from ..models import (
    SyncRequest, ProductUpsertRequest, SessionCreateRequest, 
    BinUpdateRequest, SyncEvent
)
from ..auth import require_admin
from ..exporter import build_stocktake_workbook
from ..services.enrichment import fetch_product_suggestion

router = APIRouter()

def suggestion_has_real_name(suggestion: dict, barcode: str) -> bool:
    name = normalize_identifier(suggestion.get("name"))
    return bool(name and name.lower() not in {f"product {barcode}".lower(), f"draft {barcode}".lower()})

def insert_barcode_alias(
    db: sqlite3.Connection,
    product_id: str,
    barcode: str,
    created_at: str,
    *,
    is_primary: bool,
) -> None:
    barcode = normalize_identifier(barcode)
    if not barcode:
        return
    owner = db.execute("SELECT product_id FROM product_barcodes WHERE barcode = ?", (barcode,)).fetchone()
    if owner and owner["product_id"] != product_id:
        return
    db.execute(
        """
        INSERT INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            label = CASE
                WHEN product_barcodes.product_id = excluded.product_id THEN excluded.label
                ELSE product_barcodes.label
            END,
            is_primary = CASE
                WHEN product_barcodes.product_id = excluded.product_id AND excluded.is_primary = 1 THEN 1
                ELSE product_barcodes.is_primary
            END
        """,
        (barcode, product_id, "Primary barcode" if is_primary else "Scanned alias", 1 if is_primary else 0, created_at),
    )

def apply_suggestion_to_draft(db: sqlite3.Connection, task: sqlite3.Row, suggestion: dict) -> None:
    draft_product_id = task["draft_product_id"]
    if not draft_product_id:
        return
    product = db.execute("SELECT * FROM products WHERE id = ?", (draft_product_id,)).fetchone()
    if not product or product["draft_status"] != "draft":
        return
    updates: dict[str, str] = {}
    barcode = task["barcode"]
    if suggestion_has_real_name(suggestion, barcode):
        updates["name"] = normalize_identifier(suggestion.get("name"))
    for field, suggested_field in (
        ("category", "category"),
        ("size", "size"),
        ("unit", "unit"),
        ("photo_url", "image_url"),
    ):
        value = normalize_identifier(suggestion.get(suggested_field))
        current_value = normalize_identifier(product[field])
        can_replace_default_unit = field == "unit" and current_value == "each" and value != "each"
        if value and (not current_value or can_replace_default_unit):
            updates[field] = value
    if not updates:
        return
    updates["product_updated_at"] = now_iso()
    assignments = [f"{key} = ?" for key in updates]
    db.execute(
        f"UPDATE products SET {', '.join(assignments)} WHERE id = ?",
        [updates[key] for key in updates] + [draft_product_id],
    )

def enrich_task_by_id(task_id: str) -> dict:
    init_db()
    with get_db() as db:
        task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        db.execute("UPDATE product_tasks SET status = 'enriching', error = NULL, updated_at = ? WHERE id = ?", (now_iso(), task_id))
        db.commit()
    try:
        suggestion = fetch_product_suggestion(task["barcode"])
    except Exception as exc:
        suggestion = {"barcode": task["barcode"], "lookup_error": str(exc), "confidence": 0}
    status = "review_needed" if suggestion_has_real_name(suggestion, task["barcode"]) else "failed"
    with get_db() as db:
        fresh_task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not fresh_task:
            raise HTTPException(status_code=404, detail="Task not found")
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
        if status == "review_needed":
            apply_suggestion_to_draft(db, fresh_task, suggestion)
        db.commit()
    return {"task_id": task_id, "status": status, "suggested": suggestion}

def enrich_tasks_by_id(task_ids: list[str]) -> None:
    for task_id in dict.fromkeys(task_ids):
        try:
            enrich_task_by_id(task_id)
        except Exception:
            continue

def upsert_product_task(
    db: sqlite3.Connection,
    barcode: str,
    draft_product_id: str | None,
    source: str = "scanner",
) -> str | None:
    if not barcode:
        return None
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
    return f"task-{barcode}"

def apply_event(db: sqlite3.Connection, event: SyncEvent, server_id: str) -> list[str]:
    payload = event.payload
    created = event.created_at.isoformat()
    task_ids: list[str] = []

    if event.event_type == "scan":
        product = payload.get("product") or {}
        product_id = product.get("id")
        barcode = normalize_identifier(payload.get("barcode") or product.get("barcode"))
        product["barcode"] = normalize_identifier(product.get("barcode") or barcode)
        if product_id:
            existing_product = db.execute("SELECT barcode FROM products WHERE id = ?", (product_id,)).fetchone()
            db.execute(
                """
                INSERT INTO products (
                    id, barcode, bin, name, category, size, unit, photo_url, notes,
                    draft_status, product_updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
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
                task_id = upsert_product_task(db, barcode, product_id)
                if task_id:
                    task_ids.append(task_id)
            if barcode:
                insert_barcode_alias(
                    db,
                    product_id,
                    barcode,
                    created,
                    is_primary=not existing_product or not normalize_identifier(existing_product["barcode"]),
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
            return task_ids
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
        existing_product = db.execute("SELECT barcode FROM products WHERE id = ?", (product_id,)).fetchone()
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, '', ?, '', '', 'each', ?, ?, 'draft', ?)
            ON CONFLICT(id) DO UPDATE SET
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
        if barcode:
            insert_barcode_alias(
                db,
                product_id,
                barcode,
                created,
                is_primary=not existing_product or not normalize_identifier(existing_product["barcode"]),
            )
        task_id = upsert_product_task(db, barcode, product_id)
        if task_id:
            task_ids.append(task_id)

    return task_ids

@router.post("/sync/events")
def sync_events(request: SyncRequest, background_tasks: BackgroundTasks) -> dict:
    init_db()
    results = []
    task_ids: list[str] = []
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
            task_ids.extend(apply_event(db, event, server_id))
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
    if task_ids and os.getenv("STOCKTAKE_AUTO_ENRICH", "1") != "0":
        background_tasks.add_task(enrich_tasks_by_id, task_ids)
    return {"events": results}

@router.get("/catalog")
def catalog() -> dict:
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

@router.post("/products")
def upsert_product(request: ProductUpsertRequest, _: None = Depends(require_admin)) -> dict:
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
        db.execute(
            """
            INSERT OR IGNORE INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
            VALUES (?, ?, 'Primary barcode', 1, ?)
            """,
            (barcode, product_id, current),
        )
        db.commit()
    return {"product_id": product_id, "status": "saved"}

@router.post("/sessions")
def create_session(request: SessionCreateRequest, _: None = Depends(require_admin)) -> dict:
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

@router.get("/pre-export/{session_id}")
def pre_export(session_id: str, _: None = Depends(require_admin)) -> dict:
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

@router.get("/pre-export/{session_id}/missing-bin")
def missing_bin_rows(session_id: str, _: None = Depends(require_admin)) -> dict:
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

@router.patch("/products/{product_id}/bin")
def update_product_bin(product_id: str, request: BinUpdateRequest, _: None = Depends(require_admin)) -> dict:
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

@router.get("/export/{session_id}")
def export_session(session_id: str, _: None = Depends(require_admin)) -> Response:
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
