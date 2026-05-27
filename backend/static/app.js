const DB_NAME = "stocktake-web";
const DB_VERSION = 1;
const DEVICE_KEY = "stocktake-device-id";
const SCAN_DEBOUNCE_MS = 850;
const productIndex = new Map();

const els = {
  preview: document.querySelector("#preview"),
  scannerPanel: document.querySelector("#scannerPanel"),
  autoScanBadge: document.querySelector("#autoScanBadge"),
  torchButton: document.querySelector("#torchButton"),
  wakeButton: document.querySelector("#wakeButton"),
  pulse: document.querySelector("#pulse"),
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
  syncStatus: document.querySelector("#syncStatus"),
  linesDialog: document.querySelector("#linesDialog"),
  lineSearch: document.querySelector("#lineSearch"),
  lineList: document.querySelector("#lineList"),
  editDialog: document.querySelector("#editDialog"),
  editTitle: document.querySelector("#editTitle"),
  editQuantity: document.querySelector("#editQuantity"),
  saveEditButton: document.querySelector("#saveEditButton"),
  deleteLineButton: document.querySelector("#deleteLineButton")
};

let db;
let state = {
  mode: "multi",
  period: today(),
  sessionId: `session-${today()}`,
  sessionName: today(),
  locationId: "main-bar",
  locationName: "Main Bar",
  quantity: "",
  currentProduct: null,
  pendingBarcode: "",
  lastBarcode: null,
  lastScanAt: 0,
  hardwareBlockedUntil: 0,
  sleeping: false,
  editingLine: null,
  detector: null,
  zxingReader: null,
  zxingControls: null,
  stream: null,
  scanLoopActive: false,
  inactivityTimer: null
};

