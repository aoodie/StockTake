import {
  BARCODE_FORMATS,
  CAMERA_DETECT_INTERVAL_MS,
  SCAN_DEBOUNCE_MS,
  ZXING_FAST_FORMATS,
  canonicalizeBarcode,
  confirmBarcodeCandidate,
  decodedBarcodeText,
  normalizeBarcode
} from "./frontend-utils.js?v=barcode-canonical-2";

const els = {
  loginView: document.querySelector("#mappingLoginView"),
  appView: document.querySelector("#mappingAppView"),
  loginForm: document.querySelector("#mappingLoginForm"),
  password: document.querySelector("#mappingPassword"),
  loginError: document.querySelector("#mappingLoginError"),
  preview: document.querySelector("#mappingPreview"),
  cameraPanel: document.querySelector("#mappingCameraPanel"),
  scanStatus: document.querySelector("#mappingScanStatus"),
  retryCamera: document.querySelector("#mappingRetryCamera"),
  manualForm: document.querySelector("#mappingManualForm"),
  manualBarcode: document.querySelector("#mappingManualBarcode"),
  resultCard: document.querySelector("#mappingResultCard"),
  suggestedPanel: document.querySelector("#mappingSuggestedPanel"),
  suggestedResults: document.querySelector("#mappingSuggestedResults"),
  openSearch: document.querySelector("#mappingOpenSearch"),
  actions: document.querySelector("#mappingActions"),
  showExisting: document.querySelector("#mappingShowExisting"),
  showCreate: document.querySelector("#mappingShowCreate"),
  scanNext: document.querySelector("#mappingScanNext"),
  existingPanel: document.querySelector("#mappingExistingPanel"),
  confirmPanel: document.querySelector("#mappingConfirmPanel"),
  productSearchForm: document.querySelector("#mappingProductSearchForm"),
  productSearch: document.querySelector("#mappingProductSearch"),
  productResults: document.querySelector("#mappingProductResults"),
  createPanel: document.querySelector("#mappingCreatePanel"),
  createForm: document.querySelector("#mappingCreateForm"),
  createName: document.querySelector("#mappingCreateName"),
  createBin: document.querySelector("#mappingCreateBin"),
  createCategory: document.querySelector("#mappingCreateCategory"),
  createSize: document.querySelector("#mappingCreateSize"),
  createUnit: document.querySelector("#mappingCreateUnit"),
  createPhoto: document.querySelector("#mappingCreatePhoto"),
  createNotes: document.querySelector("#mappingCreateNotes"),
  recovery: document.querySelector("#mappingRecovery")
};

const state = {
  stream: null,
  detector: null,
  zxingReader: null,
  scanning: false,
  scanInFlight: false,
  lastBarcode: "",
  lastScanAt: 0,
  barcodeCandidate: null,
  currentBarcode: "",
  currentSuggestion: {},
  scanLocked: false,
  lastAction: null,
  saveInFlight: false,
  searchTimer: null,
  pendingProduct: null,
  productChoices: new Map()
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      setAuthed(false);
      throw new Error("Login required");
    }
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function setAuthed(value) {
  els.loginView.classList.toggle("hidden", value);
  els.appView.classList.toggle("hidden", !value);
}

function setStatus(message, variant = "") {
  els.scanStatus.textContent = message;
  els.cameraPanel.classList.toggle("mapping-camera-ok", variant === "ok");
  els.cameraPanel.classList.toggle("mapping-camera-error", variant === "error");
}

function vibrate(pattern) {
  navigator.vibrate?.(pattern);
}

function showResult({ kicker, title, message, product, suggestion, variant = "" }) {
  const photo = product?.photo_url || suggestion?.image_url || "";
  els.resultCard.className = `mapping-card mapping-result ${variant}`;
  els.resultCard.innerHTML = `
    <p class="mapping-kicker">${escapeHtml(kicker)}</p>
    <div class="mapping-result-main">
      ${photo ? `<img src="${escapeHtml(photo)}" alt="">` : `<span class="mapping-photo-empty"></span>`}
      <div>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(message)}</p>
      </div>
    </div>
  `;
}

function showPanels(panel = "") {
  els.existingPanel.classList.toggle("hidden", panel !== "existing");
  els.confirmPanel.classList.toggle("hidden", panel !== "confirm");
  els.createPanel.classList.toggle("hidden", panel !== "create");
}

