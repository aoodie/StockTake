from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from sqlite3 import Connection
from typing import Any

from ..database import normalize_identifier, now_iso

PW_HEADER = [
    "PID",
    "[E]Bin number",
    "[E]Pos",
    "Tertiary Category",
    "Brand & Description",
    "Pack Size",
    "Est FC",
    "Est SC",
    "[E]Close FC",
    "[E]Close SC",
]


@dataclass
class ProcureWizardParseResult:
    encoding: str
    metadata: list[str]
    header: list[str]
    rows: list[list[str]]


def decode_csv_bytes(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin1", errors="replace"), "latin1"


def parse_procurewizard_csv_text(text: str, encoding: str = "text") -> ProcureWizardParseResult:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise ValueError("ProcureWizard CSV must include a header row.")
    if rows[0] == PW_HEADER:
        metadata: list[str] = []
        header = rows[0]
        data_rows = rows[1:]
        first_data_row_number = 2
    elif len(rows) >= 2 and rows[1] == PW_HEADER:
        metadata = rows[0]
        header = rows[1]
        data_rows = rows[2:]
        first_data_row_number = 3
    else:
        raise ValueError("CSV header does not match the expected ProcureWizard stocktake template.")
    for row_number, row in enumerate(data_rows, start=first_data_row_number):
        if len(row) < len(PW_HEADER):
            raise ValueError(
                f"ProcureWizard CSV row {row_number} has fewer than the required 10 columns."
            )
        if any(value.strip() for value in row[len(PW_HEADER):]):
            raise ValueError(
                f"ProcureWizard CSV row {row_number} has unexpected data after column 10."
            )
    return ProcureWizardParseResult(encoding=encoding, metadata=metadata, header=header, rows=data_rows)


def parse_procurewizard_csv_bytes(data: bytes) -> ProcureWizardParseResult:
    text, encoding = decode_csv_bytes(data)
    return parse_procurewizard_csv_text(text, encoding)


def normalize_match_text(value: str) -> str:
    value = value.lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def product_match_score(row: dict[str, str], product: dict[str, Any]) -> tuple[float, str]:
    row_name = normalize_match_text(row["description"])
    product_name = normalize_match_text(product.get("name") or "")
    if not row_name or not product_name:
        return 0, "missing name"
    name_score = SequenceMatcher(None, row_name, product_name).ratio()
    row_size = normalize_match_text(row.get("pack_size") or "")
    product_size = normalize_match_text(product.get("size") or "")
    size_score = SequenceMatcher(None, row_size, product_size).ratio() if row_size and product_size else 0
    row_category = normalize_match_text(row.get("category") or "")
    product_category = normalize_match_text(product.get("category") or "")
    category_score = SequenceMatcher(None, row_category, product_category).ratio() if row_category and product_category else 0
    score = (name_score * 0.72) + (size_score * 0.18) + (category_score * 0.10)
    return round(score, 4), f"name={name_score:.2f}, size={size_score:.2f}, category={category_score:.2f}"


def row_dict_from_csv(row: list[str]) -> dict[str, str]:
    return {
        "pid": row[0],
        "bin_number": row[1],
        "pos": row[2],
        "category": row[3],
        "description": row[4],
        "pack_size": row[5],
        "est_fc": row[6],
        "est_sc": row[7],
        "close_fc": row[8],
        "close_sc": row[9],
    }


def product_id_for_pid(pid: str, template_id: str = "") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", normalize_identifier(pid))
    template_safe = re.sub(r"[^A-Za-z0-9_.-]", "-", normalize_identifier(template_id))
    return f"procurewizard-{template_safe}-{safe}" if template_safe else f"procurewizard-{safe}"


def best_catalog_match(db: Connection, row: dict[str, str]) -> tuple[str | None, float, str]:
    products = [
        dict(item)
        for item in db.execute(
            """
            SELECT id, name, category, size
            FROM products
            WHERE id NOT LIKE 'procurewizard-%'
            """
        ).fetchall()
    ]
    best_id = None
    best_score = 0.0
    best_reason = ""
    for product in products:
        score, reason = product_match_score(row, product)
        if score > best_score:
            best_id = product["id"]
            best_score = score
            best_reason = reason
    if best_id and best_score == 1:
        return best_id, best_score, "exact name, size, and category match"
    return None, best_score, best_reason


def active_procurewizard_matches(
    db: Connection,
    product: dict[str, Any],
    limit: int = 5,
    min_score: float = 0.38,
    require_name_tokens: bool = False,
    outlet_id: str = "cellar",
) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT pwr.id AS row_id, pwr.pid, pwr.bin_number, pwr.pos, pwr.category,
               pwr.description, pwr.pack_size, pwm.product_id,
               pwt.id AS template_id, pwt.filename AS template_filename,
               p.id, p.barcode, p.bin, p.name, p.category AS product_category,
               p.size, p.unit, p.photo_url, p.notes, p.draft_status, p.product_updated_at
        FROM procurewizard_template_rows pwr
        JOIN procurewizard_templates pwt ON pwt.id = pwr.template_id AND pwt.archived_at IS NULL
        LEFT JOIN procurewizard_row_mappings pwm ON pwm.row_id = pwr.id
        LEFT JOIN products p ON p.id = pwm.product_id
        """
    ).fetchall()
    if not rows:
        rows = db.execute(
            """
            SELECT pwr.id AS row_id, pwr.pid, pwr.bin_number, pwr.pos, pwr.category,
                   pwr.description, pwr.pack_size, pwr.product_id,
                   pwi.id AS template_id, pwi.filename AS template_filename,
                   p.id, p.barcode, p.bin, p.name, p.category AS product_category,
                   p.size, p.unit, p.photo_url, p.notes, p.draft_status, p.product_updated_at
            FROM procurewizard_rows pwr
            JOIN procurewizard_imports pwi ON pwi.id = pwr.import_id AND pwi.active = 1
            LEFT JOIN products p ON p.id = pwr.product_id
            """
        ).fetchall()
    matches: list[dict[str, Any]] = []
    product_name_tokens = set(normalize_match_text(product.get("name") or "").split())
    for item in rows:
        row = dict(item)
        if require_name_tokens:
            row_name_tokens = set(normalize_match_text(row["description"]).split())
            if not product_name_tokens.issubset(row_name_tokens):
                continue
        score, reason = product_match_score(
            {
                "description": row["description"],
                "pack_size": row["pack_size"],
                "category": row["category"],
            },
            product,
        )
        if score < min_score or not row["id"]:
            continue
        matches.append(
            {
                "row_id": row["row_id"],
                "pid": row["pid"],
                "bin_number": row["bin_number"],
                "pos": row["pos"],
                "category": row["category"],
                "description": row["description"],
                "pack_size": row["pack_size"],
                "score": score,
                "reason": reason,
                "template_id": row["template_id"],
                "template_filename": row["template_filename"],
                "product": {
                    "id": row["id"],
                    "barcode": row["barcode"],
                    "bin": row["bin"],
                    "name": row["name"],
                    "category": row["product_category"],
                    "size": row["size"],
                    "unit": row["unit"],
                    "photo_url": row["photo_url"],
                    "notes": row["notes"],
                    "draft_status": row["draft_status"],
                    "product_updated_at": row["product_updated_at"],
                },
            }
        )
    matches.sort(key=lambda match: match["score"], reverse=True)
    return matches[: max(1, min(limit, 10))]


def ensure_procurewizard_product(
    db: Connection, row: dict[str, str], current: str, template_id: str = ""
) -> str:
    base_id = product_id_for_pid(row["pid"])
    existing = db.execute(
        "SELECT id, name, category, size FROM products WHERE id = ?",
        (base_id,),
    ).fetchone()
    if existing and (
        normalize_match_text(existing["name"]) != normalize_match_text(row["description"])
        or normalize_match_text(existing["category"] or "") != normalize_match_text(row["category"])
        or normalize_match_text(existing["size"] or "") != normalize_match_text(row["pack_size"])
    ):
        product_id = product_id_for_pid(row["pid"], template_id)
    else:
        product_id = base_id
    db.execute(
        """
        INSERT INTO products (
            id, barcode, bin, name, category, size, unit, photo_url, notes,
            draft_status, product_updated_at
        )
        VALUES (?, NULL, ?, ?, ?, ?, 'case', '', 'Imported from ProcureWizard CSV', 'confirmed', ?)
        ON CONFLICT(id) DO UPDATE SET
            bin = CASE
                WHEN COALESCE(TRIM(products.bin), '') = '' THEN excluded.bin
                ELSE products.bin
            END,
            name = excluded.name,
            category = excluded.category,
            size = excluded.size,
            product_updated_at = excluded.product_updated_at
        """,
        (
            product_id,
            row["bin_number"],
            row["description"],
            row["category"],
            row["pack_size"],
            current,
        ),
    )
    return product_id


def normalize_outlet_id(outlet_id: str) -> str:
    return normalize_identifier(outlet_id) or "cellar"


def import_procurewizard_csv_bytes(
    db: Connection,
    filename: str,
    csv_bytes: bytes,
) -> dict[str, Any]:
    parsed = parse_procurewizard_csv_bytes(csv_bytes)
    current = now_iso()
    file_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    existing = db.execute(
        "SELECT * FROM procurewizard_templates WHERE file_sha256 = ?",
        (file_sha256,),
    ).fetchone()
    if existing:
        db.execute(
            """
            INSERT INTO procurewizard_uploads (template_id, filename, reused, uploaded_at)
            VALUES (?, ?, 1, ?)
            """,
            (existing["id"], filename or existing["filename"], current),
        )
        db.commit()
        return {
            "template_id": existing["id"],
            "import_id": existing["id"],
            "filename": existing["filename"],
            "row_count": existing["row_count"],
            "reused": True,
        }
    import_id = f"pw-template-{uuid.uuid4().hex[:20]}"
    db.execute(
        """
        INSERT INTO procurewizard_templates (
            id, filename, original_bytes, file_sha256, encoding, metadata_json,
            header_json, row_count, source_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'upload', ?)
        """,
        (
            import_id, filename or "procurewizard.csv", csv_bytes, file_sha256, parsed.encoding,
            json.dumps(parsed.metadata, separators=(",", ":")),
            json.dumps(parsed.header, separators=(",", ":")), len(parsed.rows), current,
        ),
    )
    db.execute(
        """
        INSERT INTO procurewizard_uploads (template_id, filename, reused, uploaded_at)
        VALUES (?, ?, 0, ?)
        """,
        (import_id, filename or "procurewizard.csv", current),
    )
    # Keep legacy tables populated while older catalog and AI views are migrated.
    db.execute("UPDATE procurewizard_imports SET active = 0")
    db.execute(
        """
        INSERT INTO procurewizard_imports (
            id, filename, encoding, metadata_json, header_json, row_count, active, created_at, outlet_id
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'cellar')
        """,
        (
            import_id,
            filename or "procurewizard.csv",
            parsed.encoding,
            json.dumps(parsed.metadata, separators=(",", ":")),
            json.dumps(parsed.header, separators=(",", ":")),
            len(parsed.rows),
            current,
        ),
    )
    matched = 0
    imported = 0
    unmatched = 0
    for index, csv_row in enumerate(parsed.rows, start=2):
        row = row_dict_from_csv(csv_row)
        product_id, score, reason = best_catalog_match(db, row)
        status = "exact"
        if product_id:
            matched += 1
        else:
            product_id = ensure_procurewizard_product(db, row, current, import_id)
            reason = f"imported as catalog product; fuzzy suggestion score={score:.4f}"
            status = "imported"
            imported += 1
        raw = list(csv_row)
        db.execute(
            """
            INSERT INTO procurewizard_rows (
                id, import_id, row_index, pid, bin_number, pos, category, description,
                pack_size, est_fc, est_sc, close_fc, close_sc, raw_json, product_id,
                match_status, match_score, match_reason, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{import_id}-{index}",
                import_id,
                index,
                row["pid"],
                row["bin_number"],
                row["pos"],
                row["category"],
                row["description"],
                row["pack_size"],
                row["est_fc"],
                row["est_sc"],
                row["close_fc"],
                row["close_sc"],
                json.dumps(raw, separators=(",", ":")),
                product_id,
                status,
                score,
                reason,
                current,
                current,
            ),
        )
        db.execute(
            """
            INSERT INTO procurewizard_template_rows (
                id, template_id, row_index, pid, bin_number, pos, category, description,
                pack_size, est_fc, est_sc, close_fc, close_sc, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{import_id}-{index}", import_id, index, row["pid"], row["bin_number"],
                row["pos"], row["category"], row["description"], row["pack_size"],
                row["est_fc"], row["est_sc"], row["close_fc"], row["close_sc"],
                json.dumps(raw, separators=(",", ":")), current,
            ),
        )
        db.execute(
            """
            INSERT INTO procurewizard_row_mappings (row_id, product_id, status, score, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"{import_id}-{index}", product_id, status, score, reason, current),
        )
    db.commit()
    return {
        "import_id": import_id,
        "filename": filename,
        "template_id": import_id,
        "row_count": len(parsed.rows),
        "matched_count": matched,
        "imported_count": imported,
        "unmatched_count": unmatched,
        "reused": False,
    }