function today() {
  return new Date().toISOString().slice(0, 10);
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

async function saveState() {
  await put("state", {
    key: "active",
    ...state,
    stream: undefined,
    detector: undefined,
    zxingReader: undefined,
    zxingControls: undefined,
    inactivityTimer: undefined
  });
}

async function restoreState() {
  const saved = await get("state", "active");
  if (saved) state = { ...state, ...saved, stream: null, detector: null, scanLoopActive: false };
}

async function syncCatalog() {
  try {
    const response = await fetch("/catalog");
    if (!response.ok) throw new Error("Catalog failed");
    const catalog = await response.json();
    productIndex.clear();
    for (const product of catalog.products) {
      await cacheProduct(normalProduct(product));
    }
    if (catalog.locations.length) renderLocations(catalog.locations);
    await put("meta", {
      key: "catalog",
      catalog_version: catalog.catalog_version,
      last_catalog_sync_at: new Date().toISOString()
    });
    setSyncStatus("Catalog synced");
  } catch {
    setSyncStatus("Offline catalog");
  }
}

async function loadProductIndex() {
  productIndex.clear();
  for (const product of await all("products")) {
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
  for (const key of new Set(keys)) {
    productIndex.set(key, product);
  }
}

function normalizeBarcode(value) {
  return String(value ?? "").trim();
}

function barcodeLookupKeys(value) {
  const raw = normalizeBarcode(value);
  if (!raw) return [];
  const keys = [raw];
  if (/^\d+$/.test(raw)) {
    keys.push(String(Number(raw)));
    keys.push(raw.padStart(8, "0"), raw.padStart(12, "0"), raw.padStart(13, "0"));
  }
  return keys;
}

function renderLocations(locations) {
  els.locationSelect.innerHTML = "";
  for (const location of locations) {
    const option = document.createElement("option");
    option.value = location.id;
    option.textContent = location.name;
    els.locationSelect.append(option);
  }
  if (!locations.some((location) => location.id === state.locationId)) {
    state.locationId = locations[0].id;
    state.locationName = locations[0].name;
  }
  els.locationSelect.value = state.locationId;
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

async function handleScan(barcode, options = {}) {
  barcode = normalizeBarcode(barcode);
  if (!barcode) return;
  if (state.sleeping && !options.allowWhileSleeping) return;
  if (state.pendingBarcode && !options.replacePending) return;
  resetInactivityTimer();
  const now = Date.now();
  if (
    (state.mode === "multi" || options.debounce) &&
    state.lastBarcode === barcode &&
    now - state.lastScanAt < SCAN_DEBOUNCE_MS
  ) {
    return;
  }
  state.lastBarcode = barcode;
  state.lastScanAt = now;

  const product = await getProduct(barcode);
  state.currentProduct = product;
  state.pendingBarcode = barcode;
  state.quantity = "";
  renderProduct(product);
  renderQuantity();
  focusQuantity();
  beepOnce();
  pulse("Scanned\nEnter quantity");
  flashFeedback(product.draft_status === "draft" ? "error" : "success");
  vibrate(product.draft_status === "draft" ? [80, 50, 120] : 35);
  await saveState();
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
    unit: product.unit,
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
  const events = (await all("events")).filter((event) => event.sync_status !== "synced").slice(0, 50);
  if (!events.length) {
    setSyncStatus("All synced");
    return;
  }
  setSyncStatus(`${events.length} pending`);
  try {
    const response = await fetch("/sync/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events })
    });
    if (!response.ok) throw new Error("Sync failed");
    const result = await response.json();
    for (const item of result.events) {
      const event = await get("events", item.local_id);
      if (event) await put("events", { ...event, sync_status: "synced", server_id: item.server_id });
    }
    setSyncStatus("Synced");
  } catch {
    for (const event of events) await put("events", { ...event, sync_status: "failed", retry_count: event.retry_count + 1 });
    setSyncStatus(`${events.length} pending`);
  }
}

async function currentCount(barcode) {
  barcode = normalizeBarcode(barcode);
  const rows = await scopedLines();
  const total = rows
    .filter((line) => line.barcode === barcode)
    .reduce((sum, line) => sum + Number(line.quantity_decimal || "0"), 0);
  return String(Math.round(total * 10000) / 10000);
}

async function scopedLines() {
  return (await all("lines"))
    .filter((line) => line.session_id === state.sessionId && line.location_id === state.locationId)
    .sort((a, b) => b.counted_at.localeCompare(a.counted_at));
}

function renderProduct(product) {
  els.productName.textContent = product.name;
  els.productMeta.textContent = `${product.category || "Uncategorised"} ${product.size ? "• " + product.size : ""}`;
  els.productBin.textContent = `BIN: ${product.bin || "Missing"}`;
  els.productPhoto.innerHTML = product.photo_url ? `<img alt="" src="${product.photo_url}">` : "Photo";
}

function clearProductCard() {
  els.productName.textContent = "Ready to scan";
  els.productMeta.textContent = "Scan a barcode or enter one manually.";
  els.productBin.textContent = "BIN: -";
  els.productPhoto.textContent = "Photo";
}

function normalizeQuantity(value) {
  if (!isValidQuantity(value)) return "0";
  return String(Number(value));
}

function isValidQuantity(value) {
  return value !== "" && value !== "." && /^\d+(\.\d+)?$/.test(value);
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
    els.quantityInput.classList.add("error");
    flashFeedback("error");
    vibrate([80, 50, 120]);
    return;
  }
  const existingLine = await findExistingLineForProduct(state.currentProduct);
  if (existingLine) {
    const addToExisting = window.confirm(
      `${state.currentProduct.name} has already been scanned in ${state.locationName}. Add this quantity to the existing line?`
    );
    if (!addToExisting) {
      focusQuantity();
      return;
    }
    const newQuantity = addDecimalStrings(existingLine.quantity_decimal, quantity);
    await editLine(existingLine, newQuantity, "Duplicate scan added to existing line");
  } else {
    await addLine(state.currentProduct, quantity);
  }
  const count = await currentCount(state.currentProduct.barcode);
  pulse(`Saved\nCurrent count: ${count}`);
  flashFeedback("success");
  state.quantity = "";
  state.pendingBarcode = "";
  state.currentProduct = null;
  renderQuantity();
  clearProductCard();
  els.quantityInput.classList.remove("pending", "error");
  els.manualBarcode.value = "";
  els.manualBarcode.focus();
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
  const confirmed = window.confirm(`Delete scanned line for ${line.product_name} (${line.quantity_decimal})?`);
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

async function findExistingLineForProduct(product) {
  const rows = await scopedLines();
  const lookupKeys = new Set(barcodeLookupKeys(product.barcode));
  return rows.find((line) => barcodeLookupKeys(line.barcode).some((key) => lookupKeys.has(key)));
}

function addDecimalStrings(left, right) {
  const total = Number(left || "0") + Number(right || "0");
  return String(Math.round(total * 1000000) / 1000000);
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
    row.innerHTML = `
      <span>
        <strong>${escapeHtml(line.product_name)}</strong>
        <small>${escapeHtml(line.barcode)} • BIN: ${escapeHtml(line.bin || "Missing")} • ${escapeHtml(line.sync_status)}</small>
        <small>${escapeHtml(line.draft_status)} • ${new Date(line.counted_at).toLocaleTimeString()}</small>
      </span>
      <span class="qty">${escapeHtml(line.quantity_decimal)}</span>
    `;
    row.addEventListener("click", () => {
      state.editingLine = line;
      els.editTitle.textContent = line.product_name;
      els.editQuantity.value = line.quantity_decimal;
      els.editDialog.showModal();
    });
    els.lineList.append(row);
  }
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
  els.quantityInput.focus();
  els.quantityInput.select();
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
    stopTorch();
  }, 180000);
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setSyncStatus("Manual scan only");
    setAutoScan(false);
    return;
  }
  stopAutoScan();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false
    });
  } catch {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false
    });
  }
  els.preview.srcObject = state.stream;
  await els.preview.play();
  setSyncStatus("Auto scan running");
  setAutoScan(true);
  startScanLoop();
}

