from datetime import datetime, timezone

from app import database
from app.services.procurewizard import (
    build_procurewizard_csv,
    import_procurewizard_csv,
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
