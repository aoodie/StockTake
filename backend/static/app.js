import {
  APP_VERSION,
  CACHE_NAME,
  BARCODE_FORMATS,
  CAMERA_DETECT_INTERVAL_MS,
  SCAN_DEBOUNCE_MS,
  ZXING_DETECT_INTERVAL_MS,
  ZXING_FAST_FORMATS,
  addDecimalStrings,
  barcodeLookupKeys,
  decodedBarcodeText,
  isValidQuantity,
  normalizeBarcode,
  normalizeQuantity,
  scannerBlockReason
} from "./frontend-utils.js?v=qty-keypad-1";

const DB_NAME = "stocktake-web";
const DB_VERSION = 1;
const DEVICE_KEY = "stocktake-device-id";
const SESSION_MEMORY_PREFIX = "stocktake-session";
const productIndex = new Map();
let catalogProducts = [];
let catalogSessions = [];
let catalogLocations = [];

const els = {
  preview: document.querySelector("#preview"),
  scannerPanel: document.querySelector("#scannerPanel"),
  autoScanBadge: document.querySelector("#autoScanBadge"),
  torchButton: document.querySelector("#torchButton"),
  wakeButton: document.querySelector("#wakeButton"),
  pulse: document.querySelector("#pulse"),
  scanHud: document.querySelector("#scanHud"),
  modeRow: document.querySelector("#modeRow"),
  multiMode: document.querySelector("#multiMode"),
  bulkMode: document.querySelector("#bulkMode"),
  productPhoto: document.querySelector("#productPhoto"),
  productName: document.querySelector("#productName"),
  productMeta: document.querySelector("#productMeta"),
  productBin: document.querySelector("#productBin"),
  manualBarcode: document.querySelector("#manualBarcode"),
  manualScanButton: document.querySelector("#manualScanButton"),
  retryCameraButton: document.querySelector("#retryCameraButton"),
  quantityInput: document.querySelector("#quantityInput"),
  quantityDisplay: document.querySelector("#quantityDisplay"),
  keypad: document.querySelector("#keypad"),
  undoButton: document.querySelector("#undoButton"),
  linesButton: document.querySelector("#linesButton"),
  exportButton: document.querySelector("#exportButton"),
  locationSelect: document.querySelector("#locationSelect"),
  periodLabel: document.querySelector("#periodLabel"),
  changeSessionButton: document.querySelector("#changeSessionButton"),
  syncStatus: document.querySelector("#syncStatus"),
  sessionDialog: document.querySelector("#sessionDialog"),
  sessionPreset: document.querySelector("#sessionPreset"),
  sessionCodeInput: document.querySelector("#sessionCodeInput"),
  sessionLocationSelect: document.querySelector("#sessionLocationSelect"),
  startSessionButton: document.querySelector("#startSessionButton"),
  linesDialog: document.querySelector("#linesDialog"),
  lineSearch: document.querySelector("#lineSearch"),
  lineList: document.querySelector("#lineList"),
  editDialog: document.querySelector("#editDialog"),
  editTitle: document.querySelector("#editTitle"),
  editQuantity: document.querySelector("#editQuantity"),
  saveEditButton: document.querySelector("#saveEditButton"),
  deleteLineButton: document.querySelector("#deleteLineButton"),
  duplicateDialog: document.querySelector("#duplicateDialog"),
  duplicateProduct: document.querySelector("#duplicateProduct"),
  duplicateExisting: document.querySelector("#duplicateExisting"),
  duplicateNew: document.querySelector("#duplicateNew"),
  duplicateAddButton: document.querySelector("#duplicateAddButton"),
  duplicateEditButton: document.querySelector("#duplicateEditButton"),
  unknownDialog: document.querySelector("#unknownDialog"),
  unknownBarcodeText: document.querySelector("#unknownBarcodeText"),
  unknownNameInput: document.querySelector("#unknownNameInput"),
  unknownProductSuggestions: document.querySelector("#unknownProductSuggestions"),
  unknownSuggestions: document.querySelector("#unknownSuggestions"),
  unknownBinInput: document.querySelector("#unknownBinInput"),
  saveUnknownButton: document.querySelector("#saveUnknownButton"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmTitle: document.querySelector("#confirmTitle"),
  confirmMessage: document.querySelector("#confirmMessage"),
  confirmOkButton: document.querySelector("#confirmOkButton"),
  confirmCancelButton: document.querySelector("#confirmCancelButton"),
  diagnosticsButton: document.querySelector("#diagnosticsButton"),
  diagnosticsDialog: document.querySelector("#diagnosticsDialog"),
  diagnosticsList: document.querySelector("#diagnosticsList"),
  copyDiagnosticsButton: document.querySelector("#copyDiagnosticsButton"),
  resetScannerButton: document.querySelector("#resetScannerButton"),
  clearCacheButton: document.querySelector("#clearCacheButton"),
  exportDialog: document.querySelector("#exportDialog"),
  exportSummary: document.querySelector("#exportSummary"),
  missingBinList: document.querySelector("#missingBinList"),
  downloadRecoveryButton: document.querySelector("#downloadRecoveryButton"),
  downloadRawExportLink: document.querySelector("#downloadRawExportLink"),
  downloadExportLink: document.querySelector("#downloadExportLink")
};

let db;
let diagnostics = {
  app_version: APP_VERSION,
  cache_name: CACHE_NAME,
  sync_status: "Offline ready",
  service_worker: "checking",
  camera_permission: "unknown",
  camera_stream: "inactive",
  camera_track: "none",
  camera_owner: "none",
  track_settings: "-",
  video_ready: "0",
  video_size: "-",
  preview_paused: "yes",
  decoder_mode: "none",
  decoder_blocked: "-",
  zxing_loader: "checking",
  zxing_methods: "-",
  supported_formats: "-",
  decoder_heartbeat: "never",
  last_raw_barcode: "-",
  last_accepted_barcode: "-",
  last_rejected_reason: "-",
  last_scan_time: "-",
  last_error: "-",
  roi_size: "-",
  decode_ms_avg: "-",
  decode_errors: "0",
  frames_skipped: "0",
  secure_context: window.isSecureContext ? "yes" : "no",
  page_protocol: location.protocol,
  visibility: document.visibilityState,
  session_dialog: "closed",
  wake_button: "hidden",
  scanner_generation: "0"
};

const DIAGNOSTIC_LABELS = {
  app_version: "App Version",
  cache_name: "Cache",
  sync_status: "Status",
  service_worker: "Service Worker",
  camera_permission: "Camera Permission",
  camera_stream: "Camera Stream",
  camera_track: "Camera Track",
  camera_owner: "Camera Owner",
  track_settings: "Track Settings",
  video_ready: "Video Ready",
  video_size: "Video Size",
  preview_paused: "Video Paused",
  decoder_mode: "Decoder",
  decoder_blocked: "Decoder Blocked",
  zxing_loader: "ZXing Loader",
  zxing_methods: "ZXing Methods",
  supported_formats: "Formats",
  decoder_heartbeat: "Decoder Heartbeat",
  last_raw_barcode: "Last Raw Barcode",
  last_accepted_barcode: "Last Accepted",
  last_rejected_reason: "Last Rejected",
  last_scan_time: "Last Scan Time",
  last_error: "Last Error",
  roi_size: "ROI Size",
  decode_ms_avg: "Decode Avg",
  decode_errors: "Decode Errors",
  frames_skipped: "Frames Skipped",
  secure_context: "Secure Context",
  page_protocol: "Protocol",
  visibility: "Page Visibility",
  session_dialog: "Session Dialog",
  wake_button: "Wake Button",
  scanner_generation: "Scanner Generation"
};

let state = {
  mode: "multi",
  period: today(),
  sessionId: `session-${today()}`,
  sessionName: today(),
  locationId: "main-bar",
  locationName: "Bar",
  quantity: "",
  caseType: "split",
  currentProduct: null,
  pendingBarcode: "",
  lastBarcode: null,
  lastScanAt: 0,
  lastManualBarcode: null,
  lastManualScanAt: 0,
  hardwareBlockedUntil: 0,
  sleeping: false,
  scanInFlight: false,
  editingLine: null,
  detector: null,
  zxingReader: null,
  zxingControls: null,
  zxingLoadPromise: null,
  cameraStartPromise: null,
  decodeInFlight: false,
  decodeErrors: 0,
  framesSkipped: 0,
  decodeSamples: [],
  activeDecoder: "none",
  decoderGeneration: 0,
  nativeErrorStreak: 0,
  sessionStarting: false,
  restoredSession: false,
  pendingUnknownProduct: null,
  awaitingNextScan: false,
  lookupGeneration: 0,
  procurewizardMatches: [],
  unknownSuggestionMatches: [],
  stream: null,
  scanLoopActive: false,
  inactivityTimer: null,
  lastSyncAt: "",
  lastCatalogSyncAt: ""
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

function sessionMemoryKey(period = today()) {
  return `${SESSION_MEMORY_PREFIX}-${period}`;
}

function readSessionMemory() {
  try {
    const saved = JSON.parse(localStorage.getItem(sessionMemoryKey()) || "null");
    return saved?.period === today() ? saved : null;
  } catch {
    return null;
  }
}

function writeSessionMemory() {
  localStorage.setItem(sessionMemoryKey(state.period), JSON.stringify({
    period: state.period,
    sessionId: state.sessionId,
    sessionName: state.sessionName,
    locationId: state.locationId,
    locationName: state.locationName,
    selectedAt: new Date().toISOString()
  }));
}

function deviceId() {
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore("products", { keyPath: "barcode" });
      db.createObjectStore("lines", { keyPath: "id" });
      db.createObjectStore("events", { keyPath: "local_id" });
      db.createObjectStore("audit", { keyPath: "id" });
      db.createObjectStore("state", { keyPath: "key" });
      db.createObjectStore("meta", { keyPath: "key" });
    };
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

function tx(store, mode = "readonly") {
  return db.transaction(store, mode).objectStore(store);
}

function put(store, value) {
  return new Promise((resolve, reject) => {
    const request = tx(store, "readwrite").put(value);
    request.onsuccess = () => resolve(value);
    request.onerror = () => reject(request.error);
  });
}

function del(store, key) {
  return new Promise((resolve, reject) => {
    const request = tx(store, "readwrite").delete(key);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

function get(store, key) {
  return new Promise((resolve, reject) => {
    const request = tx(store).get(key);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function all(store) {
  return new Promise((resolve, reject) => {
    const request = tx(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function clearStore(store) {
  return new Promise((resolve, reject) => {
    const request = tx(store, "readwrite").clear();
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

async function applyDataEpoch(dataEpoch) {
  const catalogMeta = await get("meta", "catalog");
  if (catalogMeta?.data_epoch === dataEpoch) return true;
  for (const store of ["products", "lines", "events", "audit", "state"]) {
    await clearStore(store);
  }
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith(SESSION_MEMORY_PREFIX)) localStorage.removeItem(key);
  }
  await put("meta", { key: "catalog", data_epoch: dataEpoch });
  location.reload();
  return false;
}

async function saveState() {
  const persistent = {
    key: "active",
    mode: state.mode,
    period: state.period,
    sessionId: state.sessionId,
    sessionName: state.sessionName,
    locationId: state.locationId,
    locationName: state.locationName,
    lastSyncAt: state.lastSyncAt,
    lastCatalogSyncAt: state.lastCatalogSyncAt
  };
  await put("state", persistent);
}

async function restoreState() {
  const saved = await get("state", "active");
  if (saved) {
    state = {
      ...state,
      ...saved,
      stream: null,
      detector: null,
      zxingReader: null,
      zxingControls: null,
      zxingLoadPromise: null,
      cameraStartPromise: null,
      quantity: "",
      caseType: "split",
      currentProduct: null,
      pendingBarcode: "",
      lastBarcode: null,
      lastScanAt: 0,
      lastManualBarcode: null,
      lastManualScanAt: 0,
      sleeping: false,
      pendingUnknownProduct: null,
      awaitingNextScan: false,
      lookupGeneration: state.lookupGeneration + 1,
      procurewizardMatches: [],
      unknownSuggestionMatches: [],
      scanInFlight: false,
      scanLoopActive: false
    };
  }
}

async function syncCatalog() {
  try {
    const response = await fetch("/catalog");
    if (!response.ok) throw new Error("Catalog failed");
    const catalog = await response.json();
    if (!(await applyDataEpoch(catalog.data_epoch || "initial"))) return false;
    productIndex.clear();
    catalogProducts = catalog.products.map(normalProduct);
    for (const product of catalogProducts) {
      await cacheProduct(product);
    }
    catalogSessions = catalog.sessions || [];
    catalogLocations = catalog.locations || [];
    if (catalogLocations.length) renderLocations(catalogLocations);
    renderSessionChoices();
    state.lastCatalogSyncAt = new Date().toISOString();
    await put("meta", {
      key: "catalog",
      catalog_version: catalog.catalog_version,
      data_epoch: catalog.data_epoch || "initial",
      last_catalog_sync_at: state.lastCatalogSyncAt
    });
    setSyncStatus("Catalog synced");
    return true;
  } catch {
    setSyncStatus("Offline catalog");
    return false;
  }
}

async function loadProductIndex() {
  productIndex.clear();
  catalogProducts = await all("products");
  for (const product of catalogProducts) {
    indexProduct(product);
  }
}

function normalProduct(product) {
  const barcode = normalizeBarcode(product.barcode);
  return {
    id: product.id || `product-${barcode}`,
    barcode,
    barcode_raw: String(product.barcode ?? "").trim(),
    bin: product.bin || "",
    name: product.name || "Unknown Product",
    category: product.category || "",
    size: product.size || "",
    unit: product.unit || "each",
    photo_url: product.photo_url || "",
    notes: product.notes || "",
    barcodes: Array.isArray(product.barcodes) ? product.barcodes : [],
    procurewizard: product.procurewizard || null,
    draft_status: product.draft_status || "confirmed",
    product_updated_at: product.product_updated_at || new Date().toISOString()
  };
}

async function cacheProduct(product) {
  await put("products", product);
  indexProduct(product);
}

function indexProduct(product) {
  const keys = barcodeLookupKeys(product.barcode);
  if (product.barcode_raw) keys.push(...barcodeLookupKeys(product.barcode_raw));
  for (const alias of product.barcodes || []) {
    keys.push(...barcodeLookupKeys(alias.barcode));
  }
  if (product.procurewizard?.pid) {
    keys.push(...barcodeLookupKeys(product.procurewizard.pid));
  }
  for (const key of new Set(keys)) {
    productIndex.set(key, product);
  }
}

function renderLocations(locations) {
  catalogLocations = locations;
  els.locationSelect.innerHTML = "";
  els.sessionLocationSelect.innerHTML = "";
  for (const location of locations) {
    const option = document.createElement("option");
    option.value = location.id;
    option.textContent = location.name;
    els.locationSelect.append(option);
    els.sessionLocationSelect.append(option.cloneNode(true));
  }
  const currentLocation = locations.find((location) => location.id === state.locationId);
  if (!currentLocation) {
    state.locationId = locations[0].id;
    state.locationName = locations[0].name;
  } else {
    state.locationName = currentLocation.name;
  }
  els.locationSelect.value = state.locationId;
  els.sessionLocationSelect.value = state.locationId;
}

function renderSessionChoices() {
  els.sessionPreset.innerHTML = "";
  const sessions = [...catalogSessions].sort((a, b) => String(b.period_date).localeCompare(String(a.period_date)));
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.id;
    option.textContent = `${session.name} (${session.id})`;
    option.dataset.name = session.name;
    option.dataset.period = session.period_date;
    els.sessionPreset.append(option);
  }
  const active = sessions.find((session) => session.id === state.sessionId) || sessions[0];
  if (active) {
    els.sessionPreset.value = active.id;
    els.sessionCodeInput.value = active.id;
  }
}

function renderSessionHeader() {
  els.periodLabel.textContent = `${state.sessionName || state.sessionId} / ${state.locationName}`;
}

function syncHeaders() {
  const token = localStorage.getItem("stocktake-sync-token") || "";
  return {
    "Content-Type": "application/json",
    ...(token ? { "X-StockTake-Sync-Token": token } : {})
  };
}

async function applySessionSelection(sessionId, sessionName, period, locationId, locationName, recordEvent = true) {
  if (!catalogSessions.some((session) => session.id === sessionId)) {
    throw new Error("Select an active server session");
  }
  state.sessionId = sessionId;
  state.sessionName = sessionName || sessionId;
  state.period = period || today();
  state.locationId = locationId;
  state.locationName = locationName;
  els.locationSelect.value = locationId;
  els.sessionLocationSelect.value = locationId;
  renderSessionHeader();
  writeSessionMemory();
  if (recordEvent) {
    await enqueue("session_change", {
      session_id: state.sessionId,
      session_name: state.sessionName,
      period: state.period
    });
  }
  await saveState();
  await renderLines();
}

async function showSessionDialog(force = false) {
  renderSessionChoices();
  const saved = !force ? readSessionMemory() : null;
  if (saved && catalogSessions.some((session) => session.id === saved.sessionId)) {
    state.restoredSession = true;
    await applySessionSelection(
      saved.sessionId,
      saved.sessionName,
      saved.period,
      saved.locationId,
      saved.locationName,
      false
    );
    return;
  }
  els.startSessionButton.disabled = !catalogSessions.length;
  if (!catalogSessions.length) setSyncStatus("No active session. Ask an admin to open one.");
  els.sessionDialog.returnValue = "";
  els.sessionDialog.showModal();
  await new Promise((resolve) => {
    const onStart = async () => {
      const selected = catalogSessions.find((session) => session.id === els.sessionPreset.value);
      if (!selected) return;
      const sessionId = selected.id;
      const sessionName = selected.name;
      const period = selected.period_date;
      const locationId = els.sessionLocationSelect.value || state.locationId;
      const locationName = els.sessionLocationSelect.selectedOptions[0]?.textContent || locationId;
      els.sessionDialog.close("started");
      state.sessionStarting = true;
      ensureCameraStarted().catch(reportCameraError);
      try {
        await applySessionSelection(sessionId, sessionName, period, locationId, locationName);
      } finally {
        state.sessionStarting = false;
        resolve();
      }
    };
    els.startSessionButton.addEventListener("click", onStart, { once: true });
  });
}

async function getProduct(barcode) {
  const normalized = normalizeBarcode(barcode);
  for (const key of barcodeLookupKeys(normalized)) {
    const indexed = productIndex.get(key);
    if (indexed) return indexed;
  }
  const found = await get("products", normalized);
  if (found) {
    indexProduct(found);
    return found;
  }
  const draft = normalProduct({
    id: `draft-${normalized}`,
    barcode: normalized,
    name: `Draft ${normalized}`,
    notes: "Needs product mapping and BIN",
    draft_status: "draft"
  });
  await cacheProduct(draft);
  await enqueue("draft_product", {
    product_id: draft.id,
    barcode: normalized,
    placeholder_name: draft.name,
    notes: draft.notes
  });
  return draft;
}

function productSubtitle(product) {
  const parts = [
    product.procurewizard ? "PW linked" : "",
    product.bin ? `BIN ${product.bin}` : "No BIN",
    product.category || "",
    product.size || ""
  ].filter(Boolean);
  return parts.join(" | ");
}

function defaultCaseType(product) {
  return product?.procurewizard || String(product?.unit || "").toLowerCase() === "case" ? "full" : "split";
}

function renderCaseTypeControl() {
  for (const button of els.scanHud.querySelectorAll('[data-action="set-case-type"]')) {
    const active = button.dataset.caseType === state.caseType;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function showScanHud(product, quantity, total, variant = "success") {
  const isDraft = product?.draft_status === "draft";
  const photo = product?.photo_url
    ? `<img alt="" src="${escapeHtml(product.photo_url)}">`
    : `<span class="hud-photo"></span>`;
  els.scanHud.className = `scan-hud ${isDraft ? "draft" : ""} ${variant === "error" ? "error" : ""}`;
  els.scanHud.innerHTML = `
    <div class="hud-shell">
      <header class="hud-header">
        <span class="hud-kicker">${isDraft ? "Unknown barcode" : variant === "error" ? "Scan failed" : "Confirm count"}</span>
        <span class="hud-current" data-role="hud-current">Current total: ${escapeHtml(total)}</span>
      </header>
      <div class="hud-product">
        <span data-role="hud-photo">${photo}</span>
        <span class="hud-info">
          <strong data-role="hud-name">${escapeHtml(product?.name || "Try scanning again")}</strong>
          <small data-role="hud-meta">${escapeHtml(product ? productSubtitle(product) : "No product was found")}</small>
          <small data-role="hud-barcode">${escapeHtml(product?.barcode || "")}</small>
        </span>
      </div>
      ${product ? `
        <div class="hud-lookup" data-role="lookup-status">${isDraft ? "Looking up product details and photo..." : "Product matched"}</div>
        <div class="hud-case-type" role="group" aria-label="Count type">
          <button data-action="set-case-type" data-case-type="full" aria-pressed="${state.caseType === "full"}" class="${state.caseType === "full" ? "active" : ""}" type="button">
            <strong>Full case</strong><small>Unopened complete case</small>
          </button>
          <button data-action="set-case-type" data-case-type="split" aria-pressed="${state.caseType === "split"}" class="${state.caseType === "split" ? "active" : ""}" type="button">
            <strong>Split case</strong><small>Loose bottles or units</small>
          </button>
        </div>
        <label class="hud-quantity-label" for="hudQuantityInput">Quantity <span>Tap number or type</span></label>
        <input id="hudQuantityInput" class="hud-quantity-input" inputmode="decimal" enterkeyhint="done" autocomplete="off" aria-label="Quantity" value="${escapeHtml(quantity || "1")}" data-replace-on-entry="true">
        <div class="hud-quick" role="group" aria-label="Quick quantity">
          <button data-action="add-quantity" data-value="1" type="button">+1</button>
          <button data-action="add-quantity" data-value="6" type="button">+6</button>
          <button data-action="add-quantity" data-value="12" type="button">+12</button>
          <button data-action="clear-quantity" type="button">Clear</button>
        </div>
        <div class="hud-keypad" role="group" aria-label="Quantity keypad">
          <button data-action="quantity-key" data-value="1" type="button">1</button>
          <button data-action="quantity-key" data-value="2" type="button">2</button>
          <button data-action="quantity-key" data-value="3" type="button">3</button>
          <button data-action="quantity-key" data-value="4" type="button">4</button>
          <button data-action="quantity-key" data-value="5" type="button">5</button>
          <button data-action="quantity-key" data-value="6" type="button">6</button>
          <button data-action="quantity-key" data-value="7" type="button">7</button>
          <button data-action="quantity-key" data-value="8" type="button">8</button>
          <button data-action="quantity-key" data-value="9" type="button">9</button>
          <button data-action="quantity-key" data-value="." type="button">.</button>
          <button data-action="quantity-key" data-value="0" type="button">0</button>
          <button data-action="quantity-backspace" type="button">Del</button>
        </div>
      ` : ""}
      <div class="hud-actions">
        ${isDraft ? `<button class="hud-describe" data-action="describe-unknown" type="button">Describe</button>` : ""}
        ${product ? `<button class="hud-skip" data-action="skip-scan" type="button">Skip</button>` : ""}
        <button class="hud-next" data-action="${product ? "save-next" : "next-scan"}" type="button">${product ? "Save & Next" : "Try Again"}</button>
      </div>
    </div>
  `;
  state.awaitingNextScan = true;
  els.scanHud.classList.remove("hidden");
}

function closeScanHud({ reset = false } = {}) {
  state.lookupGeneration += 1;
  state.awaitingNextScan = false;
  els.scanHud.classList.add("hidden");
  if (reset) resetActiveScan();
  resetInactivityTimer();
  updateDiagnostics({ decoder_blocked: "-" });
}

function usefulSuggestionName(suggestion, barcode) {
  const name = normalizeBarcode(suggestion?.name);
  return Boolean(name && ![`Product ${barcode}`, `Draft ${barcode}`].includes(name));
}

function renderProcureWizardMatches(matches = []) {
  state.procurewizardMatches = matches;
  const lookup = els.scanHud.querySelector('[data-role="lookup-status"]');
  if (!lookup || !matches.length) return;
  lookup.innerHTML = `
    <strong>Possible ProcureWizard match${matches.length === 1 ? "" : "es"}</strong>
    <span>Choose one to count directly against the PW product.</span>
    <div class="hud-pw-matches">
      ${matches.map((match, index) => `
        <button data-action="choose-pw" data-index="${index}" type="button">
          <strong>${escapeHtml(match.description || match.product?.name || "PW product")}</strong>
          <small>BIN ${escapeHtml(match.bin_number || "-")} · ${escapeHtml(match.pack_size || "-")} · ${Math.round(Number(match.score || 0) * 100)}% match</small>
        </button>
      `).join("")}
    </div>
  `;
}

async function chooseProcureWizardMatch(index) {
  const match = state.procurewizardMatches[index];
  if (!match?.product || !state.pendingBarcode) return;
  const product = normalProduct({
    ...match.product,
    barcode: state.pendingBarcode,
    barcode_raw: match.product.barcode,
    procurewizard: {
      pid: match.pid,
      bin_number: match.bin_number,
      pos: match.pos,
      pack_size: match.pack_size,
      match_status: "phone_selected"
    }
  });
  state.currentProduct = product;
  state.caseType = defaultCaseType(product);
  state.pendingUnknownProduct = null;
  await cacheProduct(product);
  renderProduct(product);
  const name = els.scanHud.querySelector('[data-role="hud-name"]');
  const meta = els.scanHud.querySelector('[data-role="hud-meta"]');
  const photo = els.scanHud.querySelector('[data-role="hud-photo"]');
  const current = els.scanHud.querySelector('[data-role="hud-current"]');
  const lookup = els.scanHud.querySelector('[data-role="lookup-status"]');
  if (name) name.textContent = product.name;
  if (meta) meta.textContent = productSubtitle(product);
  if (photo) {
    photo.innerHTML = product.photo_url
      ? `<img alt="" src="${escapeHtml(product.photo_url)}">`
      : `<span class="hud-photo"></span>`;
  }
  if (current) current.textContent = `Current total: ${await currentProductCount(product)}`;
  if (lookup) lookup.textContent = `ProcureWizard product selected · PID ${match.pid}. Save & Next will map this barcode and count it against the PW row.`;
  renderCaseTypeControl();
}

function matchingCatalogProducts(query) {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  return catalogProducts
    .filter((product) => product?.id && product.draft_status !== "draft")
    .map((product) => {
      const name = (product.name || "").toLowerCase();
      const search = [product.name, product.category, product.size, product.bin].filter(Boolean).join(" ").toLowerCase();
      const words = search.split(/[^a-z0-9]+/).filter(Boolean);
      const scores = terms.map((term) => {
        if (name.includes(term)) return 4;
        if (words.some((word) => word.startsWith(term))) return 3;
        if (search.includes(term)) return 2;
        return 0;
      });
      return { product, score: scores.reduce((total, score) => total + score, 0), matches: scores.every(Boolean) };
    })
    .filter((entry) => entry.matches)
    .sort((left, right) => right.score - left.score || left.product.name.localeCompare(right.product.name))
    .map((entry) => entry.product)
    .slice(0, 6);
}

function renderUnknownProductSuggestions() {
  const query = els.unknownNameInput.value.trim();
  const matches = matchingCatalogProducts(query);
  if (!query) {
    els.unknownProductSuggestions.innerHTML = `<p>Start typing a product name to search ${catalogProducts.filter((product) => product.draft_status !== "draft").length} existing products.</p>`;
  } else if (!matches.length) {
    els.unknownProductSuggestions.innerHTML = `<p>No existing products match “${escapeHtml(query)}”. Keep typing or save it as a new description.</p>`;
  } else {
    els.unknownProductSuggestions.innerHTML = `
      <p>Choose an existing product:</p>
      ${matches.map((product, index) => `
    <button data-action="choose-existing-product" data-index="${index}" type="button">
      <strong>${escapeHtml(product.name)}</strong>
      <small>${escapeHtml(productSubtitle(product))}</small>
    </button>
      `).join("")}
    `;
  }
  els.unknownProductSuggestions._matches = matches;
}

async function chooseExistingProductForUnknown(index) {
  const match = els.unknownProductSuggestions._matches?.[index];
  if (!match || !state.pendingBarcode) return;
  const product = normalProduct({
    ...match,
    barcode: state.pendingBarcode,
    barcode_raw: match.barcode,
    barcodes: [
      ...(match.barcodes || []),
      { barcode: state.pendingBarcode, label: "Scanned alias", is_primary: 0 }
    ]
  });
  await cacheProduct(product);
  state.currentProduct = product;
  state.caseType = defaultCaseType(product);
  state.pendingUnknownProduct = null;
  renderProduct(product);
  const name = els.scanHud.querySelector('[data-role="hud-name"]');
  const meta = els.scanHud.querySelector('[data-role="hud-meta"]');
  const lookup = els.scanHud.querySelector('[data-role="lookup-status"]');
  if (name) name.textContent = product.name;
  if (meta) meta.textContent = productSubtitle(product);
  if (lookup) lookup.textContent = "Existing product selected. Save & Next will remember this barcode.";
  renderCaseTypeControl();
  els.unknownDialog.close();
  pulse("Product selected");
}

async function enrichUnknownProduct(product) {
  const generation = ++state.lookupGeneration;
  try {
    const response = await fetch(`/products/lookup/${encodeURIComponent(product.barcode)}`);
    if (!response.ok) throw new Error("Lookup failed");
    const result = await response.json();
    if (generation !== state.lookupGeneration || state.currentProduct?.barcode !== product.barcode) return;
    let updated = product;
    let status = "No public description found. Tap Describe and type a few words to search the ProcureWizard list.";
    if (result.exists && result.product) {
      updated = normalProduct(result.product);
      status = "Matched an existing catalog product.";
    } else {
      const suggestion = result.suggested || {};
      const hasName = usefulSuggestionName(suggestion, product.barcode);
      updated = normalProduct({
        ...product,
        name: hasName ? suggestion.name : product.name,
        category: suggestion.category || product.category,
        size: suggestion.size || product.size,
        unit: suggestion.unit || product.unit,
        photo_url: suggestion.image_url || product.photo_url,
        notes: [
          product.notes,
          hasName ? `Online suggestion: ${suggestion.name}` : "",
          suggestion.confidence ? `Suggestion confidence: ${suggestion.confidence}` : ""
        ].filter(Boolean).join("\n")
      });
      status = hasName
        ? `Suggested from ${suggestion.source_name || "online lookup + AI"}${suggestion.confidence ? ` · ${Math.round(Number(suggestion.confidence) * 100)}% confidence` : ""}. Admin review required.`
        : status;
    }
    await cacheProduct(updated);
    state.currentProduct = updated;
    state.pendingUnknownProduct = updated.draft_status === "draft" ? updated : null;
    renderProduct(updated);
    const name = els.scanHud.querySelector('[data-role="hud-name"]');
    const meta = els.scanHud.querySelector('[data-role="hud-meta"]');
    const photo = els.scanHud.querySelector('[data-role="hud-photo"]');
    if (name) name.textContent = updated.name;
    if (meta) meta.textContent = productSubtitle(updated);
    if (photo) {
      photo.innerHTML = updated.photo_url
        ? `<img alt="" src="${escapeHtml(updated.photo_url)}">`
        : `<span class="hud-photo"></span>`;
    }
    const lookup = els.scanHud.querySelector('[data-role="lookup-status"]');
    if (lookup) lookup.textContent = status;
    renderProcureWizardMatches(result.procurewizard_matches || []);
  } catch {
    if (generation !== state.lookupGeneration) return;
    const lookup = els.scanHud.querySelector('[data-role="lookup-status"]');
    if (lookup) lookup.textContent = "Lookup unavailable. Quantity can still be saved.";
  }
}

async function commitScanQuantity(product, quantity, { mergeDuplicate = false, reason = "Scan saved" } = {}) {
  if (mergeDuplicate) {
    const existingLine = await findExistingLineForProduct(product, state.caseType);
    if (existingLine) {
      const newQuantity = addDecimalStrings(existingLine.quantity_decimal, quantity);
      await editLine(existingLine, newQuantity, reason);
      return newQuantity;
    }
  }
  await addLine(product, quantity);
  return currentCount(product.barcode);
}

async function handleScan(barcode, options = {}) {
  barcode = normalizeBarcode(barcode);
  updateDiagnostics({ last_raw_barcode: barcode || "-", decoder_heartbeat: new Date().toLocaleTimeString() });
  if (!barcode) {
    rejectScan("empty barcode");
    return;
  }
  if (state.sleeping && !options.allowWhileSleeping) {
    rejectScan("scanner asleep");
    return;
  }
  if (state.scanInFlight) {
    rejectScan("scan already processing");
    return;
  }
  if (state.awaitingNextScan) {
    rejectScan("waiting for next scan");
    return;
  }
  if (state.mode !== "multi" && state.pendingBarcode && !options.replacePending) {
    rejectScan(`waiting for quantity: ${state.pendingBarcode}`);
    return;
  }
  resetInactivityTimer();
  const now = Date.now();
  if (
    (state.mode === "multi" || options.debounce) &&
    state.lastBarcode === barcode &&
    now - state.lastScanAt < SCAN_DEBOUNCE_MS
  ) {
    rejectScan(`debounced ${barcode}`);
    return;
  }
  state.lastBarcode = barcode;
  state.lastScanAt = now;
  state.pendingBarcode = barcode;
  state.scanInFlight = true;
  updateDiagnostics({
    last_accepted_barcode: barcode,
    last_rejected_reason: "-",
    last_scan_time: new Date().toLocaleTimeString()
  });
  beepOnce();
  try {
    const product = await getProduct(barcode);
    state.currentProduct = product;
    state.quantity = "1";
    state.caseType = defaultCaseType(product);
    renderProduct(product);
    renderQuantity();
    const total = await currentCount(product.barcode);
    showScanHud(product, state.quantity, total);
    if (product.draft_status === "draft") {
      state.pendingUnknownProduct = product;
      enrichUnknownProduct(product);
    }
    flashFeedback(product.draft_status === "draft" ? "error" : "success");
    vibrate(product.draft_status === "draft" ? [80, 50, 120] : 35);
    await saveState();
  } catch {
    state.pendingBarcode = "";
    updateDiagnostics({ last_error: "product lookup failed" });
    setSyncStatus("Scan failed");
    showScanHud(null, "0", "0", "error");
    flashFeedback("error");
    vibrate([80, 50, 120]);
  } finally {
    state.scanInFlight = false;
  }
}

function rejectScan(reason) {
  updateDiagnostics({ last_rejected_reason: reason, last_scan_time: new Date().toLocaleTimeString() });
}

async function addLine(product, quantity) {
  const line = {
    id: crypto.randomUUID(),
    session_id: state.sessionId,
    session_name: state.sessionName,
    location_id: state.locationId,
    location_name: state.locationName,
    product_id: product.id,
    barcode: product.barcode,
    bin: product.bin || "",
    product_name: product.name,
    category: product.category,
    size: product.size,
    quantity_decimal: normalizeQuantity(quantity),
    case_type: state.caseType,
    unit: product.unit,
    photo_url: product.photo_url || "",
    draft_status: product.draft_status,
    missing_bin: !product.bin,
    counted_at: new Date().toISOString(),
    device_id: deviceId(),
    sync_status: "pending",
    notes: product.notes || ""
  };
  await put("lines", line);
  await enqueue("scan", {
    line_id: line.id,
    barcode: line.barcode,
    quantity_decimal: line.quantity_decimal,
    case_type: line.case_type,
    notes: line.notes,
    product: {
      id: product.id,
      barcode: product.barcode,
      bin: product.bin || "",
      name: product.name,
      category: product.category,
      size: product.size,
      unit: product.unit,
      draft_status: product.draft_status
    }
  });
  await renderLines();
  syncEvents();
}

async function enqueue(eventType, payload) {
  const localId = crypto.randomUUID();
  await put("events", {
    local_id: localId,
    device_id: deviceId(),
    session_id: state.sessionId,
    location_id: state.locationId,
    event_type: eventType,
    payload,
    created_at: new Date().toISOString(),
    sync_status: "pending",
    retry_count: 0,
    idempotency_key: `${deviceId()}:${localId}`,
    server_id: null
  });
}

async function syncEvents() {
  const events = (await all("events"))
    .filter((event) => ["pending", "failed"].includes(event.sync_status))
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
    .slice(0, 50);
  if (!events.length) {
    setSyncStatus("All synced");
    return;
  }
  setSyncStatus(`${events.length} pending`);
  try {
    const response = await fetch("/sync/events", {
      method: "POST",
      headers: syncHeaders(),
      body: JSON.stringify({ events })
    });
    if (!response.ok) throw new Error("Sync failed");
    const result = await response.json();
    for (const item of result.events) {
      const event = await get("events", item.local_id);
      if (event) {
        if (item.status === "rejected") {
          await put("events", { ...event, sync_status: "quarantined", sync_error: item.error || "Rejected by server" });
        } else {
          await put("events", { ...event, sync_status: "synced", server_id: item.server_id });
          await markLocalLineSynced(event);
        }
      }
    }
    state.lastSyncAt = new Date().toISOString();
    await saveState();
    await renderLines();
    await updateSyncSummary("Synced");
  } catch {
    for (const event of events) await put("events", { ...event, sync_status: "failed", retry_count: event.retry_count + 1 });
    await updateSyncSummary(`${events.length} pending`);
  }
}

async function markLocalLineSynced(event) {
  const lineId = event.payload?.line_id;
  if (!lineId) return;
  const line = await get("lines", lineId);
  if (line) await put("lines", { ...line, sync_status: "synced" });
}

async function updateSyncSummary(prefix = "") {
  const events = await all("events");
  const pending = events.filter((event) => event.sync_status !== "synced").length;
  const failed = events.filter((event) => event.sync_status === "failed").length;
  const quarantined = events.filter((event) => event.sync_status === "quarantined").length;
  const synced = events.filter((event) => event.sync_status === "synced").length;
  const label = pending
    ? `${pending} queued${failed ? `, ${failed} failed` : ""}${quarantined ? `, ${quarantined} needs review` : ""}`
    : `${synced} synced`;
  setSyncStatus(prefix ? `${prefix} / ${label}` : label);
}

async function currentCount(barcode) {
  barcode = normalizeBarcode(barcode);
  const rows = await scopedLines();
  return rows
    .filter((line) => line.barcode === barcode)
    .reduce((sum, line) => addDecimalStrings(sum, line.quantity_decimal || "0"), "0");
}

async function currentProductCount(product) {
  const rows = await scopedLines();
  return rows
    .filter((line) => line.product_id === product.id)
    .reduce((sum, line) => addDecimalStrings(sum, line.quantity_decimal || "0"), "0");
}

async function scopedLines() {
  return (await all("lines"))
    .filter((line) => line.session_id === state.sessionId && line.location_id === state.locationId)
    .sort((a, b) => b.counted_at.localeCompare(a.counted_at));
}

function renderProduct(product) {
  els.productName.textContent = product.name;
  els.productMeta.textContent = [product.category || "Uncategorised", product.size].filter(Boolean).join(" | ");
  els.productBin.textContent = `BIN: ${product.bin || "Missing"}`;
  els.productPhoto.replaceChildren();
  if (product.photo_url) {
    const image = document.createElement("img");
    image.alt = "";
    image.src = product.photo_url;
    els.productPhoto.append(image);
  } else {
    els.productPhoto.textContent = "Photo";
  }
}

function clearProductCard() {
  els.productName.textContent = "Ready to scan";
  els.productMeta.textContent = "Scan a barcode or enter one manually.";
  els.productBin.textContent = "BIN: -";
  els.productPhoto.textContent = "Photo";
}

function setMode(mode) {
  state.mode = mode;
  els.multiMode.classList.toggle("active", mode === "multi");
  els.bulkMode.classList.toggle("active", mode === "bulk");
  els.modeRow.classList.toggle("bulk", mode === "bulk");
  els.scannerPanel.classList.toggle("bulk", mode === "bulk");
  saveState();
}

function appendQuantity(key) {
  if (key === "." && state.quantity.includes(".")) return;
  if (state.quantity === "0" && key !== ".") state.quantity = key;
  else state.quantity += key;
  if (key === ".") setMode("bulk");
  renderQuantity();
}

function renderQuantity() {
  els.quantityDisplay.textContent = state.quantity || "0";
  els.quantityInput.value = state.quantity;
}

async function confirmQuantity() {
  if (!state.currentProduct) {
    els.manualBarcode.focus();
    return;
  }
  const quantity = state.quantity || "1";
  if (!isValidQuantity(quantity)) {
    (els.scanHud.querySelector("#hudQuantityInput") || els.quantityInput).classList.add("error");
    flashFeedback("error");
    vibrate([80, 50, 120]);
    return;
  }
  if (state.scanInFlight) return;
  state.scanInFlight = true;
  const saveButton = els.scanHud.querySelector('[data-action="save-next"]');
  if (saveButton) saveButton.disabled = true;
  const product = state.currentProduct;
  const existingLine = await findExistingLineForProduct(product, state.caseType);
  if (existingLine) {
    const duplicateAction = await showDuplicateDialog(existingLine, quantity);
    if (duplicateAction === "cancel") {
      state.scanInFlight = false;
      if (saveButton) saveButton.disabled = false;
      focusQuantity();
      return;
    }
    if (duplicateAction === "edit") {
      closeScanHud();
      resetActiveScan();
      openLineEditor(existingLine);
      return;
    }
    const newQuantity = addDecimalStrings(existingLine.quantity_decimal, quantity);
    await editLine(existingLine, newQuantity, "Duplicate scan added to existing line");
  } else {
    await addLine(product, quantity);
  }
  const count = await currentCount(product.barcode);
  pulse(`Saved\nCurrent count: ${count}`);
  flashFeedback("success");
  closeScanHud();
  resetActiveScan();
}

function resetActiveScan(options = {}) {
  state.quantity = "";
  state.caseType = "split";
  state.pendingBarcode = "";
  state.scanInFlight = false;
  if (!options.keepProduct) state.currentProduct = null;
  renderQuantity();
  if (!options.keepProduct) clearProductCard();
  els.quantityInput.classList.remove("pending", "error");
  els.manualBarcode.value = "";
}

async function undoLastScan() {
  const rows = await scopedLines();
  const line = rows[0];
  if (!line) return;
  await del("lines", line.id);
  await enqueue("undo_scan", { line_id: line.id, quantity_decimal: line.quantity_decimal });
  await renderLines();
  syncEvents();
}

async function editLine(line, newQuantity, reason = "") {
  if (!isValidQuantity(newQuantity)) return;
  const updated = { ...line, quantity_decimal: normalizeQuantity(newQuantity), sync_status: "pending" };
  await put("lines", updated);
  await put("audit", {
    id: crypto.randomUUID(),
    line_id: line.id,
    original_quantity: line.quantity_decimal,
    new_quantity: updated.quantity_decimal,
    changed_at: new Date().toISOString(),
    change_reason: reason
  });
  await enqueue("quantity_edit", {
    line_id: line.id,
    original_quantity: line.quantity_decimal,
    new_quantity: updated.quantity_decimal,
    change_reason: reason
  });
  await renderLines();
  syncEvents();
}

async function deleteLine(line) {
  if (!line) return;
  const confirmed = await confirmDialog("Delete scanned line", `Delete ${line.product_name} (${line.quantity_decimal})?`, "Delete");
  if (!confirmed) return;
  await del("lines", line.id);
  await enqueue("delete_line", {
    line_id: line.id,
    barcode: line.barcode,
    product_name: line.product_name,
    quantity_decimal: line.quantity_decimal
  });
  state.editingLine = null;
  await renderLines();
  syncEvents();
}

async function findExistingLineForProduct(product, caseType = state.caseType) {
  const rows = await scopedLines();
  const lookupKeys = new Set(barcodeLookupKeys(product.barcode));
  return rows.find((line) => {
    const sameProduct = line.product_id === product.id || barcodeLookupKeys(line.barcode).some((key) => lookupKeys.has(key));
    return sameProduct && (line.case_type || "split") === caseType;
  });
}

async function renderLines() {
  const query = els.lineSearch.value.toLowerCase();
  const rows = (await scopedLines()).filter((line) => {
    if (!query) return true;
    return [line.product_name, line.barcode, line.bin, line.draft_status, line.missing_bin ? "missing bin" : ""]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  els.lineList.innerHTML = "";
  for (const line of rows) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "line-row";
    const badges = [
      line.missing_bin ? `<span class="badge warning">Missing BIN</span>` : "",
      line.draft_status === "draft" ? `<span class="badge draft">Draft</span>` : ""
    ].join("");
    row.innerHTML = `
      <span class="line-thumb">${line.photo_url ? `<img alt="" src="${escapeHtml(line.photo_url)}">` : "Photo"}</span>
      <span class="line-main">
        <strong>${escapeHtml(line.product_name)}</strong>
        <small>${escapeHtml(line.barcode)} | BIN: ${escapeHtml(line.bin || "Missing")} | ${escapeHtml(line.case_type === "full" ? "Full case" : "Split case")} | ${escapeHtml(line.sync_status)}</small>
        <small>${new Date(line.counted_at).toLocaleTimeString()}</small>
        <span class="line-badges">${badges}</span>
      </span>
      <span class="qty">${escapeHtml(line.quantity_decimal)}</span>
    `;
    row.addEventListener("click", () => {
      openLineEditor(line);
    });
    els.lineList.append(row);
  }
}

function openLineEditor(line) {
  state.editingLine = line;
  els.editTitle.textContent = line.product_name;
  els.editQuantity.value = line.quantity_decimal;
  els.editDialog.showModal();
}

async function openUnknownDescription(product = state.pendingUnknownProduct || state.currentProduct) {
  if (!product || product.draft_status !== "draft") return;
  state.pendingUnknownProduct = product;
  els.unknownBarcodeText.textContent = `Barcode ${product.barcode}`;
  els.unknownNameInput.value = product.name?.startsWith("Draft ") ? "" : product.name;
  els.unknownBinInput.value = product.bin || "";
  renderUnknownProductSuggestions();
  els.unknownSuggestions.innerHTML = `<p>Type at least 3 characters to search ProcureWizard descriptions.</p>`;
  state.unknownSuggestionMatches = [];
  els.unknownDialog.showModal();
  els.unknownNameInput.focus();
}

async function suggestUnknownDescription() {
  clearTimeout(suggestUnknownDescription.timer);
  const query = els.unknownNameInput.value.trim();
  if (query.length < 3) {
    state.unknownSuggestionMatches = [];
    els.unknownSuggestions.innerHTML = `<p>Type at least 3 characters to search ProcureWizard descriptions.</p>`;
    return;
  }
  suggestUnknownDescription.timer = setTimeout(async () => {
    try {
      const response = await fetch(`/products/matches?name=${encodeURIComponent(query)}&limit=5`);
      if (!response.ok) throw new Error("Match lookup failed");
      const result = await response.json();
      state.unknownSuggestionMatches = result.matches || [];
      els.unknownSuggestions.innerHTML = state.unknownSuggestionMatches.length
        ? state.unknownSuggestionMatches.map((match, index) => `
          <button data-action="choose-unknown-pw" data-index="${index}" type="button">
            <strong>${escapeHtml(match.description || match.product?.name || "PW product")}</strong>
            <small>BIN ${escapeHtml(match.bin_number || "-")} · ${escapeHtml(match.pack_size || "-")} · ${Math.round(Number(match.score || 0) * 100)}% match</small>
          </button>
        `).join("")
        : `<p>No close ProcureWizard descriptions found. Save your description for admin review.</p>`;
    } catch {
      els.unknownSuggestions.innerHTML = `<p>ProcureWizard suggestions unavailable. You can still save the description.</p>`;
    }
  }, 250);
}

async function saveUnknownDescription() {
  const product = state.pendingUnknownProduct;
  if (!product) return;
  const description = els.unknownNameInput.value.trim();
  const bin = els.unknownBinInput.value.trim();
  if (!description) {
    els.unknownNameInput.focus();
    return;
  }
  const updated = {
    ...product,
    name: description,
    bin,
    notes: [product.notes, "Staff description captured on scan"].filter(Boolean).join("\n")
  };
  await cacheProduct(updated);
  const lines = await scopedLines();
  for (const line of lines.filter((item) => item.product_id === product.id)) {
    await put("lines", {
      ...line,
      product_name: description,
      bin,
      missing_bin: !bin,
      notes: updated.notes
    });
  }
  await enqueue("draft_product", {
    product_id: updated.id,
    barcode: updated.barcode,
    bin: updated.bin,
    placeholder_name: updated.name,
    notes: updated.notes
  });
  state.pendingUnknownProduct = updated;
  renderProduct(updated);
  await renderLines();
  syncEvents();
  els.unknownDialog.close();
  pulse("Description saved");
}

function showDuplicateDialog(existingLine, newQuantity) {
  els.duplicateProduct.textContent = `${existingLine.product_name} is already counted in ${state.locationName}.`;
  els.duplicateExisting.textContent = existingLine.quantity_decimal;
  els.duplicateNew.textContent = normalizeQuantity(newQuantity);
  els.duplicateDialog.returnValue = "cancel";
  return new Promise((resolve) => {
    const cleanup = () => {
      els.duplicateAddButton.removeEventListener("click", onAdd);
      els.duplicateEditButton.removeEventListener("click", onEdit);
      els.duplicateDialog.removeEventListener("close", onClose);
    };
    const finish = (action) => {
      cleanup();
      els.duplicateDialog.close(action);
      resolve(action);
    };
    const onAdd = () => finish("add");
    const onEdit = () => finish("edit");
    const onClose = () => {
      cleanup();
      resolve(els.duplicateDialog.returnValue || "cancel");
    };
    els.duplicateAddButton.addEventListener("click", onAdd);
    els.duplicateEditButton.addEventListener("click", onEdit);
    els.duplicateDialog.addEventListener("close", onClose);
    els.duplicateDialog.showModal();
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function pulse(message) {
  els.pulse.textContent = message;
  els.pulse.classList.remove("hidden");
  clearTimeout(pulse.timer);
  pulse.timer = setTimeout(() => els.pulse.classList.add("hidden"), 1300);
}

function confirmDialog(title, message, okLabel = "Confirm") {
  return new Promise((resolve) => {
    els.confirmTitle.textContent = title;
    els.confirmMessage.textContent = message;
    els.confirmOkButton.textContent = okLabel;
    const cleanup = () => {
      els.confirmOkButton.removeEventListener("click", onOk);
      els.confirmCancelButton.removeEventListener("click", onCancel);
      els.confirmDialog.removeEventListener("close", onClose);
    };
    const finish = (value) => {
      cleanup();
      els.confirmDialog.close(value ? "ok" : "cancel");
      resolve(value);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onClose = () => {
      cleanup();
      resolve(els.confirmDialog.returnValue === "ok");
    };
    els.confirmOkButton.addEventListener("click", onOk);
    els.confirmCancelButton.addEventListener("click", onCancel);
    els.confirmDialog.addEventListener("close", onClose);
    els.confirmDialog.showModal();
  });
}

function flashFeedback(kind) {
  const className = kind === "error" ? "feedback-error" : "feedback-success";
  document.body.classList.remove("feedback-success", "feedback-error");
  void document.body.offsetWidth;
  document.body.classList.add(className);
  clearTimeout(flashFeedback.timer);
  flashFeedback.timer = setTimeout(() => document.body.classList.remove(className), 360);
}

function focusQuantity() {
  els.quantityInput.classList.remove("error");
  els.quantityInput.classList.add("pending");
  const input = state.awaitingNextScan
    ? els.scanHud.querySelector("#hudQuantityInput") || els.quantityInput
    : els.quantityInput;
  input.focus();
  input.select();
}

function beepOnce() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const context = beepOnce.context || new AudioContext();
    beepOnce.context = context;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.16, context.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.11);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.12);
  } catch {
    // Audio feedback is a convenience; scanning must never depend on it.
  }
}

function vibrate(pattern) {
  if ("vibrate" in navigator) navigator.vibrate(pattern);
}

function resetInactivityTimer() {
  clearTimeout(state.inactivityTimer);
  state.inactivityTimer = setTimeout(() => {
    state.sleeping = true;
    setAutoScan(false);
    els.scannerPanel.classList.add("sleep");
    els.wakeButton.classList.remove("hidden");
    updateDiagnostics({ last_rejected_reason: "scanner slept after inactivity" });
    stopTorch();
  }, 180000);
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setSyncStatus("Manual scan only");
    setAutoScan(false);
    updateDiagnostics({ camera_stream: "unsupported", last_error: "getUserMedia unavailable" });
    return;
  }
  stopAutoScan();
  state.sleeping = false;
  els.scannerPanel.classList.remove("sleep");
  els.wakeButton.classList.add("hidden");
  updateDiagnostics({
    camera_stream: "opening",
    camera_owner: "browser stream",
    decoder_mode: "none",
    decoder_blocked: "-",
    last_error: "-"
  });
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        focusMode: { ideal: "continuous" }
      },
      audio: false
    });
  } catch (primaryError) {
    updateDiagnostics({ last_error: `primary camera failed: ${primaryError.name || "error"}` });
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 960 },
          height: { ideal: 540 }
        },
        audio: false
      });
    } catch {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false
      });
    }
  }
  els.preview.srcObject = state.stream;
  await els.preview.play();
  updateDiagnostics(videoDiagnostics());
  setSyncStatus("Auto scan running");
  setAutoScan(true);
  await startScanLoop();
}

function reportCameraError(error) {
  setAutoScan(false);
  updateDiagnostics({
    camera_owner: "none",
    decoder_mode: "none",
    last_error: `${error.name || "camera"}: ${error.message || "blocked"}`
  });
  setSyncStatus(`Camera blocked: ${error.name || "denied"}`);
}

function ensureCameraStarted() {
  if (state.stream?.active && els.preview.srcObject) {
    state.sleeping = false;
    els.scannerPanel.classList.remove("sleep");
    els.wakeButton.classList.add("hidden");
    updateDiagnostics(videoDiagnostics());
    if (!state.scanLoopActive) return startScanLoop();
    return Promise.resolve();
  }
  if (state.cameraStartPromise) return state.cameraStartPromise;
  state.cameraStartPromise = startCamera().finally(() => {
    state.cameraStartPromise = null;
  });
  return state.cameraStartPromise;
}

async function startScanLoop() {
  state.decoderGeneration += 1;
  const generation = state.decoderGeneration;
  state.scanLoopActive = true;
  updateDiagnostics({ scanner_generation: String(generation) });
  const zxingStarted = await startZxingScanLoop(generation);
  const nativeStarted = zxingStarted ? false : await startNativeScanLoop(generation);

  if (nativeStarted || zxingStarted) {
    const decoders = zxingStarted ? "ZXing video" : "Native";
    state.activeDecoder = decoders;
    updateDiagnostics({ decoder_mode: decoders });
    setSyncStatus(`Fast scan: ${decoders}`);
    setAutoScan(true);
    return;
  }

  updateDiagnostics({ decoder_mode: "none", last_error: "no supported decoder" });
  setSyncStatus("Manual scan available");
  setAutoScan(false);
}

function currentZxing() {
  return window.ZXing || globalThis.ZXing || null;
}

function loadZxingScript() {
  if (currentZxing()?.BrowserMultiFormatReader) {
    updateDiagnostics({ zxing_loader: "ready" });
    return Promise.resolve(currentZxing());
  }
  if (state.zxingLoadPromise) return state.zxingLoadPromise;
  updateDiagnostics({ zxing_loader: "loading" });
  state.zxingLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/vendor/zxing-library.min.js?v=typed-pw-suggest-1";
    script.async = true;
    script.onload = () => {
      const zxing = currentZxing();
      if (zxing?.BrowserMultiFormatReader) {
        updateDiagnostics({ zxing_loader: "ready" });
        resolve(zxing);
        return;
      }
      updateDiagnostics({ zxing_loader: "missing", last_error: "ZXing loaded without reader" });
      reject(new Error("ZXing reader unavailable"));
    };
    script.onerror = () => {
      updateDiagnostics({ zxing_loader: "failed", last_error: "ZXing script failed" });
      reject(new Error("ZXing script failed"));
    };
    document.head.appendChild(script);
  }).catch((error) => {
    state.zxingLoadPromise = null;
    throw error;
  });
  return state.zxingLoadPromise;
}

function zxingMethodSummary(reader) {
  return [
    typeof reader.decode === "function" ? "direct-video" : "",
    typeof reader.decodeFromVideoElementContinuously === "function" ? "library-continuous" : ""
  ].filter(Boolean).join(", ") || "none";
}

function makeZxingReader(zxing) {
  const hints = new Map();
  const formats = ZXING_FAST_FORMATS
    .map((format) => zxing.BarcodeFormat?.[format])
    .filter((format) => format !== undefined);
  if (zxing.DecodeHintType?.POSSIBLE_FORMATS) {
    hints.set(zxing.DecodeHintType.POSSIBLE_FORMATS, formats);
  }
  const reader = new zxing.BrowserMultiFormatReader(hints, ZXING_DETECT_INTERVAL_MS);
  updateDiagnostics({ zxing_methods: zxingMethodSummary(reader) });
  return reader;
}

async function startZxingScanLoop(generation = state.decoderGeneration) {
  const zxing = await loadZxingScript().catch(() => null);
  if (generation !== state.decoderGeneration || !state.scanLoopActive) return false;
  if (zxing?.BrowserMultiFormatReader) {
    state.zxingReader = makeZxingReader(zxing);
    if (typeof state.zxingReader.decode !== "function") {
      updateDiagnostics({ zxing_loader: "missing", last_error: "ZXing direct video decoder unavailable" });
      state.zxingReader = null;
      return false;
    }
    void runZxingVideoLoop(state.zxingReader, generation);
    return true;
  }
  return false;
}

function recordDecodeDuration(startedAt) {
  const elapsed = Math.max(0, Math.round(performance.now() - startedAt));
  state.decodeSamples.push(elapsed);
  state.decodeSamples = state.decodeSamples.slice(-20);
  const avg = Math.round(state.decodeSamples.reduce((sum, item) => sum + item, 0) / state.decodeSamples.length);
  updateDiagnostics({ decode_ms_avg: `${avg}ms` });
}

function shouldSkipDecode() {
  const reason = scannerBlockReason({
    sleeping: state.sleeping,
    sessionStarting: state.sessionStarting,
    scanInFlight: state.scanInFlight,
    awaitingNextScan: state.awaitingNextScan,
    documentHidden: document.hidden,
    videoReady: els.preview.readyState,
    mode: state.mode,
    pendingBarcode: state.pendingBarcode
  });
  updateDiagnostics({ decoder_blocked: reason || "-" });
  return Boolean(reason);
}

function decoderIsCurrent(generation, decoder) {
  return state.scanLoopActive && generation === state.decoderGeneration && (!decoder || decoder === state.detector || decoder === state.zxingReader);
}

function isExpectedZxingMiss(error) {
  const zxing = currentZxing();
  return [
    zxing?.NotFoundException,
    zxing?.ChecksumException,
    zxing?.FormatException
  ].some((ErrorType) => ErrorType && error instanceof ErrorType);
}

async function runZxingVideoLoop(reader, generation) {
  updateDiagnostics({ roi_size: "full video", decoder_heartbeat: "starting controlled loop" });
  while (decoderIsCurrent(generation, reader)) {
    if (shouldSkipDecode()) {
      state.framesSkipped += 1;
      updateDiagnostics({ frames_skipped: String(state.framesSkipped) });
    } else {
      const startedAt = performance.now();
      try {
        const result = reader.decode(els.preview);
        recordDecodeDuration(startedAt);
        updateDiagnostics({ decoder_heartbeat: new Date().toLocaleTimeString(), decoder_blocked: "-" });
        const barcode = decodedBarcodeText(result);
        if (barcode) {
          updateDiagnostics({ last_raw_barcode: barcode });
          await handleScan(barcode);
        }
      } catch (error) {
        updateDiagnostics({ decoder_heartbeat: new Date().toLocaleTimeString() });
        if (!isExpectedZxingMiss(error)) {
          state.decodeErrors += 1;
          updateDiagnostics({
            decode_errors: String(state.decodeErrors),
            last_error: `decode frame: ${error?.name || error?.message || "failed"}`
          });
        }
      }
    }
    await new Promise((resolve) => setTimeout(resolve, ZXING_DETECT_INTERVAL_MS));
  }
}

async function startNativeScanLoop(generation = state.decoderGeneration) {
  if (!("BarcodeDetector" in window)) {
    return false;
  }
  const supportedFormats = await BarcodeDetector.getSupportedFormats?.().catch(() => []) || [];
  const formats = BARCODE_FORMATS.filter((format) => supportedFormats.length === 0 || supportedFormats.includes(format));
  if (!formats.length) return false;
  updateDiagnostics({ supported_formats: formats.join(", ") });
  try {
    state.detector = new BarcodeDetector({ formats });
  } catch (error) {
    updateDiagnostics({ last_error: `native detector failed: ${error.name || "error"}` });
    return false;
  }
  state.nativeErrorStreak = 0;
  runNativeScanLoop(state.detector, generation);
  return true;
}

async function switchNativeToZxing(detector, generation, reason) {
  if (!decoderIsCurrent(generation, detector)) return;
  updateDiagnostics({ decoder_mode: "Native -> ZXing", last_rejected_reason: reason });
  state.detector = null;
  const zxingStarted = await startZxingScanLoop(generation);
  if (zxingStarted && generation === state.decoderGeneration) {
    state.activeDecoder = "ZXing video";
    updateDiagnostics({ decoder_mode: "ZXing video" });
    setSyncStatus("Fast scan: ZXing video");
  }
}

async function runNativeScanLoop(detector, generation) {
  let emptyFrames = 0;
  while (decoderIsCurrent(generation, detector)) {
    if (!shouldSkipDecode()) {
      state.decodeInFlight = true;
      const startedAt = performance.now();
      try {
        const codes = await detector.detect(els.preview);
        if (!decoderIsCurrent(generation, detector)) break;
        const barcode = decodedBarcodeText(codes[0]);
        recordDecodeDuration(startedAt);
        updateDiagnostics({ decoder_heartbeat: new Date().toLocaleTimeString() });
        state.nativeErrorStreak = 0;
        if (barcode) {
          emptyFrames = 0;
          updateDiagnostics({ last_raw_barcode: barcode });
          await handleScan(barcode);
        } else {
          emptyFrames += 1;
          if (emptyFrames >= 45) {
            await switchNativeToZxing(detector, generation, "native returned no barcode");
            break;
          }
        }
      } catch {
        state.decodeErrors += 1;
        state.nativeErrorStreak += 1;
        updateDiagnostics({ decode_errors: String(state.decodeErrors) });
        if (state.nativeErrorStreak >= 8) {
          await switchNativeToZxing(detector, generation, "native detector errors");
          break;
        }
        // Native barcode detection can throw while video focus/exposure settles.
      } finally {
        state.decodeInFlight = false;
      }
    } else {
      state.framesSkipped += 1;
      updateDiagnostics({ frames_skipped: String(state.framesSkipped) });
    }
    await new Promise((resolve) => setTimeout(resolve, CAMERA_DETECT_INTERVAL_MS));
  }
}

function stopAutoScan() {
  state.decoderGeneration += 1;
  state.scanLoopActive = false;
  state.zxingReader?.stopContinuousDecode?.();
  state.zxingReader?.stopAsyncDecode?.();
  state.zxingControls?.stop?.();
  state.zxingReader?.reset?.();
  state.zxingControls = null;
  state.zxingReader = null;
  state.decodeInFlight = false;
  state.activeDecoder = "none";
  state.detector = null;
  updateDiagnostics({ decoder_mode: "stopped", scanner_generation: String(state.decoderGeneration) });
}

function stopCameraStream() {
  state.stream?.getTracks?.().forEach((track) => track.stop());
  state.stream = null;
  els.preview.srcObject = null;
  updateDiagnostics(videoDiagnostics());
}

function setAutoScan(enabled) {
  els.autoScanBadge.textContent = enabled ? "Auto Scan On" : "Auto Scan Off";
  els.autoScanBadge.classList.toggle("on", enabled);
}

async function toggleTorch() {
  const track = state.stream?.getVideoTracks?.()[0];
  const capabilities = track?.getCapabilities?.();
  if (!track || !capabilities?.torch) {
    pulse("Torch not available");
    return;
  }
  const enabled = els.torchButton.dataset.enabled !== "true";
  await track.applyConstraints({ advanced: [{ torch: enabled }] });
  els.torchButton.dataset.enabled = String(enabled);
  els.torchButton.textContent = enabled ? "Flash On" : "Flash";
}

function stopTorch() {
  const track = state.stream?.getVideoTracks?.()[0];
  track?.applyConstraints?.({ advanced: [{ torch: false }] }).catch(() => {});
  els.torchButton.dataset.enabled = "false";
  els.torchButton.textContent = "Flash";
}

function setSyncStatus(text) {
  els.syncStatus.textContent = text;
  updateDiagnostics({ sync_status: text });
}

function updateDiagnostics(patch) {
  diagnostics = { ...diagnostics, ...patch };
  if (els.diagnosticsDialog?.open) renderDiagnostics();
}

function renderDiagnostics() {
  if (!els.diagnosticsList) return;
  const entries = { ...diagnostics, ...runtimeDiagnostics() };
  els.diagnosticsList.innerHTML = Object.entries(DIAGNOSTIC_LABELS)
    .map(([key, label]) => `<dt>${label}</dt><dd>${escapeHtml(entries[key] ?? "-")}</dd>`)
    .join("");
}

function diagnosticsText() {
  const entries = { ...diagnostics, ...runtimeDiagnostics() };
  return Object.entries(DIAGNOSTIC_LABELS)
    .map(([key, label]) => `${label}: ${entries[key] ?? "-"}`)
    .join("\n");
}

async function copyDiagnostics() {
  const text = diagnosticsText();
  try {
    await navigator.clipboard.writeText(text);
    pulse("Diagnostics copied");
    setSyncStatus("Diagnostics copied");
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.readOnly = true;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    pulse("Diagnostics copied");
    setSyncStatus("Diagnostics copied");
  }
}

function videoDiagnostics() {
  const track = state.stream?.getVideoTracks?.()[0];
  const settings = track?.getSettings?.();
  return {
    camera_stream: state.stream?.active ? "active" : "inactive",
    camera_track: track ? `${track.label || "camera"} (${track.readyState})` : "none",
    track_settings: settings
      ? `${settings.facingMode || "-"} ${settings.width || "-"}x${settings.height || "-"} @${settings.frameRate || "-"}fps`
      : "-",
    video_ready: String(els.preview.readyState),
    video_size: els.preview.videoWidth ? `${els.preview.videoWidth}x${els.preview.videoHeight}` : "-",
    preview_paused: els.preview.paused ? "yes" : "no"
  };
}

function runtimeDiagnostics() {
  return {
    ...videoDiagnostics(),
    secure_context: window.isSecureContext ? "yes" : "no",
    page_protocol: location.protocol,
    visibility: document.visibilityState,
    session_dialog: els.sessionDialog?.open ? "open" : "closed",
    wake_button: els.wakeButton?.classList.contains("hidden") ? "hidden" : "visible"
  };
}

async function refreshCameraPermission() {
  try {
    if (!navigator.permissions?.query) {
      updateDiagnostics({ camera_permission: "unsupported" });
      return;
    }
    const permission = await navigator.permissions.query({ name: "camera" });
    updateDiagnostics({ camera_permission: permission.state });
    permission.onchange = () => updateDiagnostics({ camera_permission: permission.state });
  } catch {
    updateDiagnostics({ camera_permission: "unknown" });
  }
}

async function resetScanner() {
  setSyncStatus("Resetting scanner...");
  stopAutoScan();
  stopCameraStream();
  state.pendingBarcode = "";
  state.scanInFlight = false;
  updateDiagnostics({
    decoder_mode: "resetting",
    last_rejected_reason: "-",
    last_error: "-"
  });
  await ensureCameraStarted().catch(reportCameraError);
}

async function clearCacheAndReload() {
  const confirmed = await confirmDialog("Clear cache", "Clear cached app shell and reload? Locally queued stocktake data remains in this browser database.", "Clear & Reload");
  if (!confirmed) return;
  if ("serviceWorker" in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
  }
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
  }
  location.reload();
}

