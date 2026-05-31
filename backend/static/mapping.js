import {
  BARCODE_FORMATS,
  CAMERA_DETECT_INTERVAL_MS,
  SCAN_DEBOUNCE_MS,
  ZXING_FAST_FORMATS,
  decodedBarcodeText,
  normalizeBarcode
} from "./frontend-utils.js?v=phone-mapping-1";

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
  actions: document.querySelector("#mappingActions"),
  showExisting: document.querySelector("#mappingShowExisting"),
  showCreate: document.querySelector("#mappingShowCreate"),
  scanNext: document.querySelector("#mappingScanNext"),
  clear: document.querySelector("#mappingClear"),
  existingPanel: document.querySelector("#mappingExistingPanel"),
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
  createNotes: document.querySelector("#mappingCreateNotes")
};

const state = {
  stream: null,
  detector: null,
  zxingReader: null,
  scanning: false,
  scanInFlight: false,
  lastBarcode: "",
  lastScanAt: 0,
  currentBarcode: "",
  currentSuggestion: {},
  searchTimer: null
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
  els.createPanel.classList.toggle("hidden", panel !== "create");
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
  const barcode = normalizeBarcode(rawBarcode);
  if (!barcode || state.scanInFlight) return;
  const now = Date.now();
  if (barcode === state.lastBarcode && now - state.lastScanAt < SCAN_DEBOUNCE_MS) return;
  state.lastBarcode = barcode;
  state.lastScanAt = now;
  state.scanInFlight = true;
  state.currentBarcode = barcode;
  setStatus(`Checking ${barcode}...`);
  showPanels("");
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
      return;
    }
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
    const query = state.currentSuggestion.name || barcode;
    els.productSearch.value = query;
    await searchProducts(query);
  } catch (err) {
    showResult({
      kicker: `Barcode ${barcode}`,
      title: "Lookup failed",
      message: err.message,
      variant: "error"
    });
    setStatus("Lookup failed", "error");
  } finally {
    state.scanInFlight = false;
  }
}

async function searchProducts(search = els.productSearch.value.trim()) {
  const params = new URLSearchParams({
    search,
    only_missing: "false",
    limit: "20",
    offset: "0"
  });
  try {
    const data = await api(`/admin/api/barcode-mapping/products?${params}`);
    renderProducts(data.products || []);
  } catch (err) {
    els.productResults.innerHTML = `<p class="mapping-error">${escapeHtml(err.message)}</p>`;
  }
}

function renderProducts(products) {
  els.productResults.innerHTML = products.length ? products.map((product) => `
    <button class="mapping-product-choice" type="button" data-product-id="${escapeHtml(product.id)}">
      ${product.photo_url ? `<img src="${escapeHtml(product.photo_url)}" alt="">` : `<span></span>`}
      <strong>${escapeHtml(product.name)}</strong>
      <small>BIN ${escapeHtml(product.bin || product.procurewizard?.bin_number || "-")} | PID ${escapeHtml(product.procurewizard?.pid || "-")} | ${escapeHtml(product.size || "-")}</small>
    </button>
  `).join("") : `<p>No products found. Try another search or add a new product.</p>`;
}

async function mapToProduct(productId) {
  if (!state.currentBarcode) return;
  try {
    await api(`/admin/api/products/${encodeURIComponent(productId)}/barcodes`, {
      method: "POST",
      body: JSON.stringify({
        barcode: state.currentBarcode,
        label: "Mapped barcode",
        is_primary: false
      })
    });
    showResult({
      kicker: `Mapped ${state.currentBarcode}`,
      title: "Barcode saved",
      message: `Linked to ${productId}. Scan the next product.`,
      variant: "mapped"
    });
    setStatus("Saved", "ok");
    resetForNext(false);
  } catch (err) {
    showResult({
      kicker: `Barcode ${state.currentBarcode}`,
      title: "Could not save mapping",
      message: err.message,
      variant: "error"
    });
    setStatus("Save failed", "error");
  }
}

async function createProduct(event) {
  event.preventDefault();
  if (!state.currentBarcode) return;
  const name = els.createName.value.trim();
  if (!name) {
    els.createName.focus();
    return;
  }
  try {
    await api("/admin/api/products", {
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
        draft_status: "confirmed"
      })
    });
    showResult({
      kicker: `Created ${state.currentBarcode}`,
      title: name,
      message: "New catalog product saved. Scan the next barcode.",
      suggestion: { image_url: els.createPhoto.value.trim() },
      variant: "mapped"
    });
    setStatus("Created", "ok");
    resetForNext(false);
  } catch (err) {
    showResult({
      kicker: `Barcode ${state.currentBarcode}`,
      title: "Could not create product",
      message: err.message,
      variant: "error"
    });
    setStatus("Create failed", "error");
  }
}

function resetForNext(clearCard = true) {
  state.currentBarcode = "";
  state.currentSuggestion = {};
  els.manualBarcode.value = "";
  els.productSearch.value = "";
  els.productResults.innerHTML = "";
  els.createForm.reset();
  els.createUnit.value = "each";
  setReadyForMapping(false);
  showPanels("");
  if (clearCard) {
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
      if (!state.scanInFlight && els.preview.readyState >= 2) {
        const codes = await state.detector.detect(els.preview);
        const barcode = decodedBarcodeText(codes[0]);
        if (barcode) await lookupBarcode(barcode);
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
    if (barcode && !state.scanInFlight) lookupBarcode(barcode);
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
  els.showExisting.addEventListener("click", () => {
    showPanels("existing");
    els.productSearch.focus();
  });
  els.showCreate.addEventListener("click", () => {
    showPanels("create");
    els.createName.focus();
  });
  els.scanNext.addEventListener("click", () => resetForNext(true));
  els.clear.addEventListener("click", () => resetForNext(true));
  els.productSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    searchProducts();
  });
  els.productSearch.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => searchProducts(), 250);
  });
  els.productResults.addEventListener("click", (event) => {
    const button = event.target.closest(".mapping-product-choice");
    if (button?.dataset.productId) mapToProduct(button.dataset.productId);
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