def import_procurewizard_csv(
    db: Connection,
    filename: str,
    csv_text: str,
    outlet_id: str = "cellar",
) -> dict[str, Any]:
    return import_procurewizard_csv_bytes(db, filename, csv_text.encode("cp1252", errors="replace"))


def template_library(db: Connection, include_archived: bool = False) -> list[dict[str, Any]]:
    archived_filter = "" if include_archived else "WHERE pwt.archived_at IS NULL"
    return [
        dict(row)
        for row in db.execute(
            f"""
            SELECT pwt.*,
                   COUNT(DISTINCT ptr.id) AS parsed_rows,
                   SUM(CASE WHEN prm.product_id IS NOT NULL THEN 1 ELSE 0 END) AS mapped_rows,
                   COUNT(DISTINCT pwu.id) AS upload_count,
                   MAX(pwu.uploaded_at) AS last_uploaded_at
            FROM procurewizard_templates pwt
            LEFT JOIN procurewizard_template_rows ptr ON ptr.template_id = pwt.id
            LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
            LEFT JOIN procurewizard_uploads pwu ON pwu.template_id = pwt.id
            {archived_filter}
            GROUP BY pwt.id
            ORDER BY pwt.archived_at IS NOT NULL, pwt.created_at DESC
            """
        ).fetchall()
    ]


