from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app import database

def open_session(session_id: str = "session-a") -> None:
    database.init_db()
    with database.get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO sessions (id, name, period_date, status) VALUES (?, ?, '2026-06-10', 'open')",
            (session_id, session_id),
        )
        db.commit()

def test_catalog_has_operational_outlets_and_renames_main_bar_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    with database.get_db() as db:
        db.execute("INSERT INTO locations (id, name) VALUES ('main-bar', 'Main Bar')")
        db.commit()

    response = TestClient(app).get("/catalog")

    assert response.status_code == 200
    assert response.json()["locations"] == [
        {"id": "main-bar", "name": "Bar"},
        {"id": "brasseries", "name": "Brasseries"},
        {"id": "cellar", "name": "Cellar"},
        {"id": "m-and-e", "name": "M&E"},
    ]

def test_sync_rejects_offline_events_from_before_go_live_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    open_session()
    with database.get_db() as db:
        db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('accept_events_after', '2026-06-11T09:00:00+00:00', '2026-06-11T09:00:00+00:00')"
        )
        db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('data_epoch', 'go-live-2026-06-11', '2026-06-11T09:00:00+00:00')"
        )
        db.commit()
    event = {
        "local_id": "old-offline-scan",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "main-bar",
        "event_type": "scan",
        "payload": {"line_id": "old-line", "barcode": "123", "quantity_decimal": "1", "product": {"id": "p1", "barcode": "123", "name": "Old test product"}},
        "created_at": "2026-06-10T09:00:00+00:00",
        "idempotency_key": "device-a:old-offline-scan",
    }

    client = TestClient(app)
    response = client.post("/sync/events", json={"events": [event]})

    assert response.json()["events"][0]["status"] == "rejected"
    assert "go-live reset" in response.json()["events"][0]["error"]
    assert client.get("/catalog").json()["data_epoch"] == "go-live-2026-06-11"

