from datetime import datetime, timezone
import csv
import io
import json
import zipfile
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
    assert "mapping.js?v=search-clear-1" in response.text


def test_admin_page_loads_ai_copilot_bundle():
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "AI Product Copilot" in response.text
    assert "admin.js?v=catalog-portability-1" in response.text


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


def test_draft_product_event_auto_enriches_task_without_mutating_draft(tmp_path, monkeypatch):
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
    assert product["name"] == "Draft 98765"
    assert product["category"] == ""
    assert product["size"] == ""
    assert product["unit"] == "each"
    assert product["photo_url"] is None
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


def test_admin_task_approval_cannot_steal_existing_barcode_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    owner = client.post(
        "/admin/api/products",
        json={"barcode": "owner-primary", "name": "Original Owner", "bin": "A-1"},
    )
    assert owner.status_code == 200
    alias = client.post(
        "/admin/api/products/product-owner-primary/barcodes",
        json={"barcode": "stolen", "label": "Bottle barcode"},
    )
    assert alias.status_code == 200

    now = datetime.now(timezone.utc).isoformat()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO product_tasks (
                id, barcode, status, source, draft_product_id, suggested_json, created_at, updated_at
            )
            VALUES ('task-stolen', 'stolen', 'review_needed', 'scanner', NULL, '{}', ?, ?)
            """,
            (now, now),
        )
        db.commit()

    approve = client.post(
        "/admin/api/tasks/task-stolen/approve",
        json={
            "name": "Stale Task Product",
            "bin": "B-2",
            "category": "",
            "size": "",
            "unit": "each",
            "photo_url": "",
            "notes": "",
        },
    )
    assert approve.status_code == 400

    lookup = client.get("/admin/api/products/lookup/stolen")
    assert lookup.status_code == 200
    assert lookup.json()["product"]["id"] == "product-owner-primary"
    assert lookup.json()["product"]["name"] == "Original Owner"
    assert client.get("/admin/api/products/product-stolen").status_code == 404


def test_admin_task_approval_with_draft_product_cannot_ignore_owned_barcode(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    owner = client.post(
        "/admin/api/products",
        json={"barcode": "owner-primary", "name": "Original Owner", "bin": "A-1"},
    )
    assert owner.status_code == 200
    alias = client.post(
        "/admin/api/products/product-owner-primary/barcodes",
        json={"barcode": "stolen-draft", "label": "Bottle barcode"},
    )
    assert alias.status_code == 200

    now = datetime.now(timezone.utc).isoformat()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO products (
                id, barcode, bin, name, category, size, unit, photo_url, notes,
                draft_status, product_updated_at
            )
            VALUES ('draft-owned', 'draft-owned-primary', '', 'Draft owned', '', '', 'each', '', '', 'draft', ?)
            """,
            (now,),
        )
        db.execute(
            """
            INSERT INTO product_tasks (
                id, barcode, status, source, draft_product_id, suggested_json, created_at, updated_at
            )
            VALUES ('task-stolen-draft', 'stolen-draft', 'review_needed', 'scanner', 'draft-owned', '{}', ?, ?)
            """,
            (now, now),
        )
        db.commit()

    approve = client.post(
        "/admin/api/tasks/task-stolen-draft/approve",
        json={
            "name": "Should Not Approve",
            "bin": "B-2",
            "category": "",
            "size": "",
            "unit": "each",
            "photo_url": "",
            "notes": "",
        },
    )
    assert approve.status_code == 400

    task = client.get("/admin/api/tasks").json()["tasks"][0]
    assert task["id"] == "task-stolen-draft"
    assert task["status"] == "review_needed"

    lookup = client.get("/admin/api/products/lookup/stolen-draft")
    assert lookup.status_code == 200
    assert lookup.json()["product"]["id"] == "product-owner-primary"


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
        db.execute(
            """
            INSERT INTO procurewizard_imports (
                id, filename, encoding, metadata_json, header_json, row_count, active, created_at
            )
            VALUES ('pw-merge', 'pw.csv', 'text', '[]', '[]', 1, 1, ?)
            """,
            (now,),
        )
        db.execute(
            """
            INSERT INTO procurewizard_rows (
                id, import_id, row_index, pid, bin_number, pos, category, description,
                pack_size, est_fc, est_sc, close_fc, close_sc, raw_json, product_id,
                match_status, match_score, match_reason, created_at, updated_at
            )
            VALUES (
                'pw-merge-2', 'pw-merge', 2, 'PW222', 'PW222', '', 'Wine', 'House Merlot',
                '75cl', '0', '0', '', '', '[]', 'product-222',
                'manual', 1, 'manual test link', ?, ?
            )
            """,
            (now, now),
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
    with database.get_db() as db:
        pw_row = db.execute("SELECT product_id FROM procurewizard_rows WHERE id = 'pw-merge-2'").fetchone()
        assert pw_row["product_id"] == "product-111"

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


def test_barcode_mapping_recent_and_undo_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    created = client.post(
        "/admin/api/products",
        json={"barcode": "primary-undo", "name": "Undo Test Product", "bin": "A-1"},
    )
    assert created.status_code == 200

    mapped = client.post(
        "/admin/api/products/product-primary-undo/barcodes",
        json={"barcode": "alias-undo", "label": "Bottle barcode", "source_screen": "phone_mapping"},
    )
    assert mapped.status_code == 200
    audit_id = mapped.json()["mapping_audit_id"]

    recent = client.get("/admin/api/barcode-mapping/recent")
    assert recent.status_code == 200
    rows = recent.json()["mappings"]
    assert rows[0]["id"] == audit_id
    assert rows[0]["barcode"] == "alias-undo"
    assert rows[0]["source"] == "phone_mapping"
    assert rows[0]["undone_at"] is None

    undone = client.post(f"/admin/api/barcode-mapping/recent/{audit_id}/undo")
    assert undone.status_code == 200

    lookup = client.get("/admin/api/barcode-mapping/barcodes/alias-undo")
    assert lookup.status_code == 200
    assert lookup.json()["owner"] is None

    second_undo = client.post(f"/admin/api/barcode-mapping/recent/{audit_id}/undo")
    assert second_undo.status_code == 400


def test_barcode_mapping_same_product_primary_is_not_audited_or_undoable(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    created = client.post(
        "/admin/api/products",
        json={"barcode": "primary-safe", "name": "Primary Safe Product", "bin": "A-1"},
    )
    assert created.status_code == 200

    remap_primary = client.post(
        "/admin/api/products/product-primary-safe/barcodes",
        json={"barcode": "primary-safe", "label": "Mapped barcode", "source_screen": "phone_mapping"},
    )
    assert remap_primary.status_code == 400

    alias = client.post(
        "/admin/api/products/product-primary-safe/barcodes",
        json={"barcode": "alias-safe", "label": "Bottle barcode", "source_screen": "phone_mapping"},
    )
    assert alias.status_code == 200

    remap_alias = client.post(
        "/admin/api/products/product-primary-safe/barcodes",
        json={"barcode": "alias-safe", "label": "Bottle barcode", "source_screen": "phone_mapping"},
    )
    assert remap_alias.status_code == 200
    assert remap_alias.json()["status"] == "already_mapped"
    assert remap_alias.json()["mapping_audit_id"] is None

    recent = client.get("/admin/api/barcode-mapping/recent")
    assert recent.status_code == 200
    alias_rows = [row for row in recent.json()["mappings"] if row["barcode"] == "alias-safe"]
    assert len(alias_rows) == 1

    detail = client.get("/admin/api/products/product-primary-safe").json()["product"]
    primary_alias = next(row for row in detail["barcodes"] if row["barcode"] == "primary-safe")
    assert primary_alias["is_primary"] == 1


def test_barcode_mapping_create_undo_blocked_after_later_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    created = client.post(
        "/admin/api/products",
        json={
            "barcode": "draft-safe",
            "name": "Draft Safe Product",
            "bin": "A-1",
            "draft_status": "draft",
            "source_screen": "phone_mapping",
        },
    )
    assert created.status_code == 200
    audit_id = created.json()["mapping_audit_id"]

    edited = client.patch("/admin/api/products/product-draft-safe", json={"bin": "B-2"})
    assert edited.status_code == 200

    undo = client.post(f"/admin/api/barcode-mapping/recent/{audit_id}/undo")
    assert undo.status_code == 400

    detail = client.get("/admin/api/products/product-draft-safe")
    assert detail.status_code == 200


def test_barcode_mapping_create_undo_blocked_after_bulk_update(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    created = client.post(
        "/admin/api/products",
        json={
            "barcode": "bulk-safe",
            "name": "Bulk Safe Product",
            "bin": "A-1",
            "draft_status": "draft",
            "source_screen": "phone_mapping",
        },
    )
    assert created.status_code == 200
    audit_id = created.json()["mapping_audit_id"]

    updated = client.post(
        "/admin/api/products/bulk-update",
        json={"product_ids": ["product-bulk-safe"], "bin": "B-2"},
    )
    assert updated.status_code == 200

    undo = client.post(f"/admin/api/barcode-mapping/recent/{audit_id}/undo")
    assert undo.status_code == 400

    detail = client.get("/admin/api/products/product-bulk-safe")
    assert detail.status_code == 200
    assert detail.json()["product"]["bin"] == "B-2"


def test_barcode_mapping_rejects_leading_zero_variant_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    first = client.post(
        "/admin/api/products",
        json={"barcode": "012345678905", "name": "UPC Variant Product", "bin": "A-1"},
    )
    assert first.status_code == 200

    duplicate = client.post(
        "/admin/api/products",
        json={"barcode": "12345678905", "name": "Duplicate UPC", "bin": "A-2"},
    )
    assert duplicate.status_code == 400

    lookup = client.get("/admin/api/products/lookup/12345678905")
    assert lookup.status_code == 200
    assert lookup.json()["exists"] is True
    assert lookup.json()["product"]["name"] == "UPC Variant Product"


def test_barcode_mapping_rejects_transitive_upc_ean_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    first = client.post(
        "/admin/api/products",
        json={"barcode": "0012345678905", "name": "EAN Variant Product", "bin": "A-1"},
    )
    assert first.status_code == 200

    for variant in ("012345678905", "12345678905"):
        lookup = client.get(f"/admin/api/products/lookup/{variant}")
        assert lookup.status_code == 200
        assert lookup.json()["exists"] is True
        assert lookup.json()["product"]["name"] == "EAN Variant Product"

        duplicate = client.post(
            "/admin/api/products",
            json={"barcode": variant, "name": f"Duplicate {variant}", "bin": "A-2"},
        )
        assert duplicate.status_code == 400

        other = client.post(
            "/admin/api/products/product-0012345678905/barcodes",
            json={"barcode": variant, "label": "Variant barcode", "source_screen": "phone_mapping"},
        )
        assert other.status_code in {200, 400}
        if other.status_code == 200:
            assert other.json()["status"] == "already_mapped"
            assert other.json()["mapping_audit_id"] is None


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


def test_ai_copilot_generates_and_applies_product_issue_suggestion(tmp_path, monkeypatch):
    from app.routers import ai
    from app.services import enrichment

    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "")
    monkeypatch.setattr(
        ai,
        "fetch_product_suggestion",
        lambda barcode: {
            "barcode": barcode,
            "name": "AI Filled Lager",
            "brand": "Demo Brewery",
            "category": "Beer",
            "size": "330ml",
            "unit": "bottle",
            "image_url": "https://example.test/lager.jpg",
            "image_candidates": ["https://example.test/lager.jpg"],
            "source_urls": ["https://example.test/product/501"],
            "source_name": "Test Lookup",
            "confidence": 0.88,
        },
    )
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    product = client.post(
        "/admin/api/products",
        json={
            "barcode": "501",
            "name": "Draft 501",
            "bin": "",
            "unit": "each",
            "draft_status": "draft",
        },
    )
    assert product.status_code == 200

    generated = client.post("/admin/api/ai-suggestions/generate-issues", json={"limit": 5})
    assert generated.status_code == 200
    suggestions = generated.json()["suggestions"]
    assert suggestions
    suggestion = suggestions[0]
    assert suggestion["status"] == "pending"
    assert suggestion["field_values"]["name"] == "AI Filled Lager"
    assert suggestion["field_values"]["unit"] == "bottle"

    listed = client.get("/admin/api/ai-suggestions")
    assert listed.status_code == 200
    assert listed.json()["suggestions"][0]["id"] == suggestion["id"]

    empty_apply = client.post(f"/admin/api/ai-suggestions/{suggestion['id']}/apply", json={})
    assert empty_apply.status_code == 422

    applied = client.post(
        f"/admin/api/ai-suggestions/{suggestion['id']}/apply",
        json={"fields": ["name", "category", "size", "unit", "photo_url", "draft_status"]},
    )
    assert applied.status_code == 200
    assert set(applied.json()["fields"]).issuperset({"name", "category", "size", "unit", "photo_url"})

    detail = client.get("/admin/api/products/product-501")
    assert detail.status_code == 200
    applied_product = detail.json()["product"]
    assert applied_product["name"] == "AI Filled Lager"
    assert applied_product["category"] == "Beer"
    assert applied_product["size"] == "330ml"
    assert applied_product["unit"] == "bottle"
    assert applied_product["photo_url"] == "https://example.test/lager.jpg"
    assert applied_product["draft_status"] == "confirmed"


def test_ai_copilot_reject_keeps_catalog_unchanged(tmp_path, monkeypatch):
    from app.routers import ai
    from app.services import enrichment

    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "")
    monkeypatch.setattr(
        ai,
        "fetch_product_suggestion",
        lambda barcode: {
            "barcode": barcode,
            "name": "Rejected AI Name",
            "category": "Wine",
            "size": "75cl",
            "unit": "bottle",
            "image_url": "",
            "source_urls": [],
            "source_name": "Test Lookup",
            "confidence": 0.8,
        },
    )
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200
    assert client.post(
        "/admin/api/products",
        json={"barcode": "777", "name": "Draft 777", "bin": "", "draft_status": "draft"},
    ).status_code == 200

    generated = client.post(
        "/admin/api/ai-suggestions/generate",
        json={"product_id": "product-777", "force": True},
    )
    assert generated.status_code == 200
    suggestion_id = generated.json()["suggestion"]["id"]

    rejected = client.post(f"/admin/api/ai-suggestions/{suggestion_id}/reject", json={})
    assert rejected.status_code == 200

    detail = client.get("/admin/api/products/product-777").json()["product"]
    assert detail["name"] == "Draft 777"
    assert detail["category"] == ""


def test_admin_can_change_openai_model_and_token_setting(tmp_path, monkeypatch):
    from app.routers import ai
    from app.services import enrichment

    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-env-default")
    monkeypatch.setattr(enrichment, "DEFAULT_OPENAI_MODEL", "gpt-env-default")
    monkeypatch.setattr(enrichment, "OPENAI_API_KEY_FILE", tmp_path / "openai_api_key.txt")
    client = TestClient(app)
    database.init_db()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200

    current = client.get("/admin/api/settings/llm")
    assert current.status_code == 200
    assert current.json()["openai_model"] == "gpt-env-default"
    assert current.json()["has_openai_key"] is False
    missing_test = client.post("/admin/api/settings/llm/test", json={})
    assert missing_test.status_code == 400
    assert missing_test.json()["detail"] == "No OpenAI token is configured."

    saved = client.patch(
        "/admin/api/settings/llm",
        json={"openai_model": "gpt-4.1", "openai_api_key": "sk-test-token-1234567890"},
    )
    assert saved.status_code == 200
    assert saved.json()["openai_model"] == "gpt-4.1"
    assert saved.json()["has_openai_key"] is True
    assert saved.json()["openai_key_source"] == "admin"
    assert enrichment.openai_model() == "gpt-4.1"
    assert enrichment.openai_api_key() == "sk-test-token-1234567890"
    monkeypatch.setattr(
        ai,
        "test_openai_connection",
        lambda: {"ok": True, "model": "gpt-4.1", "message": "Connected. Model gpt-4.1 is available."},
    )
    connected = client.post("/admin/api/settings/llm/test", json={})
    assert connected.status_code == 200
    assert connected.json()["ok"] is True
    assert connected.json()["has_openai_key"] is True

    invalid = client.patch("/admin/api/settings/llm", json={"openai_model": "bad model name"})
    assert invalid.status_code == 400

    too_short = client.patch(
        "/admin/api/settings/llm",
        json={"openai_model": "gpt-4.1", "openai_api_key": "short"},
    )
    assert too_short.status_code == 400

    cleared = client.patch(
        "/admin/api/settings/llm",
        json={"openai_model": "gpt-4.1", "clear_openai_api_key": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_openai_key"] is False
    assert enrichment.openai_api_key() == ""


def test_bin_cleanup_does_not_approve_draft_and_session_archive_preserves_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    client = TestClient(app)
    database.init_db()
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO products (id, barcode, bin, name, unit, draft_status, product_updated_at)
            VALUES ('draft-1', '123', '', 'Draft', 'each', 'draft', ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        db.execute("INSERT INTO sessions (id, name, period_date, status) VALUES ('s1', 'Trial', '2026-06-10', 'open')")
        db.execute(
            """
            INSERT INTO stocktake_lines
                (id, session_id, quantity_decimal, draft_status, counted_at, device_id)
            VALUES ('line-1', 's1', '1', 'confirmed', ?, 'phone-a')
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        db.commit()
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200
    assert client.patch("/products/draft-1/bin", json={"bin": "A-1"}).status_code == 200
    assert client.delete("/admin/api/sessions/s1").status_code == 200
    with database.get_db() as db:
        assert db.execute("SELECT draft_status FROM products WHERE id = 'draft-1'").fetchone()["draft_status"] == "draft"
        assert db.execute("SELECT status FROM sessions WHERE id = 's1'").fetchone()["status"] == "archived"
        assert db.execute("SELECT COUNT(*) AS c FROM stocktake_lines WHERE session_id = 's1'").fetchone()["c"] == 1


def test_catalog_exports_are_reimportable_and_backup_includes_photos(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "stocktake-admin")
    database.init_db()
    image_dir = tmp_path / "product-images"
    image_dir.mkdir()
    (image_dir / "gin.png").write_bytes(b"fake-png")
    current = datetime.now(timezone.utc).isoformat()
    with database.get_db() as db:
        db.executemany(
            """
            INSERT INTO products (id, barcode, bin, name, category, size, unit, photo_url, draft_status, product_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("gin-1", "500001", "A-1", "House Gin", "Gin", "70cl", "bottle", "/product-images/gin.png", "confirmed", current),
                ("wine-1", None, "W-1", "House Wine", "Wine", "75cl", "bottle", None, "confirmed", current),
            ],
        )
        db.executemany(
            "INSERT INTO product_barcodes (barcode, product_id, label, is_primary, created_at) VALUES (?, 'gin-1', ?, ?, ?)",
            [
                ("500001", "Primary barcode", 1, current),
                ("500002", "Mapped bottle barcode", 0, current),
            ],
        )
        db.execute(
            """
            INSERT INTO barcode_mapping_audit (barcode, product_id, product_name, action, label, source, details_json, created_at)
            VALUES ('500002', 'gin-1', 'House Gin', 'added', 'Mapped bottle barcode', 'phone_mapping', '{}', ?)
            """,
            (current,),
        )
        db.commit()

    client = TestClient(app)
    assert client.post("/admin/api/login", json={"password": "stocktake-admin"}).status_code == 200
    summary = client.get("/admin/api/catalog-export/summary")
    assert summary.json()["mapped_products"] == 1
    assert summary.json()["unmapped_products"] == 1

    mapped = client.get("/admin/api/catalog-export/products.csv?scope=mapped")
    assert mapped.status_code == 200
    mapped_text = mapped.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(mapped_text)))
    assert [row["product_id"] for row in rows] == ["gin-1"]
    assert {alias["barcode"] for alias in json.loads(rows[0]["barcodes_json"])} == {"500001", "500002"}

    backup = client.get("/admin/api/catalog-export/backup.zip")
    assert backup.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert "catalog/mapped-products.csv" in archive.namelist()
        assert "catalog/mapping-audit.csv" in archive.namelist()
        assert archive.read("product-images/gin.png") == b"fake-png"

    with database.get_db() as db:
        db.execute("DELETE FROM product_barcodes")
        db.execute("DELETE FROM products")
        db.commit()
    restored = client.post(
        "/admin/api/catalog-export/restore",
        json={"filename": "mapped-products.csv", "csv_text": mapped_text},
    )
    assert restored.status_code == 200
    assert restored.json()["restored_products"] == 1
    assert restored.json()["restored_barcodes"] == 2
    with database.get_db() as db:
        assert db.execute("SELECT name FROM products WHERE id = 'gin-1'").fetchone()["name"] == "House Gin"
        assert db.execute("SELECT COUNT(*) AS c FROM product_barcodes WHERE product_id = 'gin-1'").fetchone()["c"] == 2
        db.execute(
            """
            INSERT INTO products (id, barcode, name, unit, draft_status, product_updated_at)
            VALUES ('conflict', '500002', 'Conflicting Product', 'each', 'confirmed', ?)
            """,
            (current,),
        )
        db.commit()
    conflict = client.post(
        "/admin/api/catalog-export/restore",
        json={"filename": "mapped-products.csv", "csv_text": mapped_text},
    )
    assert conflict.status_code == 400
    assert "primary barcode for product conflict" in conflict.json()["detail"]
