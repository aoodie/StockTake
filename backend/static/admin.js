const state = {
  authed: false,
  tasks: [],
  aiSuggestions: [],
  llmSettings: null,
  products: [],
  sessions: [],
  productIssues: [],
  selectedTask: null,
  selectedProductDetail: null,
  procurewizard: null,
  lookupTimer: null,
  // Pagination & Selection State
  productsLimit: 50,
  productsOffset: 0,
  productsTotal: 0,
  selectedProductIds: [],
  mappingProducts: [],
  mappingRecent: [],
  mappingLimit: 50,
  mappingOffset: 0,
  mappingTotal: 0,
  selectedMappingProductId: null,
  mappingLookupTimer: null,
  mappingSearchTimer: null
};

const els = {
  adminStatus: document.querySelector("#adminStatus"),
  loginView: document.querySelector("#loginView"),
  appView: document.querySelector("#appView"),
  loginForm: document.querySelector("#loginForm"),
  loginError: document.querySelector("#loginError"),
  adminPassword: document.querySelector("#adminPassword"),
  logoutButton: document.querySelector("#logoutButton"),
  summaryGrid: document.querySelector("#summaryGrid"),
  tabs: [...document.querySelectorAll(".tabs button")],
  views: [...document.querySelectorAll(".view")],
  taskList: document.querySelector("#taskList"),
  refreshTasksButton: document.querySelector("#refreshTasksButton"),
  aiSuggestionList: document.querySelector("#aiSuggestionList"),
  aiSuggestionStatus: document.querySelector("#aiSuggestionStatus"),
  generateIssueSuggestionsButton: document.querySelector("#generateIssueSuggestionsButton"),
  reloadAiSuggestionsButton: document.querySelector("#reloadAiSuggestionsButton"),
  llmSettingsForm: document.querySelector("#llmSettingsForm"),
  openaiModelInput: document.querySelector("#openaiModelInput"),
  openaiTokenInput: document.querySelector("#openaiTokenInput"),
  clearOpenaiTokenInput: document.querySelector("#clearOpenaiTokenInput"),
  testLlmSettingsButton: document.querySelector("#testLlmSettingsButton"),
  llmSettingsStatus: document.querySelector("#llmSettingsStatus"),
  productSearchForm: document.querySelector("#productSearchForm"),
  productSearch: document.querySelector("#productSearch"),
  productList: document.querySelector("#productList"),
  mappingSearchForm: document.querySelector("#mappingSearchForm"),
  mappingSearch: document.querySelector("#mappingSearch"),
  mappingOnlyMissing: document.querySelector("#mappingOnlyMissing"),
  mappingReloadButton: document.querySelector("#mappingReloadButton"),
  mappingRecentReloadButton: document.querySelector("#mappingRecentReloadButton"),
  mappingRecentPanel: document.querySelector("#mappingRecentPanel"),
  mappingRecentList: document.querySelector("#mappingRecentList"),
  mappingCountText: document.querySelector("#mappingCountText"),
  mappingActiveCard: document.querySelector("#mappingActiveCard"),
  mappingBarcodeForm: document.querySelector("#mappingBarcodeForm"),
  mappingBarcodeInput: document.querySelector("#mappingBarcodeInput"),
  mappingLabelInput: document.querySelector("#mappingLabelInput"),
  mappingLookupStatus: document.querySelector("#mappingLookupStatus"),
  mappingSkipButton: document.querySelector("#mappingSkipButton"),
  mappingOpenDetailButton: document.querySelector("#mappingOpenDetailButton"),
  mappingProductList: document.querySelector("#mappingProductList"),
  mappingPageText: document.querySelector("#mappingPageText"),
  mappingLoadMoreButton: document.querySelector("#mappingLoadMoreButton"),
  sessionForm: document.querySelector("#sessionForm"),
  sessionId: document.querySelector("#sessionId"),
  sessionName: document.querySelector("#sessionName"),
  sessionDate: document.querySelector("#sessionDate"),
  sessionList: document.querySelector("#sessionList"),
  exportSession: document.querySelector("#exportSession"),
  exportReview: document.querySelector("#exportReview"),
  pwOutlet: document.querySelector("#pwOutlet"),
  pwCsvFile: document.querySelector("#pwCsvFile"),
  pwImportButton: document.querySelector("#pwImportButton"),
  pwDownloadLink: document.querySelector("#pwDownloadLink"),
  pwStatus: document.querySelector("#pwStatus"),
  pwRows: document.querySelector("#pwRows"),
  catalogExportRefresh: document.querySelector("#catalogExportRefresh"),
  catalogExportSummary: document.querySelector("#catalogExportSummary"),
  catalogRestoreFile: document.querySelector("#catalogRestoreFile"),
  catalogRestoreButton: document.querySelector("#catalogRestoreButton"),
  catalogRestoreStatus: document.querySelector("#catalogRestoreStatus"),
  
  // Barcode review dialog
  taskDialog: document.querySelector("#taskDialog"),
  taskDialogTitle: document.querySelector("#taskDialogTitle"),
  taskBarcodeLock: document.querySelector("#taskBarcodeLock"),
  taskName: document.querySelector("#taskName"),
  taskBin: document.querySelector("#taskBin"),
  taskCategory: document.querySelector("#taskCategory"),
  taskSize: document.querySelector("#taskSize"),
  taskUnit: document.querySelector("#taskUnit"),
  taskPhoto: document.querySelector("#taskPhoto"),
  taskNotes: document.querySelector("#taskNotes"),
  taskPhotoPreview: document.querySelector("#taskPhotoPreview"),
  taskSources: document.querySelector("#taskSources"),
  approveTaskButton: document.querySelector("#approveTaskButton"),
  rejectTaskButton: document.querySelector("#rejectTaskButton"),
  
  // Custom Toast System
  toastContainer: document.querySelector("#toastContainer"),
  
  // Pagination & Add controls
  loadMoreProductsButton: document.querySelector("#loadMoreProductsButton"),
  productsCountText: document.querySelector("#productsCountText"),
  createProductButton: document.querySelector("#createProductButton"),
  reviewIssuesButton: document.querySelector("#reviewIssuesButton"),
  productIssueList: document.querySelector("#productIssueList"),
  
  // Bulk panel controls
  bulkActionPanel: document.querySelector("#bulkActionPanel"),
  selectedCountText: document.querySelector("#selectedCountText"),
  bulkBin: document.querySelector("#bulkBin"),
  bulkCategory: document.querySelector("#bulkCategory"),
  bulkUpdateButton: document.querySelector("#bulkUpdateButton"),
  bulkDeleteButton: document.querySelector("#bulkDeleteButton"),
  
  // Create/Edit product dialog
  productDialog: document.querySelector("#productDialog"),
  productDialogForm: document.querySelector("#productDialogForm"),
  productDialogTitle: document.querySelector("#productDialogTitle"),
  pDialogId: document.querySelector("#pDialogId"),
  pDialogBarcode: document.querySelector("#pDialogBarcode"),
  pDialogName: document.querySelector("#pDialogName"),
  pDialogBin: document.querySelector("#pDialogBin"),
  pDialogCategory: document.querySelector("#pDialogCategory"),
  pDialogSize: document.querySelector("#pDialogSize"),
  pDialogUnit: document.querySelector("#pDialogUnit"),
  pDialogPhoto: document.querySelector("#pDialogPhoto"),
  pDialogNotes: document.querySelector("#pDialogNotes"),
  productLookupStatus: document.querySelector("#productLookupStatus"),
  productPhotoPreview: document.querySelector("#productPhotoPreview"),
  cancelProductDialogButton: document.querySelector("#cancelProductDialogButton"),
  saveProductDialogButton: document.querySelector("#saveProductDialogButton"),
  
  // Product master detail dialog
  productDetailDialog: document.querySelector("#productDetailDialog"),
  productDetailForm: document.querySelector("#productDetailForm"),
  productDetailTitle: document.querySelector("#productDetailTitle"),
  productDetailSummary: document.querySelector("#productDetailSummary"),
  productAliasList: document.querySelector("#productAliasList"),
  productAuditList: document.querySelector("#productAuditList"),
  aliasBarcode: document.querySelector("#aliasBarcode"),
  aliasLabel: document.querySelector("#aliasLabel"),
  addAliasButton: document.querySelector("#addAliasButton"),
  generateProductAiButton: document.querySelector("#generateProductAiButton"),
  mergeSourceProductId: document.querySelector("#mergeSourceProductId"),
  mergeTargetProductId: document.querySelector("#mergeTargetProductId"),
  mergeProductButton: document.querySelector("#mergeProductButton"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmTitle: document.querySelector("#confirmTitle"),
  confirmMessage: document.querySelector("#confirmMessage"),
  confirmOkButton: document.querySelector("#confirmOkButton"),
  confirmCancelButton: document.querySelector("#confirmCancelButton")
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

// Toast Alert System
function showToast(message, type = 'success') {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'error' ? '❌' : 'ℹ️'}</span>
    <span>${escapeHtml(message)}</span>
  `;
  els.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 5000);
}

function confirmDialog(title, message, okLabel = "Confirm") {
  els.confirmTitle.textContent = title;
  els.confirmMessage.textContent = message;
  els.confirmOkButton.textContent = okLabel;
  return new Promise((resolve) => {
    const closeWith = (value) => {
      els.confirmDialog.close(value ? "ok" : "cancel");
    };
    const onClose = () => {
      els.confirmOkButton.removeEventListener("click", onOk);
      els.confirmCancelButton.removeEventListener("click", onCancel);
      els.confirmDialog.removeEventListener("close", onClose);
      resolve(els.confirmDialog.returnValue === "ok");
    };
    const onOk = () => closeWith(true);
    const onCancel = () => closeWith(false);
    els.confirmOkButton.addEventListener("click", onOk);
    els.confirmCancelButton.addEventListener("click", onCancel);
    els.confirmDialog.addEventListener("close", onClose);
    els.confirmDialog.showModal();
  });
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
      throw new Error("Admin session expired. Log in again.");
    }
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function setAuthed(value) {
  state.authed = value;
  els.loginView.classList.toggle("hidden", value);
  els.appView.classList.toggle("hidden", !value);
  els.adminStatus.textContent = value ? "Signed in" : "Login required";
}

async function loadDashboard() {
  const data = await api("/admin/api/dashboard");
  els.summaryGrid.innerHTML = Object.entries(data)
    .map(([key, value]) => `
      <div class="metric">
        <span>${escapeHtml(key.replaceAll("_", " "))}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `)
    .join("");
}

function statusBadge(status) {
  const bad = ["failed", "rejected"].includes(status);
  const warn = ["queued", "enriching", "review_needed"].includes(status);
  return `<span class="badge ${bad ? "bad" : warn ? "warn" : ""}">${escapeHtml(status)}</span>`;
}

function issueBadges(issues = []) {
  if (!issues.length) return `<span class="badge">clean</span>`;
  return issues.map((issue) => `<span class="badge warn">${escapeHtml(issue.replaceAll("_", " "))}</span>`).join("");
}

function confidenceBadge(confidence = 0, risk = "review") {
  const value = Number(confidence || 0);
  const label = `${Math.round(value * 100)}% · ${risk.replaceAll("_", " ")}`;
  const tone = risk === "blocked" || risk === "low_confidence" ? "bad" : risk === "review" ? "warn" : "";
  return `<span class="badge ${tone}">${escapeHtml(label)}</span>`;
}

function imageCandidates(suggestion = {}) {
  const candidates = Array.isArray(suggestion.image_candidates) ? [...suggestion.image_candidates] : [];
  if (suggestion.image_url && !candidates.includes(suggestion.image_url)) candidates.unshift(suggestion.image_url);
  return candidates.filter(Boolean).slice(0, 6);
}

function setPhotoPreview(container, url, label = "Product photo") {
  const cleanUrl = (url || "").trim();
  container.classList.toggle("hidden", !cleanUrl);
  container.innerHTML = cleanUrl ? `
    <img src="${escapeHtml(cleanUrl)}" alt="${escapeHtml(label)}">
    <div>
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(cleanUrl)}</span>
    </div>
  ` : "";
}

function applySuggestionToProductDialog(suggestion = {}) {
  const name = (suggestion.name || "").trim();
  const photoUrl = (suggestion.image_url || imageCandidates(suggestion)[0] || "").trim();
  if (name && (!els.pDialogName.value.trim() || els.pDialogName.value.startsWith("Product "))) {
    els.pDialogName.value = name;
  }
  if (suggestion.category && !els.pDialogCategory.value.trim()) els.pDialogCategory.value = suggestion.category;
  if (suggestion.size && !els.pDialogSize.value.trim()) els.pDialogSize.value = suggestion.size;
  if (suggestion.unit && (!els.pDialogUnit.value.trim() || els.pDialogUnit.value === "each")) els.pDialogUnit.value = suggestion.unit;
  if (photoUrl && !els.pDialogPhoto.value.trim()) {
    els.pDialogPhoto.value = photoUrl;
    setPhotoPreview(els.productPhotoPreview, photoUrl, "Suggested photo");
  }
  const noteLines = [
    suggestion.brand ? `Brand: ${suggestion.brand}` : "",
    suggestion.source_name ? `Source: ${suggestion.source_name}` : "",
    suggestion.confidence ? `Confidence: ${suggestion.confidence}` : ""
  ].filter(Boolean);
  if (noteLines.length && !els.pDialogNotes.value.trim()) els.pDialogNotes.value = noteLines.join("\n");
}

async function lookupProductForDialog() {
  if (els.pDialogId.value) return;
  const barcode = els.pDialogBarcode.value.trim();
  if (barcode.length < 4) {
    els.productLookupStatus.textContent = "";
    return;
  }
  els.productLookupStatus.textContent = "Looking up product details...";
  try {
    const result = await api(`/admin/api/products/lookup/${encodeURIComponent(barcode)}`);
    if (result.exists) {
      const product = result.product || {};
      els.productLookupStatus.textContent = `Already exists: ${product.name || product.id}`;
      showToast(`Barcode already belongs to ${product.name || product.id}`, "error");
      return;
    }
    const suggestion = result.suggested || {};
    applySuggestionToProductDialog(suggestion);
    els.productLookupStatus.textContent = suggestion.name ? `Filled from ${suggestion.source_name || "lookup"}` : "No strong online match found";
  } catch (err) {
    els.productLookupStatus.textContent = "Lookup failed";
    showToast(err.message, "error");
  }
}

async function loadTasks() {
  try {
    const data = await api("/admin/api/tasks");
    state.tasks = data.tasks;
    els.taskList.innerHTML = state.tasks.length ? state.tasks.map((task) => {
      const suggestion = task.suggested || {};
      const title = suggestion.name || task.current_name || `Barcode ${task.barcode}`;
      return `
        <article class="task-row">
          ${suggestion.image_url ? `<img class="row-thumb" src="${escapeHtml(suggestion.image_url)}" alt="">` : `<div class="row-thumb empty"></div>`}
          <div>
            <h3>${escapeHtml(title)}</h3>
            <p class="meta-details">
              <span><strong>Barcode:</strong> ${escapeHtml(task.barcode)}</span>
              <span><strong>Bin:</strong> ${escapeHtml(task.current_bin || "No BIN")}</span>
              <span><strong>Updated:</strong> ${escapeHtml(task.updated_at.slice(0, 16).replace('T', ' '))}</span>
            </p>
            ${task.error ? `<p class="error" style="text-align:left;">${escapeHtml(task.error)}</p>` : ""}
          </div>
          ${statusBadge(task.status)}
          <div>
            <button class="secondary" data-action="enrich" data-id="${escapeHtml(task.id)}" type="button">Enrich</button>
            <button class="primary-btn" data-action="review" data-id="${escapeHtml(task.id)}" type="button">Review</button>
          </div>
        </article>
      `;
    }).join("") : `<p class="meta" style="grid-column: 1/-1; text-align: center; padding: 24px;">No product tasks.</p>`;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderAiSuggestions() {
  els.aiSuggestionList.innerHTML = state.aiSuggestions.length ? state.aiSuggestions.map((item) => {
    const fields = item.field_values || {};
    const reasons = item.reasons || [];
    const sources = item.sources || [];
    const fieldRows = Object.entries(fields).map(([key, value]) => `
      <label class="ai-field-row">
        <input type="checkbox" data-ai-field="${escapeHtml(key)}" ${(key === "photo_url" || key === "draft_status") ? "" : "checked"}>
        <span>${escapeHtml(key.replaceAll("_", " "))}</span>
        <strong>${escapeHtml(value)}</strong>
      </label>
    `).join("");
    return `
      <article class="ai-card" data-ai-card="${escapeHtml(item.id)}">
        <div class="ai-card-head">
          <div>
            <h3>${escapeHtml(item.title || item.target_id || "AI suggestion")}</h3>
            <p class="meta-details">
              <span><strong>Target:</strong> ${escapeHtml(item.target_type)} · ${escapeHtml(item.target_id || "unlinked")}</span>
              <span><strong>Barcode:</strong> ${escapeHtml(item.barcode || "None")}</span>
              <span><strong>Updated:</strong> ${escapeHtml((item.updated_at || "").slice(0, 16).replace("T", " "))}</span>
            </p>
          </div>
          ${statusBadge(item.status)}
          ${confidenceBadge(item.confidence, item.risk_level)}
        </div>
        <div class="ai-card-body">
          <div class="ai-field-grid">
            ${fieldRows || `<p class="meta">No safe field changes found. Keep for manual review.</p>`}
          </div>
          <div class="ai-evidence">
            ${reasons.length ? `<h4>Why</h4>${reasons.map((reason) => `<p>${escapeHtml(reason)}</p>`).join("")}` : ""}
            ${sources.length ? `<h4>Sources</h4>${sources.map((source) => (
              `<a href="${escapeHtml(source.url || source)}" target="_blank" rel="noreferrer">${escapeHtml(source.name || source.url || source)}</a>`
            )).join("")}` : ""}
            ${item.error ? `<p class="error" style="text-align:left;">${escapeHtml(item.error)}</p>` : ""}
          </div>
        </div>
        <div class="ai-actions">
          <button class="secondary" data-action="open-ai-target" data-target-type="${escapeHtml(item.target_type)}" data-target-id="${escapeHtml(item.target_id || "")}" type="button">Open Target</button>
          <button class="secondary warning" data-action="reject-ai" data-id="${escapeHtml(item.id)}" type="button" ${item.status === "pending" ? "" : "disabled"}>Reject</button>
          <button class="primary-btn" data-action="apply-ai" data-id="${escapeHtml(item.id)}" type="button" ${item.status === "pending" && Object.keys(fields).length ? "" : "disabled"}>Apply Fields</button>
        </div>
      </article>
    `;
  }).join("") : `<p class="meta" style="text-align:center; padding:24px;">No AI suggestions in this queue.</p>`;
}

async function loadAiSuggestions() {
  try {
    const status = els.aiSuggestionStatus.value;
    const data = await api(`/admin/api/ai-suggestions?status=${encodeURIComponent(status)}&limit=50`);
    state.aiSuggestions = data.suggestions || [];
    renderAiSuggestions();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadLlmSettings() {
  try {
    const data = await api("/admin/api/settings/llm");
    state.llmSettings = data;
    els.openaiModelInput.value = data.openai_model || "";
    els.openaiTokenInput.value = "";
    els.clearOpenaiTokenInput.checked = false;
    const keyText = data.has_openai_key
      ? `Token configured (${data.openai_key_source}: ${data.openai_key_preview})`
      : "No token";
    els.llmSettingsStatus.textContent = `${keyText} · Env default: ${data.env_default || "none"}`;
    els.llmSettingsStatus.classList.toggle("error", !data.has_openai_key);
  } catch (err) {
    els.llmSettingsStatus.textContent = err.message;
    els.llmSettingsStatus.classList.add("error");
  }
}

async function saveLlmSettings() {
  const openai_model = els.openaiModelInput.value.trim();
  const openai_api_key = els.openaiTokenInput.value.trim();
  const clear_openai_api_key = els.clearOpenaiTokenInput.checked;
  if (!openai_model) {
    showToast("OpenAI model is required.", "error");
    return;
  }
  try {
    const payload = { openai_model, clear_openai_api_key };
    if (openai_api_key) payload.openai_api_key = openai_api_key;
    const data = await api("/admin/api/settings/llm", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    state.llmSettings = data;
    els.openaiTokenInput.value = "";
    els.clearOpenaiTokenInput.checked = false;
    if (!data.has_openai_key) {
      els.llmSettingsStatus.textContent = `Saved model ${data.openai_model}, but no token is configured.`;
      els.llmSettingsStatus.classList.add("error");
      showToast("Model saved, but an OpenAI token is required.", "error");
      return;
    }
    await testLlmSettings();
  } catch (err) {
    els.llmSettingsStatus.textContent = err.message;
    els.llmSettingsStatus.classList.add("error");
    showToast(err.message, "error");
  }
}

async function testLlmSettings() {
  els.testLlmSettingsButton.disabled = true;
  els.llmSettingsStatus.textContent = "Testing saved token and model access...";
  els.llmSettingsStatus.classList.remove("error");
  try {
    const data = await api("/admin/api/settings/llm/test", {
      method: "POST",
      body: "{}"
    });
    els.llmSettingsStatus.textContent = data.message;
    els.llmSettingsStatus.classList.remove("error");
    showToast(data.message);
    return true;
  } catch (err) {
    els.llmSettingsStatus.textContent = `Connection failed: ${err.message}`;
    els.llmSettingsStatus.classList.add("error");
    showToast(err.message, "error");
    return false;
  } finally {
    els.testLlmSettingsButton.disabled = false;
  }
}

async function generateIssueSuggestions() {
  els.generateIssueSuggestionsButton.disabled = true;
  try {
    const data = await api("/admin/api/ai-suggestions/generate-issues", {
      method: "POST",
      body: JSON.stringify({ limit: 12 })
    });
    showToast(`Generated ${data.total || 0} AI suggestions`);
    await loadAiSuggestions();
    await loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    els.generateIssueSuggestionsButton.disabled = false;
  }
}

async function generateSuggestionForProduct(productId, force = false) {
  try {
    const data = await api("/admin/api/ai-suggestions/generate", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, force })
    });
    showToast(`AI suggestion ready: ${data.suggestion?.title || productId}`);
    await loadAiSuggestions();
    await loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function applyAiSuggestion(id) {
  const item = state.aiSuggestions.find((suggestion) => suggestion.id === id);
  if (!item) return;
  const card = [...document.querySelectorAll("[data-ai-card]")].find((node) => node.dataset.aiCard === id);
  const fields = [...(card?.querySelectorAll("[data-ai-field]:checked") || [])].map((input) => input.dataset.aiField);
  if (!fields.length) {
    showToast("Select at least one AI field to apply.", "error");
    return;
  }
  if (!(await confirmDialog("Apply AI fields", `Apply ${fields.length} selected field(s) to ${item.title || item.target_id}?`, "Apply"))) return;
  try {
    const result = await api(`/admin/api/ai-suggestions/${encodeURIComponent(id)}/apply`, {
      method: "POST",
      body: JSON.stringify({ fields })
    });
    showToast(`Applied ${result.fields?.length || 0} fields`);
    await hydrate();
    await loadAiSuggestions();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function rejectAiSuggestion(id) {
  try {
    await api(`/admin/api/ai-suggestions/${encodeURIComponent(id)}/reject`, {
      method: "POST",
      body: "{}"
    });
    showToast("AI suggestion rejected");
    await loadAiSuggestions();
    await loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadProducts(search = "", append = false) {
  try {
    if (!append) {
      state.productsOffset = 0;
      state.selectedProductIds = [];
      updateBulkPanel();
    }
    
    const data = await api(`/admin/api/products?search=${encodeURIComponent(search)}&limit=${state.productsLimit}&offset=${state.productsOffset}`);
    
    state.productsTotal = data.total;
    if (append) {
      state.products = [...state.products, ...data.products];
    } else {
      state.products = data.products;
    }
    
    els.productsCountText.textContent = `Showing ${state.products.length} of ${state.productsTotal} products`;
    
    // Toggle Load More button
    if (state.products.length < state.productsTotal) {
      els.loadMoreProductsButton.classList.remove("hidden");
    } else {
      els.loadMoreProductsButton.classList.add("hidden");
    }
    
    els.productList.innerHTML = state.products.length ? state.products.map((product) => {
      const isChecked = state.selectedProductIds.includes(product.id) ? "checked" : "";
      return `
        <article class="data-row" data-product-id="${escapeHtml(product.id)}">
          <div class="checkbox-container">
            <input type="checkbox" class="product-select" data-id="${escapeHtml(product.id)}" ${isChecked}>
          </div>
          ${product.photo_url ? `<img class="row-thumb" src="${escapeHtml(product.photo_url)}" alt="">` : `<div class="row-thumb empty"></div>`}
          <div>
            <h3>${escapeHtml(product.name)}</h3>
            <p class="meta-details">
              <span><strong>Barcode:</strong> ${escapeHtml(product.barcode)}</span>
              <span><strong>Aliases:</strong> ${escapeHtml(product.barcode_count || 0)}</span>
              <span><strong>Cat:</strong> ${escapeHtml(product.category || "None")}</span>
              <span><strong>Size:</strong> ${escapeHtml(product.size || "None")} · ${escapeHtml(product.unit)}</span>
            </p>
            <p class="meta-details">${issueBadges(product.issues || [])}</p>
          </div>
          <input value="${escapeHtml(product.bin || "")}" aria-label="BIN for ${escapeHtml(product.name)}" data-field="bin" data-id="${escapeHtml(product.id)}" style="max-width: 120px;">
          ${statusBadge(product.draft_status)}
          <div style="display:flex; gap:6px;">
            <button class="secondary" data-action="detail-product" data-id="${escapeHtml(product.id)}" type="button" style="min-height:34px; padding:0 10px;">Detail</button>
            <button class="secondary" data-action="edit-product" data-id="${escapeHtml(product.id)}" type="button" style="min-height:34px; padding:0 10px;">Edit</button>
            <button class="secondary warning" data-action="delete-product" data-id="${escapeHtml(product.id)}" type="button" style="min-height:34px; padding:0 10px;">Delete</button>
          </div>
          <button class="primary-btn" data-action="save-product-bin" data-id="${escapeHtml(product.id)}" type="button" style="min-height:34px; padding:0 12px;">Save BIN</button>
        </article>
      `;
    }).join("") : `<p class="meta" style="text-align: center; padding: 24px;">No products found.</p>`;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadProductIssues() {
  try {
    const data = await api("/admin/api/products/issues");
    state.productIssues = data.issues || [];
    els.productIssueList.classList.toggle("hidden", state.productIssues.length === 0);
    els.productIssueList.innerHTML = state.productIssues.length ? state.productIssues.map((row) => {
      const product = row.product || {};
      return `
        <article class="task-row">
          <div>
            <h3>${escapeHtml(product.name || product.id)}</h3>
            <p class="meta-details">
              <span><strong>ID:</strong> ${escapeHtml(product.id)}</span>
              <span><strong>Barcode:</strong> ${escapeHtml(product.barcode || "None")}</span>
              <span><strong>BIN:</strong> ${escapeHtml(product.bin || "Missing")}</span>
            </p>
            <p class="meta-details">${issueBadges(row.issues || [])}</p>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="secondary" data-action="generate-ai-product" data-id="${escapeHtml(product.id)}" type="button">Generate AI</button>
            <button class="primary-btn" data-action="detail-product" data-id="${escapeHtml(product.id)}" type="button">Open Detail</button>
          </div>
        </article>
      `;
    }).join("") : `<p class="meta" style="text-align:center; padding:24px;">No product issues found.</p>`;
    showToast(state.productIssues.length ? `Found ${state.productIssues.length} product issues` : "No product issues found");
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function selectedMappingProduct() {
  return state.mappingProducts.find((product) => product.id === state.selectedMappingProductId) || null;
}

function renderMappingProducts() {
  const active = selectedMappingProduct();
  els.mappingCountText.textContent = `${state.mappingTotal} ${els.mappingOnlyMissing.checked ? "need barcode" : "products"}`;
  els.mappingPageText.textContent = `Showing ${state.mappingProducts.length} of ${state.mappingTotal}`;
  els.mappingLoadMoreButton.classList.toggle("hidden", state.mappingProducts.length >= state.mappingTotal);
  if (!active) {
    els.mappingActiveCard.innerHTML = `
      <div class="mapping-empty">
        <h3>No product selected</h3>
        <p class="meta">Search or reload the queue, then choose a product before scanning its barcode.</p>
      </div>
    `;
  } else {
    const aliases = active.barcodes || [];
    els.mappingActiveCard.innerHTML = `
      <div class="mapping-active-head">
        ${active.photo_url ? `<img class="row-thumb" src="${escapeHtml(active.photo_url)}" alt="">` : `<div class="row-thumb empty"></div>`}
        <div>
          <h3>${escapeHtml(active.name)}</h3>
          <p class="meta-details">
            <span><strong>BIN:</strong> ${escapeHtml(active.bin || active.procurewizard?.bin_number || "Missing")}</span>
            <span><strong>PID:</strong> ${escapeHtml(active.procurewizard?.pid || "None")}</span>
            <span><strong>Size:</strong> ${escapeHtml(active.size || active.procurewizard?.pack_size || "None")}</span>
          </p>
          <p class="meta-details">
            <span>${escapeHtml(active.category || "No category")}</span>
            <span>${escapeHtml(active.real_barcode_count || 0)} real barcodes</span>
          </p>
        </div>
        ${active.needs_real_barcode ? statusBadge("needs barcode") : statusBadge("mapped")}
      </div>
      <div class="mapping-aliases">
        ${aliases.map((alias) => `
          <span class="alias-pill ${alias.label === "ProcureWizard PID" ? "muted" : ""}">
            ${escapeHtml(alias.barcode)} · ${escapeHtml(alias.label || "Alias")}
          </span>
        `).join("") || `<span class="alias-pill muted">No aliases</span>`}
      </div>
    `;
  }
  els.mappingProductList.innerHTML = state.mappingProducts.length ? state.mappingProducts.map((product) => `
    <article class="mapping-row ${product.id === state.selectedMappingProductId ? "selected" : ""}" data-product-id="${escapeHtml(product.id)}">
      ${product.photo_url ? `<img class="row-thumb" src="${escapeHtml(product.photo_url)}" alt="">` : `<div class="row-thumb empty"></div>`}
      <div>
        <h3>${escapeHtml(product.name)}</h3>
        <p class="meta-details">
          <span><strong>BIN:</strong> ${escapeHtml(product.bin || product.procurewizard?.bin_number || "Missing")}</span>
          <span><strong>PID:</strong> ${escapeHtml(product.procurewizard?.pid || "None")}</span>
          <span><strong>Aliases:</strong> ${escapeHtml(product.barcode_count || 0)}</span>
        </p>
      </div>
      ${product.needs_real_barcode ? statusBadge("needs barcode") : statusBadge("mapped")}
      <button class="secondary" data-action="select-map-product" data-id="${escapeHtml(product.id)}" type="button">Select</button>
    </article>
  `).join("") : `<p class="meta" style="text-align:center; padding:24px;">No products match this mapping queue.</p>`;
}

async function loadMappingProducts(append = false) {
  try {
    if (!append) state.mappingOffset = 0;
    const params = new URLSearchParams({
      search: els.mappingSearch.value.trim(),
      only_missing: els.mappingOnlyMissing.checked ? "true" : "false",
      limit: String(state.mappingLimit),
      offset: String(state.mappingOffset)
    });
    const data = await api(`/admin/api/barcode-mapping/products?${params}`);
    state.mappingTotal = data.total || 0;
    state.mappingProducts = append ? [...state.mappingProducts, ...(data.products || [])] : (data.products || []);
    if (!state.mappingProducts.some((product) => product.id === state.selectedMappingProductId)) {
      state.selectedMappingProductId = state.mappingProducts[0]?.id || null;
    }
    renderMappingProducts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderMappingRecent() {
  els.mappingRecentList.innerHTML = state.mappingRecent.length ? state.mappingRecent.map((item) => {
    const name = item.current_product_name || item.product_name || item.product_id;
    const undone = Boolean(item.undone_at);
    const canUndo = !undone && ["add_alias", "create_product"].includes(item.action);
    return `
      <article class="mapping-recent-row ${undone ? "undone" : ""}">
        <div>
          <h3>${escapeHtml(name)}</h3>
          <p class="meta-details">
            <span><strong>Barcode:</strong> ${escapeHtml(item.barcode)}</span>
            <span><strong>Action:</strong> ${escapeHtml(item.action.replaceAll("_", " "))}</span>
            <span><strong>Source:</strong> ${escapeHtml(item.source || "admin")}</span>
            <span><strong>Time:</strong> ${escapeHtml((item.created_at || "").slice(0, 16).replace("T", " "))}</span>
          </p>
          ${item.draft_status === "draft" ? `<p class="meta-details">${statusBadge("draft review")}</p>` : ""}
        </div>
        ${undone ? statusBadge("undone") : statusBadge(item.action === "create_product" ? "draft created" : "mapped")}
        <button class="secondary ${canUndo ? "warning" : ""}" data-action="undo-mapping" data-id="${escapeHtml(item.id)}" type="button" ${canUndo ? "" : "disabled"}>Undo</button>
      </article>
    `;
  }).join("") : `<p class="meta" style="text-align:center; padding:16px;">No recent mapping activity.</p>`;
}

async function loadMappingRecent() {
  try {
    const data = await api("/admin/api/barcode-mapping/recent?limit=20");
    state.mappingRecent = data.mappings || [];
    renderMappingRecent();
  } catch (err) {
    els.mappingRecentList.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

async function undoMappingAudit(auditId) {
  const item = state.mappingRecent.find((entry) => String(entry.id) === String(auditId));
  if (!item) return;
  const name = item.current_product_name || item.product_name || item.product_id;
  if (!(await confirmDialog("Undo mapping", `Undo ${item.barcode} from ${name}?`, "Undo"))) return;
  try {
    await api(`/admin/api/barcode-mapping/recent/${encodeURIComponent(auditId)}/undo`, {
      method: "POST",
      body: "{}"
    });
    showToast("Mapping undone");
    await loadMappingRecent();
    await loadMappingProducts();
    await loadDashboard();
    await loadProducts(els.productSearch.value);
  } catch (err) {
    showToast(err.message, "error");
  }
}

function selectNextMappingProduct() {
  if (!state.mappingProducts.length) {
    state.selectedMappingProductId = null;
    renderMappingProducts();
    return;
  }
  const currentIndex = state.mappingProducts.findIndex((product) => product.id === state.selectedMappingProductId);
  const nextIndex = currentIndex >= 0 ? Math.min(currentIndex + 1, state.mappingProducts.length - 1) : 0;
  state.selectedMappingProductId = state.mappingProducts[nextIndex]?.id || null;
  renderMappingProducts();
  els.mappingBarcodeInput.focus();
}

async function lookupMappingBarcode() {
  const barcode = els.mappingBarcodeInput.value.trim();
  if (!barcode) {
    els.mappingLookupStatus.textContent = "";
    els.mappingLookupStatus.classList.remove("error");
    return;
  }
  try {
    const data = await api(`/admin/api/barcode-mapping/barcodes/${encodeURIComponent(barcode)}`);
    if (data.owner) {
      els.mappingLookupStatus.textContent = `Already mapped to ${data.owner.name} (${data.owner.id})`;
      els.mappingLookupStatus.classList.add("error");
    } else {
      els.mappingLookupStatus.textContent = "Ready to save as a barcode alias.";
      els.mappingLookupStatus.classList.remove("error");
    }
  } catch (err) {
    els.mappingLookupStatus.textContent = err.message;
    els.mappingLookupStatus.classList.add("error");
  }
}

async function saveMappedBarcode() {
  const product = selectedMappingProduct();
  const barcode = els.mappingBarcodeInput.value.trim();
  if (!product) {
    showToast("Select a product first.", "error");
    return;
  }
  if (!barcode) {
    els.mappingBarcodeInput.focus();
    return;
  }
  const physicalBarcodes = (product.barcodes || [])
    .filter((alias) => alias.label !== "ProcureWizard PID")
    .map((alias) => alias.barcode);
  const addingAnother = physicalBarcodes.length > 0 && !physicalBarcodes.includes(barcode);
  if (addingAnother && !(await confirmDialog(
    "Add another physical barcode?",
    `${product.name} already has: ${physicalBarcodes.join(", ")}. Confirm ${barcode} is another valid bottle, case, or packaging barcode for this same product.`,
    "Confirm & Add"
  ))) return;
  try {
    await api(`/admin/api/products/${encodeURIComponent(product.id)}/barcodes`, {
      method: "POST",
      body: JSON.stringify({
        barcode,
        label: els.mappingLabelInput.value.trim() || "Mapped barcode",
        is_primary: false,
        confirm_additional_barcode: addingAnother,
        source_screen: "admin_mapping"
      })
    });
    showToast(`Mapped ${barcode} to ${product.name}`);
    els.mappingBarcodeInput.value = "";
    els.mappingLookupStatus.textContent = "";
    await loadMappingRecent();
    await loadMappingProducts(false);
    await loadDashboard();
    await loadProducts(els.productSearch.value);
    els.mappingBarcodeInput.focus();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function openProductDetail(productId) {
  try {
    const data = await api(`/admin/api/products/${encodeURIComponent(productId)}`);
    const product = data.product;
    state.selectedProductDetail = product;
    els.productDetailTitle.textContent = product.name || product.id;
    els.mergeTargetProductId.value = product.id;
    els.mergeSourceProductId.value = "";
    els.aliasBarcode.value = "";
    els.aliasLabel.value = "";
    const primaryLabel = product.procurewizard ? "ProcureWizard PID" : "Primary barcode";
    els.productDetailSummary.innerHTML = `
      <p><strong>ID:</strong> ${escapeHtml(product.id)}</p>
      <p><strong>${primaryLabel}:</strong> ${escapeHtml(product.procurewizard?.pid || product.barcode || "None")}</p>
      <p><strong>BIN:</strong> ${escapeHtml(product.bin || "Missing")} · <strong>Status:</strong> ${escapeHtml(product.draft_status)}</p>
    `;
    els.productAliasList.innerHTML = `
      <h3>Barcode Aliases</h3>
      ${(product.barcodes || []).map((alias) => `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
          <span>${escapeHtml(alias.barcode)} · ${escapeHtml(alias.label || "Alias")} ${alias.is_primary && alias.label !== "ProcureWizard PID" ? "· Primary" : ""}</span>
          ${alias.is_primary ? "" : `<button class="secondary warning" data-action="delete-alias" data-barcode="${escapeHtml(alias.barcode)}" type="button">Remove</button>`}
        </div>
      `).join("") || `<p class="meta">No aliases yet.</p>`}
    `;
    els.productAuditList.innerHTML = `
      <h3>Recent Audit</h3>
      ${(product.audit || []).map((row) => `
        <p class="meta-details"><span>${escapeHtml(row.created_at.slice(0, 16).replace("T", " "))}</span><span>${escapeHtml(row.action)}</span></p>
      `).join("") || `<p class="meta">No audit entries yet.</p>`}
    `;
    els.productDetailDialog.showModal();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadSessions() {
  try {
    const data = await api("/admin/api/sessions");
    state.sessions = data.sessions;
    els.sessionList.innerHTML = state.sessions.map((session) => `
      <article class="data-row" data-session-id="${escapeHtml(session.id)}" style="grid-template-columns: minmax(0, 1fr) auto auto auto;">
        <div>
          <h3>${escapeHtml(session.name)}</h3>
          <p class="meta-details">
            <span><strong>ID:</strong> ${escapeHtml(session.id)}</span>
            <span><strong>Date:</strong> ${escapeHtml(session.period_date)}</span>
            <span><strong>Devices:</strong> ${escapeHtml(session.device_count)}</span>
            <span><strong>Last count:</strong> ${escapeHtml(session.last_counted_at || "None")}</span>
          </p>
        </div>
        <span class="badge">${escapeHtml(session.line_count)} lines</span>
        <select data-session-status data-id="${escapeHtml(session.id)}">
          ${["draft", "open", "counting", "review", "approved", "exported", "archived"].map((status) => (
            `<option value="${status}" ${status === session.status ? "selected" : ""}>${status}</option>`
          )).join("")}
        </select>
        <div style="display:flex; gap:8px;">
          <button class="secondary" data-action="update-session-status" data-id="${escapeHtml(session.id)}" type="button">Update</button>
          <button class="primary-btn" data-action="export-session" data-id="${escapeHtml(session.id)}" type="button">Review Export</button>
          <button class="warning" data-action="delete-session" data-id="${escapeHtml(session.id)}" type="button">Archive</button>
        </div>
      </article>
    `).join("");
    
    els.exportSession.innerHTML = state.sessions.map((session) => (
      `<option value="${escapeHtml(session.id)}">${escapeHtml(session.name)} (${escapeHtml(session.id)})</option>`
    )).join("");
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadExportReview(sessionId = els.exportSession.value) {
  if (!sessionId) {
    els.exportReview.innerHTML = `<p class="meta" style="text-align:center; padding:24px;">Create or select a session.</p>`;
    return;
  }
  try {
    const data = await api(`/admin/api/export/${encodeURIComponent(sessionId)}/review`);
    const ready = data.line_count > 0 && data.missing_bin_count === 0 && data.draft_count === 0;
    const rows = data.missing_bin_rows || [];
    els.exportReview.innerHTML = `
      <div class="export-readiness ${ready ? "ready" : data.line_count ? "warning" : "blocked"}">
        <div>
          <strong>${ready ? "Validated export ready" : data.line_count ? "Export needs review" : "No scans in this session"}</strong>
          <span>${ready ? "All scanned lines have confirmed products and BINs." : data.line_count ? "Raw scans can be downloaded now. Resolve exceptions before using the validated Excel export." : "Choose a session containing scanned stocktake lines."}</span>
        </div>
      </div>
      <div class="summary-grid">
        <div class="metric"><span>Lines Counted</span><strong>${escapeHtml(data.line_count)}</strong></div>
        <div class="metric"><span>Missing BIN</span><strong>${escapeHtml(data.missing_bin_count)}</strong></div>
        <div class="metric"><span>Unresolved Drafts</span><strong>${escapeHtml(data.draft_count)}</strong></div>
      </div>
      <div class="export-downloads">
        <a class="download-link ${data.line_count ? "" : "disabled"}" href="/export/scanned/${encodeURIComponent(sessionId)}">
          <strong>All Scanned Lines</strong><span>Complete Excel backup, including unmapped products</span>
        </a>
        <a class="download-link ${ready ? "" : "disabled"}" href="/export/${encodeURIComponent(sessionId)}">
          <strong>Validated Stocktake Excel</strong><span>Available after BIN and draft issues are resolved</span>
        </a>
      </div>
      <div class="task-list">
        ${rows.map((row) => `
          <article class="missing-row">
            <div>
              <h3>${escapeHtml(row.product_name || row.barcode)}</h3>
              <p class="meta-details">
                <span><strong>Barcode:</strong> ${escapeHtml(row.barcode)}</span>
                <span><strong>Location:</strong> ${escapeHtml(row.location)}</span>
                <span><strong>Qty:</strong> ${escapeHtml(row.quantity_decimal)}</span>
              </p>
            </div>
            <input placeholder="BIN (e.g. A-12)" data-field="missing-bin" data-product-id="${escapeHtml(row.product_id)}">
            <button class="primary-btn" data-action="save-bin" data-product-id="${escapeHtml(row.product_id)}" type="button">Save BIN</button>
          </article>
        `).join("")}
      </div>
    `;
  } catch (err) {
    showToast(err.message, 'error');
  }
  await loadProcureWizardStatus(sessionId);
}

async function loadCatalogExportSummary() {
  try {
    const data = await api("/admin/api/catalog-export/summary");
    els.catalogExportSummary.innerHTML = `
      <div><span>Total products</span><strong>${escapeHtml(data.total_products)}</strong></div>
      <div class="good"><span>Mapped</span><strong>${escapeHtml(data.mapped_products)}</strong></div>
      <div class="${Number(data.unmapped_products) ? "warn" : "good"}"><span>Unmapped</span><strong>${escapeHtml(data.unmapped_products)}</strong></div>
      <div><span>ProcureWizard linked</span><strong>${escapeHtml(data.procurewizard_products)}</strong></div>
      <div class="${Number(data.draft_products) ? "warn" : "good"}"><span>Draft products</span><strong>${escapeHtml(data.draft_products)}</strong></div>
    `;
  } catch (err) {
    els.catalogExportSummary.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

async function restoreCatalogCsv() {
  const file = els.catalogRestoreFile.files?.[0];
  if (!file) {
    showToast("Choose a StockTake catalog CSV first.", "error");
    return;
  }
  els.catalogRestoreButton.disabled = true;
  els.catalogRestoreStatus.textContent = "Validating products and barcode ownership...";
  try {
    const csv_text = await file.text();
    const result = await api("/admin/api/catalog-export/restore", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, csv_text })
    });
    els.catalogRestoreStatus.textContent = `Restored ${result.restored_products} products and ${result.restored_barcodes} barcodes.`;
    showToast("Catalog restore completed");
    await hydrate();
    await loadCatalogExportSummary();
  } catch (err) {
    els.catalogRestoreStatus.textContent = err.message;
    showToast(err.message, "error");
  } finally {
    els.catalogRestoreButton.disabled = false;
  }
}

async function loadProcureWizardStatus(sessionId = els.exportSession.value) {
  if (!els.pwStatus) return;
  const outletId = els.pwOutlet?.value || "cellar";
  try {
    const data = await api(`/admin/api/procurewizard/status?session_id=${encodeURIComponent(sessionId || "")}&outlet_id=${encodeURIComponent(outletId)}`);
    state.procurewizard = data;
    const active = data.active;
    if (!active) {
      els.pwStatus.innerHTML = `<p class="meta">No ProcureWizard CSV imported for ${escapeHtml(els.pwOutlet?.selectedOptions?.[0]?.textContent || outletId)} yet.</p>`;
      els.pwRows.innerHTML = "";
      els.pwDownloadLink.classList.add("disabled");
      els.pwDownloadLink.href = "#";
      return;
    }
    const counts = data.counts || {};
    const session = data.session || {};
    const hasScans = Number(session.line_count || 0) > 0;
    const hasPwCounts = Number(session.pw_product_count || 0) > 0;
    els.pwStatus.innerHTML = `
      <div class="pw-active-file">
        <div><span>Active ${escapeHtml(els.pwOutlet?.selectedOptions?.[0]?.textContent || outletId)} template</span><strong>${escapeHtml(active.filename)}</strong></div>
        <span>${escapeHtml(active.row_count)} rows · ${escapeHtml(counts.manual || 0)} manual links</span>
      </div>
      <div class="pw-session-summary">
        <div><span>Scanned products</span><strong>${escapeHtml(session.product_count || 0)}</strong><small>Qty ${escapeHtml(session.quantity_total || 0)}</small></div>
        <div class="${hasPwCounts ? "good" : "warn"}"><span>Going to ProcureWizard</span><strong>${escapeHtml(session.pw_product_count || 0)}</strong><small>Qty ${escapeHtml(session.pw_quantity_total || 0)}</small></div>
        <div class="${Number(session.unmapped_product_count || 0) ? "warn" : "good"}"><span>Not in PW export</span><strong>${escapeHtml(session.unmapped_product_count || 0)}</strong><small>Qty ${escapeHtml(session.unmapped_quantity_total || 0)}</small></div>
      </div>
      <div class="pw-export-message ${hasPwCounts ? "ready" : "blocked"}">
        <strong>${hasPwCounts ? "ProcureWizard CSV ready" : hasScans ? "No scanned products are linked to ProcureWizard" : "Selected session has no scans"}</strong>
        <span>${hasPwCounts ? `${session.pw_product_count} product counts will be written into the template.` : hasScans ? "Use All Scanned Lines or map scanned products before downloading a ProcureWizard CSV." : "Select a session with counts before exporting."}</span>
      </div>
    `;
    if (sessionId && hasPwCounts) {
      els.pwDownloadLink.href = `/admin/api/procurewizard/export/${encodeURIComponent(sessionId)}?outlet_id=${encodeURIComponent(outletId)}`;
      els.pwDownloadLink.classList.remove("disabled");
    } else {
      els.pwDownloadLink.href = "#";
      els.pwDownloadLink.classList.add("disabled");
    }
    const countedRows = (data.rows || []).filter((row) => Number(row.counted_quantity || 0) > 0);
    const unmappedProducts = session.unmapped_products || [];
    els.pwRows.innerHTML = `
      ${unmappedProducts.length ? `
        <section class="pw-exceptions">
          <header><strong>Excluded from ProcureWizard CSV</strong><span>These scans remain available in All Scanned Lines.</span></header>
          ${unmappedProducts.map((product) => `
            <div>
              <span><strong>${escapeHtml(product.product_name)}</strong><small>${escapeHtml(product.barcode || product.product_id || "")}</small></span>
              <span>Qty ${escapeHtml(product.quantity_total)}</span>
            </div>
          `).join("")}
        </section>
      ` : ""}
      ${countedRows.length ? `<h3 class="pw-counted-title">Counts written to ProcureWizard</h3>` : ""}
      ${countedRows.map((row) => `
      <article class="task-row pw-row">
        <div class="pw-row-main">
          <div class="pw-row-heading">
            <h3>${escapeHtml(row.description)}</h3>
            <span class="pw-count-badge">Qty ${escapeHtml(row.counted_quantity)}</span>
          </div>
          <dl class="pw-row-details">
            <div><dt>PID</dt><dd>${escapeHtml(row.pid)}</dd></div>
            <div><dt>BIN</dt><dd>${escapeHtml(row.bin_number || "None")}</dd></div>
            <div><dt>Pack</dt><dd>${escapeHtml(row.pack_size || "None")}</dd></div>
            <div><dt>Category</dt><dd>${escapeHtml(row.category || "None")}</dd></div>
          </dl>
          <p class="pw-linked-product"><strong>Linked product:</strong> ${escapeHtml(row.product_name || row.product_id || "None")}</p>
          ${row.match_reason ? `<p class="pw-match-reason">${escapeHtml(row.match_reason)}</p>` : ""}
        </div>
        <div class="pw-link-controls">
          <label>
            Product ID
            <input value="${escapeHtml(row.product_id || "")}" data-pw-row-id="${escapeHtml(row.id)}" placeholder="Search or enter product ID">
          </label>
          <button class="secondary" data-action="link-pw-row" data-id="${escapeHtml(row.id)}" type="button">Link</button>
        </div>
      </article>
      `).join("")}
      ${!countedRows.length && !unmappedProducts.length ? `<p class="empty-state">No counted products to preview for this session.</p>` : ""}
    `;
  } catch (err) {
    els.pwStatus.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

async function importProcureWizardCsv() {
  const file = els.pwCsvFile.files?.[0];
  if (!file) {
    showToast("Choose a ProcureWizard CSV first.", "error");
    return;
  }
  els.pwImportButton.disabled = true;
  try {
    const buffer = await file.arrayBuffer();
    const csv_text = new TextDecoder("windows-1252").decode(buffer);
    const result = await api("/admin/api/procurewizard/import", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, csv_text, outlet_id: els.pwOutlet?.value || "cellar" })
    });
    showToast(`Imported ${result.row_count} ProcureWizard rows for ${els.pwOutlet?.selectedOptions?.[0]?.textContent || result.outlet_id}`);
    await hydrate();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    els.pwImportButton.disabled = false;
  }
}

function showTask(task) {
  const suggestion = task.suggested || {};
  state.selectedTask = task;
  const candidates = imageCandidates(suggestion);
  const selectedPhoto = suggestion.image_url || candidates[0] || "";
  els.taskDialogTitle.textContent = "Confirm Suggested Product";
  els.taskBarcodeLock.innerHTML = `
    <span>Locked barcode</span>
    <strong>${escapeHtml(task.barcode)}</strong>
    <small>Barcode identity cannot be edited here. Add extra codes as aliases after approval.</small>
  `;
  els.taskName.value = suggestion.name || task.current_name || "";
  els.taskBin.value = suggestion.bin || task.current_bin || "";
  els.taskCategory.value = suggestion.category || "";
  els.taskSize.value = suggestion.size || "";
  els.taskUnit.value = suggestion.unit || "each";
  els.taskPhoto.value = selectedPhoto;
  els.taskNotes.value = [
    suggestion.brand ? `Brand: ${suggestion.brand}` : "",
    suggestion.source_name ? `Source: ${suggestion.source_name}` : "",
    suggestion.confidence ? `Confidence: ${suggestion.confidence}` : ""
  ].filter(Boolean).join("\n");
  const sources = suggestion.source_urls || [];
  setPhotoPreview(els.taskPhotoPreview, selectedPhoto, "Selected photo");
  els.taskSources.innerHTML = `
    ${candidates.length ? `
      <h3>Photo candidates</h3>
      <div class="image-candidates">
        ${candidates.map((url) => `
          <button class="image-choice ${url === selectedPhoto ? "selected" : ""}" data-photo-url="${escapeHtml(url)}" type="button">
            <img src="${escapeHtml(url)}" alt="">
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${sources.length ? `<h3>Sources</h3>` : ""}
    ${sources.map((url) => (
      `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`
    )).join("")}
  `;
  els.taskDialog.showModal();
}

function updateBulkPanel() {
  const count = state.selectedProductIds.length;
  if (count > 0) {
    els.selectedCountText.textContent = `${count} product${count > 1 ? 's' : ''} selected`;
    els.bulkActionPanel.classList.remove("hidden");
  } else {
    els.bulkActionPanel.classList.add("hidden");
  }
}

function openProductDialog(product = null) {
  if (product) {
    els.productDialogTitle.textContent = "Edit Product Details";
    els.pDialogId.value = product.id;
    els.pDialogBarcode.value = product.barcode || "";
    els.pDialogBarcode.disabled = Boolean(product.barcode);
    els.pDialogBarcode.readOnly = Boolean(product.barcode);
    els.productLookupStatus.textContent = product.barcode ? "Primary barcode is locked. Use Detail to add aliases." : "";
    els.pDialogName.value = product.name || "";
    els.pDialogBin.value = product.bin || "";
    els.pDialogCategory.value = product.category || "";
    els.pDialogSize.value = product.size || "";
    els.pDialogUnit.value = product.unit || "each";
    els.pDialogPhoto.value = product.photo_url || "";
    els.pDialogNotes.value = product.notes || "";
    setPhotoPreview(els.productPhotoPreview, product.photo_url || "", "Current photo");
  } else {
    els.productDialogTitle.textContent = "Create New Product";
    els.pDialogId.value = "";
    els.pDialogBarcode.value = "";
    els.pDialogBarcode.disabled = false;
    els.pDialogBarcode.readOnly = false;
    els.productLookupStatus.textContent = "Enter a barcode to auto-fill details.";
    els.pDialogName.value = "";
    els.pDialogBin.value = "";
    els.pDialogCategory.value = "";
    els.pDialogSize.value = "";
    els.pDialogUnit.value = "each";
    els.pDialogPhoto.value = "";
    els.pDialogNotes.value = "";
    setPhotoPreview(els.productPhotoPreview, "", "Suggested photo");
  }
  els.productDialog.showModal();
}

async function saveProductDialog() {
  const id = els.pDialogId.value;
  const barcode = els.pDialogBarcode.value.trim();
  const name = els.pDialogName.value.trim();
  const bin = els.pDialogBin.value.trim();
  const category = els.pDialogCategory.value.trim();
  const size = els.pDialogSize.value.trim();
  const unit = els.pDialogUnit.value.trim() || "each";
  const photo_url = els.pDialogPhoto.value.trim();
  const notes = els.pDialogNotes.value.trim();

  if (!name) {
    showToast("Product name is required.", "error");
    return;
  }
  if (!id && !barcode) {
    showToast("Barcode is required for a new product.", "error");
    return;
  }

  try {
    if (id) {
      const payload = { name, bin, category, size, unit, photo_url, notes };
      await api(`/admin/api/products/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      showToast("Product updated");
    } else {
      await api(`/admin/api/products`, {
        method: "POST",
        body: JSON.stringify({ barcode, name, bin, category, size, unit, photo_url, notes, draft_status: "confirmed" })
      });
      showToast("Product created");
    }
    els.productDialog.close();
    await hydrate();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function addSelectedProductAlias() {
  const product = state.selectedProductDetail;
  if (!product) return;
  const barcode = els.aliasBarcode.value.trim();
  if (!barcode) {
    showToast("Enter an alias barcode", "error");
    return;
  }
  const physicalBarcodes = (product.barcodes || [])
    .filter((alias) => alias.label !== "ProcureWizard PID")
    .map((alias) => alias.barcode);
  const addingAnother = physicalBarcodes.length > 0 && !physicalBarcodes.includes(barcode);
  if (addingAnother && !(await confirmDialog(
    "Add another physical barcode?",
    `${product.name} already has: ${physicalBarcodes.join(", ")}. Confirm ${barcode} belongs to the same product.`,
    "Confirm & Add"
  ))) return;
  try {
    await api(`/admin/api/products/${encodeURIComponent(product.id)}/barcodes`, {
      method: "POST",
      body: JSON.stringify({
        barcode,
        label: els.aliasLabel.value.trim() || "Alias barcode",
        is_primary: false,
        confirm_additional_barcode: addingAnother,
        source_screen: "admin"
      })
    });
    showToast("Barcode alias added");
    await openProductDetail(product.id);
    await loadProducts(els.productSearch.value);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function mergeSelectedProduct() {
  const product = state.selectedProductDetail;
  const sourceId = els.mergeSourceProductId.value.trim();
  if (!product || !sourceId) {
    showToast("Enter the duplicate product ID to merge from", "error");
    return;
  }
  if (!(await confirmDialog("Merge products", `Merge ${sourceId} into ${product.id}? Counts and barcode aliases will move to the current product.`, "Merge"))) return;
  try {
    await api("/admin/api/products/merge", {
      method: "POST",
      body: JSON.stringify({
        source_product_id: sourceId,
        target_product_id: product.id
      })
    });
    showToast("Products merged");
    await openProductDetail(product.id);
    await hydrate();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function bindEvents() {
  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.loginError.textContent = "";
    try {
      await api("/admin/api/login", {
        method: "POST",
        body: JSON.stringify({ password: els.adminPassword.value })
      });
      setAuthed(true);
      showToast("Logged in successfully");
      await hydrate();
    } catch (error) {
      els.loginError.textContent = error.message;
    }
  });

  els.logoutButton.addEventListener("click", async () => {
    await api("/admin/api/logout", { method: "POST", body: "{}" }).catch(() => {});
    setAuthed(false);
    showToast("Logged out successfully");
  });

  els.tabs.forEach((button) => {
    button.addEventListener("click", () => {
      els.tabs.forEach((tab) => tab.classList.toggle("active", tab === button));
      els.views.forEach((view) => view.classList.toggle("hidden", view.id !== `${button.dataset.view}View`));
      if (button.dataset.view === "mapping") {
        loadMappingProducts();
        loadMappingRecent();
        setTimeout(() => els.mappingBarcodeInput.focus(), 80);
      }
      if (button.dataset.view === "ai") loadAiSuggestions();
      if (button.dataset.view === "export") {
        loadExportReview();
        loadCatalogExportSummary();
      }
    });
  });

  els.refreshTasksButton.addEventListener("click", async () => {
    await loadTasks();
    showToast("Tasks list refreshed");
  });

  els.generateIssueSuggestionsButton.addEventListener("click", generateIssueSuggestions);
  els.reloadAiSuggestionsButton.addEventListener("click", loadAiSuggestions);
  els.aiSuggestionStatus.addEventListener("change", loadAiSuggestions);
  els.llmSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveLlmSettings();
  });
  els.testLlmSettingsButton.addEventListener("click", testLlmSettings);
  els.aiSuggestionList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.action === "apply-ai") await applyAiSuggestion(button.dataset.id);
    if (button.dataset.action === "reject-ai") await rejectAiSuggestion(button.dataset.id);
    if (button.dataset.action === "open-ai-target") {
      if (button.dataset.targetType === "product" && button.dataset.targetId) {
        await openProductDetail(button.dataset.targetId);
      }
      if (button.dataset.targetType === "task") {
        const task = state.tasks.find((item) => item.id === button.dataset.targetId);
        if (task) showTask(task);
      }
    }
  });

  // Task dialog / list events
  els.taskList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const task = state.tasks.find((item) => item.id === button.dataset.id);
    if (!task) return;
    if (button.dataset.action === "review") showTask(task);
    if (button.dataset.action === "enrich") {
      button.disabled = true;
      try {
        await api(`/admin/api/tasks/${encodeURIComponent(task.id)}/enrich`, { method: "POST", body: "{}" });
        showToast("Enriched barcode info successfully");
        await loadTasks();
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
        button.disabled = false;
      }
    }
  });

  els.taskSources.addEventListener("click", (event) => {
    const button = event.target.closest(".image-choice");
    if (!button) return;
    const url = button.dataset.photoUrl || "";
    els.taskPhoto.value = url;
    setPhotoPreview(els.taskPhotoPreview, url, "Selected photo");
    els.taskSources.querySelectorAll(".image-choice").forEach((item) => {
      item.classList.toggle("selected", item === button);
    });
  });

  els.taskPhoto.addEventListener("input", () => {
    setPhotoPreview(els.taskPhotoPreview, els.taskPhoto.value, "Selected photo");
  });

  els.approveTaskButton.addEventListener("click", async () => {
    if (!state.selectedTask) return;
    try {
      await api(`/admin/api/tasks/${encodeURIComponent(state.selectedTask.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({
          name: els.taskName.value.trim(),
          bin: els.taskBin.value.trim(),
          category: els.taskCategory.value.trim(),
          size: els.taskSize.value.trim(),
          unit: els.taskUnit.value.trim() || "each",
          photo_url: els.taskPhoto.value.trim(),
          notes: els.taskNotes.value.trim()
        })
      });
      showToast("Product approved into catalog");
      els.taskDialog.close();
      await hydrate();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
  
  els.rejectTaskButton.addEventListener("click", async () => {
    if (!state.selectedTask) return;
    if (!(await confirmDialog("Reject task", "Reject and delete this task and its draft product?", "Reject & Delete"))) return;
    try {
      await api(`/admin/api/tasks/${encodeURIComponent(state.selectedTask.id)}/reject`, {
        method: "POST"
      });
      showToast("Task and draft product deleted");
      els.taskDialog.close();
      await hydrate();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // Product page events
  els.productSearchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadProducts(els.productSearch.value);
  });
  
  els.loadMoreProductsButton.addEventListener("click", async () => {
    state.productsOffset += state.productsLimit;
    await loadProducts(els.productSearch.value, true);
  });
  
  els.createProductButton.addEventListener("click", () => {
    openProductDialog();
  });

  els.pDialogBarcode.addEventListener("input", () => {
    clearTimeout(state.lookupTimer);
    state.lookupTimer = setTimeout(lookupProductForDialog, 650);
  });
  els.pDialogBarcode.addEventListener("blur", lookupProductForDialog);
  els.pDialogPhoto.addEventListener("input", () => {
    setPhotoPreview(els.productPhotoPreview, els.pDialogPhoto.value, "Selected photo");
  });

  els.reviewIssuesButton.addEventListener("click", async () => {
    await loadProductIssues();
  });
  
  els.productList.addEventListener("change", (event) => {
    if (event.target.classList.contains("product-select")) {
      const id = event.target.dataset.id;
      if (event.target.checked) {
        state.selectedProductIds.push(id);
      } else {
        state.selectedProductIds = state.selectedProductIds.filter(pid => pid !== id);
      }
      updateBulkPanel();
    }
  });

  els.productList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    
    const id = button.dataset.id;
    
    if (button.dataset.action === "save-product-bin") {
      const row = button.closest(".data-row");
      const bin = row.querySelector("[data-field='bin']").value.trim();
      try {
        await api(`/admin/api/products/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify({ bin, draft_status: bin ? "confirmed" : undefined })
        });
        showToast("BIN updated successfully");
        await loadProducts(els.productSearch.value);
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }

    if (button.dataset.action === "detail-product") {
      await openProductDetail(id);
    }
    
    if (button.dataset.action === "edit-product") {
      const product = state.products.find(p => p.id === id);
      if (product) openProductDialog(product);
    }
    
    if (button.dataset.action === "delete-product") {
      if (!(await confirmDialog("Delete product", "Delete this product from the catalog?", "Delete"))) return;
      try {
        await api(`/admin/api/products/${encodeURIComponent(id)}`, {
          method: "DELETE"
        });
        showToast("Product deleted successfully");
        await loadProducts(els.productSearch.value);
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }
  });

  els.productIssueList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.action === "detail-product") await openProductDetail(button.dataset.id);
    if (button.dataset.action === "generate-ai-product") await generateSuggestionForProduct(button.dataset.id, true);
  });

  els.mappingSearchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadMappingProducts();
    els.mappingBarcodeInput.focus();
  });
  els.mappingSearch.addEventListener("input", () => {
    clearTimeout(state.mappingSearchTimer);
    state.mappingSearchTimer = setTimeout(() => loadMappingProducts(), 250);
  });
  els.mappingOnlyMissing.addEventListener("change", () => loadMappingProducts());
  els.mappingReloadButton.addEventListener("click", () => loadMappingProducts());
  els.mappingRecentReloadButton.addEventListener("click", () => loadMappingRecent());
  els.mappingRecentList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (button?.dataset.action === "undo-mapping") await undoMappingAudit(button.dataset.id);
  });
  els.mappingLoadMoreButton.addEventListener("click", async () => {
    state.mappingOffset += state.mappingLimit;
    await loadMappingProducts(true);
  });
  els.mappingProductList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    const row = event.target.closest(".mapping-row");
    const productId = button?.dataset.id || row?.dataset.productId;
    if (!productId) return;
    state.selectedMappingProductId = productId;
    renderMappingProducts();
    els.mappingBarcodeInput.focus();
  });
  els.mappingBarcodeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveMappedBarcode();
  });
  els.mappingBarcodeInput.addEventListener("input", () => {
    clearTimeout(state.mappingLookupTimer);
    state.mappingLookupTimer = setTimeout(lookupMappingBarcode, 220);
  });
  els.mappingSkipButton.addEventListener("click", selectNextMappingProduct);
  els.mappingOpenDetailButton.addEventListener("click", async () => {
    const product = selectedMappingProduct();
    if (product) await openProductDetail(product.id);
  });
  
  // Custom dialog events
  els.cancelProductDialogButton.addEventListener("click", () => {
    els.productDialog.close();
  });

  document.querySelectorAll(".close-dialog-btn").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog")?.close());
  });

  els.productDialogForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveProductDialog();
  });
  els.saveProductDialogButton.addEventListener("click", saveProductDialog);

  els.productDetailForm.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  els.addAliasButton.addEventListener("click", addSelectedProductAlias);
  els.generateProductAiButton.addEventListener("click", async () => {
    const product = state.selectedProductDetail;
    if (product) await generateSuggestionForProduct(product.id, true);
  });

  els.productAliasList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    const product = state.selectedProductDetail;
    if (!button || !product || button.dataset.action !== "delete-alias") return;
    try {
      await api(`/admin/api/products/${encodeURIComponent(product.id)}/barcodes/${encodeURIComponent(button.dataset.barcode)}`, {
        method: "DELETE"
      });
      showToast("Barcode alias removed");
      await openProductDetail(product.id);
      await loadProducts(els.productSearch.value);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  els.mergeProductButton.addEventListener("click", mergeSelectedProduct);
  
  // Bulk Actions Handlers
  els.bulkUpdateButton.addEventListener("click", async () => {
    const bin = els.bulkBin.value.trim();
    const category = els.bulkCategory.value.trim();
    if (!bin && !category) {
      showToast("Please enter a BIN or Category to update", "error");
      return;
    }
    try {
      await api("/admin/api/products/bulk-update", {
        method: "POST",
        body: JSON.stringify({
          product_ids: state.selectedProductIds,
          bin: bin || null,
          category: category || null
        })
      });
      showToast(`Bulk updated ${state.selectedProductIds.length} products`);
      els.bulkBin.value = "";
      els.bulkCategory.value = "";
      state.selectedProductIds = [];
      await hydrate();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
  
  els.bulkDeleteButton.addEventListener("click", async () => {
    if (!(await confirmDialog("Bulk delete products", `Delete ${state.selectedProductIds.length} selected products?`, "Delete"))) return;
    try {
      await api("/admin/api/products/bulk-delete", {
        method: "POST",
        body: JSON.stringify({
          product_ids: state.selectedProductIds
        })
      });
      showToast(`Deleted ${state.selectedProductIds.length} products`);
      state.selectedProductIds = [];
      await hydrate();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // Sessions events
  els.sessionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/sessions", {
        method: "POST",
        body: JSON.stringify({
          id: els.sessionId.value.trim(),
          name: els.sessionName.value.trim(),
          period_date: els.sessionDate.value
        })
      });
      showToast("Session created/updated");
      await loadSessions();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
  
  els.sessionList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    
    const id = button.dataset.id;
    if (button.dataset.action === "export-session") {
      els.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === "export"));
      els.views.forEach((view) => view.classList.toggle("hidden", view.id !== "exportView"));
      els.exportSession.value = id;
      await loadExportReview(id);
    }
    
    if (button.dataset.action === "delete-session") {
      if (!(await confirmDialog("Archive session", "Archive this session? Counts and audit history will be preserved.", "Archive"))) return;
      try {
        await api(`/admin/api/sessions/${encodeURIComponent(id)}`, {
          method: "DELETE"
        });
        showToast("Session archived");
        await loadSessions();
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }

    if (button.dataset.action === "update-session-status") {
      const select = button.closest("[data-session-id]").querySelector("[data-session-status]");
      try {
        await api(`/admin/api/sessions/${encodeURIComponent(id)}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: select.value, reason: "Updated from admin session control" })
        });
        showToast("Session status updated");
        await loadSessions();
      } catch (err) {
        showToast(err.message, "error");
      }
    }
  });

  els.exportSession.addEventListener("change", () => loadExportReview());
  els.pwImportButton.addEventListener("click", importProcureWizardCsv);
  els.pwOutlet?.addEventListener("change", () => loadProcureWizardStatus());
  els.catalogExportRefresh.addEventListener("click", loadCatalogExportSummary);
  els.catalogRestoreButton.addEventListener("click", restoreCatalogCsv);
  els.pwRows.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.dataset.action !== "link-pw-row") return;
    const row = button.closest(".pw-row");
    const input = row.querySelector("[data-pw-row-id]");
    try {
      await api(`/admin/api/procurewizard/rows/${encodeURIComponent(button.dataset.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ product_id: input.value.trim() || null })
      });
      showToast("ProcureWizard row link updated");
      await loadProcureWizardStatus();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
  els.exportReview.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.dataset.action !== "save-bin") return;
    const row = button.closest(".missing-row");
    const bin = row.querySelector("[data-field='missing-bin']").value.trim();
    if (!bin) return;
    try {
      await api(`/products/${encodeURIComponent(button.dataset.productId)}/bin`, {
        method: "PATCH",
        body: JSON.stringify({ bin })
      });
      showToast("BIN saved");
      await loadExportReview();
      await loadDashboard();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

async function hydrate() {
  await loadDashboard();
  await Promise.all([loadTasks(), loadProducts(), loadSessions(), loadMappingProducts(), loadAiSuggestions(), loadLlmSettings()]);
  if (els.exportSession.value) await loadExportReview();
  await loadProcureWizardStatus();
  await loadCatalogExportSummary();
}

async function init() {
  bindEvents();
  const today = new Date().toISOString().slice(0, 10);
  els.sessionDate.value = today;
  els.sessionId.value = `session-${today}`;
  els.sessionName.value = today;
  try {
    await api("/admin/api/me");
    setAuthed(true);
    await hydrate();
  } catch {
    setAuthed(false);
  }
}

init();
