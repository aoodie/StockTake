from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app import database

def test_sync_idempotency_ignores_duplicate_events(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
    client = TestClient(app)

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
        row = db.execute("SELECT quantity_decimal FROM stocktake_lines WHERE id = 'line-a'").fetchone()
        audit = db.execute("SELECT new_quantity FROM quantity_audit WHERE line_id = 'line-a'").fetchone()
    assert row["quantity_decimal"] == "0"
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
    assert response.status_code == 400
    assert "Quantity cannot be negative" in response.json()["detail"]


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
