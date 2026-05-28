const state = {
  authed: false,
  tasks: [],
  products: [],
  sessions: [],
  selectedTask: null
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
  taskDialog: document.querySelector("#taskDialog"),
  taskDialogTitle: document.querySelector("#taskDialogTitle"),
  taskName: document.querySelector("#taskName"),
  taskBin: document.querySelector("#taskBin"),
  taskCategory: document.querySelector("#taskCategory"),
  taskSize: document.querySelector("#taskSize"),
  taskUnit: document.querySelector("#taskUnit"),
  taskPhoto: document.querySelector("#taskPhoto"),
  taskNotes: document.querySelector("#taskNotes"),
  taskSources: document.querySelector("#taskSources"),
  approveTaskButton: document.querySelector("#approveTaskButton")
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
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

async function loadTasks() {
  const data = await api("/admin/api/tasks");
  state.tasks = data.tasks;
  els.taskList.innerHTML = state.tasks.length ? state.tasks.map((task) => {
    const suggestion = task.suggested || {};
    const title = suggestion.name || task.current_name || `Barcode ${task.barcode}`;
    return `
      <article class="task-row">
        <div>
          <h3>${escapeHtml(title)}</h3>
          <p class="meta">${escapeHtml(task.barcode)} · ${escapeHtml(task.current_bin || "No BIN")} · updated ${escapeHtml(task.updated_at)}</p>
          ${task.error ? `<p class="error">${escapeHtml(task.error)}</p>` : ""}
        </div>
        ${statusBadge(task.status)}
        <div>
          <button class="secondary" data-action="enrich" data-id="${escapeHtml(task.id)}" type="button">Enrich</button>
          <button data-action="review" data-id="${escapeHtml(task.id)}" type="button">Review</button>
        </div>
      </article>
    `;
  }).join("") : `<p class="meta">No product tasks.</p>`;
}

async function loadProducts(search = "") {
  const data = await api(`/admin/api/products?search=${encodeURIComponent(search)}`);
  state.products = data.products;
  els.productList.innerHTML = state.products.length ? state.products.map((product) => `
    <article class="data-row">
      <div>
        <h3>${escapeHtml(product.name)}</h3>
        <p class="meta">${escapeHtml(product.barcode)} · ${escapeHtml(product.category || "No category")} · ${escapeHtml(product.size || "No size")}</p>
      </div>
      <input value="${escapeHtml(product.bin || "")}" aria-label="BIN for ${escapeHtml(product.name)}" data-field="bin" data-id="${escapeHtml(product.id)}">
      ${statusBadge(product.draft_status)}
      <button data-action="save-product" data-id="${escapeHtml(product.id)}" type="button">Save</button>
    </article>
  `).join("") : `<p class="meta">No products found.</p>`;
}

async function loadSessions() {
  const data = await api("/admin/api/sessions");
  state.sessions = data.sessions;
  els.sessionList.innerHTML = state.sessions.map((session) => `
    <article class="data-row">
      <div>
        <h3>${escapeHtml(session.name)}</h3>
        <p class="meta">${escapeHtml(session.id)} · ${escapeHtml(session.period_date)}</p>
      </div>
      <span class="badge">${escapeHtml(session.line_count)} lines</span>
      <button data-action="export-session" data-id="${escapeHtml(session.id)}" type="button">Review Export</button>
    </article>
  `).join("");
  els.exportSession.innerHTML = state.sessions.map((session) => (
    `<option value="${escapeHtml(session.id)}">${escapeHtml(session.name)} (${escapeHtml(session.id)})</option>`
  )).join("");
}

async function loadExportReview(sessionId = els.exportSession.value) {
  if (!sessionId) {
    els.exportReview.innerHTML = `<p class="meta">Create or select a session.</p>`;
    return;
  }
  const data = await api(`/admin/api/export/${encodeURIComponent(sessionId)}/review`);
  const ready = data.line_count > 0 && data.missing_bin_count === 0 && data.draft_count === 0;
  const rows = data.missing_bin_rows || [];
  els.exportReview.innerHTML = `
    <div class="summary-grid">
      <div class="metric"><span>Lines</span><strong>${escapeHtml(data.line_count)}</strong></div>
      <div class="metric"><span>Missing BIN</span><strong>${escapeHtml(data.missing_bin_count)}</strong></div>
      <div class="metric"><span>Drafts</span><strong>${escapeHtml(data.draft_count)}</strong></div>
    </div>
    <div>
      <a class="download-link ${ready ? "" : "disabled"}" href="/export/${encodeURIComponent(sessionId)}">Download Excel</a>
      <p class="meta">${ready ? "Export is ready." : "Fix missing BINs and draft products before final export."}</p>
    </div>
    <div class="task-list">
      ${rows.map((row) => `
        <article class="missing-row">
          <div>
            <h3>${escapeHtml(row.product_name || row.barcode)}</h3>
            <p class="meta">${escapeHtml(row.barcode)} · ${escapeHtml(row.location)} · qty ${escapeHtml(row.quantity_decimal)}</p>
          </div>
          <input placeholder="BIN" data-field="missing-bin" data-product-id="${escapeHtml(row.product_id)}">
          <button data-action="save-bin" data-product-id="${escapeHtml(row.product_id)}" type="button">Save BIN</button>
        </article>
      `).join("")}
    </div>
  `;
}

function showTask(task) {
  const suggestion = task.suggested || {};
  state.selectedTask = task;
  els.taskDialogTitle.textContent = `Review ${task.barcode}`;
  els.taskName.value = suggestion.name || task.current_name || "";
  els.taskBin.value = suggestion.bin || task.current_bin || "";
  els.taskCategory.value = suggestion.category || "";
  els.taskSize.value = suggestion.size || "";
  els.taskUnit.value = suggestion.unit || "each";
  els.taskPhoto.value = suggestion.image_url || "";
  els.taskNotes.value = [
    suggestion.brand ? `Brand: ${suggestion.brand}` : "",
    suggestion.confidence ? `Confidence: ${suggestion.confidence}` : ""
  ].filter(Boolean).join("\n");
  const sources = suggestion.source_urls || [];
  els.taskSources.innerHTML = sources.map((url) => (
    `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`
  )).join("");
  els.taskDialog.showModal();
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
      await hydrate();
    } catch (error) {
      els.loginError.textContent = error.message;
    }
  });

  els.logoutButton.addEventListener("click", async () => {
    await api("/admin/api/logout", { method: "POST", body: "{}" }).catch(() => {});
    setAuthed(false);
  });

  els.tabs.forEach((button) => {
    button.addEventListener("click", () => {
      els.tabs.forEach((tab) => tab.classList.toggle("active", tab === button));
      els.views.forEach((view) => view.classList.toggle("hidden", view.id !== `${button.dataset.view}View`));
      if (button.dataset.view === "export") loadExportReview();
    });
  });

  els.refreshTasksButton.addEventListener("click", loadTasks);

  els.taskList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const task = state.tasks.find((item) => item.id === button.dataset.id);
    if (!task) return;
    if (button.dataset.action === "review") showTask(task);
    if (button.dataset.action === "enrich") {
      button.disabled = true;
      await api(`/admin/api/tasks/${encodeURIComponent(task.id)}/enrich`, { method: "POST", body: "{}" });
      await loadTasks();
      await loadDashboard();
    }
  });

  els.approveTaskButton.addEventListener("click", async () => {
    if (!state.selectedTask) return;
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
    els.taskDialog.close();
    await hydrate();
  });

  els.productSearchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadProducts(els.productSearch.value);
  });

  els.productList.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.dataset.action !== "save-product") return;
    const row = button.closest(".data-row");
    const bin = row.querySelector("[data-field='bin']").value.trim();
    await api(`/admin/api/products/${encodeURIComponent(button.dataset.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ bin, draft_status: bin ? "confirmed" : undefined })
    });
    await loadProducts(els.productSearch.value);
    await loadDashboard();
  });

  els.sessionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/sessions", {
      method: "POST",
      body: JSON.stringify({
        id: els.sessionId.value.trim(),
        name: els.sessionName.value.trim(),
        period_date: els.sessionDate.value
      })
    });
    await loadSessions();
  });

  els.exportSession.addEventListener("change", () => loadExportReview());
  els.exportReview.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.dataset.action !== "save-bin") return;
    const row = button.closest(".missing-row");
    const bin = row.querySelector("[data-field='missing-bin']").value.trim();
    if (!bin) return;
    await api(`/products/${encodeURIComponent(button.dataset.productId)}/bin`, {
      method: "PATCH",
      body: JSON.stringify({ bin })
    });
    await loadExportReview();
  });
}

async function hydrate() {
  await loadDashboard();
  await Promise.all([loadTasks(), loadProducts(), loadSessions()]);
  await loadExportReview();
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
