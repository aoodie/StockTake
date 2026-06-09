# StockTake Scope of Work and Continuation Handoff

Last updated: 2026-06-09

Repository: `https://github.com/aoodie/StockTake`

Production: `https://stock.aoodie.xyz`

Production source commit at handoff: `2d7ecc3`

## Purpose

StockTake is a phone-first, offline-capable stocktaking system for hospitality
inventory. Staff scan physical product barcodes, confirm quantities, and sync
counts to a FastAPI backend. The desktop admin manages products, unknown
barcode tasks, ProcureWizard integration, LLM settings, and exports.

This document is the primary continuation guide for another development
machine. It describes what is implemented, what is live, how production is
deployed, and the recommended next work.

## Start Here on Another Machine

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/aoodie/StockTake.git
   cd StockTake
   git checkout main
   git pull --ff-only origin main
   ```

2. Create the backend environment:

   ```bash
   cd backend
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Run tests:

   ```bash
   .venv/bin/pytest
   node --test static/frontend-utils.test.mjs static/scanner-smoke.test.mjs
   node --check static/app.js
   node --check static/admin.js
   node --check static/sw.js
   ```

4. Run locally:

   ```bash
   ADMIN_PASSWORD=stocktake-admin .venv/bin/uvicorn app.main:app --reload --port 8101
   ```

5. Open:

   - Phone scanner: `http://127.0.0.1:8101/`
   - Desktop admin: `http://127.0.0.1:8101/admin`
   - Phone barcode mapper: `http://127.0.0.1:8101/mapping`

Camera access generally requires HTTPS on a real phone. Manual barcode entry
works locally.

## Important Data Warning

GitHub contains source code only. It does not contain production operational
data or secrets.

Ignored production state under `backend/data/` includes:

- SQLite database and WAL files
- Product images
- Saved OpenAI API token
- Generated admin password file
- App settings and cached product lookups

Do not replace `/opt/stocktake/backend/data` when deploying source updates.
Back up production before migrations or risky changes:

```bash
ssh aoodie@194.164.127.139
cd /opt/stocktake
bash deploy/backup_vps.sh
```

SSH access and credentials must be configured separately on the new machine.
No passwords, API keys, or private SSH keys should be committed to GitHub.

## Current User Workflows

### Phone Stocktake Scanner

1. Staff selects or resumes a stocktake session and location.
2. Camera scanner reads the physical barcode.
3. Scanner pauses and opens a full-screen confirmation HUD.
4. HUD displays product identity, photo, BIN, barcode, and current total.
5. Quantity defaults to `1`.
6. Staff can use `1`, `+1`, `+6`, `+12`, `Clear`, or type a decimal quantity.
7. Count is not saved until staff taps **Save & Next**.
8. **Skip** returns to scanning without saving.
9. Scanner resumes only after confirmation or skip.

Scanner implementation details:

- App-controlled direct ZXing video decode loop
- Native detector fallback support
- Scanner pauses while confirmation is open
- Recovery after page visibility changes and phone sleep
- Persistent-state blockers are not restored after reload
- Diagnostics screen reports camera state and decoder blocking reason

### Unknown Barcode Enrichment

When a scanned barcode is not in the local catalog:

1. A local draft product is created.
2. Full-screen quantity confirmation opens immediately.
3. Quantity entry remains usable while lookup runs.
4. Backend checks its lookup cache.
5. Backend queries Open Food Facts.
6. If configured, OpenAI refines the available lookup evidence.
7. The HUD updates with suggested name, category, size, unit, and photo.
8. Low-confidence or missing results remain drafts for admin review.

An LLM cannot reliably identify a product from barcode digits alone. The LLM
is used to normalize evidence returned by product lookup sources, not to invent
an identity.

### ProcureWizard Matching During Scan

After an unknown barcode receives a useful product identity:

1. The backend searches rows in the active ProcureWizard import.
2. Candidates are ranked by name, pack size, and category similarity.
3. Credible candidates appear in the full-screen phone HUD.
4. Staff selects the correct ProcureWizard candidate.
5. **Save & Next** counts against that ProcureWizard product.
6. The physical barcode is synced as an alias for future scans.

Fuzzy ProcureWizard candidates are never auto-linked without user selection.

### Phone Barcode Mapper

`/mapping` is a separate online-only admin-authenticated phone workflow:

