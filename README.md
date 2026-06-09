# StockTake

Offline-first stocktaking system for alcoholic drink inventory.

For the complete current scope, production handoff, continuation steps, and
recommended next work, read
[`docs/SCOPE_OF_WORK.md`](docs/SCOPE_OF_WORK.md).

This repository contains:

- `backend/static`: web-based scanner app/PWA for phones, tablets, and desktops.
- `backend`: FastAPI VPS backend with idempotent event sync and Excel export.
- `ios/StockTakeApp`: earlier native Swift/SwiftUI iPhone source kept as reference.

## Web app

The web app implements:

- Browser-based barcode scanning with manual barcode fallback.
- Local-first stocktake events in IndexedDB with idempotency keys.
- Product catalog caching including BIN and catalog version metadata.
- Multi-scan and bulk-count modes.
- Decimal quantity entry stored as text through the sync/export path.
- Explicit zero count support.
- Unknown barcode draft products.
- Scanned line review and quantity adjustment.
- Undo last scan.
- Scanner sleep state for battery safety.
- PWA app shell caching for poor-connectivity cellars.

Open [https://stock.aoodie.xyz](https://stock.aoodie.xyz) from a phone browser. Camera barcode scanning requires HTTPS in production.
If the browser does not support `BarcodeDetector`, the manual barcode field still works.

## Backend

Run locally:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Important endpoints:

- `GET /`: serves the web stocktake app.
- `GET /admin`: desktop admin for product tasks, products, sessions, and export review.
- `GET /catalog`: downloads products, locations, sessions, and catalog version metadata.
- `POST /products`: creates/updates product catalog rows.
- `POST /sessions`: creates/updates a stocktake session code.
- `POST /sync/events`: accepts queued browser events idempotently.
- `GET /export/{session_id}`: downloads the locked v1 Excel workbook.
- `GET /pre-export/{session_id}`: shows missing BIN validation counts.
- `GET /pre-export/{session_id}/missing-bin`: lists rows needing BIN cleanup.
- `PATCH /products/{product_id}/bin`: quick BIN update for validation cleanup.

Excel export columns:

`Session ID`, `Session Name`, `Location`, `BIN`, `Barcode`, `Product Name`, `Category`, `Size`, `Quantity`, `Unit`, `Draft Status`, `Missing BIN Flag`, `Counted At`, `Device ID`, `Notes`

`quantity = 0` is exported as `0`, never blank.

## Admin and enrichment

Unknown scanned barcodes create draft products and product tasks. Open `/admin` from a desktop browser to review tasks, run online enrichment, approve product details, manage sessions, and run export preflight checks.

Set these environment variables in production:

- `ADMIN_PASSWORD`: admin login password. If unset, a random password is generated in `backend/data/admin_password.txt`.
- `ADMIN_SECRET`: cookie signing secret. Defaults to the admin password.
- `OPENAI_API_KEY`: optional; enables cited web-search fallback and LLM cleanup when the structured barcode databases have no match.
- `OPENAI_MODEL`: optional model override for enrichment. Defaults to `gpt-4.1-mini`.

Approved product photos are saved under `backend/data/product-images`, with the product record storing the served image URL and source metadata.

Barcode enrichment checks Open Food Facts, Open Products Facts, Open Beauty Facts, and Open Pet Food Facts. If none identify the barcode and an OpenAI token is configured, it performs a cited web search and keeps the result for review.

For local development, set `ADMIN_PASSWORD=stocktake-admin` if you want the predictable development password.

## VPS deployment target

Production domain: `stock.aoodie.xyz`

Recommended setup:

- Run FastAPI with Uvicorn on `127.0.0.1:8099`.
- Put Nginx/Caddy in front of it for HTTPS.
- Proxy `https://stock.aoodie.xyz` to `http://127.0.0.1:8099`.
- Ensure the TLS certificate is valid; mobile camera access will not work reliably over plain HTTP.