function openCreatePanel() {
  showPanels("create");
  els.createName.focus();
}

function showSuggestedMatches(show) {
  els.suggestedPanel.classList.toggle("hidden", !show);
}

function setReadyForMapping(ready) {
  els.actions.classList.toggle("hidden", !ready);
}

function suggestionNameIsUseful(suggestion, barcode) {
  const name = normalizeBarcode(suggestion?.name || "");
  return Boolean(name && name.toLowerCase() !== `product ${barcode}`.toLowerCase() && name.toLowerCase() !== `draft ${barcode}`.toLowerCase());
}

function prefillCreateForm(suggestion = {}, barcode = state.currentBarcode) {
  els.createName.value = suggestionNameIsUseful(suggestion, barcode) ? suggestion.name : "";
  els.createBin.value = suggestion.bin || "";
  els.createCategory.value = suggestion.category || "";
  els.createSize.value = suggestion.size || "";
  els.createUnit.value = suggestion.unit || "each";
  els.createPhoto.value = suggestion.image_url || "";
  const sourceUrls = Array.isArray(suggestion.source_urls) ? suggestion.source_urls.join("\n") : "";
  els.createNotes.value = [suggestion.source_name ? `Source: ${suggestion.source_name}` : "", sourceUrls].filter(Boolean).join("\n");
}

async function lookupBarcode(rawBarcode) {
  const barcode = canonicalizeBarcode(rawBarcode);
  if (!barcode || state.scanInFlight) return;
  if (state.scanLocked) return;
  const now = Date.now();
  if (barcode === state.lastBarcode && now - state.lastScanAt < SCAN_DEBOUNCE_MS) return;
  state.lastBarcode = barcode;
  state.lastScanAt = now;
  state.scanInFlight = true;
  state.currentBarcode = barcode;
  els.recovery.classList.add("hidden");
  setStatus(`Checking ${barcode}...`);
  showPanels("");
  showSuggestedMatches(false);
  setReadyForMapping(false);
  try {
    const result = await api(`/admin/api/products/lookup/${encodeURIComponent(barcode)}`);
    state.currentSuggestion = result.suggested || {};
    if (result.exists) {
      showResult({
        kicker: `Barcode ${barcode}`,
        title: result.product?.name || result.product?.id || "Already mapped",
        message: `Already belongs to ${result.product?.id || "a catalog product"}.`,
        product: result.product,
        variant: "mapped"
      });
      setStatus("Already mapped", "ok");
      vibrate(35);
      return;
    }
    state.scanLocked = true;
    prefillCreateForm(state.currentSuggestion, barcode);
    showResult({
      kicker: `New barcode ${barcode}`,
      title: state.currentSuggestion.name || "Barcode is not mapped",
      message: state.currentSuggestion.name
        ? "Choose an existing product or create a new one with these suggested details."
        : "Choose an existing product or add a new product name before saving.",
      suggestion: state.currentSuggestion,
      variant: "unmapped"
    });
    setReadyForMapping(true);
    setStatus("Ready to map", "ok");
    vibrate([30, 40, 30]);
    const query = state.currentSuggestion.name || barcode;
    els.productSearch.value = query;
    await searchProducts(query, {
      target: els.suggestedResults,
      limit: 5,
      onlyMissing: true,
      supplementAll: true,
      emptyMessage: "No close matches yet. Search all products or create a draft."
    });
    showSuggestedMatches(true);
    showPanels("existing");
    await searchProducts(query);
  } catch (err) {
    showResult({
      kicker: `Barcode ${barcode}`,
      title: "Lookup failed",
      message: `${err.message}. Retry, type another barcode, or keep scanning.`,
      variant: "error"
    });
    setStatus("Lookup failed", "error");
    vibrate([80, 40, 80]);
  } finally {
    state.scanInFlight = false;
  }
}

async function searchProducts(search = els.productSearch.value.trim(), options = {}) {
  const target = options.target || els.productResults;
  const limit = options.limit || 20;
  const onlyMissing = options.onlyMissing ? "true" : "false";
  const params = new URLSearchParams({
    search,
    only_missing: onlyMissing,
    limit: String(limit),
    offset: "0"
  });
  try {
    const data = await api(`/admin/api/barcode-mapping/products?${params}`);
    let products = data.products || [];
    if (options.supplementAll && products.length < limit) {
      const allParams = new URLSearchParams({
        search,
        only_missing: "false",
        limit: String(limit),
        offset: "0"
      });
      const allData = await api(`/admin/api/barcode-mapping/products?${allParams}`);
      const seen = new Set(products.map((product) => product.id));
      products = [
        ...products,
        ...(allData.products || []).filter((product) => !seen.has(product.id))
      ].slice(0, limit);
    }
    renderProducts(products, target, options.emptyMessage);
    return products;
  } catch (err) {
    target.innerHTML = `<p class="mapping-error">${escapeHtml(err.message)}</p>`;
    return [];
  }
}