- Scan or manually enter a barcode
- Detect an existing mapping
- Search and map to an existing product
- Create a new product with lookup suggestions
- Prevent duplicate barcode ownership
- Continue rapidly to the next barcode

### Desktop Admin

`/admin` includes:

- Dashboard and issue counts
- Product catalog search and editing
- Barcode alias management
- Product merge workflow
- Bulk category/BIN updates and deletion
- Unknown barcode task review, enrichment, approval, and rejection
- Barcode mapping queue and undo audit
- ProcureWizard CSV import, row linking, status, and export
- Session management
- Export review
- AI Product Copilot suggestion review
- OpenAI model/token settings and connection test

### Export Options

There are three distinct export paths:

1. **Download All Scanned Lines**
   - Available from phone and desktop admin
   - Does not require ProcureWizard mapping
   - Does not require completed products or BINs
   - Includes drafts and unmapped scans
   - Preserves physical barcode and product name captured at scan time
   - Endpoint: `GET /export/scanned/{session_id}`

2. **Final Locked Excel**
   - Intended for cleaned catalog data
   - Requires admin authentication
   - Admin UI keeps this disabled until missing BINs and drafts are resolved
   - Endpoint: `GET /export/{session_id}`

3. **ProcureWizard CSV**
   - Uses the imported PW template structure
   - Counts linked products against PW rows
   - Endpoint: `GET /admin/api/procurewizard/export/{session_id}`

## Architecture

### Backend

- Framework: FastAPI
- Database: SQLite with WAL-oriented concurrency settings
- Main entry point: `backend/app/main.py`
- Database/schema/helpers: `backend/app/database.py`
- Validation models: `backend/app/models.py`
- Authentication: `backend/app/auth.py`
- Excel export: `backend/app/exporter.py`
- Scanner/sync/catalog/export routes: `backend/app/routers/sync.py`
- Admin/product/task/PW routes: `backend/app/routers/admin.py`
- AI settings and suggestion routes: `backend/app/routers/ai.py`
- Online lookup and LLM enrichment: `backend/app/services/enrichment.py`
- ProcureWizard parsing/matching/export: `backend/app/services/procurewizard.py`

### Frontend

- Phone stocktake app: `backend/static/index.html`, `app.js`, `styles.css`
- Desktop admin: `backend/static/admin.html`, `admin.js`, `admin.css`
- Phone mapper: `backend/static/mapping.html`, `mapping.js`
- Shared scanner utilities: `backend/static/frontend-utils.js`
- Service worker/PWA cache: `backend/static/sw.js`
- Bundled scanner library: `backend/static/vendor/zxing-library.min.js`

### Storage and Sync

- Phone app stores catalog, scans, events, and session state in IndexedDB.
- Events use idempotency keys before syncing to `/sync/events`.
- Explicit zero and decimal quantities are preserved as text.
- Draft products create backend review tasks.
- Product barcodes are aliases with one owning product.
- Physical scan barcodes remain available in stocktake line snapshots.

## Key Endpoints

Public or phone-facing:

- `GET /`
- `GET /mapping`
- `GET /catalog`
- `GET /products/lookup/{barcode}`
- `POST /sync/events`
- `POST /sessions`
- `GET /export/scanned/{session_id}`

Admin-authenticated:

- `GET /admin`
- `POST /admin/api/login`
- `GET /admin/api/products`
- `POST /admin/api/products`
- `PATCH /admin/api/products/{product_id}`
- `POST /admin/api/products/{product_id}/barcodes`
- `GET /admin/api/tasks`
- `POST /admin/api/tasks/{task_id}/enrich`
- `POST /admin/api/tasks/{task_id}/approve`
- `POST /admin/api/procurewizard/import`
- `GET /admin/api/procurewizard/status`
- `GET /admin/api/procurewizard/export/{session_id}`
- `GET/PATCH/POST /admin/api/settings/llm...`
- `GET /export/{session_id}`

## Authentication and Security State

- Admin sessions use random server-side tokens stored as SHA-256 hashes.
- Admin sessions expire after 12 hours and are revocable on logout.
- Admin APIs require the admin session cookie.
- `ADMIN_PASSWORD` may be supplied through the environment.
- The current code explicitly permits `demo` as a temporary admin password.
- OpenAI tokens saved through admin are stored in
  `backend/data/openai_api_key.txt`, outside Git.
- `STOCKTAKE_SYNC_TOKEN` can protect sync writes when configured.

