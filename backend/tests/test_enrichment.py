from datetime import datetime, timedelta, timezone

from app import database
from app.services import enrichment


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, responses=None, post_response=None, **_kwargs):
        self.responses = iter(responses or [])
        self.post_response = post_response

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url):
        return next(self.responses)

    def post(self, *_args, **_kwargs):
        return self.post_response


def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stocktake.db")
    database.init_db(force=True)


def test_lookup_tries_other_open_facts_sources(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    responses = [
        FakeResponse({"status": 0}, 404),
        FakeResponse(
            {
                "status": 1,
                "product": {
                    "product_name": "Hotel Shampoo",
                    "brands": "Example",
                    "quantity": "250ml",
                    "categories_tags": ["en:shampoo"],
                    "image_front_url": "https://images.example/shampoo.jpg",
                },
            }
        ),
    ]
    monkeypatch.setattr(enrichment.httpx, "Client", lambda **kwargs: FakeClient(responses=responses, **kwargs))
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "")

    result = enrichment.fetch_product_suggestion("5012345678900")

    assert result["name"] == "Example Hotel Shampoo"
    assert result["source_name"] == "Open Products Facts"
    assert result["lookup_sources"] == ["Open Products Facts"]
    assert result["lookup_cache_version"] == enrichment.LOOKUP_CACHE_VERSION


def test_stale_failed_lookup_cache_is_retried(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    with database.get_db() as db:
        db.execute(
            """
            INSERT INTO product_lookup_cache (barcode, suggested_json, cached_at)
            VALUES ('123', '{"barcode":"123","name":"Product 123","confidence":0.25}', 'old')
            """
        )
        db.commit()
    responses = [
        FakeResponse(
            {
                "status": 1,
                "product": {"product_name": "Recovered Product"},
            }
        ),
    ]
    monkeypatch.setattr(enrichment.httpx, "Client", lambda **kwargs: FakeClient(responses=responses, **kwargs))
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "")

    result = enrichment.fetch_product_suggestion("123")

    assert result["name"] == "Recovered Product"
    assert result["source_name"] == "Open Food Facts"


def test_openai_web_search_requires_cited_sources(monkeypatch):
    cited = FakeResponse(
        {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"name":"Example Gin","brand":"Example","category":"Gin","size":"70cl","unit":"bottle","confidence":0.9}',
                            "annotations": [{"type": "url_citation", "url": "https://example.com/gin"}],
                        }
                    ]
                }
            ]
        }
    )
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "test-key")
    monkeypatch.setattr(enrichment.httpx, "Client", lambda **kwargs: FakeClient(post_response=cited, **kwargs))

    result = enrichment.openai_web_search_product("5000000000000")

    assert result["name"] == "Example Gin"
    assert result["source_name"] == "OpenAI web search"
    assert result["source_urls"] == ["https://example.com/gin"]
    assert result["confidence"] == 0.68


def test_openai_web_search_rejects_uncited_identity(monkeypatch):
    uncited = FakeResponse(
        {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"name":"Invented Product","confidence":0.9}',
                            "annotations": [],
                        }
                    ]
                }
            ]
        }
    )
    monkeypatch.setattr(enrichment, "openai_api_key", lambda: "test-key")
    monkeypatch.setattr(enrichment.httpx, "Client", lambda **kwargs: FakeClient(post_response=uncited, **kwargs))

    assert enrichment.openai_web_search_product("5000000000000") == {}


def test_negative_lookup_cache_expires():
    result = {
        "name": "Product 123",
        "source_urls": [],
        "lookup_cache_version": enrichment.LOOKUP_CACHE_VERSION,
    }
    recent = datetime.now(timezone.utc).isoformat()
    expired = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()

    assert enrichment._cached_lookup_is_fresh(result, recent, "123") is True
    assert enrichment._cached_lookup_is_fresh(result, expired, "123") is False
