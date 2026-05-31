from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import database, auth

def test_weak_password_validation():
    auth.validate_password_strength("demo")
    with pytest.raises(ValueError):
        auth.validate_password_strength("admin")
    with pytest.raises(ValueError):
        auth.validate_password_strength("1234")
    # This should pass:
    auth.validate_password_strength("secure-password-123")


def test_weak_password_can_be_explicitly_allowed_for_temporary_demo(monkeypatch):
    monkeypatch.setenv("ALLOW_WEAK_ADMIN_PASSWORD", "1")
    auth.validate_password_strength("demo")


def test_mapping_page_is_served():
    client = TestClient(app)
    response = client.get("/mapping")
    assert response.status_code == 200
    assert "mapping.js?v=phone-mapping-1" in response.text


def test_secure_session_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db()
    
    token = auth.create_admin_session()
    assert token
    assert auth.validate_admin_session(token) is True
    
    auth.revoke_admin_session(token)
    assert auth.validate_admin_session(token) is False


def test_draft_product_event_creates_admin_task(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    monkeypatch.setenv("STOCKTAKE_AUTO_ENRICH", "0")
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

    with database.get_db() as db:
        task = db.execute("SELECT barcode, status, draft_product_id FROM product_tasks").fetchone()

    assert task["barcode"] == "12345"
    assert task["status"] == "queued"
    assert task["draft_product_id"] == "draft-12345"


def test_draft_product_event_auto_enriches_and_prefills_draft(tmp_path, monkeypatch):
    from app.routers import sync

    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    monkeypatch.delenv("STOCKTAKE_AUTO_ENRICH", raising=False)
    monkeypatch.setattr(
        sync,
        "fetch_product_suggestion",
        lambda barcode: {
            "barcode": barcode,
            "name": "Auto Filled Lager",
            "brand": "Demo Brewery",
            "category": "Beer",
            "size": "330ml",
            "unit": "bottle",
            "image_url": "https://example.test/lager.jpg",
            "image_candidates": ["https://example.test/lager.jpg"],
            "source_urls": ["https://example.test/product/98765"],
            "source_name": "Test Provider",
            "confidence": 0.91,
        },
    )
    client = TestClient(app)

    event = {
        "local_id": "draft-auto",
        "device_id": "device-a",
        "session_id": "session-a",
        "location_id": "main-bar",
        "event_type": "draft_product",
        "payload": {
            "product_id": "draft-98765",
            "barcode": "98765",
            "placeholder_name": "Draft 98765",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "device-a:draft-auto",
    }

    response = client.post("/sync/events", json={"events": [event]})
    assert response.status_code == 200

    with database.get_db() as db:
        task = db.execute("SELECT status, suggested_json FROM product_tasks WHERE barcode = '98765'").fetchone()
        product = db.execute(
            "SELECT name, category, size, unit, photo_url, draft_status FROM products WHERE id = 'draft-98765'"
        ).fetchone()

    assert task["status"] == "review_needed"
    assert "Auto Filled Lager" in task["suggested_json"]
    assert product["name"] == "Auto Filled Lager"
    assert product["category"] == "Beer"
    assert product["size"] == "330ml"
    assert product["unit"] == "bottle"
    assert product["photo_url"] == "https://example.test/lager.jpg"
    assert product["draft_status"] == "draft"


def test_admin_login_and_task_approval_confirms_product(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    
    with database.get_db() as db:
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

    tasks = client.get("/admin/api/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["tasks"][0]["barcode"] == "abc"

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

    with database.get_db() as db:
        product = db.execute("SELECT name, bin, draft_status FROM products WHERE id = 'draft-abc'").fetchone()
        task = db.execute("SELECT status, approved_at FROM product_tasks WHERE id = 'task-abc'").fetchone()

    assert product["name"] == "Approved Product"
    assert product["bin"] == "A-101"
    assert product["draft_status"] == "confirmed"
    assert task["status"] == "approved"
    assert task["approved_at"]


def test_admin_only_management_routes_and_status_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()

    session_payload = {"id": "session-a", "name": "Session A", "period_date": "2026-05-30"}
    assert client.post("/sessions", json=session_payload).status_code == 401

    login = client.post("/admin/api/login", json={"password": "stocktake-admin"})
    assert login.status_code == 200
    assert client.post("/sessions", json=session_payload).status_code == 200

    invalid_product = client.post(
        "/admin/api/products",
        json={
            "barcode": "invalid-status",
            "name": "Invalid Status",
            "draft_status": "done",
        },
    )
    assert invalid_product.status_code == 422

    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO product_tasks (
                id, barcode, status, source, draft_product_id, suggested_json, created_at, updated_at
            )
            VALUES ('task-invalid', 'invalid', 'queued', 'scanner', NULL, '{}', ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()

    invalid_task = client.patch("/admin/api/tasks/task-invalid", json={"status": "done"})
    assert invalid_task.status_code == 422

    assert client.patch("/admin/api/products/missing", json={"barcode": ""}).status_code in {400, 404}


def test_product_alias_issue_detail_and_merge_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    first = client.post(
        "/admin/api/products",
        json={
            "barcode": "111",
            "name": "House Merlot",
            "bin": "W-01",
            "category": "Wine",
            "size": "75cl",
            "unit": "bottle",
        },
    )
    second = client.post(
        "/admin/api/products",
        json={
            "barcode": "222",
            "name": "House Merlot",
            "bin": "",
            "category": "Wine",
            "size": "75cl",
            "unit": "bottle",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    alias = client.post(
        "/admin/api/products/product-111/barcodes",
        json={"barcode": "case-111", "label": "Case barcode"},
    )
    assert alias.status_code == 200

    search = client.get("/admin/api/products?search=case-111")
    assert search.status_code == 200
    assert search.json()["products"][0]["id"] == "product-111"
    assert search.json()["products"][0]["barcode_count"] == 2

    conflict = client.post(
        "/admin/api/products/product-222/barcodes",
        json={"barcode": "case-111", "label": "Duplicate alias"},
    )
    assert conflict.status_code == 400

    issues = client.get("/admin/api/products/issues")
    assert issues.status_code == 200
    issue_names = {
        issue
        for row in issues.json()["issues"]
        for issue in row["issues"]
    }
    assert {"missing_bin", "possible_duplicate"}.issubset(issue_names)

    now = datetime.now(timezone.utc).isoformat()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes
            )
            VALUES ('line-merge', 'session-a', 'cellar', 'product-222', '222', '', 'House Merlot', '1', 'confirmed', ?, 'device-a', '')
            """,
            (now,),
        )
        db.commit()

    merged = client.post(
        "/admin/api/products/merge",
        json={"source_product_id": "product-222", "target_product_id": "product-111"},
    )
    assert merged.status_code == 200

    detail = client.get("/admin/api/products/product-111")
    assert detail.status_code == 200
    product = detail.json()["product"]
    barcodes = {row["barcode"] for row in product["barcodes"]}
    assert {"111", "222", "case-111"}.issubset(barcodes)
    assert product["count_history"][0]["session_id"] == "session-a"
    assert any(row["action"] == "merge_target_received" for row in product["audit"])

    assert client.get("/admin/api/products/product-222").status_code == 404


def test_barcode_mapping_queue_tracks_real_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    csv_text = "\n".join(
        [
            "21041,928291,<-- Do not delete or edit,,,,,,,",
            "PID,[E]Bin number,[E]Pos,Tertiary Category,Brand & Description,Pack Size,Est FC,Est SC,[E]Close FC,[E]Close SC",
            "3862551,3862551,,Whiskey,Jack Daniels Rye,1 x 70 cl [1],0,0,,",
        ]
    )
    imported = client.post(
        "/admin/api/procurewizard/import",
        json={"filename": "pw.csv", "csv_text": csv_text},
    )
    assert imported.status_code == 200

    queue = client.get("/admin/api/barcode-mapping/products?only_missing=true")
    assert queue.status_code == 200
    body = queue.json()
    assert body["total"] == 1
    product = body["products"][0]
    assert product["id"] == "procurewizard-3862551"
    assert product["procurewizard"]["pid"] == "3862551"
    assert product["needs_real_barcode"] is True

    mapped = client.post(
        "/admin/api/products/procurewizard-3862551/barcodes",
        json={"barcode": "5010327001234", "label": "Bottle barcode"},
    )
    assert mapped.status_code == 200

    lookup = client.get("/admin/api/barcode-mapping/barcodes/5010327001234")
    assert lookup.status_code == 200
    assert lookup.json()["owner"]["id"] == "procurewizard-3862551"

    missing = client.get("/admin/api/barcode-mapping/products?only_missing=true")
    assert missing.status_code == 200
    assert missing.json()["total"] == 0

    all_products = client.get("/admin/api/barcode-mapping/products?only_missing=false")
    assert all_products.status_code == 200
    assert all_products.json()["products"][0]["real_barcode_count"] == 1


def test_product_patch_rejects_barcode_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    for barcode in ("dup-a", "dup-b"):
        response = client.post(
            "/admin/api/products",
            json={"barcode": barcode, "name": f"Product {barcode}", "bin": "A-1"},
        )
        assert response.status_code == 200

    blank = client.patch("/admin/api/products/product-dup-a", json={"barcode": ""})
    assert blank.status_code == 400

    duplicate = client.patch("/admin/api/products/product-dup-a", json={"barcode": "dup-b"})
    assert duplicate.status_code == 400

    same_barcode = client.patch("/admin/api/products/product-dup-a", json={"barcode": "dup-a"})
    assert same_barcode.status_code == 400

    regular_edit = client.patch("/admin/api/products/product-dup-a", json={"bin": "A-2", "category": "Wine"})
    assert regular_edit.status_code == 200