def test_sync_idempotency_ignores_duplicate_events(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    client = TestClient(app)
    open_session()

    event = {
        "local_id": "local-1",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "location-a",
        "event_type": "scan",
        "payload": {
            "line_id": "line-a",
            "barcode": "5000213014231",
            "quantity_decimal": "0",
            "product": {
                "id": "product-a",
                "barcode": "5000213014231",
                "bin": "G-402",
                "name": "Test Bottle",
                "category": "Spirit",
                "size": "70cl",
                "unit": "bottle",
                "draft_status": "confirmed",
            },
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-a:local-1",
    }

    first = client.post("/sync/events", json={"events": [event]})
    second = client.post("/sync/events", json={"events": [event]})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["events"][0]["status"] == "synced"
    assert second.json()["events"][0]["status"] == "duplicate_ignored"


def test_quantity_edit_and_delete_events_update_line(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    client = TestClient(app)
    open_session()

    base = {
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "location-a",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    scan = {
        **base,
        "local_id": "local-scan",
        "event_type": "scan",
        "idempotency_key": "device-a:local-scan",
        "payload": {
            "line_id": "line-a",
            "barcode": "5000213014231",
            "quantity_decimal": "1",
            "case_type": "full",
            "product": {
                "id": "product-a",
                "barcode": "5000213014231",
                "bin": "G-402",
                "name": "Test Bottle",
                "category": "Spirit",
                "size": "70cl",
                "unit": "bottle",
                "draft_status": "confirmed",
            },
        },
    }
    edit = {
        **base,
        "local_id": "local-edit",
        "event_type": "quantity_edit",
        "idempotency_key": "device-a:local-edit",
        "payload": {
            "line_id": "line-a",
            "original_quantity": "1",
            "new_quantity": "0",
            "change_reason": "zero count checked",
        },
    }
    delete = {
        **base,
        "local_id": "local-delete",
        "event_type": "delete_line",
        "idempotency_key": "device-a:local-delete",
        "payload": {"line_id": "line-a"},
    }

    response = client.post("/sync/events", json={"events": [scan, edit]})
    assert response.status_code == 200

    with database.get_db() as db:
        row = db.execute("SELECT quantity_decimal, case_type FROM stocktake_lines WHERE id = 'line-a'").fetchone()
        audit = db.execute("SELECT new_quantity FROM quantity_audit WHERE line_id = 'line-a'").fetchone()
    assert row["quantity_decimal"] == "0"
    assert row["case_type"] == "full"
    assert audit["new_quantity"] == "0"

    response = client.post("/sync/events", json={"events": [delete]})
    assert response.status_code == 200
    with database.get_db() as db:
        row = db.execute("SELECT id FROM stocktake_lines WHERE id = 'line-a'").fetchone()
    assert row is None


def test_scan_sync_does_not_mutate_existing_product_barcode(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    client = TestClient(app)
    open_session()

    base = {
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "location-a",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_type": "scan",
    }
    first = {
        **base,
        "local_id": "scan-original",
        "idempotency_key": "device-a:scan-original",
        "payload": {
            "line_id": "line-original",
            "barcode": "original-code",
            "quantity_decimal": "1",
            "product": {
                "id": "product-a",
                "barcode": "original-code",
                "bin": "A-1",
                "name": "Immutable Product",
                "unit": "each",
                "draft_status": "confirmed",
            },
        },
    }
    second = {
        **base,
        "local_id": "scan-alias",
        "idempotency_key": "device-a:scan-alias",
        "payload": {
            "line_id": "line-alias",
            "barcode": "new-scanned-code",
            "quantity_decimal": "1",
            "product": {
                "id": "product-a",
                "barcode": "new-scanned-code",
                "bin": "A-2",
                "name": "Client Renamed Product",
                "unit": "box",
                "draft_status": "confirmed",
            },
        },
    }

    assert client.post("/sync/events", json={"events": [first]}).status_code == 200
    assert client.post("/sync/events", json={"events": [second]}).status_code == 200

    with database.get_db() as db:
        product = db.execute("SELECT barcode, name, bin, unit FROM products WHERE id = 'product-a'").fetchone()
        aliases = db.execute(
            "SELECT barcode, is_primary FROM product_barcodes WHERE product_id = 'product-a' ORDER BY barcode"
        ).fetchall()

    assert product["barcode"] == "original-code"
    assert product["name"] == "Immutable Product"
    assert product["bin"] == "A-1"
    assert product["unit"] == "each"
    assert {row["barcode"] for row in aliases} == {"new-scanned-code", "original-code"}
    assert {row["barcode"] for row in aliases if row["is_primary"]} == {"original-code"}


def test_sync_token_is_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    monkeypatch.setenv("STOCKTAKE_SYNC_TOKEN", "trial-token")
    client = TestClient(app)
    open_session()

    event = {
        "local_id": "local-token",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "location-a",
        "event_type": "scan",
        "payload": {
            "line_id": "line-token",
            "barcode": "5000213014231",
            "quantity_decimal": "1",
            "product": {
                "id": "product-token",
                "barcode": "5000213014231",
                "name": "Token Test",
                "draft_status": "confirmed",
            },
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-a:local-token",
    }

    assert client.post("/sync/events", json={"events": [event]}).status_code == 403
    response = client.post(
        "/sync/events",
        json={"events": [event]},
        headers={"X-StockTake-Sync-Token": "trial-token"},
    )
    assert response.status_code == 200


def test_sync_rejects_invalid_quantities(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    monkeypatch.delenv("STOCKTAKE_SYNC_TOKEN", raising=False)
    client = TestClient(app)
    open_session()

    event = {
        "local_id": "local-negative",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "location-a",
        "event_type": "scan",
        "payload": {
            "line_id": "line-negative",
            "barcode": "5000213014231",
            "quantity_decimal": "-1",
            "product": {
                "id": "product-negative",
                "barcode": "5000213014231",
                "name": "Bad Quantity",
                "draft_status": "confirmed",
            },
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-a:local-negative",
    }

    response = client.post("/sync/events", json={"events": [event]})
    assert response.status_code == 200
    assert response.json()["events"][0]["status"] == "rejected"
    assert "Quantity cannot be negative" in response.json()["events"][0]["error"]


def test_scanner_lookup_returns_enrichment_for_unknown_barcode(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setattr(
        "app.routers.sync.fetch_product_suggestion",
        lambda barcode: {
            "barcode": barcode,
            "name": "Suggested Bottle",
            "category": "Spirits",
            "size": "70cl",
            "unit": "bottle",
            "image_url": "https://example.com/bottle.jpg",
            "confidence": 0.82,
        },
    )
    client = TestClient(app)

    response = client.get("/products/lookup/5012345678900")

    assert response.status_code == 200
    assert response.json()["exists"] is False
    assert response.json()["suggested"]["name"] == "Suggested Bottle"


def test_scanner_lookup_returns_procurewizard_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setattr(
        "app.routers.sync.fetch_product_suggestion",
        lambda barcode: {"barcode": barcode, "name": "Grey Goose Vodka", "category": "Spirits", "size": "70cl"},
    )
    database.init_db()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO procurewizard_imports
                (id, filename, encoding, metadata_json, header_json, row_count, active, created_at)
            VALUES ('pw-active', 'pw.csv', 'utf-8', '[]', '[]', 1, 1, '2026-06-06')
            """
        )
        db.execute(
            """
            INSERT INTO products
                (id, barcode, bin, name, category, size, unit, draft_status, product_updated_at)
            VALUES ('procurewizard-100', '100', 'B-10', 'Grey Goose Vodka', 'Spirits', '70cl', 'case', 'confirmed', '2026-06-06')
            """
        )
        db.execute(
            """
            INSERT INTO procurewizard_rows
                (id, import_id, row_index, pid, bin_number, pos, category, description, pack_size,
                 raw_json, product_id, match_status, match_score, created_at, updated_at)
            VALUES
                ('pw-row-1', 'pw-active', 2, '100', 'B-10', '', 'Spirits', 'Grey Goose Vodka',
                 '70cl', '[]', 'procurewizard-100', 'imported', 1, '2026-06-06', '2026-06-06')
            """
        )
        db.commit()
    client = TestClient(app)

    response = client.get("/products/lookup/5012345678900")

    assert response.status_code == 200
    assert response.json()["procurewizard_matches"][0]["product"]["id"] == "procurewizard-100"
    assert response.json()["procurewizard_matches"][0]["score"] >= 0.9


def test_typed_description_returns_procurewizard_suggestions(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO procurewizard_imports
                (id, filename, encoding, metadata_json, header_json, row_count, active, created_at)
            VALUES ('pw-active', 'pw.csv', 'utf-8', '[]', '[]', 1, 1, '2026-06-09')
            """
        )
        db.execute(
            """
            INSERT INTO products
                (id, barcode, name, category, size, unit, draft_status, product_updated_at)
            VALUES ('procurewizard-200', '200', 'Monkey 47 Schwarzwald Dry Gin', 'Gin', '50cl', 'case', 'confirmed', '2026-06-09')
            """
        )
        db.execute(
            """
            INSERT INTO procurewizard_rows
                (id, import_id, row_index, pid, category, description, pack_size, raw_json,
                 product_id, match_status, match_score, created_at, updated_at)
            VALUES ('pw-row-2', 'pw-active', 2, '200', 'Gin', 'Monkey 47 Schwarzwald Dry Gin',
                    '6 x 50cl', '[]', 'procurewizard-200', 'imported', 1, '2026-06-09', '2026-06-09')
            """
        )
        db.commit()
    client = TestClient(app)

    response = client.get("/products/matches", params={"name": "Monkey 47"})

    assert response.status_code == 200
    assert response.json()["matches"][0]["product"]["id"] == "procurewizard-200"
    assert all("Monkey" in match["description"] for match in response.json()["matches"])


def test_raw_scanned_export_includes_unmapped_draft_without_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO stocktake_lines
                (id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                 product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes)
            VALUES
                ('raw-line', 'raw-session', 'main-bar', NULL, '9990001112223', '',
                 'Unmapped scanned product', '3', 'draft', '2026-06-07T10:00:00Z', 'phone-a', '')
            """
        )
        db.commit()
    client = TestClient(app)

    response = client.get("/export/scanned/raw-session")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="scanned-lines-raw-session.xlsx"'
    assert len(response.content) > 1000


def test_sync_rejects_closed_session_without_blocking_valid_event(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    database.init_db()
    with database.get_db() as db:
        db.execute("INSERT INTO sessions (id, name, period_date, status) VALUES ('closed', 'Closed', '2026-06-09', 'archived')")
        db.execute("INSERT INTO sessions (id, name, period_date, status) VALUES ('open', 'Open', '2026-06-10', 'open')")
        db.commit()
    client = TestClient(app)

    def scan(local_id, session_id, line_id):
        return {
            "local_id": local_id,
            "device_id": "device-a",
            "session_id": session_id,
            "location_id": "main",
            "event_type": "scan",
            "payload": {
                "line_id": line_id,
                "barcode": local_id,
                "quantity_decimal": "1",
                "product": {"id": f"p-{local_id}", "barcode": local_id, "name": local_id, "draft_status": "confirmed"},
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": f"device-a:{local_id}",
        }

    response = client.post("/sync/events", json={"events": [scan("bad", "closed", "bad-line"), scan("good", "open", "good-line")]})
    assert {row["local_id"]: row["status"] for row in response.json()["events"]} == {"bad": "rejected", "good": "synced"}


def test_sync_prevents_cross_device_line_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    with database.get_db() as db:
        db.execute("INSERT INTO sessions (id, name, period_date, status) VALUES ('s1', 'S1', '2026-06-10', 'open')")
        db.execute(
            """
            INSERT INTO stocktake_lines
                (id, session_id, location_id, quantity_decimal, draft_status, counted_at, device_id)
            VALUES ('line-a', 's1', 'main', '1', 'confirmed', ?, 'device-a')
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        db.commit()
    client = TestClient(app)
    event = {
        "local_id": "edit-other",
        "device_id": "device-b",
        "session_id": "s1",
        "location_id": "main",
        "event_type": "quantity_edit",
        "payload": {"line_id": "line-a", "new_quantity": "99"},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-b:edit-other",
    }
    assert client.post("/sync/events", json={"events": [event]}).json()["events"][0]["status"] == "rejected"
    with database.get_db() as db:
        assert db.execute("SELECT quantity_decimal FROM stocktake_lines WHERE id = 'line-a'").fetchone()["quantity_decimal"] == "1"
