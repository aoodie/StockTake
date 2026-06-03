from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from typing import Any
import sqlite3
import json
from ..database import (
    get_db, now_iso, normalize_identifier, init_db,
    product_select_sql, task_from_row, ensure_default_rows
)
from ..models import (
    LoginRequest, ProductPatchRequest, ProductUpsertRequest,
    TaskPatchRequest, TaskApproveRequest, BulkProductUpdateRequest,
    BulkProductDeleteRequest, ProductBarcodeRequest, ProductMergeRequest,
    ProcureWizardImportRequest, ProcureWizardLinkRequest
)
from ..auth import (
    admin_password, create_admin_session, revoke_admin_session,
    require_admin, ADMIN_COOKIE
)
from ..services.enrichment import fetch_product_suggestion, save_product_image
from ..services.procurewizard import (
    build_procurewizard_csv,
    import_procurewizard_csv,
    import_summary,
    link_procurewizard_row,
)
from .sync import enrich_task_by_id, pre_export, missing_bin_rows

router = APIRouter()

def audit_product_change(
    db: sqlite3.Connection,
    product_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO product_audit (product_id, action, before_json, after_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            product_id,
            action,
            json.dumps(before, separators=(",", ":")) if before is not None else None,
            json.dumps(after, separators=(",", ":")) if after is not None else None,
            now_iso(),
        ),
    )