function renderProducts(products, target = els.productResults, emptyMessage = "No products found. Try another search or add a new product.") {
  products.forEach((product) => state.productChoices.set(product.id, product));
  target.innerHTML = products.length ? products.map((product) => `
    <button class="mapping-product-choice" type="button" data-product-id="${escapeHtml(product.id)}">
      ${product.photo_url ? `<img src="${escapeHtml(product.photo_url)}" alt="">` : `<span></span>`}
      <strong>${escapeHtml(product.name)}</strong>
      <small>BIN ${escapeHtml(product.bin || product.procurewizard?.bin_number || "-")} | PID ${escapeHtml(product.procurewizard?.pid || "-")} | ${escapeHtml(product.size || product.procurewizard?.pack_size || "-")}</small>
    </button>
  `).join("") : `
    <div class="mapping-no-results">
      <p>${escapeHtml(emptyMessage)}</p>
      <button class="mapping-create-draft-cta" type="button">No match - create draft product</button>
    </div>
  `;
}

function showMapConfirmation(productId) {
  const product = state.productChoices.get(productId);
  if (!product || !state.currentBarcode) return;
  state.pendingProduct = product;
  const photo = product.photo_url || "";
  const aliases = Array.isArray(product.barcodes)
    ? product.barcodes.map((alias) => alias.barcode).filter(Boolean).slice(0, 4).join(", ")
    : "";
  els.confirmPanel.innerHTML = `
    <p class="mapping-kicker">Confirm mapping</p>
    <div class="mapping-confirm-product">
      ${photo ? `<img src="${escapeHtml(photo)}" alt="">` : `<span class="mapping-photo-empty"></span>`}
      <div>
        <h2>${escapeHtml(product.name || product.id)}</h2>
        <p>Scanned barcode: <strong>${escapeHtml(state.currentBarcode)}</strong></p>
        <small>BIN ${escapeHtml(product.bin || product.procurewizard?.bin_number || "-")} | PID ${escapeHtml(product.procurewizard?.pid || "-")} | ${escapeHtml(product.size || product.procurewizard?.pack_size || "-")}</small>
        ${aliases ? `<small>Known barcodes: ${escapeHtml(aliases)}</small>` : ""}
      </div>
    </div>
    <div class="mapping-confirm-actions">
      <button id="mappingConfirmMap" type="button">Map to this product</button>
      <button id="mappingCancelMap" class="mapping-secondary" type="button">Choose another</button>
    </div>
  `;
  showPanels("confirm");
  setStatus("Confirm product");
}

async function mapToProduct(productId) {
  if (!state.currentBarcode || state.saveInFlight) return;
  state.saveInFlight = true;
  try {
    const result = await api(`/admin/api/products/${encodeURIComponent(productId)}/barcodes`, {
      method: "POST",
      body: JSON.stringify({
        barcode: state.currentBarcode,
        label: "Mapped barcode",
        is_primary: false,
        source_screen: "phone_mapping"
      })
    });
    showResult({
      kicker: `Mapped ${state.currentBarcode}`,
      title: "Barcode saved",
      message: `Linked to ${productId}. Scan the next product.`,
      variant: "mapped"
    });
    state.lastAction = { auditId: result.mapping_audit_id, barcode: state.currentBarcode, productId, title: productId };
    setStatus("Saved", "ok");
    vibrate(45);
    showRecovery(`Mapped to ${productId}`);
    resetForNext(false);
  } catch (err) {
    showResult({
      kicker: `Barcode ${state.currentBarcode}`,
      title: "Could not save mapping",
      message: err.message,
      variant: "error"
    });
    setStatus("Save failed", "error");
    vibrate([90, 45, 90]);
  } finally {
    state.saveInFlight = false;
  }
}

