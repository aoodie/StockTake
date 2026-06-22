from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from typing import Any

from .. import database
from ..database import now_iso


CATALOG_COLUMNS = [
    "format_version",
    "product_id",
    "primary_barcode",
    "name",
    "bin",
    "category",
    "size",
    "unit",
    "photo_url",
    "notes",
    "draft_status",
    "product_updated_at",
    "barcodes_json",
    "procurewizard_pid",
    "procurewizard_bin",
    "procurewizard_pack_size",
]

MAPPING_AUDIT_COLUMNS = [
    "id",
    "barcode",
    "product_id",
    "product_name",
    "action",
    "label",
    "source",
    "details_json",
    "created_at",
    "undone_at",
]

PROCUREWIZARD_PID_LABEL = "ProcureWizard PID"


def catalog_summary(db: sqlite3.Connection) -> dict[str, int]:
    row = db.execute(
        """
        SELECT
          COUNT(*) AS total_products,
          SUM(CASE WHEN draft_status = 'draft' THEN 1 ELSE 0 END) AS draft_products,
          SUM(CASE WHEN EXISTS (
            SELECT 1 FROM product_barcodes pb
            WHERE pb.product_id = products.id AND COALESCE(pb.label, '') != ?
          ) THEN 1 ELSE 0 END) AS mapped_products,
          SUM(CASE WHEN NOT EXISTS (
            SELECT 1 FROM product_barcodes pb
            WHERE pb.product_id = products.id AND COALESCE(pb.label, '') != ?
          ) THEN 1 ELSE 0 END) AS unmapped_products,
          SUM(CASE WHEN EXISTS (
            SELECT 1 FROM procurewizard_row_mappings prm
            WHERE prm.product_id = products.id
          ) THEN 1 ELSE 0 END) AS procurewizard_products
        FROM products
        """,
        (PROCUREWIZARD_PID_LABEL, PROCUREWIZARD_PID_LABEL),
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _catalog_rows(db: sqlite3.Connection, mapped: bool | None = None) -> list[list[str]]:
    where = ""
    if mapped is not None:
        qualifier = "EXISTS" if mapped else "NOT EXISTS"
        where = f"""
          WHERE {qualifier} (
            SELECT 1 FROM product_barcodes pb
            WHERE pb.product_id = p.id AND COALESCE(pb.label, '') != '{PROCUREWIZARD_PID_LABEL}'
          )
        """
    products = db.execute(
        f"""
        SELECT p.*
        FROM products p
        {where}
        ORDER BY lower(p.name), p.id
        """
    ).fetchall()
    rows: list[list[str]] = []
    for product in products:
        aliases = [
            dict(row)
            for row in db.execute(
                """
                SELECT barcode, label, is_primary, created_at
                FROM product_barcodes
                WHERE product_id = ? AND COALESCE(label, '') != ?
                ORDER BY is_primary DESC, barcode
                """,
                (product["id"], PROCUREWIZARD_PID_LABEL),
            ).fetchall()
        ]
        primary_barcode = next(
            (
                alias["barcode"]
                for alias in aliases
                if alias["is_primary"] and alias["barcode"] == product["barcode"]
            ),
            aliases[0]["barcode"] if aliases else "",
        )
        pw = db.execute(
            """
            SELECT ptr.pid, ptr.bin_number, ptr.pack_size
            FROM procurewizard_template_rows ptr
            JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
            WHERE prm.product_id = ?
            ORDER BY ptr.row_index
            LIMIT 1
            """,
            (product["id"],),
        ).fetchone()
        rows.append(
            [
                "1",
                product["id"],
                primary_barcode,
                product["name"] or "",
                product["bin"] or "",
                product["category"] or "",
                product["size"] or "",
                product["unit"] or "each",
                product["photo_url"] or "",
                product["notes"] or "",
                product["draft_status"] or "confirmed",
                product["product_updated_at"] or "",
                json.dumps(aliases, ensure_ascii=True, separators=(",", ":")),
                pw["pid"] if pw else "",
                pw["bin_number"] if pw else "",
                pw["pack_size"] if pw else "",
            ]
        )
    return rows


def build_catalog_csv(db: sqlite3.Connection, mapped: bool | None = None) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(CATALOG_COLUMNS)
    writer.writerows(_catalog_rows(db, mapped))
    return stream.getvalue().encode("utf-8-sig")


def build_mapping_audit_csv(db: sqlite3.Connection) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(MAPPING_AUDIT_COLUMNS)
    rows = db.execute(
        f"SELECT {', '.join(MAPPING_AUDIT_COLUMNS)} FROM barcode_mapping_audit ORDER BY id"
    ).fetchall()
    writer.writerows([list(row) for row in rows])
    return stream.getvalue().encode("utf-8-sig")


def build_catalog_backup(db: sqlite3.Connection) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("catalog/products.csv", build_catalog_csv(db))
        archive.writestr("catalog/mapped-products.csv", build_catalog_csv(db, True))
        archive.writestr("catalog/unmapped-products.csv", build_catalog_csv(db, False))
        archive.writestr("catalog/mapping-audit.csv", build_mapping_audit_csv(db))
        archive.writestr(
            "catalog/manifest.json",
            json.dumps({"format_version": 1, "created_at": now_iso(), "summary": catalog_summary(db)}, indent=2),
        )
        templates = [
            dict(row)
            for row in db.execute(
                """
                SELECT id, filename, file_sha256, encoding, metadata_json, header_json,
                       row_count, source_type, archived_at, created_at
                FROM procurewizard_templates ORDER BY created_at
                """
            ).fetchall()
        ]
        mappings = [
            dict(row)
            for row in db.execute(
                """
                SELECT ptr.template_id, ptr.id AS row_id, ptr.row_index, ptr.pid,
                       prm.product_id, prm.status, prm.score, prm.reason, prm.updated_at
                FROM procurewizard_template_rows ptr
                LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
                ORDER BY ptr.template_id, ptr.row_index
                """
            ).fetchall()
        ]
        archive.writestr("procurewizard/templates.json", json.dumps(templates, indent=2))
        archive.writestr("procurewizard/row-mappings.json", json.dumps(mappings, indent=2))
        archive.writestr(
            "procurewizard/uploads.json",
            json.dumps(
                [dict(row) for row in db.execute("SELECT * FROM procurewizard_uploads ORDER BY uploaded_at").fetchall()],
                indent=2,
            ),
        )
        archive.writestr(
            "procurewizard/export-runs.json",
            json.dumps(
                [
                    dict(row)
                    for row in db.execute(
                        """
                        SELECT id, template_id, session_id, location_id, warnings_json,
                               warnings_acknowledged, output_sha256, filename, created_at
                        FROM procurewizard_export_runs ORDER BY created_at
                        """
                    ).fetchall()
                ],
                indent=2,
            ),
        )
        for run in db.execute(
            "SELECT id, filename, output_bytes FROM procurewizard_export_runs WHERE output_bytes IS NOT NULL"
        ).fetchall():
            archive.writestr(f"procurewizard/exports/{run['id']}-{run['filename']}", run["output_bytes"])
        for template in db.execute(
            "SELECT id, filename, original_bytes FROM procurewizard_templates WHERE original_bytes IS NOT NULL"
        ).fetchall():
            archive.writestr(
                f"procurewizard/templates/{template['id']}-{template['filename']}",
                template["original_bytes"],
            )
        image_dir = database.DATA_DIR / "product-images"
        if image_dir.exists():
            for path in sorted(image_dir.iterdir()):
                if path.is_file():
                    archive.write(path, f"product-images/{path.name}")
    return stream.getvalue()


def restore_catalog_csv(db: sqlite3.Connection, csv_text: str) -> dict[str, int]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if reader.fieldnames != CATALOG_COLUMNS:
        raise ValueError("Catalog CSV columns do not match the StockTake catalog backup format.")
    rows = list(reader)
    if len(rows) > 100_000:
        raise ValueError("Catalog CSV is too large.")

    parsed: list[tuple[dict[str, str], list[dict[str, Any]]]] = []
    seen_barcodes: dict[str, str] = {}
    for index, row in enumerate(rows, start=2):
        product_id = (row["product_id"] or "").strip()
        name = (row["name"] or "").strip()
        if not product_id or not name:
            raise ValueError(f"Catalog CSV row {index} requires product_id and name.")
        try:
            aliases = json.loads(row["barcodes_json"] or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Catalog CSV row {index} has invalid barcodes_json.") from exc
        if not isinstance(aliases, list):
            raise ValueError(f"Catalog CSV row {index} has invalid barcodes_json.")
        primary = (row["primary_barcode"] or "").strip()
        if primary and not any(str(alias.get("barcode") or "").strip() == primary for alias in aliases):
            aliases.insert(0, {"barcode": primary, "label": "Primary barcode", "is_primary": 1, "created_at": now_iso()})
        for alias in aliases:
            barcode = str(alias.get("barcode") or "").strip()
            if not barcode:
                continue
            owner = seen_barcodes.get(barcode)
            if owner and owner != product_id:
                raise ValueError(f"Barcode {barcode} is assigned to multiple products in the CSV.")
            seen_barcodes[barcode] = product_id
        parsed.append((row, aliases))

    for barcode, product_id in seen_barcodes.items():
        owner = db.execute("SELECT product_id FROM product_barcodes WHERE barcode = ?", (barcode,)).fetchone()
        if owner and owner["product_id"] != product_id:
            raise ValueError(f"Barcode {barcode} already belongs to product {owner['product_id']}.")
        product_owner = db.execute("SELECT id FROM products WHERE barcode = ?", (barcode,)).fetchone()
        if product_owner and product_owner["id"] != product_id:
            raise ValueError(f"Barcode {barcode} is the primary barcode for product {product_owner['id']}.")

    current = now_iso()
    try:
        db.execute("BEGIN")
        for row, aliases in parsed:
            product_id = row["product_id"].strip()
            db.execute(
                """
                INSERT INTO products (
                    id, barcode, bin, name, category, size, unit, photo_url, notes,
                    draft_status, product_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    barcode = excluded.barcode, bin = excluded.bin, name = excluded.name,
                    category = excluded.category, size = excluded.size, unit = excluded.unit,
                    photo_url = excluded.photo_url, notes = excluded.notes,
                    draft_status = excluded.draft_status, product_updated_at = excluded.product_updated_at
                """,
                (
                    product_id,
                    row["primary_barcode"].strip() or None,
                    row["bin"].strip() or None,
                    row["name"].strip(),
                    row["category"].strip(),
                    row["size"].strip(),
                    row["unit"].strip() or "each",
                    row["photo_url"].strip() or None,
                    row["notes"],
                    row["draft_status"].strip() or "confirmed",
                    row["product_updated_at"].strip() or current,
                ),
            )
            db.execute("DELETE FROM product_barcodes WHERE product_id = ?", (product_id,))
            for alias in aliases:
                barcode = str(alias.get("barcode") or "").strip()
                if not barcode:
                    continue
                db.execute(
                    """
                    INSERT INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        barcode,
                        product_id,
                        str(alias.get("label") or "Mapped barcode"),
                        1 if alias.get("is_primary") else 0,
                        str(alias.get("created_at") or current),
                    ),
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"restored_products": len(parsed), "restored_barcodes": len(seen_barcodes)}
