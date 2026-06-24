import json
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response
from ..database import (
    barcode_lookup_values, canonicalize_barcode, get_db, now_iso, normalize_identifier, init_db,
    ensure_default_rows, get_setting, product_select_sql
)
from ..models import (
    SyncRequest, ProductUpsertRequest, SessionCreateRequest, 
    BinUpdateRequest, SyncEvent
)
from ..auth import require_admin
from ..exporter import build_stocktake_workbook
from ..services.enrichment import fetch_product_suggestion
from ..services.procurewizard import active_procurewizard_matches

router = APIRouter()

def require_sync_write_token(x_stocktake_sync_token: str | None = Header(default=None)) -> None:
    required = os.getenv("STOCKTAKE_SYNC_TOKEN", "").strip()
    if required and x_stocktake_sync_token != required:
        raise HTTPException(status_code=403, detail="Sync token required")

def normalize_event_quantity(value: object) -> str:
    text = normalize_identifier(value)
    if not text:
        raise HTTPException(status_code=400, detail="Quantity is required")
    try:
        quantity = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Quantity must be a decimal number") from exc
    if quantity < 0:
        raise HTTPException(status_code=400, detail="Quantity cannot be negative")
    if quantity > Decimal("999999"):
        raise HTTPException(status_code=400, detail="Quantity is too large")
    if abs(quantity.as_tuple().exponent) > 4:
        raise HTTPException(status_code=400, detail="Quantity supports up to 4 decimal places")
    formatted = format(quantity.normalize(), "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted

def normalize_case_type(value: object) -> str:
    case_type = normalize_identifier(value or "split").lower()
    if case_type not in {"full", "split"}:
        raise HTTPException(status_code=400, detail="Case type must be full or split")
    return case_type

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
    barcode = canonicalize_barcode(barcode)
    if not barcode:
        return
    codes = barcode_lookup_values(barcode)
    placeholders = ",".join("?" for _ in codes)
    owner = db.execute(
        f"SELECT barcode, product_id FROM product_barcodes WHERE barcode IN ({placeholders})",
        codes,
    ).fetchone()
    if owner and owner["product_id"] != product_id:
        return
    barcode = owner["barcode"] if owner else barcode
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
        barcode = canonicalize_barcode(payload.get("barcode") or product.get("barcode"))
        product["barcode"] = canonicalize_barcode(product.get("barcode") or barcode)
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

        line_id = payload.get("line_id", server_id)
        existing_line = db.execute(
            "SELECT device_id, session_id FROM stocktake_lines WHERE id = ?",
            (line_id,),
        ).fetchone()
        if existing_line and (
            existing_line["device_id"] != event.device_id or existing_line["session_id"] != event.session_id
        ):
            raise ValueError("Line belongs to another device or session")
        db.execute(
            """
            INSERT OR REPLACE INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, case_type, draft_status, counted_at, device_id, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                line_id,
                event.session_id,
                event.location_id,
                product_id,
                barcode,
                product.get("bin"),
                product.get("name"),
                normalize_event_quantity(payload.get("quantity_decimal", "1")),
                normalize_case_type(payload.get("case_type")),
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
            "SELECT quantity_decimal, device_id, session_id FROM stocktake_lines WHERE id = ?", (line_id,)
        ).fetchone()
        if not current:
            raise ValueError("Line not found")
        if current["device_id"] != event.device_id or current["session_id"] != event.session_id:
            raise ValueError("Line belongs to another device or session")
        original = str(payload.get("original_quantity", current["quantity_decimal"] if current else "0"))
        new = normalize_event_quantity(payload.get("new_quantity", "0"))
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
            current = db.execute(
                "SELECT device_id, session_id FROM stocktake_lines WHERE id = ?",
                (line_id,),
            ).fetchone()
            if not current:
                raise ValueError("Line not found")
            if current["device_id"] != event.device_id or current["session_id"] != event.session_id:
                raise ValueError("Line belongs to another device or session")
            db.execute("DELETE FROM stocktake_lines WHERE id = ?", (line_id,))

    elif event.event_type == "draft_product":
        product_id = payload.get("product_id") or f"draft-{event.local_id}"
        barcode = canonicalize_barcode(payload.get("barcode"))
        existing_product = db.execute("SELECT barcode FROM products WHERE id = ?", (product_id,)).fetchone()
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, ?, ?, '', '', 'each', ?, ?, 'draft', ?)
            ON CONFLICT(id) DO UPDATE SET
                bin = CASE WHEN products.draft_status = 'draft' THEN excluded.bin ELSE products.bin END,
                name = CASE WHEN products.draft_status = 'draft' THEN excluded.name ELSE products.name END,
                photo_url = COALESCE(products.photo_url, excluded.photo_url),
                notes = excluded.notes,
                product_updated_at = excluded.product_updated_at
            """,
            (
                product_id,
                barcode,
                payload.get("bin", ""),
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

def validate_counting_session(db: sqlite3.Connection, event: SyncEvent) -> None:
    if event.event_type not in {"scan", "quantity_edit", "undo_scan", "delete_line"}:
        return
    session = db.execute("SELECT status FROM sessions WHERE id = ?", (event.session_id,)).fetchone()
    if not session:
        raise ValueError("Session does not exist; select an active server session")
    if session["status"] not in {"open", "counting"}:
        raise ValueError(f"Session is {session['status']} and cannot accept counts")

def validate_event_epoch(db: sqlite3.Connection, event: SyncEvent) -> None:
    row = db.execute("SELECT value FROM app_settings WHERE key = 'accept_events_after'").fetchone()
    if not row or not row["value"]:
        return
    cutoff = datetime.fromisoformat(row["value"].replace("Z", "+00:00"))
    created_at = event.created_at
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if created_at < cutoff:
        raise ValueError("Event predates the go-live reset and was discarded")

@router.post("/sync/events")
def sync_events(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_sync_write_token),
) -> dict:
    init_db()
    results = []
    task_ids: list[str] = []
    with get_db() as db:
        event_priority = {"scan": 0, "draft_product": 0, "photo_capture": 1, "quantity_edit": 2, "undo_scan": 3, "delete_line": 3}
        ordered_events = sorted(
            request.events,
            key=lambda event: (event.created_at, event_priority.get(event.event_type, 1), event.local_id),
        )
        for event in ordered_events:
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
            db.execute("SAVEPOINT sync_event")
            try:
                validate_event_epoch(db, event)
                validate_counting_session(db, event)
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
                db.execute("RELEASE SAVEPOINT sync_event")
                results.append({"local_id": event.local_id, "server_id": server_id, "status": "synced"})
            except Exception as exc:
                db.execute("ROLLBACK TO SAVEPOINT sync_event")
                db.execute("RELEASE SAVEPOINT sync_event")
                error = str(exc)[:500] or exc.__class__.__name__
                db.execute(
                    """
                    INSERT INTO sync_failures (
                        local_id, idempotency_key, device_id, session_id, event_type,
                        error, payload_json, failed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.local_id, event.idempotency_key, event.device_id, event.session_id,
                        event.event_type, error, json.dumps(event.payload, separators=(",", ":")), now_iso(),
                    ),
                )
                results.append({"local_id": event.local_id, "status": "rejected", "error": error})
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
        product_payload = []
        for row in products:
            product = dict(row)
            product["barcodes"] = [
                dict(alias)
                for alias in db.execute(
                    """
                    SELECT barcode, label, is_primary
                    FROM product_barcodes
                    WHERE product_id = ?
                    ORDER BY is_primary DESC, barcode
                    """,
                    (product["id"],),
                ).fetchall()
            ]
            procurewizard = db.execute(
                """
                SELECT ptr.pid, ptr.bin_number, ptr.pos, ptr.pack_size,
                       prm.status AS match_status, pwt.id AS import_id, pwt.filename
                FROM procurewizard_template_rows ptr
                JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
                JOIN procurewizard_templates pwt ON pwt.id = ptr.template_id
                WHERE prm.product_id = ?
                ORDER BY pwt.archived_at IS NOT NULL, pwt.created_at DESC, ptr.row_index
                LIMIT 1
                """,
                (product["id"],),
            ).fetchone()
            product["procurewizard"] = dict(procurewizard) if procurewizard else None
            product_payload.append(product)
        locations = db.execute(
            "SELECT id, name FROM locations WHERE COALESCE(active, 1) = 1 ORDER BY name"
        ).fetchall()
        sessions = db.execute(
            """
            SELECT id, name, period_date, status
            FROM sessions
            WHERE status IN ('open', 'counting')
            ORDER BY period_date DESC
            """
        ).fetchall()
    return {
        "catalog_version": now_iso(),
        "data_epoch": get_setting("data_epoch", "initial"),
        "products": product_payload,
        "locations": [dict(row) for row in locations],
        "sessions": [dict(row) for row in sessions],
    }

@router.get("/products/lookup/{barcode}")
def scanner_lookup_product(barcode: str, location_id: str = "cellar") -> dict:
    init_db()
    barcode = canonicalize_barcode(barcode)
    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")
    codes = barcode_lookup_values(barcode)
    placeholders = ",".join("?" for _ in codes)
    with get_db() as db:
        owner = db.execute(
            f"""
            SELECT p.id, p.barcode, pb.barcode AS matched_barcode, p.bin, p.name, p.category, p.size, p.unit, p.photo_url,
                   p.notes, p.draft_status, p.product_updated_at
            FROM product_barcodes pb
            JOIN products p ON p.id = pb.product_id
            WHERE pb.barcode IN ({placeholders})
              AND COALESCE(pb.label, '') != 'ProcureWizard PID'
            ORDER BY CASE WHEN pb.barcode = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (*codes, barcode),
        ).fetchone()
        if owner and owner["draft_status"] != "draft":
            product = dict(owner)
            product["catalog_barcode"] = product["barcode"]
            product["barcode"] = barcode
            return {"barcode": barcode, "exists": True, "product": product, "suggested": {}}
    suggestion = fetch_product_suggestion(barcode)
    with get_db() as db:
        pw_matches = active_procurewizard_matches(
            db,
            {
                "name": suggestion.get("name"),
                "category": suggestion.get("category"),
                "size": suggestion.get("size"),
            },
            outlet_id=location_id,
        )
    return {"barcode": barcode, "exists": False, "suggested": suggestion, "procurewizard_matches": pw_matches}

@router.get("/products/matches")
def scanner_product_matches(
    name: str = "",
    category: str = "",
    size: str = "",
    limit: int = 5,
    location_id: str = "cellar",
) -> dict:
    name = normalize_identifier(name)
    if len(name) < 3:
        return {"matches": []}
    with get_db() as db:
        matches = active_procurewizard_matches(
            db,
            {"name": name, "category": category, "size": size},
            limit=limit,
            min_score=0.28,
            require_name_tokens=True,
            outlet_id=location_id,
        )
    return {"matches": matches}

@router.post("/products")
def upsert_product(request: ProductUpsertRequest, _: None = Depends(require_admin)) -> dict:
    init_db()
    barcode = canonicalize_barcode(request.barcode)
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
            INSERT INTO sessions (id, name, period_date, status, created_at, updated_at)
            VALUES (?, ?, ?, 'open', ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, period_date = excluded.period_date
            """,
            (session_id, request.name, request.period_date, now_iso(), now_iso()),
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
                COUNT(DISTINCT CASE WHEN COALESCE(p.bin, sl.bin_snapshot, '') = ''
                    THEN COALESCE(sl.product_id, sl.id) END) AS missing_bin_count,
                COUNT(DISTINCT CASE WHEN COALESCE(p.draft_status, sl.draft_status, 'confirmed') = 'draft'
                    THEN COALESCE(sl.product_id, sl.id) END) AS draft_count,
                SUM(CASE WHEN INSTR(COALESCE(sl.quantity_decimal, ''), '.') > 0
                    THEN 1 ELSE 0 END) AS decimal_quantity_count
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
        "decimal_quantity_count": stats["decimal_quantity_count"] or 0,
    }

@router.get("/pre-export/{session_id}/missing-bin")
def missing_bin_rows(session_id: str, _: None = Depends(require_admin)) -> dict:
    init_db()
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                MIN(sl.id) AS line_id,
                sl.product_id,
                COALESCE(p.barcode, sl.barcode_snapshot, '') AS barcode,
                COALESCE(p.name, sl.product_name_snapshot, '') AS product_name,
                COALESCE(l.name, sl.location_id) AS location,
                CAST(SUM(CAST(sl.quantity_decimal AS REAL)) AS TEXT) AS quantity_decimal,
                MAX(sl.counted_at) AS counted_at,
                COUNT(*) AS affected_line_count
            FROM stocktake_lines sl
            LEFT JOIN products p ON p.id = sl.product_id
            LEFT JOIN locations l ON l.id = sl.location_id
            WHERE sl.session_id = ?
              AND COALESCE(p.bin, sl.bin_snapshot, '') = ''
            GROUP BY sl.product_id, barcode, product_name, location
            ORDER BY MAX(sl.counted_at) DESC
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
            SET bin = ?, product_updated_at = ?
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
    review = pre_export(session_id)
    if review["missing_bin_count"] or review["draft_count"] or review["decimal_quantity_count"]:
        raise HTTPException(status_code=409, detail="Export blocked until product issues and decimal counts are resolved")
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS count FROM stocktake_lines WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"]
        if count == 0:
            raise HTTPException(status_code=404, detail="No stocktake lines for session")
        workbook = build_stocktake_workbook(db, session_id)
        current = now_iso()
        old_status = db.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
        db.execute(
            "UPDATE sessions SET status = 'exported', exported_at = ?, updated_at = ? WHERE id = ?",
            (current, current, session_id),
        )
        db.execute(
            """
            INSERT INTO session_audit (session_id, old_status, new_status, reason, changed_by, changed_at)
            VALUES (?, ?, 'exported', 'Final Excel export', 'admin', ?)
            """,
            (session_id, old_status["status"] if old_status else None, current),
        )
        db.commit()
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stocktake-{session_id}.xlsx"'},
    )

@router.get("/export/scanned/{session_id}")
def export_scanned_session(session_id: str) -> Response:
    """Export every saved scan, including drafts, missing BINs, and unmapped products."""
    init_db()
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS count FROM stocktake_lines WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"]
        if count == 0:
            raise HTTPException(status_code=404, detail="No scanned lines for session")
        workbook = build_stocktake_workbook(db, session_id, prefer_scan_snapshots=True)
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="scanned-lines-{session_id}.xlsx"'},
    )
