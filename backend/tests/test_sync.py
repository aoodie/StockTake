from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_sync_idempotency_ignores_duplicate_events(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "stocktake.db")
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

