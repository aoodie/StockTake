import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "stocktake.db"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_INITIALIZED_DB_PATH: Path | None = None


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA synchronous = NORMAL")
    return db

def normalize_identifier(value: Any) -> str:
    return str(value or "").strip()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None

def add_column_if_missing(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db(force: bool = False) -> None:
    global _INITIALIZED_DB_PATH
    if not force and _INITIALIZED_DB_PATH == DB_PATH and DB_PATH.exists():
        return
    with get_db() as db:
        db.execute("PRAGMA journal_mode = WAL")
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

            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_lookup_cache (
                barcode TEXT PRIMARY KEY,
                suggested_json TEXT NOT NULL,
                cached_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_barcodes (
                barcode TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                label TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS product_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                action TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS barcode_mapping_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT NOT NULL,
                product_id TEXT NOT NULL,
                product_name TEXT,
                action TEXT NOT NULL,
                label TEXT,
                source TEXT NOT NULL DEFAULT 'admin',
                details_json TEXT,
                created_at TEXT NOT NULL,
                undone_at TEXT
            );

            CREATE TABLE IF NOT EXISTS procurewizard_imports (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                encoding TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                header_json TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS procurewizard_rows (
                id TEXT PRIMARY KEY,
                import_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                pid TEXT NOT NULL,
                bin_number TEXT,
                pos TEXT,
                category TEXT,
                description TEXT NOT NULL,
                pack_size TEXT,
                est_fc TEXT,
                est_sc TEXT,
                close_fc TEXT,
                close_sc TEXT,
                raw_json TEXT NOT NULL,
                product_id TEXT,
                match_status TEXT NOT NULL DEFAULT 'unmatched',
                match_score REAL NOT NULL DEFAULT 0,
                match_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(import_id) REFERENCES procurewizard_imports(id) ON DELETE CASCADE,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
            );
            """
        )
        add_column_if_missing(db, "products", "photo_source_url", "TEXT")
        add_column_if_missing(db, "products", "photo_source_name", "TEXT")
        add_column_if_missing(db, "products", "photo_saved_path", "TEXT")
        add_column_if_missing(db, "products", "photo_approved_at", "TEXT")
        db.execute(
            """
            INSERT OR IGNORE INTO product_barcodes (barcode, product_id, label, is_primary, created_at)
            SELECT barcode, id, 'Primary barcode', 1, product_updated_at
            FROM products
            WHERE COALESCE(barcode, '') != ''
            """
        )
        db.execute(
            """
            UPDATE product_barcodes
            SET is_primary = CASE
                WHEN barcode = (
                    SELECT products.barcode
                    FROM products
                    WHERE products.id = product_barcodes.product_id
                ) THEN 1
                ELSE 0
            END
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_product_barcodes_one_primary
            ON product_barcodes(product_id)
            WHERE is_primary = 1
            """
        )
        db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_stocktake_lines_session_counted
            ON stocktake_lines(session_id, counted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_stocktake_lines_product_counted
            ON stocktake_lines(product_id, counted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_stocktake_lines_session_location_counted
            ON stocktake_lines(session_id, location_id, counted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_product_tasks_status_updated
            ON product_tasks(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_product_barcodes_product_lookup
            ON product_barcodes(product_id, is_primary, barcode);
            CREATE INDEX IF NOT EXISTS idx_products_updated
            ON products(product_updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_products_name_nocase
            ON products(name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_barcode_mapping_audit_created
            ON barcode_mapping_audit(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_barcode_mapping_audit_barcode
            ON barcode_mapping_audit(barcode);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_procurewizard_rows_import_pid
            ON procurewizard_rows(import_id, pid);
            CREATE INDEX IF NOT EXISTS idx_procurewizard_rows_product
            ON procurewizard_rows(product_id);
            CREATE INDEX IF NOT EXISTS idx_procurewizard_rows_status
            ON procurewizard_rows(import_id, match_status, match_score DESC);
            """
        )
        db.commit()
    _INITIALIZED_DB_PATH = DB_PATH

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