def set_template_archived(db: Connection, template_id: str, archived: bool) -> dict[str, Any]:
    value = now_iso() if archived else None
    result = db.execute(
        "UPDATE procurewizard_templates SET archived_at = ? WHERE id = ?",
        (value, template_id),
    )
    if not result.rowcount:
        raise ValueError("ProcureWizard template not found")
    db.commit()
    return {"template_id": template_id, "archived": archived}


def active_import(db: Connection, outlet_id: str = "cellar") -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT * FROM procurewizard_templates
        WHERE archived_at IS NULL
        ORDER BY created_at DESC LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def import_summary(
    db: Connection,
    session_id: str = "",
    outlet_id: str = "cellar",
    template_id: str = "",
) -> dict[str, Any]:
    outlet_id = normalize_outlet_id(outlet_id)
    active = (
        db.execute("SELECT * FROM procurewizard_templates WHERE id = ?", (template_id,)).fetchone()
        if template_id
        else active_import(db)
    )
    templates = template_library(db, include_archived=True)
    if not active:
        return {"active": None, "templates": templates, "outlet_id": outlet_id, "rows": [], "counts": {}, "session": {}, "warnings": []}
    active = dict(active)
    counts = {
        row["status"]: row["c"]
        for row in db.execute(
            """
            SELECT prm.status, COUNT(*) AS c
            FROM procurewizard_template_rows ptr
            LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
            WHERE ptr.template_id = ?
            GROUP BY prm.status
            """,
            (active["id"],),
        ).fetchall()
    }
    session = {
        "session_id": session_id,
        "line_count": 0,
        "product_count": 0,
        "quantity_total": "0",
        "pw_product_count": 0,
        "pw_quantity_total": "0",
        "unmapped_product_count": 0,
        "unmapped_quantity_total": "0",
        "unmapped_products": [],
    }
    if session_id:
        stocktake = db.execute(
            """
            SELECT COUNT(*) AS line_count, COUNT(DISTINCT product_id) AS product_count,
                   COALESCE(SUM(CAST(quantity_decimal AS REAL)), 0) AS quantity_total
            FROM stocktake_lines
            WHERE session_id = ? AND location_id = ?
            """,
            (session_id, outlet_id),
        ).fetchone()
        pw_totals = db.execute(
            """
            SELECT COUNT(DISTINCT sl.product_id) AS product_count,
                   COALESCE(SUM(CAST(sl.quantity_decimal AS REAL)), 0) AS quantity_total
            FROM stocktake_lines sl
            WHERE sl.session_id = ? AND sl.location_id = ?
              AND EXISTS (
                SELECT 1 FROM procurewizard_template_rows ptr
                JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
                WHERE ptr.template_id = ? AND prm.product_id = sl.product_id
              )
            """,
            (session_id, outlet_id, active["id"]),
        ).fetchone()
        unmapped_totals = db.execute(
            """
            SELECT COUNT(DISTINCT sl.product_id) AS product_count,
                   COALESCE(SUM(CAST(sl.quantity_decimal AS REAL)), 0) AS quantity_total
            FROM stocktake_lines sl
            WHERE sl.session_id = ? AND sl.location_id = ?
              AND NOT EXISTS (
                SELECT 1 FROM procurewizard_template_rows ptr
                JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
                WHERE ptr.template_id = ? AND prm.product_id = sl.product_id
              )
            """,
            (session_id, outlet_id, active["id"]),
        ).fetchone()
        unmapped = [
            dict(row)
            for row in db.execute(
                """
                SELECT sl.product_id, COALESCE(p.name, sl.product_name_snapshot, sl.barcode_snapshot) AS product_name,
                       COALESCE(p.barcode, sl.barcode_snapshot, '') AS barcode,
                       COUNT(*) AS line_count, SUM(CAST(sl.quantity_decimal AS REAL)) AS quantity_total
                FROM stocktake_lines sl
                LEFT JOIN products p ON p.id = sl.product_id
                WHERE sl.session_id = ? AND sl.location_id = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM procurewizard_template_rows ptr
                    JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
                    WHERE ptr.template_id = ? AND prm.product_id = sl.product_id
                  )
                GROUP BY sl.product_id, product_name, barcode
                ORDER BY quantity_total DESC, product_name
                LIMIT 20
                """,
                (session_id, outlet_id, active["id"]),
            ).fetchall()
        ]
        session.update(
            {
                "line_count": stocktake["line_count"] or 0,
                "product_count": stocktake["product_count"] or 0,
                "quantity_total": format_decimal(Decimal(str(stocktake["quantity_total"] or 0))),
                "pw_product_count": pw_totals["product_count"] or 0,
                "pw_quantity_total": format_decimal(Decimal(str(pw_totals["quantity_total"] or 0))),
                "unmapped_product_count": unmapped_totals["product_count"] or 0,
                "unmapped_quantity_total": format_decimal(Decimal(str(unmapped_totals["quantity_total"] or 0))),
                "unmapped_products": unmapped,
            }
        )
    rows = [
        dict(row)
        for row in db.execute(
            f"""
            SELECT ptr.*, prm.product_id, prm.status AS match_status, prm.score AS match_score,
                   prm.reason AS match_reason, p.name AS product_name, p.barcode AS product_barcode,
                   COALESCE((
                     SELECT SUM(CAST(sl.quantity_decimal AS REAL))
                     FROM stocktake_lines sl
                     WHERE sl.session_id = ? AND sl.location_id = ? AND sl.product_id = prm.product_id
                   ), 0) AS counted_quantity
            FROM procurewizard_template_rows ptr
            LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
            LEFT JOIN products p ON p.id = prm.product_id
            WHERE ptr.template_id = ?
            ORDER BY CASE WHEN counted_quantity > 0 THEN 0 ELSE 1 END,
                     CASE prm.status WHEN 'unmatched' THEN 0 WHEN 'exact' THEN 1 ELSE 2 END,
                     prm.score ASC, ptr.row_index ASC
            LIMIT 500
            """,
            (session_id, outlet_id, active["id"]),
        ).fetchall()
    ]
    duplicate_mappings = [
        dict(row)
        for row in db.execute(
            """
            SELECT prm.product_id, p.name AS product_name, COUNT(*) AS row_count
            FROM procurewizard_template_rows ptr
            JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
            LEFT JOIN products p ON p.id = prm.product_id
            WHERE ptr.template_id = ? AND prm.product_id IS NOT NULL
            GROUP BY prm.product_id
            HAVING COUNT(*) > 1
            ORDER BY row_count DESC, product_name
            """,
            (active["id"],),
        ).fetchall()
    ]
    warnings = []
    if session["unmapped_product_count"]:
        warnings.append(f"{session['unmapped_product_count']} counted products are not mapped to this template.")
    if duplicate_mappings:
        warnings.append(f"{len(duplicate_mappings)} products map to multiple rows and will receive duplicate counts.")
    export_runs = [
        dict(row)
        for row in db.execute(
            """
            SELECT id, template_id, session_id, location_id, warnings_json,
                   warnings_acknowledged, output_sha256, filename, created_at
            FROM procurewizard_export_runs
            WHERE template_id = ? AND session_id = ? AND location_id = ?
            ORDER BY created_at DESC LIMIT 10
            """,
            (active["id"], session_id, outlet_id),
        ).fetchall()
    ] if session_id else []
    return {
        "active": active,
        "templates": templates,
        "outlet_id": outlet_id,
        "rows": rows,
        "counts": counts,
        "session": session,
        "duplicate_mappings": duplicate_mappings,
        "warnings": warnings,
        "export_runs": export_runs,
    }