async function createProduct(event) {
  event.preventDefault();
  if (!state.currentBarcode || state.saveInFlight) return;
  const name = els.createName.value.trim();
  if (!name) {
    els.createName.focus();
    return;
  }
  state.saveInFlight = true;
  try {
    const result = await api("/admin/api/products", {
      method: "POST",
      body: JSON.stringify({
        barcode: state.currentBarcode,
        name,
        bin: els.createBin.value.trim(),
        category: els.createCategory.value.trim(),
        size: els.createSize.value.trim(),
        unit: els.createUnit.value.trim() || "each",
        photo_url: els.createPhoto.value.trim() || null,
        notes: els.createNotes.value.trim() || null,
        draft_status: "draft",
        source_screen: "phone_mapping"
      })
    });
    showResult({
      kicker: `Created ${state.currentBarcode}`,
      title: name,
      message: "Draft product saved for admin review. Scan the next barcode.",
      suggestion: { image_url: els.createPhoto.value.trim() },
      variant: "mapped"
    });
    state.lastAction = { auditId: result.mapping_audit_id, barcode: state.currentBarcode, productId: result.product_id, title: name };
    setStatus("Created", "ok");
    vibrate(45);
    showRecovery(`Created draft ${name}`);
    resetForNext(false);
  } catch (err) {
    showResult({
      kicker: `Barcode ${state.currentBarcode}`,
      title: "Could not create product",
      message: err.message,
      variant: "error"
    });
    setStatus("Create failed", "error");
    vibrate([90, 45, 90]);
  } finally {
    state.saveInFlight = false;
  }
}

function showRecovery(message) {
  const action = state.lastAction;
  els.recovery.innerHTML = `
    <div>
      <strong>${escapeHtml(message)}</strong>
      <span>${escapeHtml(action?.barcode || "")}</span>
    </div>
    <button id="mappingUndoLast" type="button" ${action?.auditId ? "" : "disabled"}>Undo</button>
    <button id="mappingRecoveryNext" type="button">Scan next</button>
  `;
  els.recovery.classList.remove("hidden");
}

async function undoLastAction() {
  const action = state.lastAction;
  if (!action?.auditId) return;
  try {
    await api(`/admin/api/barcode-mapping/recent/${encodeURIComponent(action.auditId)}/undo`, {
      method: "POST",
      body: "{}"
    });
    showResult({
      kicker: `Undone ${action.barcode}`,
      title: "Last mapping removed",
      message: "The barcode is available again. Scan or type it when ready.",
      variant: "unmapped"
    });
    setStatus("Undo complete", "ok");
    vibrate([30, 30, 30]);
    state.lastAction = null;
    els.recovery.classList.add("hidden");
    resetForNext(false);
  } catch (err) {
    showResult({
      kicker: "Undo failed",
      title: "Could not undo last action",
      message: err.message,
      variant: "error"
    });
    setStatus("Undo failed", "error");
    vibrate([90, 45, 90]);
  }
}

function resetForNext(clearCard = true) {
  state.currentBarcode = "";
  state.currentSuggestion = {};
  state.pendingProduct = null;
  state.scanLocked = false;
  els.manualBarcode.value = "";
  els.productSearch.value = "";
  els.productResults.innerHTML = "";
  els.suggestedResults.innerHTML = "";
  els.createForm.reset();
  els.createUnit.value = "each";
  setReadyForMapping(false);
  showPanels("");
  showSuggestedMatches(false);
  if (clearCard) {
    els.recovery.classList.add("hidden");
    showResult({
      kicker: "Waiting for barcode",
      title: "Scan a bottle or case barcode",
      message: "When the barcode is not already mapped, choose an existing product or add it as a new catalog item."
    });
    setStatus("Ready");
  }
}

async function startCamera() {
  stopCamera();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false
    });
    els.preview.srcObject = state.stream;
    await els.preview.play();
    state.scanning = true;
    setStatus("Scanning", "ok");
    if ("BarcodeDetector" in window) {
      state.detector = new BarcodeDetector({ formats: BARCODE_FORMATS });
      runNativeLoop();
    } else {
      startZxingLoop();
    }
  } catch (err) {
    setStatus(`Camera blocked: ${err.name || "denied"}`, "error");
  }
}

function stopCamera() {
  state.scanning = false;
  state.detector = null;
  state.zxingReader?.reset?.();
  state.zxingReader = null;
  state.stream?.getTracks?.().forEach((track) => track.stop());
  state.stream = null;
}