async function processManualScan() {
  const rawInput = els.manualBarcode.value;
  els.manualBarcode.value = "";

  const barcode = normalizeBarcode(rawInput);
  if (!barcode) return;
  if (state.pendingBarcode && state.pendingBarcode !== barcode) {
    const replace = await confirmDialog("Replace pending scan", "There is an unsaved scanned product. Replace it with this manual barcode?", "Replace");
    if (!replace) {
      focusQuantity();
      return;
    }
    resetActiveScan();
  }

  const now = Date.now();
  if (state.lastManualBarcode === barcode && now - state.lastManualScanAt < SCAN_DEBOUNCE_MS) {
    rejectScan(`manual debounced ${barcode}`);
    return;
  }
  state.lastManualBarcode = barcode;
  state.lastManualScanAt = now;

  handleScan(barcode, { allowWhileSleeping: true, debounce: true, replacePending: false });
}

async function showExportReview() {
  await syncEvents();
  els.downloadExportLink.classList.add("hidden");
  els.downloadRawExportLink.href = `/export/scanned/${encodeURIComponent(state.sessionId)}`;
  els.downloadRawExportLink.classList.remove("hidden");
  els.missingBinList.innerHTML = "";
  try {
    const response = await fetch(`/pre-export/${encodeURIComponent(state.sessionId)}`);
    if (!response.ok) throw new Error("review failed");
    const review = await response.json();
    els.exportSummary.innerHTML = `
      <div class="export-metric"><span>Lines</span><strong>${escapeHtml(review.line_count || 0)}</strong></div>
      <div class="export-metric"><span>Missing BIN</span><strong>${escapeHtml(review.missing_bin_count || 0)}</strong></div>
      <div class="export-metric"><span>Drafts</span><strong>${escapeHtml(review.draft_count || 0)}</strong></div>
    `;
    if (review.missing_bin_count) {
      const rowsResponse = await fetch(`/pre-export/${encodeURIComponent(state.sessionId)}/missing-bin`);
      const rows = await rowsResponse.json();
      els.missingBinList.innerHTML = rows.rows.map((row) => `
        <div class="missing-bin-row">
          <span>
            <strong>${escapeHtml(row.product_name || row.barcode)}</strong>
            <small>${escapeHtml(row.barcode)} | ${escapeHtml(row.location)} | Qty ${escapeHtml(row.quantity_decimal)}</small>
          </span>
          <input placeholder="BIN" aria-label="BIN for ${escapeHtml(row.product_name || row.barcode)}">
          <button data-product-id="${escapeHtml(row.product_id)}" type="button">Save BIN</button>
        </div>
      `).join("");
    }
    if (!review.missing_bin_count && !review.draft_count && review.line_count) {
      els.downloadExportLink.href = `/export/${encodeURIComponent(state.sessionId)}`;
      els.downloadExportLink.classList.remove("hidden");
    }
    els.exportDialog.showModal();
  } catch {
    els.exportSummary.innerHTML = `<p>Export review is unavailable. Sync the phone before downloading scanned lines.</p>`;
    els.exportDialog.showModal();
  }
}

