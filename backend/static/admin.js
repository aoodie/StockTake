const state = {
  authed: false,
  tasks: [],
  products: [],
  sessions: [],
  productIssues: [],
  selectedTask: null,
  selectedProductDetail: null,
  lookupTimer: null,
  // Pagination & Selection State
  productsLimit: 50,
  productsOffset: 0,
  productsTotal: 0,
  selectedProductIds: []
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
  productSearchForm: document.querySelector("#productSearchForm"),
  productSearch: document.querySelector("#productSearch"),
  productList: document.querySelector("#productList"),
  sessionForm: document.querySelector("#sessionForm"),
  sessionId: document.querySelector("#sessionId"),
  sessionName: document.querySelector("#sessionName"),
  sessionDate: document.querySelector("#sessionDate"),
  sessionList: document.querySelector("#sessionList"),
  exportSession: document.querySelector("#exportSession"),
  exportReview: document.querySelector("#exportReview"),
  
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
  mergeSourceProductId: document.querySelector("#mergeSourceProductId"),
  mergeTargetProductId: document.querySelector("#mergeTargetProductId"),
  mergeProductButton: document.querySelector("#mergeProductButton")
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
          <button class="primary-btn" data-action="detail-product" data-id="${escapeHtml(product.id)}" type="button">Open Detail</button>
        </article>
      `;
    }).join("") : `<p class="meta" style="text-align:center; padding:24px;">No product issues found.</p>`;
    showToast(state.productIssues.length ? `Found ${state.productIssues.length} product issues` : "No product issues found");
  } catch (err) {
    showToast(err.message, 'error');
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
    els.productDetailSummary.innerHTML = `
      <p><strong>ID:</strong> ${escapeHtml(product.id)}</p>
      <p><strong>Primary barcode:</strong> ${escapeHtml(product.barcode || "None")}</p>
      <p><strong>BIN:</strong> ${escapeHtml(product.bin || "Missing")} · <strong>Status:</strong> ${escapeHtml(product.draft_status)}</p>
    `;
    els.productAliasList.innerHTML = `
      <h3>Barcode Aliases</h3>
      ${(product.barcodes || []).map((alias) => `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
          <span>${escapeHtml(alias.barcode)} · ${escapeHtml(alias.label || "Alias")} ${alias.is_primary ? "· Primary" : ""}</span>
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
      <article class="data-row" style="grid-template-columns: minmax(0, 1fr) auto auto;">
        <div>
          <h3>${escapeHtml(session.name)}</h3>
          <p class="meta-details">
            <span><strong>ID:</strong> ${escapeHtml(session.id)}</span>
            <span><strong>Date:</strong> ${escapeHtml(session.period_date)}</span>
          </p>
        </div>
        <span class="badge">${escapeHtml(session.line_count)} lines</span>
        <div style="display:flex; gap:8px;">
          <button class="primary-btn" data-action="export-session" data-id="${escapeHtml(session.id)}" type="button">Review Export</button>
          <button class="warning" data-action="delete-session" data-id="${escapeHtml(session.id)}" type="button">Delete</button>
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
      <div class="summary-grid">
        <div class="metric"><span>Lines Counted</span><strong>${escapeHtml(data.line_count)}</strong></div>
        <div class="metric"><span>Missing BIN</span><strong>${escapeHtml(data.missing_bin_count)}</strong></div>
        <div class="metric"><span>Unresolved Drafts</span><strong>${escapeHtml(data.draft_count)}</strong></div>
      </div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px;">
        <a class="download-link ${ready ? "" : "disabled"}" href="/export/${encodeURIComponent(sessionId)}">Download Locked Excel Sheet</a>
        <p class="meta">${ready ? "✅ Export is ready for locking." : "⚠️ Resolve missing BINs and draft details before final export."}</p>
      </div>
      <div class="task-list" style="margin-top:12px;">
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
  try {
    await api(`/admin/api/products/${encodeURIComponent(product.id)}/barcodes`, {
      method: "POST",
      body: JSON.stringify({
        barcode,
        label: els.aliasLabel.value.trim() || "Alias barcode",
        is_primary: false
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
  if (!confirm(`Merge ${sourceId} into ${product.id}? Counts and barcode aliases will move to the current product.`)) return;
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
      if (button.dataset.view === "export") loadExportReview();
    });
  });

  els.refreshTasksButton.addEventListener("click", async () => {
    await loadTasks();
    showToast("Tasks list refreshed");
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
    if (!confirm("Are you sure you want to reject and delete this task and its draft product?")) return;
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
      if (!confirm("Are you sure you want to delete this product?")) return;
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
    if (!button || button.dataset.action !== "detail-product") return;
    await openProductDetail(button.dataset.id);
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
    if (!confirm(`Are you sure you want to delete ${state.selectedProductIds.length} selected products?`)) return;
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
      if (!confirm("Are you sure you want to delete this session and all its stocktake line counts? This cannot be undone!")) return;
      try {
        await api(`/admin/api/sessions/${encodeURIComponent(id)}`, {
          method: "DELETE"
        });
        showToast("Session deleted successfully");
        await loadSessions();
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }
  });

  els.exportSession.addEventListener("change", () => loadExportReview());
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
  await Promise.all([loadTasks(), loadProducts(), loadSessions()]);
  if (els.exportSession.value) await loadExportReview();
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
