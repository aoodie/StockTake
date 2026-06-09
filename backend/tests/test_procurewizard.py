from datetime import datetime, timezone

from app import database
from app.services.procurewizard import (
    build_procurewizard_csv,
    import_summary,
    import_procurewizard_csv,
    link_procurewizard_row,
    parse_procurewizard_csv_bytes,
)


def sample_csv() -> str:
    return (
        "21041,928291,<-- Do not delete or edit,,,,,,,\r\n"
        "PID,[E]Bin number,[E]Pos,Tertiary Category,Brand & Description,Pack Size,Est FC,Est SC,[E]Close FC,[E]Close SC\r\n"
        "3862551,3862551,0,Bourbon / American Whiskey,Jack Daniels Rye,1 x 70 cl [1],0,0,,\r\n"
        "675430,675430,19264,Rosé Wine,\"Mirabeau Pure Rosé, Côtes de Provence\",6 x 75 cl [6],0,0,,\r\n"
    )


def test_procurewizard_parser_accepts_cp1252_metadata_and_header():
    parsed = parse_procurewizard_csv_bytes(sample_csv().encode("cp1252"))

    assert parsed.encoding == "utf-8-sig" or parsed.encoding == "cp1252"
    assert parsed.metadata[2] == "<-- Do not delete or edit"
    assert parsed.header[4] == "Brand & Description"
    assert len(parsed.rows) == 2
    assert parsed.rows[1][4] == "Mirabeau Pure Rosé, Côtes de Provence"


def test_procurewizard_parser_accepts_short_metadata_and_empty_trailing_column():
    csv_text = (
        "21041,939303,<-- Do not delete or edit\r\n"
        "PID,[E]Bin number,[E]Pos,Tertiary Category,Brand & Description,Pack Size,Est FC,Est SC,[E]Close FC,[E]Close SC\r\n"
        '"3862551","3862551","0","Bourbon / American Whiskey","Jack Daniels Rye","1 x 70 cl [1]","1","0","","",\r\n'
    )

    parsed = parse_procurewizard_csv_bytes(csv_text.encode("cp1252"))

    assert len(parsed.metadata) == 3
    assert len(parsed.rows[0]) == 11
    assert parsed.rows[0][10] == ""


def test_procurewizard_parser_accepts_header_without_metadata():
    csv_text = "\r\n".join(sample_csv().splitlines()[1:]) + "\r\n"

    parsed = parse_procurewizard_csv_bytes(csv_text.encode("cp1252"))

    assert parsed.metadata == []
    assert parsed.header[0] == "PID"
    assert len(parsed.rows) == 2


def test_procurewizard_parser_rejects_non_empty_trailing_column():
    csv_text = sample_csv().replace("0,0,,\r\n", "0,0,,,unexpected\r\n", 1)

    try:
        parse_procurewizard_csv_bytes(csv_text.encode("cp1252"))
    except ValueError as exc:
        assert str(exc) == "ProcureWizard CSV row 3 has unexpected data after column 10."
    else:
        raise AssertionError("Expected non-empty trailing column to be rejected")