async function startScanLoop() {
  if (window.ZXing?.BrowserMultiFormatReader) {
    state.zxingReader = new window.ZXing.BrowserMultiFormatReader();
    state.zxingControls = await state.zxingReader.decodeFromVideoElementContinuously(els.preview, (result) => {
      if (result?.text && !state.sleeping) handleScan(result.text);
    });
    return;
  }

  if (!("BarcodeDetector" in window)) {
    setSyncStatus("Manual scan available");
    setAutoScan(false);
    return;
  }
  state.detector = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39"] });
  state.scanLoopActive = true;
  while (state.scanLoopActive) {
    if (!state.sleeping && els.preview.readyState >= 2) {
      try {
        const codes = await state.detector.detect(els.preview);
        if (codes[0]?.rawValue) await handleScan(codes[0].rawValue);
      } catch {
        setSyncStatus("Scanner warming");
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 180));
  }
}

function stopAutoScan() {
  state.scanLoopActive = false;
  state.zxingControls?.stop?.();
  state.zxingReader?.reset?.();
  state.zxingControls = null;
  state.zxingReader = null;
  state.detector = null;
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
}

function processManualScan() {
  const rawInput = els.manualBarcode.value;
  els.manualBarcode.value = "";

  const barcode = normalizeBarcode(rawInput);
  if (!barcode) return;

  const now = Date.now();
  if (now < state.hardwareBlockedUntil) return;
  state.hardwareBlockedUntil = now + SCAN_DEBOUNCE_MS;

  handleScan(barcode, { allowWhileSleeping: true, debounce: true, replacePending: true });
}

function bindEvents() {
  els.multiMode.addEventListener("click", () => setMode("multi"));
  els.bulkMode.addEventListener("click", () => setMode("bulk"));
  els.manualScanButton.addEventListener("click", processManualScan);
  els.retryCameraButton.addEventListener("click", () => {
    setSyncStatus("Opening camera...");
    startCamera().catch((error) => {
      setAutoScan(false);
      setSyncStatus(`Camera blocked: ${error.name || "denied"}`);
    });
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
    state.locationId = els.locationSelect.value;
    state.locationName = els.locationSelect.selectedOptions[0]?.textContent || state.locationId;
    await enqueue("location_change", { location_id: state.locationId, location_name: state.locationName });
    await saveState();
    await renderLines();
  });
  els.torchButton.addEventListener("click", toggleTorch);
  els.wakeButton.addEventListener("click", () => {
    state.sleeping = false;
    els.scannerPanel.classList.remove("sleep");
    els.wakeButton.classList.add("hidden");
    setAutoScan(!!state.stream);
    resetInactivityTimer();
  });
  els.exportButton.addEventListener("click", () => {
    window.location.href = `/export/${encodeURIComponent(state.sessionId)}`;
  });
  window.addEventListener("online", () => {
    syncCatalog();
    syncEvents();
  });
}

async function init() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  db = await openDb();
  await restoreState();
  els.periodLabel.textContent = state.period;
  renderLocations([{ id: "main-bar", name: "Main Bar" }, { id: "cellar", name: "Cellar" }]);
  bindEvents();
  setMode(state.mode);
  renderQuantity();
  await loadProductIndex();
  await syncCatalog();
  await renderLines();
  await syncEvents();
  resetInactivityTimer();
  startCamera().catch((error) => {
    setAutoScan(false);
    setSyncStatus(`Camera blocked: ${error.name || "denied"}`);
  });
}

init();