Important security caveats before commercial/external deployment:

- Replace the temporary `demo` password.
- Configure and enforce `STOCKTAKE_SYNC_TOKEN`.
- Decide whether raw scanned export should remain unauthenticated. It is
  currently intentionally phone-accessible at `/export/scanned/{session_id}`.
- Add rate limiting and request-size controls at Nginx or application level.
- Review access logging and backup retention.

## Production Deployment

Production source directory:

```text
/opt/stocktake
```

Service:

```text
stocktake
```

Normal source-only deployment:

```bash
git push origin main

ssh aoodie@194.164.127.139 '
  set -e
  cd /opt/stocktake
  git pull --ff-only origin main
  sudo systemctl restart stocktake
  sudo systemctl is-active stocktake
  git rev-parse --short HEAD
'
```

Verify live assets and service:

```bash
curl -fsS https://stock.aoodie.xyz/ | head
curl -fsS https://stock.aoodie.xyz/sw.js | head
ssh aoodie@194.164.127.139 'sudo systemctl is-active stocktake'
```

For bootstrap, Nginx, HTTPS, and backup details, read
[`deploy/README.md`](../deploy/README.md).

## Verification Baseline

At this handoff, the verified baseline is:

- Backend: `36 passed`
- Frontend/scanner Node tests: `11 passed`
- Live service: active
- Live source commit before this documentation commit: `2d7ecc3`
- Live service worker cache: `stocktake-v22`

Run before every deployment:

```bash
cd backend
.venv/bin/pytest
node --test static/frontend-utils.test.mjs static/scanner-smoke.test.mjs
node --check static/app.js
node --check static/admin.js
node --check static/sw.js
cd ..
git diff --check
```

For scanner changes, also verify with a real phone or a deterministic fake
camera feed. Do not rely only on syntax tests.

## Known Limitations and Risks

- ProcureWizard matching is fuzzy and requires staff confirmation.
- Open Food Facts coverage is incomplete, especially for hospitality alcohol
  inventory.
- LLM refinement cannot identify products when lookup sources provide no useful
  evidence.
- The full-screen confirmation flow prioritizes accuracy over maximum scanning
  speed. A separate Rapid Mode is not yet implemented.
- Raw scanned export requires the phone to sync first; it exports backend
  stocktake lines, not unsynced IndexedDB-only lines.
- Final export and phone export review still use separate authentication paths.
- Service worker cache versions must be bumped when changing phone assets.
- Production data is SQLite on one VPS. Backups exist, but automated off-server
  backup and restore testing should be added.

## Recommended Next Work

Priority 1: trial reliability

1. Run a real first stocktake trial with representative cellar/bar products.
2. Verify camera scanning, full-screen quantity entry, PW matching, and raw
   export on the staff phones that will actually be used.
3. Add an admin view showing scan-to-PW match decisions and confidence.
4. Add a clear sync-complete check before phone raw export.
5. Add an export of unsynced local phone lines for emergency recovery.

Priority 2: product management quality

1. Add more product lookup sources suited to alcohol/hospitality inventory.
2. Improve PW matching with token weighting, brand extraction, and normalized
   pack-size parsing.
3. Add bulk approval for high-confidence enrichment/PW matches.
4. Add product photo candidate review and reliable image download/storage.
5. Add duplicate-product detection before creating drafts.

Priority 3: commercial hardening

1. Remove the `demo` password exception and rotate production credentials.
2. Require authenticated staff roles for scanner, mapper, and raw export.
3. Configure `STOCKTAKE_SYNC_TOKEN`.
4. Add rate limiting, structured logs, monitoring, and error reporting.
5. Add automated off-server backups and documented restore drills.
6. Add database migrations rather than schema mutation only at startup.
7. Add CI for Python tests, Node tests, and browser smoke checks.

## Continuation Rules

- Work from the latest `main`; production currently deploys directly from it.
- Back up the VPS before risky database or product-management changes.
- Never commit `backend/data`, API keys, passwords, or SSH credentials.
- Keep barcode ownership immutable; add aliases or merge products instead of
  silently changing existing primary barcodes.
- Preserve scan snapshots so raw exports remain auditable.
- Require explicit confirmation before accepting fuzzy or LLM-generated product
  identity.
- Test phone layout at an iPhone-sized viewport and on a real mobile browser
  after significant scanner/HUD changes.