def link_procurewizard_row(db: Connection, row_id: str, product_id: str | None) -> dict[str, Any]:
    current = now_iso()
    row = db.execute(
        """
        SELECT ptr.pid, prm.product_id
        FROM procurewizard_template_rows ptr
        LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
        WHERE ptr.id = ?
        """,
        (row_id,),
    ).fetchone()
    if not row:
        raise ValueError("ProcureWizard row not found")
    if product_id:
        product = db.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            raise ValueError("Product not found")
    result = db.execute(
        """
        INSERT INTO procurewizard_row_mappings (row_id, product_id, status, score, reason, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(row_id) DO UPDATE SET
            product_id = excluded.product_id,
            status = excluded.status,
            score = excluded.score,
            reason = excluded.reason,
            updated_at = excluded.updated_at
        """,
        (
            row_id,
            product_id,
            "manual" if product_id else "unmatched",
            1.0 if product_id else 0,
            "manual admin link" if product_id else "manual unlink",
            current,
        ),
    )
    db.execute(
        """
        UPDATE procurewizard_rows
        SET product_id = ?, match_status = ?, match_score = ?, match_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (product_id, "manual" if product_id else "unmatched", 1.0 if product_id else 0,
         "manual admin link" if product_id else "manual unlink", current, row_id),
    )
    db.commit()
    return {"row_id": row_id, "product_id": product_id, "status": "linked" if product_id else "unlinked"}


def format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def counted_quantities_by_product(
    db: Connection,
    session_id: str,
    outlet_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    rows = db.execute(
        """
        SELECT product_id, quantity_decimal, COALESCE(case_type, 'split') AS case_type
        FROM stocktake_lines
        WHERE session_id = ? AND COALESCE(product_id, '') != ''
          AND (? IS NULL OR location_id = ?)
        """,
        (session_id, outlet_id, outlet_id),
    ).fetchall()
    for row in rows:
        try:
            quantity = Decimal(str(row["quantity_decimal"] or "0"))
        except Exception:
            quantity = Decimal("0")
        product_totals = totals.setdefault(
            row["product_id"],
            {"full": Decimal("0"), "split": Decimal("0"), "full_counted": False, "split_counted": False},
        )
        case_type = row["case_type"] if row["case_type"] in {"full", "split"} else "split"
        product_totals[case_type] += quantity
        product_totals[f"{case_type}_counted"] = True
    return totals


def build_procurewizard_csv(
    db: Connection,
    session_id: str,
    outlet_id: str = "cellar",
    template_id: str = "",
    warnings_acknowledged: bool = False,
) -> tuple[str, bytes]:
    outlet_id = normalize_outlet_id(outlet_id)
    active = (
        db.execute("SELECT * FROM procurewizard_templates WHERE id = ?", (template_id,)).fetchone()
        if template_id
        else active_import(db)
    )
    if not active:
        raise ValueError("No ProcureWizard template selected.")
    active = dict(active)
    totals = counted_quantities_by_product(db, session_id, outlet_id)
    mapped_product_count = db.execute(
        """
        SELECT COUNT(DISTINCT prm.product_id) AS c
        FROM procurewizard_template_rows ptr
        JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
        WHERE ptr.template_id = ? AND prm.product_id IN (
          SELECT DISTINCT product_id FROM stocktake_lines WHERE session_id = ? AND location_id = ?
        )
        """,
        (active["id"], session_id, outlet_id),
    ).fetchone()["c"]
    if not mapped_product_count:
        raise ValueError(
            "This session has no ProcureWizard-linked counted products. Download All Scanned Lines instead or map products first."
        )
    summary = import_summary(db, session_id, outlet_id, active["id"])
    if summary["warnings"] and not warnings_acknowledged:
        raise ValueError("Export has warnings. Review them and explicitly acknowledge before downloading.")
    output_rows: list[list[str]] = [
        json.loads(active["metadata_json"]),
        json.loads(active["header_json"]),
    ]
    for row in db.execute(
        """
        SELECT ptr.*, prm.product_id
        FROM procurewizard_template_rows ptr
        LEFT JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
        WHERE ptr.template_id = ?
        ORDER BY ptr.row_index
        """,
        (active["id"],),
    ).fetchall():
        raw = json.loads(row["raw_json"])
        raw[8] = ""
        raw[9] = ""
        if row["product_id"] in totals:
            full = totals[row["product_id"]]["full"]
            split = totals[row["product_id"]]["split"]
            raw[8] = format_decimal(full) if totals[row["product_id"]]["full_counted"] else ""
            raw[9] = format_decimal(split) if totals[row["product_id"]]["split_counted"] else ""
        output_rows.append(raw)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerows(output_rows)
    filename = f"procurewizard-{outlet_id}-{session_id}-{active['id']}.csv"
    payload = stream.getvalue().encode(active["encoding"] if active["encoding"] != "text" else "cp1252", errors="replace")
    if (
        db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        and db.execute("SELECT 1 FROM locations WHERE id = ?", (outlet_id,)).fetchone()
    ):
        db.execute(
            """
            INSERT INTO procurewizard_export_runs (
                id, template_id, session_id, location_id, warnings_json,
                warnings_acknowledged, output_sha256, output_bytes, filename, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"pw-export-{uuid.uuid4().hex}", active["id"], session_id, outlet_id,
                json.dumps(summary["warnings"], separators=(",", ":")),
                1 if warnings_acknowledged else 0, hashlib.sha256(payload).hexdigest(),
                payload, filename, now_iso(),
            ),
        )
    db.commit()
    return filename, payload