async function runNativeLoop() {
  while (state.scanning && state.detector) {
    try {
      if (!state.scanInFlight && !state.scanLocked && els.preview.readyState >= 2) {
        const codes = await state.detector.detect(els.preview);
        const barcode = decodedBarcodeText(codes[0]);
        const decision = confirmBarcodeCandidate(state.barcodeCandidate, barcode);
        state.barcodeCandidate = decision.candidate;
        if (decision.confirmed) {
          state.barcodeCandidate = null;
          await lookupBarcode(barcode);
        }
      }
    } catch {
      // Camera frames can fail while focus/exposure settles.
    }
    await new Promise((resolve) => setTimeout(resolve, CAMERA_DETECT_INTERVAL_MS));
  }
}

function startZxingLoop() {
  if (!window.ZXing?.BrowserMultiFormatReader) {
    setStatus("Scanner unavailable", "error");
    return;
  }
  const hints = new Map();
  const formats = ZXING_FAST_FORMATS
    .map((format) => window.ZXing.BarcodeFormat?.[format])
    .filter((format) => format !== undefined);
  if (window.ZXing.DecodeHintType?.POSSIBLE_FORMATS) {
    hints.set(window.ZXing.DecodeHintType.POSSIBLE_FORMATS, formats);
  }
  state.zxingReader = new window.ZXing.BrowserMultiFormatReader(hints, 180);
  state.zxingReader.decodeFromVideoElementContinuously(els.preview, (result) => {
    const barcode = decodedBarcodeText(result);
    const decision = confirmBarcodeCandidate(state.barcodeCandidate, barcode);
    state.barcodeCandidate = decision.candidate;
    if (decision.confirmed && !state.scanInFlight && !state.scanLocked) {
      state.barcodeCandidate = null;
      lookupBarcode(barcode);
    }
  });
}

function bindEvents() {
  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.loginError.textContent = "";
    try {
      await api("/admin/api/login", {
        method: "POST",
        body: JSON.stringify({ password: els.password.value })
      });
      setAuthed(true);
      await startCamera();
    } catch (err) {
      els.loginError.textContent = err.message;
    }
  });
  els.retryCamera.addEventListener("click", startCamera);
  els.manualForm.addEventListener("submit", (event) => {
    event.preventDefault();
    lookupBarcode(els.manualBarcode.value);
  });
  els.openSearch.addEventListener("click", () => {
    showPanels("existing");
    els.productSearch.focus();
  });
  els.showExisting.addEventListener("click", () => {
    showPanels("existing");
    els.productSearch.focus();
  });
  els.showCreate.addEventListener("click", () => {
    openCreatePanel();
  });
  els.scanNext.addEventListener("click", () => resetForNext(true));
  els.productSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    searchProducts();
  });
  els.productSearch.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => searchProducts(), 250);
  });
  els.productSearch.addEventListener("focus", () => {
    if (!els.productSearch.value) return;
    els.productSearch.value = "";
    els.productResults.innerHTML = "";
  });
  els.productResults.addEventListener("click", (event) => {
    if (event.target.closest(".mapping-create-draft-cta")) {
      openCreatePanel();
      return;
    }
    const button = event.target.closest(".mapping-product-choice");
    if (button?.dataset.productId) showMapConfirmation(button.dataset.productId);
  });
  els.suggestedResults.addEventListener("click", (event) => {
    if (event.target.closest(".mapping-create-draft-cta")) {
      openCreatePanel();
      return;
    }
    const button = event.target.closest(".mapping-product-choice");
    if (button?.dataset.productId) showMapConfirmation(button.dataset.productId);
  });
  els.confirmPanel.addEventListener("click", (event) => {
    if (event.target.closest("#mappingConfirmMap") && state.pendingProduct?.id) {
      mapToProduct(state.pendingProduct.id);
    }
    if (event.target.closest("#mappingCancelMap")) {
      state.pendingProduct = null;
      showPanels("existing");
      setStatus("Ready to map", "ok");
    }
  });
  els.recovery.addEventListener("click", (event) => {
    if (event.target.closest("#mappingUndoLast")) undoLastAction();
    if (event.target.closest("#mappingRecoveryNext")) resetForNext(true);
  });
  els.createForm.addEventListener("submit", createProduct);
  window.addEventListener("pagehide", stopCamera);
}

async function init() {
  bindEvents();
  try {
    await api("/admin/api/me");
    setAuthed(true);
    await startCamera();
  } catch {
    setAuthed(false);
  }
}

init();