function csvCell(value) {
  const text = String(value ?? "");
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

async function downloadLocalRecovery() {
  const lines = (await all("lines")).filter((line) => line.session_id === state.sessionId);
  const events = (await all("events")).filter((event) => event.session_id === state.sessionId && event.sync_status !== "synced");
  const rows = [["record_type", "session_id", "location_id", "id", "barcode", "product_name", "quantity", "case_type", "sync_status", "created_at", "error"].map(csvCell).join(",")];
  for (const line of lines) {
    rows.push(["line", line.session_id, line.location_id, line.id, line.barcode, line.product_name, line.quantity_decimal, line.case_type || "split", line.sync_status, line.counted_at, ""].map(csvCell).join(","));
  }
  for (const event of events) {
    rows.push(["event", event.session_id, event.location_id, event.local_id, event.payload?.barcode || "", event.payload?.product_name || "", event.payload?.quantity_decimal || "", event.payload?.case_type || "split", event.sync_status, event.created_at, event.sync_error || ""].map(csvCell).join(","));
  }
  const url = URL.createObjectURL(new Blob([`\ufeff${rows.join("\r\n")}`], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `stocktake-${state.sessionId}-local-recovery.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  els.sessionDialog.addEventListener("cancel", (event) => event.preventDefault());
  els.multiMode.addEventListener("click", () => setMode("multi"));
  els.bulkMode.addEventListener("click", () => setMode("bulk"));
  els.manualScanButton.addEventListener("click", processManualScan);
  els.retryCameraButton.addEventListener("click", () => {
    resetScanner();
  });
  els.manualBarcode.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      processManualScan();
    }
  });
  els.quantityInput.addEventListener("input", () => {
    state.quantity = els.quantityInput.value.trim();
    renderQuantity();
  });
  els.quantityInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      state.quantity = els.quantityInput.value.trim();
      confirmQuantity();
    }
  });
  els.keypad.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.classList.contains("filler")) return;
    const key = button.dataset.key;
    const action = button.dataset.action;
    if (key) appendQuantity(key);
    if (action === "clear") state.quantity = "";
    if (action === "backspace") state.quantity = state.quantity.slice(0, -1);
    if (action === "confirm") confirmQuantity();
    renderQuantity();
  });
  els.scanHud.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button?.dataset.action === "describe-unknown") openUnknownDescription();
    if (button?.dataset.action === "next-scan") closeScanHud();
    if (button?.dataset.action === "skip-scan") closeScanHud({ reset: true });
    if (button?.dataset.action === "save-next") confirmQuantity();
    if (button?.dataset.action === "set-case-type") {
      state.caseType = button.dataset.caseType === "full" ? "full" : "split";
      renderCaseTypeControl();
      vibrate(20);
    }
    if (button?.dataset.action === "set-quantity") {
      state.quantity = button.dataset.value || "1";
      const input = els.scanHud.querySelector("#hudQuantityInput");
      if (input) {
        input.value = state.quantity;
        input.dataset.replaceOnEntry = "true";
      }
      renderQuantity();
    }
    if (button?.dataset.action === "add-quantity") {
      state.quantity = addDecimalStrings(state.quantity || "0", button.dataset.value || "0");
      const input = els.scanHud.querySelector("#hudQuantityInput");
      if (input) {
        input.value = state.quantity;
        input.dataset.replaceOnEntry = "true";
      }
      renderQuantity();
    }
    if (button?.dataset.action === "clear-quantity") {
      state.quantity = "";
      const input = els.scanHud.querySelector("#hudQuantityInput");
      if (input) {
        input.value = "";
        input.dataset.replaceOnEntry = "true";
      }
      renderQuantity();
    }
    if (button?.dataset.action === "quantity-key") {
      const input = els.scanHud.querySelector("#hudQuantityInput");
      const key = button.dataset.value || "";
      if (!input || (key === "." && state.quantity.includes("."))) return;
      if (input.dataset.replaceOnEntry === "true") {
        state.quantity = key === "." ? "0." : key;
        input.dataset.replaceOnEntry = "false";
      } else {
        state.quantity = state.quantity === "0" && key !== "." ? key : `${state.quantity}${key}`;
      }
      input.value = state.quantity;
      renderQuantity();
    }
    if (button?.dataset.action === "quantity-backspace") {
      const input = els.scanHud.querySelector("#hudQuantityInput");
      state.quantity = state.quantity.slice(0, -1);
      if (input) {
        input.value = state.quantity;
        input.dataset.replaceOnEntry = "false";
      }
      renderQuantity();
    }
    if (button?.dataset.action === "choose-pw") chooseProcureWizardMatch(Number(button.dataset.index));
  });
  els.scanHud.addEventListener("input", (event) => {
    if (event.target.id !== "hudQuantityInput") return;
    state.quantity = event.target.value.trim();
    event.target.dataset.replaceOnEntry = "false";
    renderQuantity();
  });
  els.scanHud.addEventListener("focusin", (event) => {
    if (event.target.id !== "hudQuantityInput") return;
    event.target.select();
    event.target.dataset.replaceOnEntry = "true";
  });
  els.scanHud.addEventListener("keydown", (event) => {
    if (event.target.id === "hudQuantityInput" && event.key === "Enter") {
      event.preventDefault();
      confirmQuantity();
    }
  });
  els.saveUnknownButton.addEventListener("click", saveUnknownDescription);
  els.unknownNameInput.addEventListener("input", renderUnknownProductSuggestions);
  els.unknownProductSuggestions.addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="choose-existing-product"]');
    if (button) chooseExistingProductForUnknown(Number(button.dataset.index));
  });
  els.unknownNameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveUnknownDescription();
    }
  });
  els.unknownNameInput.addEventListener("input", suggestUnknownDescription);
  els.unknownSuggestions.addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="choose-unknown-pw"]');
    if (!button) return;
    const match = state.unknownSuggestionMatches[Number(button.dataset.index)];
    if (!match) return;
    state.procurewizardMatches = [match];
    chooseProcureWizardMatch(0);
    els.unknownDialog.close();
  });
  els.undoButton.addEventListener("click", undoLastScan);
  els.linesButton.addEventListener("click", async () => {
    await renderLines();
    els.linesDialog.showModal();
  });
  els.lineSearch.addEventListener("input", renderLines);
  els.saveEditButton.addEventListener("click", async () => {
    await editLine(state.editingLine, els.editQuantity.value);
    els.editDialog.close();
  });
  els.deleteLineButton.addEventListener("click", async () => {
    await deleteLine(state.editingLine);
    els.editDialog.close();
  });
  els.locationSelect.addEventListener("change", async () => {
    const rows = await scopedLines();
    if (rows.length && !(await confirmDialog("Switch location", "Switch location for new scans? Existing lines stay in their original location.", "Switch"))) {
      els.locationSelect.value = state.locationId;
      return;
    }
    state.locationId = els.locationSelect.value;
    state.locationName = els.locationSelect.selectedOptions[0]?.textContent || state.locationId;
    writeSessionMemory();
    renderSessionHeader();
    await enqueue("location_change", { location_id: state.locationId, location_name: state.locationName });
    await saveState();
    await renderLines();
  });
  els.sessionPreset.addEventListener("change", () => {
    const selected = catalogSessions.find((session) => session.id === els.sessionPreset.value);
    els.sessionCodeInput.value = selected?.id || els.sessionPreset.value;
  });
  els.changeSessionButton.addEventListener("click", async () => {
    const rows = await scopedLines();
    if (rows.length && !(await confirmDialog("Change session", "Change session for new scans? Existing counted lines will stay in the current session.", "Change"))) {
      return;
    }
    stopAutoScan();
    await showSessionDialog(true);
    resetScanner();
  });
  els.torchButton.addEventListener("click", toggleTorch);
  els.wakeButton.addEventListener("click", () => {
    state.sleeping = false;
    els.scannerPanel.classList.remove("sleep");
    els.wakeButton.classList.add("hidden");
    resetInactivityTimer();
    if (!state.stream?.active) {
      resetScanner();
      return;
    }
    setAutoScan(true);
    if (!state.scanLoopActive) startScanLoop();
  });
  els.exportButton.addEventListener("click", showExportReview);
  els.downloadRecoveryButton.addEventListener("click", downloadLocalRecovery);
  els.diagnosticsButton.addEventListener("click", () => {
    renderDiagnostics();
    els.diagnosticsDialog.showModal();
  });
  els.copyDiagnosticsButton.addEventListener("click", copyDiagnostics);
  els.resetScannerButton.addEventListener("click", resetScanner);
  els.clearCacheButton.addEventListener("click", clearCacheAndReload);
  els.missingBinList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const row = button.closest(".missing-bin-row");
    const bin = row.querySelector("input").value.trim();
    if (!bin) return;
    await fetch(`/products/${encodeURIComponent(button.dataset.productId)}/bin`, {
      method: "PATCH",
      headers: syncHeaders(),
      body: JSON.stringify({ bin })
    });
    await syncCatalog();
    await showExportReview();
  });
  window.addEventListener("online", async () => {
    if (await syncCatalog()) syncEvents();
  });
  document.addEventListener("visibilitychange", () => {
    updateDiagnostics({ visibility: document.visibilityState });
    if (document.hidden || state.sleeping || els.sessionDialog.open) return;
    if (!state.stream?.active) {
      ensureCameraStarted().catch(reportCameraError);
      return;
    }
    els.preview.play().catch(reportCameraError);
    if (!state.scanLoopActive) startScanLoop();
  });
}

async function init() {
  await initServiceWorker();
  await refreshCameraPermission();
  db = await openDb();
  await restoreState();
  renderLocations([
    { id: "cellar", name: "Cellar" },
    { id: "main-bar", name: "Bar" },
    { id: "brasseries", name: "Brasseries" },
    { id: "m-and-e", name: "M&E" }
  ]);
  bindEvents();
  setMode(state.mode);
  renderQuantity();
  await loadProductIndex();
  if (!(await syncCatalog())) return;
  await showSessionDialog(false);
  renderSessionHeader();
  await renderLines();
  await syncEvents();
  resetInactivityTimer();
  if (state.restoredSession && diagnostics.camera_permission !== "granted") {
    els.wakeButton.classList.remove("hidden");
    setSyncStatus("Tap to start scanner");
    return;
  }
  ensureCameraStarted().catch(reportCameraError);
}

init();

async function initServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    updateDiagnostics({ service_worker: "unsupported" });
    return;
  }
  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    updateDiagnostics({ service_worker: registration.active ? "active" : "installing" });
    if (registration.waiting) updateDiagnostics({ service_worker: "update waiting" });
    registration.addEventListener("updatefound", () => {
      updateDiagnostics({ service_worker: "update found" });
    });
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      updateDiagnostics({ service_worker: "controller changed" });
    });
  } catch (error) {
    updateDiagnostics({ service_worker: "registration failed", last_error: error.message || "sw failed" });
  }
}