def audit_barcode_mapping(
    db: sqlite3.Connection,
    barcode: str,
    product_id: str,
    product_name: str,
    action: str,
    label: str = "",
    source: str = "admin",
    details: dict[str, Any] | None = None,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO barcode_mapping_audit (
            barcode, product_id, product_name, action, label, source, details_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            barcode,
            product_id,
            product_name,
            action,
            label,
            source or "admin",
            json.dumps(details or {}, separators=(",", ":")),
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)

def barcode_lookup_values(value: str) -> list[str]:
    code = normalize_identifier(value)
    if not code:
        return []
    values = [code]
    if code.isdigit():
        stripped = code.lstrip("0") or "0"
        values.append(stripped)
        values.extend([
            stripped.zfill(8),
            stripped.zfill(12),
            stripped.zfill(13),
        ])
        if len(code) in {8, 12, 13}:
            values.append(code.lstrip("0") or code)
    return list(dict.fromkeys(values))

def product_snapshot(db: sqlite3.Connection, product_id: str) -> dict[str, Any] | None:
    row = db.execute(f"{product_select_sql()} WHERE id = ?", (product_id,)).fetchone()
    if not row:
        return None
    product = dict(row)
    product["barcodes"] = [
        dict(alias)
        for alias in db.execute(
            """
            SELECT barcode, label, is_primary, created_at
            FROM product_barcodes
            WHERE product_id = ?
            ORDER BY is_primary DESC, barcode
            """,
            (product_id,),
        ).fetchall()
    ]
    return product

def ensure_primary_barcode_alias(db: sqlite3.Connection, product_id: str, barcode: str, current: str | None = None) -> None:
    barcode = normalize_identifier(barcode)
    if not barcode:
        return
    owner = db.execute(
        "SELECT product_id FROM product_barcodes WHERE barcode = ?",
        (barcode,),
    ).fetchone()
    if owner and owner["product_id"] != product_id:
        raise HTTPException(status_code=400, detail=f"Barcode {barcode} already belongs to another product.")
    if current and current != barcode:
        db.execute(
            "UPDATE product_barcodes SET is_primary = 0, label = COALESCE(label, 'Alias barcode') WHERE product_id = ?",
            (product_id,),
        )
    db.execute(
        """
        INSERT INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
        VALUES (?, ?, 'Primary barcode', 1, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            label = excluded.label,
            is_primary = 1
        WHERE product_barcodes.product_id = excluded.product_id
        """,
        (barcode, product_id, now_iso()),
    )

def product_issue_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT p.*, COUNT(pb.barcode) AS barcode_count
        FROM products p
        LEFT JOIN product_barcodes pb ON pb.product_id = p.id
        GROUP BY p.id
        ORDER BY p.product_updated_at DESC
        """
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for row in rows:
        product = dict(row)
        product_issues = []
        if not (product.get("bin") or "").strip():
            product_issues.append("missing_bin")
        if product.get("draft_status") == "draft":
            product_issues.append("draft_product")
        if not (product.get("unit") or "").strip():
            product_issues.append("missing_unit")
        if not product.get("barcode_count"):
            product_issues.append("missing_barcode")
        if product_issues:
            issues.append({"product": product, "issues": product_issues})
    duplicate_rows = db.execute(
        """
        SELECT lower(trim(name)) AS name_key, lower(trim(COALESCE(size, ''))) AS size_key,
               COUNT(*) AS product_count, GROUP_CONCAT(id) AS product_ids
        FROM products
        WHERE COALESCE(name, '') != ''
        GROUP BY name_key, size_key
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    duplicate_ids = {
        product_id
        for row in duplicate_rows
        for product_id in (row["product_ids"] or "").split(",")
        if product_id
    }
    for product_id in duplicate_ids:
        product = db.execute(f"{product_select_sql()} WHERE id = ?", (product_id,)).fetchone()
        if product:
            issues.append({"product": dict(product), "issues": ["possible_duplicate"]})
    return issues

def decorate_product(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    product = dict(row)
    aliases = db.execute(
        "SELECT barcode, label, is_primary FROM product_barcodes WHERE product_id = ? ORDER BY is_primary DESC, barcode",
        (product["id"],),
    ).fetchall()
    real_barcode_count = sum(
        1 for alias in aliases if (alias["label"] or "") != "ProcureWizard PID"
    )
    issue_names = []
    if not (product.get("bin") or "").strip():
        issue_names.append("missing_bin")
    if product.get("draft_status") == "draft":
        issue_names.append("draft_product")
    if not (product.get("unit") or "").strip():
        issue_names.append("missing_unit")
    if not real_barcode_count:
        issue_names.append("missing_barcode")
    product["barcode_count"] = len(aliases)
    product["real_barcode_count"] = real_barcode_count
    product["barcodes"] = [dict(alias) for alias in aliases]
    product["issues"] = issue_names
    return product

def mapping_product(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    product = decorate_product(db, row)
    procurewizard = db.execute(
        """
        SELECT pwr.id AS row_id, pwr.pid, pwr.bin_number, pwr.pos, pwr.pack_size,
               pwr.match_status, pwi.filename
        FROM procurewizard_rows pwr
        JOIN procurewizard_imports pwi ON pwi.id = pwr.import_id AND pwi.active = 1
        WHERE pwr.product_id = ?
        ORDER BY pwr.row_index
        LIMIT 1
        """,
        (product["id"],),
    ).fetchone()
    product["procurewizard"] = dict(procurewizard) if procurewizard else None
    product["needs_real_barcode"] = product["real_barcode_count"] == 0
    return product

def mapping_audit_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["details"] = json.loads(item.pop("details_json") or "{}")
    return item

@router.post("/admin/api/login")
def admin_login(request: Request, payload: LoginRequest, response: Response) -> dict:
    import hmac
    # Verify the plain text password
    if not hmac.compare_digest(payload.password, admin_password()):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Generate database-backed session token
    session_token = create_admin_session()
    
    response.set_cookie(
        ADMIN_COOKIE,
        session_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return {"status": "ok"}

@router.post("/admin/api/logout")
def admin_logout(response: Response, stocktake_admin: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    if stocktake_admin:
        revoke_admin_session(stocktake_admin)
    response.delete_cookie(ADMIN_COOKIE)
    return {"status": "ok"}

@router.get("/admin/api/me")
def admin_me(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    return {"authenticated": True}

@router.get("/admin/api/dashboard")
def admin_dashboard(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        counts = {
            "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
            "draft_products": db.execute("SELECT COUNT(*) AS c FROM products WHERE draft_status = 'draft'").fetchone()["c"],
            "product_issues": len(product_issue_rows(db)),
            "tasks": db.execute("SELECT COUNT(*) AS c FROM product_tasks WHERE status != 'approved'").fetchone()["c"],
            "pw_rows": db.execute(
                """
                SELECT COUNT(*) AS c
                FROM procurewizard_rows
                WHERE import_id = (
                    SELECT id FROM procurewizard_imports WHERE active = 1 ORDER BY created_at DESC LIMIT 1
                )
                """
            ).fetchone()["c"],
            "sessions": db.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"],
            "lines": db.execute("SELECT COUNT(*) AS c FROM stocktake_lines").fetchone()["c"],
        }
    return counts

@router.get("/admin/api/products")
def admin_products(
    search: str = "",
    limit: int = 50,
    offset: int = 0,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    query = f"%{search.lower()}%"
    with get_db() as db:
        if search:
            count_row = db.execute(
                """
                SELECT COUNT(*) as c
                FROM products
                WHERE lower(name || ' ' || barcode || ' ' || COALESCE(bin, '')) LIKE ?
                   OR id IN (
                        SELECT product_id FROM product_barcodes WHERE lower(barcode || ' ' || COALESCE(label, '')) LIKE ?
                   )
                """,
                (query, query),
            ).fetchone()
            total = count_row["c"] if count_row else 0
            rows = db.execute(
                f"""
                {product_select_sql()}
                WHERE lower(name || ' ' || barcode || ' ' || COALESCE(bin, '')) LIKE ?
                   OR id IN (
                        SELECT product_id FROM product_barcodes WHERE lower(barcode || ' ' || COALESCE(label, '')) LIKE ?
                   )
                ORDER BY product_updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (query, query, limit, offset),
            ).fetchall()
        else:
            count_row = db.execute("SELECT COUNT(*) as c FROM products").fetchone()
            total = count_row["c"] if count_row else 0
            rows = db.execute(
                f"{product_select_sql()} ORDER BY product_updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        products = [decorate_product(db, row) for row in rows]
    return {"products": products, "total": total}

@router.get("/admin/api/barcode-mapping/products")
def admin_barcode_mapping_products(
    search: str = "",
    only_missing: bool = True,
    limit: int = 50,
    offset: int = 0,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    where = []
    params: list[Any] = []
    if search:
        query = f"%{search.lower()}%"
        where.append(
            """
            (
                lower(p.name || ' ' || COALESCE(p.barcode, '') || ' ' || COALESCE(p.bin, '') || ' ' ||
                      COALESCE(p.category, '') || ' ' || COALESCE(p.size, '')) LIKE ?
                OR p.id IN (
                    SELECT product_id
                    FROM product_barcodes
                    WHERE lower(barcode || ' ' || COALESCE(label, '')) LIKE ?
                )
                OR EXISTS (
                    SELECT 1
                    FROM procurewizard_rows pwr
                    JOIN procurewizard_imports pwi ON pwi.id = pwr.import_id AND pwi.active = 1
                    WHERE pwr.product_id = p.id
                      AND lower(pwr.pid || ' ' || COALESCE(pwr.bin_number, '') || ' ' ||
                                pwr.description || ' ' || COALESCE(pwr.category, '') || ' ' ||
                                COALESCE(pwr.pack_size, '')) LIKE ?
                )
            )
            """
        )
        params.extend([query, query, query])
    if only_missing:
        where.append(
            """
            (
                SELECT COUNT(*)
                FROM product_barcodes pb
                WHERE pb.product_id = p.id
                  AND COALESCE(pb.label, '') != 'ProcureWizard PID'
            ) = 0
            """
        )
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    select_sql = """
        SELECT p.id, p.barcode, p.bin, p.name, p.category, p.size, p.unit, p.photo_url, p.notes,
               p.draft_status, p.product_updated_at, p.photo_source_url, p.photo_source_name,
               p.photo_saved_path, p.photo_approved_at
        FROM products p
    """
    with get_db() as db:
        count_row = db.execute(f"SELECT COUNT(*) AS c FROM products p {where_sql}", params).fetchone()
        rows = db.execute(
            f"""
            {select_sql}
            {where_sql}
            ORDER BY
                (
                    SELECT COUNT(*)
                    FROM product_barcodes pb
                    WHERE pb.product_id = p.id
                      AND COALESCE(pb.label, '') != 'ProcureWizard PID'
                ) ASC,
                CASE WHEN p.id LIKE 'procurewizard-%' THEN 0 ELSE 1 END,
                lower(COALESCE(p.bin, '')),
                lower(p.name)
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        products = [mapping_product(db, row) for row in rows]
    return {"products": products, "total": count_row["c"] if count_row else 0}

@router.get("/admin/api/barcode-mapping/barcodes/{barcode}")
def admin_barcode_mapping_lookup(
    barcode: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    code = normalize_identifier(barcode)
    codes = barcode_lookup_values(code)
    if not codes:
        return {"barcode": code, "owner": None}
    placeholders = ",".join("?" for _ in codes)
    with get_db() as db:
        row = db.execute(
            f"""
            SELECT p.id, p.name, p.barcode, pb.label
            FROM product_barcodes pb
            JOIN products p ON p.id = pb.product_id
            WHERE pb.barcode IN ({placeholders})
            LIMIT 1
            """,
            codes,
        ).fetchone()
    return {"barcode": code, "owner": dict(row) if row else None}

@router.get("/admin/api/products/issues")
def admin_product_issues(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        issues = product_issue_rows(db)
    return {"issues": issues, "total": len(issues)}

@router.post("/admin/api/products/merge")
def admin_merge_products(
    request: ProductMergeRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    source_id = normalize_identifier(request.source_product_id)
    target_id = normalize_identifier(request.target_product_id)
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="Choose two different products to merge.")
    with get_db() as db:
        source_before = product_snapshot(db, source_id)
        target_before = product_snapshot(db, target_id)
        if not source_before or not target_before:
            raise HTTPException(status_code=404, detail="Source or target product not found")

        db.execute("UPDATE stocktake_lines SET product_id = ? WHERE product_id = ?", (target_id, source_id))
        db.execute("UPDATE product_tasks SET draft_product_id = ? WHERE draft_product_id = ?", (target_id, source_id))
        db.execute(
            """
            UPDATE product_barcodes
            SET product_id = ?, is_primary = 0,
                label = CASE WHEN COALESCE(label, '') = '' OR is_primary = 1 THEN 'Merged alias' ELSE label END
            WHERE product_id = ?
            """,
            (target_id, source_id),
        )
        db.execute("DELETE FROM products WHERE id = ?", (source_id,))
        audit_product_change(db, source_id, "merge_source_removed", source_before, {"merged_into": target_id})
        audit_product_change(db, target_id, "merge_target_received", target_before, product_snapshot(db, target_id))
        db.commit()
    return {"status": "merged", "source_product_id": source_id, "target_product_id": target_id}

@router.post("/admin/api/products")
def admin_create_product(
    request: ProductUpsertRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    barcode = normalize_identifier(request.barcode)
    codes = barcode_lookup_values(barcode)
    if not codes:
        raise HTTPException(status_code=400, detail="Barcode is required")
    placeholders = ",".join("?" for _ in codes)
    product_id = f"product-{barcode}"
    current = now_iso()
    with get_db() as db:
        existing = db.execute(f"SELECT id FROM products WHERE barcode IN ({placeholders})", codes).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"Product with barcode {barcode} already exists.")
        alias_owner = db.execute(f"SELECT product_id FROM product_barcodes WHERE barcode IN ({placeholders})", codes).fetchone()
        if alias_owner:
            raise HTTPException(status_code=400, detail=f"Barcode {barcode} already belongs to another product.")
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ensure_primary_barcode_alias(db, product_id, barcode)
        audit_product_change(db, product_id, "create_product", None, product_snapshot(db, product_id))
        mapping_audit_id = audit_barcode_mapping(
            db,
            barcode,
            product_id,
            request.name,
            "create_product",
            "Primary barcode",
            request.source_screen,
            {"draft_status": request.draft_status},
        )
        db.commit()
    return {"product_id": product_id, "status": "created", "mapping_audit_id": mapping_audit_id}

@router.get("/admin/api/products/{product_id}")
def admin_product_detail(
    product_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        product = product_snapshot(db, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        product["count_history"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT session_id, location_id, quantity_decimal, counted_at, device_id, notes
                FROM stocktake_lines
                WHERE product_id = ?
                ORDER BY counted_at DESC
                LIMIT 25
                """,
                (product_id,),
            ).fetchall()
        ]
        product["audit"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT id, action, before_json, after_json, created_at
                FROM product_audit
                WHERE product_id = ?
                ORDER BY id DESC
                LIMIT 25
                """,
                (product_id,),
            ).fetchall()
        ]
    return {"product": product}

@router.post("/admin/api/products/{product_id}/barcodes")
def admin_add_product_barcode(
    product_id: str,
    request: ProductBarcodeRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    barcode = normalize_identifier(request.barcode)
    codes = barcode_lookup_values(barcode)
    if not codes:
        raise HTTPException(status_code=400, detail="Barcode is required")
    placeholders = ",".join("?" for _ in codes)
    if request.is_primary:
        raise HTTPException(status_code=400, detail="Primary barcode is locked. Add this code as an alias instead.")
    with get_db() as db:
        before = product_snapshot(db, product_id)
        if not before:
            raise HTTPException(status_code=404, detail="Product not found")
        owner = db.execute(
            f"SELECT barcode, product_id, is_primary FROM product_barcodes WHERE barcode IN ({placeholders})",
            codes,
        ).fetchone()
        if owner and owner["product_id"] != product_id:
            raise HTTPException(status_code=400, detail=f"Barcode {barcode} already belongs to another product.")
        if owner and owner["is_primary"]:
            raise HTTPException(status_code=400, detail="This barcode is already the product's locked primary barcode.")
        if owner and owner["product_id"] == product_id:
            return {
                "status": "already_mapped",
                "product_id": product_id,
                "barcode": owner["barcode"],
                "mapping_audit_id": None,
            }
        result = db.execute(
            """
            INSERT INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO NOTHING
            """,
            (barcode, product_id, request.label, 1 if request.is_primary else 0, now_iso()),
        )
        if result.rowcount == 0:
            owner = db.execute("SELECT product_id, is_primary FROM product_barcodes WHERE barcode = ?", (barcode,)).fetchone()
            if not owner or owner["product_id"] != product_id or owner["is_primary"]:
                raise HTTPException(status_code=409, detail=f"Barcode {barcode} was mapped by another device.")
            return {"status": "already_mapped", "product_id": product_id, "barcode": barcode, "mapping_audit_id": None}
        audit_product_change(db, product_id, "add_barcode", before, product_snapshot(db, product_id))
        mapping_audit_id = audit_barcode_mapping(
            db,
            barcode,
            product_id,
            before.get("name") or product_id,
            "add_alias",
            request.label,
            request.source_screen,
            {"is_primary": request.is_primary},
        )
        db.commit()
    return {"status": "saved", "product_id": product_id, "barcode": barcode, "mapping_audit_id": mapping_audit_id}

@router.delete("/admin/api/products/{product_id}/barcodes/{barcode}")
def admin_delete_product_barcode(
    product_id: str,
    barcode: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    barcode = normalize_identifier(barcode)
    with get_db() as db:
        before = product_snapshot(db, product_id)
        if not before:
            raise HTTPException(status_code=404, detail="Product not found")
        alias = db.execute(
            "SELECT is_primary FROM product_barcodes WHERE product_id = ? AND barcode = ?",
            (product_id, barcode),
        ).fetchone()
        if not alias:
            raise HTTPException(status_code=404, detail="Barcode alias not found")
        if alias["is_primary"]:
            raise HTTPException(status_code=400, detail="Primary barcode cannot be deleted. Set another primary barcode first.")
        db.execute("DELETE FROM product_barcodes WHERE product_id = ? AND barcode = ?", (product_id, barcode))
        audit_product_change(db, product_id, "delete_barcode", before, product_snapshot(db, product_id))
        db.commit()
    return {"status": "deleted", "product_id": product_id, "barcode": barcode}

@router.patch("/admin/api/products/{product_id}")
def admin_update_product(
    product_id: str,
    request: ProductPatchRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    values = request.model_dump(exclude_unset=True)
    if "barcode" in values:
        raise HTTPException(status_code=400, detail="Primary barcode is locked. Add extra barcodes as aliases.")
    for key in ("name", "unit"):
        if key in values and not normalize_identifier(values[key]):
            raise HTTPException(status_code=400, detail=f"{key} cannot be blank")
    if not values:
        return {"product_id": product_id, "status": "unchanged"}
    allowed = ["bin", "name", "category", "size", "unit", "photo_url", "notes", "draft_status"]
    assignments = [f"{key} = ?" for key in allowed if key in values]
    args = [values[key] for key in allowed if key in values]
    assignments.append("product_updated_at = ?")
    args.append(now_iso())
    args.append(product_id)
    with get_db() as db:
        before = product_snapshot(db, product_id)
        if not before:
            raise HTTPException(status_code=404, detail="Product not found")
        result = db.execute(
            f"UPDATE products SET {', '.join(assignments)} WHERE id = ?",
            args,
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")
        audit_product_change(db, product_id, "update_product", before, product_snapshot(db, product_id))
        db.commit()
    return {"product_id": product_id, "status": "saved"}

@router.delete("/admin/api/products/{product_id}")
def admin_delete_product(
    product_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        before = product_snapshot(db, product_id)
        if not before:
            raise HTTPException(status_code=404, detail="Product not found")
        audit_product_change(db, product_id, "delete_product", before, None)
        res = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "deleted"}

@router.post("/admin/api/products/bulk-update")
def admin_bulk_update_products(
    payload: BulkProductUpdateRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    if not payload.product_ids:
        raise HTTPException(status_code=400, detail="No product IDs provided")
    
    assignments = []
    args = []
    if payload.bin is not None:
        assignments.append("bin = ?")
        args.append(payload.bin)
    if payload.category is not None:
        assignments.append("category = ?")
        args.append(payload.category)
        
    if not assignments:
        raise HTTPException(status_code=400, detail="No fields to update")
        
    assignments.append("product_updated_at = ?")
    args.append(now_iso())
    
    query = f"UPDATE products SET {', '.join(assignments)} WHERE id IN ({','.join(['?'] * len(payload.product_ids))})"
    args.extend(payload.product_ids)
    
    with get_db() as db:
        db.execute(query, args)
        db.commit()
    return {"status": "ok", "updated_count": len(payload.product_ids)}

@router.post("/admin/api/products/bulk-delete")
def admin_bulk_delete_products(
    payload: BulkProductDeleteRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    if not payload.product_ids:
        raise HTTPException(status_code=400, detail="No product IDs provided")
        
    query = f"DELETE FROM products WHERE id IN ({','.join(['?'] * len(payload.product_ids))})"
    
    with get_db() as db:
        db.execute(query, payload.product_ids)
        db.commit()
    return {"status": "ok", "deleted_count": len(payload.product_ids)}

@router.get("/admin/api/tasks")
def admin_tasks(status: str = "", _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
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

@router.patch("/admin/api/tasks/{task_id}")
def admin_patch_task(
    task_id: str,
    request: TaskPatchRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    values = request.model_dump(exclude_unset=True)
    assignments = []
    args = []
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

@router.post("/admin/api/tasks/{task_id}/enrich")
def admin_enrich_task(task_id: str, _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    return enrich_task_by_id(task_id)

@router.get("/admin/api/products/lookup/{barcode}")
def admin_lookup_product(
    barcode: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    barcode = normalize_identifier(barcode)
    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")
    codes = barcode_lookup_values(barcode)
    placeholders = ",".join("?" for _ in codes)
    with get_db() as db:
        owner = db.execute(
            f"""
            SELECT p.id, p.barcode, p.bin, p.name, p.category, p.size, p.unit, p.photo_url, p.notes,
                   p.draft_status, p.product_updated_at, p.photo_source_url, p.photo_source_name,
                   p.photo_saved_path, p.photo_approved_at
            FROM product_barcodes pb
            JOIN products p ON p.id = pb.product_id
            WHERE pb.barcode IN ({placeholders})
            LIMIT 1
            """,
            codes,
        ).fetchone()
        if owner:
            return {"barcode": barcode, "exists": True, "product": mapping_product(db, owner), "suggested": {}}
    suggestion = fetch_product_suggestion(barcode)
    return {"barcode": barcode, "exists": False, "suggested": suggestion}

@router.get("/admin/api/barcode-mapping/recent")
def admin_recent_barcode_mappings(
    limit: int = 20,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    limit = max(1, min(limit, 100))
    with get_db() as db:
        rows = db.execute(
            """
            SELECT bma.*, p.name AS current_product_name, p.draft_status
            FROM barcode_mapping_audit bma
            LEFT JOIN products p ON p.id = bma.product_id
            ORDER BY bma.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"mappings": [mapping_audit_row(row) for row in rows]}

@router.post("/admin/api/barcode-mapping/recent/{audit_id}/undo")
def admin_undo_barcode_mapping(
    audit_id: int,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    current = now_iso()
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM barcode_mapping_audit WHERE id = ?",
            (audit_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Mapping audit entry not found")
        if row["undone_at"]:
            raise HTTPException(status_code=400, detail="This mapping has already been undone.")

        product_id = row["product_id"]
        barcode = normalize_identifier(row["barcode"])
        before = product_snapshot(db, product_id)
        if row["action"] == "add_alias":
            alias = db.execute(
                "SELECT is_primary FROM product_barcodes WHERE product_id = ? AND barcode = ?",
                (product_id, barcode),
            ).fetchone()
            if not alias:
                raise HTTPException(status_code=404, detail="Barcode alias is no longer present.")
            if alias["is_primary"]:
                raise HTTPException(status_code=400, detail="Primary barcode cannot be undone from mapping history.")
            db.execute("DELETE FROM product_barcodes WHERE product_id = ? AND barcode = ?", (product_id, barcode))
            audit_product_change(db, product_id, "undo_barcode_mapping", before, product_snapshot(db, product_id))
        elif row["action"] == "create_product":
            if not before:
                raise HTTPException(status_code=404, detail="Product is already missing.")
            if before.get("draft_status") != "draft":
                raise HTTPException(status_code=400, detail="Only draft products can be undone from mapping history.")
            if before.get("product_updated_at") and before["product_updated_at"] > row["created_at"]:
                raise HTTPException(status_code=400, detail="Cannot undo product creation after later catalog edits.")
            alias_count = db.execute(
                "SELECT COUNT(*) AS c FROM product_barcodes WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            if alias_count and alias_count["c"] > 1:
                raise HTTPException(status_code=400, detail="Cannot undo product creation after extra barcodes were added.")
            changed_after = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM product_audit
                WHERE product_id = ?
                  AND action != 'create_product'
                  AND created_at > ?
                """,
                (product_id, row["created_at"]),
            ).fetchone()
            if changed_after and changed_after["c"]:
                raise HTTPException(status_code=400, detail="Cannot undo product creation after later catalog edits.")
            count_row = db.execute(
                "SELECT COUNT(*) AS c FROM stocktake_lines WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            if count_row and count_row["c"]:
                raise HTTPException(status_code=400, detail="Cannot undo product creation after stocktake counts exist.")
            db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            audit_product_change(db, product_id, "undo_created_product", before, None)
        else:
            raise HTTPException(status_code=400, detail="This mapping action cannot be undone.")

        db.execute("UPDATE barcode_mapping_audit SET undone_at = ? WHERE id = ?", (current, audit_id))
        db.commit()
    return {"status": "undone", "audit_id": audit_id, "product_id": product_id, "barcode": barcode}

@router.post("/admin/api/tasks/{task_id}/approve")
def admin_approve_task(
    task_id: str,
    request: TaskApproveRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        barcode = task["barcode"]
        product_id = task["draft_product_id"] or f"product-{barcode}"
        before = product_snapshot(db, product_id)
        codes = barcode_lookup_values(barcode)
        if not codes:
            raise HTTPException(status_code=400, detail="Task barcode is required")
        placeholders = ",".join("?" for _ in codes)
        owner = db.execute(
            f"SELECT barcode, product_id FROM product_barcodes WHERE barcode IN ({placeholders}) LIMIT 1",
            codes,
        ).fetchone()
        if owner and owner["product_id"] != product_id:
            raise HTTPException(status_code=400, detail=f"Barcode {barcode} already belongs to another product.")
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
        if before and normalize_identifier(before.get("barcode")) and normalize_identifier(before.get("barcode")) != barcode:
            db.execute(
                """
                INSERT OR IGNORE INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
                VALUES (?, ?, 'Approved scan alias', 0, ?)
                """,
                (barcode, product_id, current),
            )
        else:
            ensure_primary_barcode_alias(db, product_id, barcode)
        db.execute(
            """
            UPDATE product_tasks
            SET status = 'approved', approved_at = ?, updated_at = ?, draft_product_id = ?
            WHERE id = ?
            """,
            (current, current, product_id, task_id),
        )
        audit_product_change(db, product_id, "approve_task", before, product_snapshot(db, product_id))
        db.commit()
    return {"task_id": task_id, "product_id": product_id, "photo_url": photo_url, "status": "approved"}

@router.post("/admin/api/tasks/{task_id}/reject")
def admin_reject_task(
    task_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Delete task
        db.execute("DELETE FROM product_tasks WHERE id = ?", (task_id,))
        # Delete related draft product
        if task["draft_product_id"]:
            db.execute("DELETE FROM products WHERE id = ?", (task["draft_product_id"],))
        db.commit()
    return {"task_id": task_id, "status": "rejected"}

@router.post("/admin/api/procurewizard/import")
def admin_import_procurewizard(
    request: ProcureWizardImportRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        try:
            result = import_procurewizard_csv(db, request.filename, request.csv_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result

@router.get("/admin/api/procurewizard/status")
def admin_procurewizard_status(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        return import_summary(db)

@router.patch("/admin/api/procurewizard/rows/{row_id}")
def admin_link_procurewizard_row(
    row_id: str,
    request: ProcureWizardLinkRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        try:
            return link_procurewizard_row(db, row_id, request.product_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/admin/api/procurewizard/export/{session_id}")
def admin_export_procurewizard_csv(
    session_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> Response:
    require_admin(_)
    init_db()
    with get_db() as db:
        try:
            filename, payload = build_procurewizard_csv(db, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        payload,
        media_type="text/csv; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/admin/api/sessions")
def admin_sessions(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
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

@router.delete("/admin/api/sessions/{session_id}")
def admin_delete_session(
    session_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)
) -> dict:
    require_admin(_)
    init_db()
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db.execute("DELETE FROM stocktake_lines WHERE session_id = ?", (session_id,))
        db.commit()
    return {"status": "deleted"}

@router.get("/admin/api/export/{session_id}/review")
def admin_export_review(session_id: str, _: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    review = pre_export(session_id)
    missing = missing_bin_rows(session_id)
    return {**review, "missing_bin_rows": missing["rows"]}