def test_procurewizard_import_creates_catalog_products_and_round_trips_export(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db(force=True)

    with database.get_db() as db:
        result = import_procurewizard_csv(db, "pw.csv", sample_csv())

    assert result["row_count"] == 2
    assert result["imported_count"] == 2

    now = datetime.now(timezone.utc).isoformat()
    with database.get_db() as db:
        product = db.execute("SELECT id, barcode, name, bin FROM products WHERE id = 'procurewizard-3862551'").fetchone()
        assert product["barcode"] == "3862551"
        assert product["name"] == "Jack Daniels Rye"
        assert product["bin"] == "3862551"
        db.execute(
            """
            INSERT INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes
            )
            VALUES ('line-pw', 'session-pw', 'cellar', 'procurewizard-3862551', '3862551', '3862551',
                    'Jack Daniels Rye', '11.5', 'confirmed', ?, 'device-a', '')
            """,
            (now,),
        )
        db.commit()
        filename, payload = build_procurewizard_csv(db, "session-pw")

    exported = payload.decode("cp1252")
    assert filename == "procurewizard-session-pw.csv"
    assert "21041,928291,<-- Do not delete or edit" in exported
    assert "3862551,3862551,0,Bourbon / American Whiskey,Jack Daniels Rye,1 x 70 cl [1],0,0,,11.5" in exported
    assert "675430,675430,19264,Rosé Wine,\"Mirabeau Pure Rosé, Côtes de Provence\",6 x 75 cl [6],0,0,," in exported


def test_manual_procurewizard_link_persists_as_pid_alias_across_reimport(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db(force=True)

    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO products (id, barcode, bin, name, category, size, unit, draft_status, product_updated_at)
            VALUES ('product-real-jd', '5010327001234', 'W-01', 'Jack Daniels Rye Real', 'Whiskey', '70cl', 'bottle', 'confirmed', ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        result = import_procurewizard_csv(db, "pw.csv", sample_csv())
        row_id = f"{result['import_id']}-2"
        linked = link_procurewizard_row(db, row_id, "product-real-jd")
        assert linked["status"] == "linked"

    with database.get_db() as db:
        alias = db.execute("SELECT product_id, label FROM product_barcodes WHERE barcode = '3862551'").fetchone()
        assert alias["product_id"] == "product-real-jd"
        assert alias["label"] == "ProcureWizard PID"
        second = import_procurewizard_csv(db, "pw2.csv", sample_csv())
        row = db.execute(
            "SELECT product_id, match_reason FROM procurewizard_rows WHERE import_id = ? AND pid = '3862551'",
            (second["import_id"],),
        ).fetchone()
        assert row["product_id"] == "product-real-jd"
        assert row["match_reason"] == "pid/barcode match"


def test_procurewizard_session_summary_separates_mapped_and_unmapped_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db(force=True)
    now = datetime.now(timezone.utc).isoformat()

    with database.get_db() as db:
        import_procurewizard_csv(db, "pw.csv", sample_csv())
        db.execute(
            """
            INSERT INTO products (id, barcode, name, category, size, unit, draft_status, product_updated_at)
            VALUES ('outside-pw', '999', 'Outside PW', '', '', 'each', 'confirmed', ?)
            """,
            (now,),
        )
        db.executemany(
            """
            INSERT INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes
            ) VALUES (?, 'session-summary', 'cellar', ?, ?, '', ?, ?, 'confirmed', ?, 'device-a', '')
            """,
            [
                ("line-mapped", "procurewizard-3862551", "3862551", "Jack Daniels Rye", "4", now),
                ("line-unmapped", "outside-pw", "999", "Outside PW", "2", now),
            ],
        )
        db.commit()
        summary = import_summary(db, "session-summary")

    assert summary["session"]["product_count"] == 2
    assert summary["session"]["pw_product_count"] == 1
    assert summary["session"]["pw_quantity_total"] == "4"
    assert summary["session"]["unmapped_product_count"] == 1
    assert summary["rows"][0]["description"] == "Jack Daniels Rye"
    assert summary["rows"][0]["counted_quantity"] == 4


def test_procurewizard_export_rejects_session_without_linked_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db(force=True)
    now = datetime.now(timezone.utc).isoformat()

    with database.get_db() as db:
        import_procurewizard_csv(db, "pw.csv", sample_csv())
        db.execute(
            """
            INSERT INTO products (id, barcode, name, category, size, unit, draft_status, product_updated_at)
            VALUES ('outside-pw', '999', 'Outside PW', '', '', 'each', 'confirmed', ?)
            """,
            (now,),
        )
        db.execute(
            """
            INSERT INTO stocktake_lines (
                id, session_id, location_id, product_id, barcode_snapshot, bin_snapshot,
                product_name_snapshot, quantity_decimal, draft_status, counted_at, device_id, notes
            ) VALUES ('line-outside', 'session-no-pw', 'cellar', 'outside-pw', '999', '', 'Outside PW',
                      '2', 'confirmed', ?, 'device-a', '')
            """,
            (now,),
        )
        db.commit()
        try:
            build_procurewizard_csv(db, "session-no-pw")
        except ValueError as exc:
            assert "no ProcureWizard-linked counted products" in str(exc)
        else:
            raise AssertionError("Expected ProcureWizard export to reject an unchanged template")
