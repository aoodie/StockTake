from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_draft_product_event_creates_admin_task(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)

    event = {
        "local_id": "draft-1",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "main-bar",
        "event_type": "draft_product",
        "payload": {
            "product_id": "draft-12345",
            "barcode": "12345",
            "placeholder_name": "Draft 12345",
            "notes": "Needs product mapping and BIN",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-a:draft-1",
    }

    response = client.post("/sync/events", json={"events": [event]})
    assert response.status_code == 200

    with main.get_db() as db:
        task = db.execute("SELECT barcode, status, draft_product_id FROM product_tasks").fetchone()

    assert task["barcode"] == "12345"
    assert task["status"] == "queued"
    assert task["draft_product_id"] == "draft-12345"


def test_admin_login_and_task_approval_confirms_product(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    main.init_db()
    with main.get_db() as db:
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES ('draft-abc', 'abc', '', 'Draft abc', '', '', 'each', '', '', 'draft', ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        db.execute(
            """
            INSERT INTO product_tasks (
                id, barcode, status, source, draft_product_id, created_at, updated_at
            )
            VALUES ('task-abc', 'abc', 'review_needed', 'scanner', 'draft-abc', ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()

    assert client.get("/admin/api/tasks").status_code == 401
    login = client.post("/admin/api/login", json={"password": "stocktake-admin"})
    assert login.status_code == 200

    approve = client.post(
        "/admin/api/tasks/task-abc/approve",
        json={
            "name": "Approved Product",
            "bin": "A-101",
            "category": "Spirit",
            "size": "70cl",
            "unit": "bottle",
            "photo_url": "",
            "notes": "Approved in admin",
        },
    )
    assert approve.status_code == 200

    with main.get_db() as db:
        product = db.execute("SELECT name, bin, draft_status FROM products WHERE id = 'draft-abc'").fetchone()
        task = db.execute("SELECT status, approved_at FROM product_tasks WHERE id = 'task-abc'").fetchone()

    assert product["name"] == "Approved Product"
    assert product["bin"] == "A-101"
    assert product["draft_status"] == "confirmed"
    assert task["status"] == "approved"
    assert task["approved_at"]
