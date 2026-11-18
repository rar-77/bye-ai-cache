/* ==========================================================================
   BYE-AI-CACHE v1.0 // FRONTEND CONTROLLER & 3D CUSHION TREEMAP ENGINE
========================================================================== */

const state = {
  scanData: null,
  allItems: [],
  filteredItems: [],
  selectedIds: new Set(),
  highlightedId: null,
  safetyFilter: "all",
  categoryFilter: "ALL",
  driveFilter: "ALL",
  minAgeDays: 0,
  searchQuery: "",
  sortBy: "size_desc",
  treemapColorMode: "safety", // 'safety' | 'category'
  treemapRects: [],
  pendingCleanMode: "recycle",
  playlistLimit: 250,
};

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let val = Number(bytes);
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx++;
  }
  return idx <= 1 ? `${Math.round(val)} ${units[idx]}` : `${val.toFixed(2)} ${units[idx]}`;
}

/* ==========================================================================
   INITIALIZATION & THEME / WINDOW CONTROLS
========================================================================== */
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initWindowControls();
  initFiltersAndButtons();
  initCanvasEvents();

  // Trigger initial Smart Scan on load
  runSmartScan();

  window.addEventListener("resize", () => {
    renderTreemap();
  });
});

function initTheme() {
  const saved = localStorage.getItem("bye_ai_cache_theme") || "dark-blue";
  setTheme(saved);

  document.getElementById("btn-theme-light").addEventListener("click", () => setTheme("light-grey"));
  document.getElementById("btn-theme-dark").addEventListener("click", () => setTheme("dark-blue"));
}

function setTheme(themeName) {
  document.documentElement.setAttribute("data-theme", themeName);
  localStorage.setItem("bye_ai_cache_theme", themeName);
  document.getElementById("btn-theme-light").classList.toggle("active", themeName === "light-grey");
  document.getElementById("btn-theme-dark").classList.toggle("active", themeName === "dark-blue");
  renderTreemap();
}

function initWindowControls() {
  // WindowShade (_) buttons
  document.querySelectorAll(".shade-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const targetId = btn.getAttribute("data-target");
      const bodyEl = document.getElementById(targetId);
      if (bodyEl) {
        bodyEl.classList.toggle("shaded");
        setTimeout(() => renderTreemap(), 50);
      }
    });
  });

  // Double-click titlebar to shade/unshade like Winamp
  document.querySelectorAll(".win-titlebar").forEach((bar) => {
    bar.addEventListener("dblclick", (e) => {
      if (e.target.tagName === "BUTTON") return;
      const targetId = bar.getAttribute("data-shade-target");
      if (targetId) {
        const bodyEl = document.getElementById(targetId);
        if (bodyEl) {
          bodyEl.classList.toggle("shaded");
          setTimeout(() => renderTreemap(), 50);
        }
      }
    });
  });

  // Module visibility toggles (EQ, PL, 3D)
  document.querySelectorAll(".toggle-mod-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modId = btn.getAttribute("data-mod");
      const winEl = document.getElementById(modId);
      if (!winEl) return;
      const isHidden = winEl.style.display === "none";
      winEl.style.display = isHidden ? "" : "none";
      btn.classList.toggle("active", isHidden);
      setTimeout(() => renderTreemap(), 50);
    });
  });
}

/* ==========================================================================
   SCANNING & API ACTIONS
========================================================================== */
async function runSmartScan() {
  setScanningUI(true, "ESCANEANDO RADARES DE IA (HERMES, COMFYUI, GEMINI, HF, OLLAMA, PIP)...");
  try {
    const res = await fetch("/api/scan/smart");
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    ingestScanResult(data);
  } catch (err) {
    setScanningUI(false, `ERROR DE ESCANEO: ${err.message}`);
  }
}

async function runCustomScan(pathStr) {
  if (!pathStr || !pathStr.trim()) return;
  setScanningUI(true, `ESCANEANDO RUTA PERSONALIZADA: ${pathStr} ...`);
  try {
    const res = await fetch("/api/scan/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pathStr.trim() }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    ingestScanResult(data);
  } catch (err) {
    setScanningUI(false, `ERROR: ${err.message}`);
  }
}

function setScanningUI(scanning, message) {
  const stateEl = document.getElementById("lcd-state");
  const marqueeEl = document.getElementById("lcd-marquee");
  const progText = document.getElementById("scan-progress-text");
  const progBar = document.getElementById("scan-progress-bar");

  if (scanning) {
    stateEl.textContent = "SCANNING...";
    marqueeEl.textContent = `*** ${message} ***`;
    progText.textContent = message;
    progBar.style.width = "60%";
  } else {
    stateEl.textContent = "READY // ONLINE";
    progText.textContent = message;
    progBar.style.width = "100%";
  }
}

function renderDriveChips(driveTotals) {
  const container = document.getElementById("drive-chips");
  if (!container) return;

  const entries = Object.entries(driveTotals || {}).filter(([, info]) => info && info.bytes > 0);
  if (state.driveFilter !== "ALL" && !entries.some(([drv]) => drv === state.driveFilter)) {
    state.driveFilter = "ALL";
  }

  container.innerHTML = `<span class="win-label" style="margin-right:4px;">DISCO:</span>`;

  const allBtn = document.createElement("button");
  allBtn.className = `win-btn chip-btn drive-btn${state.driveFilter === "ALL" ? " active" : ""}`;
  allBtn.setAttribute("data-drive", "ALL");
  allBtn.textContent = "🌐 TODOS";
  allBtn.addEventListener("click", () => {
    state.driveFilter = "ALL";
    container.querySelectorAll(".drive-btn").forEach((b) => b.classList.remove("active"));
    allBtn.classList.add("active");
    applyFilters();
  });
  container.appendChild(allBtn);

  entries.forEach(([drv, info]) => {
    const btn = document.createElement("button");
    btn.className = `win-btn chip-btn drive-btn${state.driveFilter === drv ? " active" : ""}`;
    btn.setAttribute("data-drive", drv);
    const icon = drv === "C:" ? "💻" : "💿";
    btn.textContent = `${icon} DISCO ${drv} (${info.human})`;
    btn.addEventListener("click", () => {
      state.driveFilter = drv;
      container.querySelectorAll(".drive-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      applyFilters();
    });
    container.appendChild(btn);
  });
}

function ingestScanResult(data) {
  state.scanData = data;
  state.allItems = data.items || [];
  state.selectedIds.clear();

  // Auto-select nothing by default, or keep safe choice clear until user clicks or selects
  document.getElementById("lcd-total-gb").textContent = data.total_human || "0 B";
  document.getElementById("lcd-files-count").textContent = String(data.files_scanned || 0);
  document.getElementById("lcd-scan-speed").textContent = `${data.elapsed_ms || 1}ms`;

  const greenH = data.safety_totals?.green?.human || "0 B";
  const yellowH = data.safety_totals?.yellow?.human || "0 B";
  const redH = data.safety_totals?.red?.human || "0 B";

  renderDriveChips(data.drive_totals || {});

  const driveSummary = Object.entries(data.drive_totals || {})
    .filter(([, info]) => info && info.bytes > 0)
    .map(([drv, info]) => `${drv} ${info.human}`)
    .join(" | ");

  document.getElementById("tot-all").textContent = data.total_human || "0 B";
  document.getElementById("tot-green").textContent = greenH;
  document.getElementById("tot-yellow").textContent = yellowH;
  document.getElementById("tot-red").textContent = redH;

  document.getElementById("lcd-marquee").textContent =
    `*** SCAN COMPLETO [${data.mode}] — ${driveSummary || data.total_human} || 🟢 SEGURO: ${greenH} | 🟡 MODELOS: ${yellowH} | 🔴 PROTEGIDO: ${redH} ***`;

  setScanningUI(
    false,
    `DETECTADOS ${state.allItems.length} GRUPOS (${data.files_scanned} ARCHIVOS) EN ${data.elapsed_ms} MS`
  );

  updateSpectrumBars(data.category_totals || {}, data.total_bytes || 1);
  applyFilters();
}

function updateSpectrumBars(catTotals, totalBytes) {
  const cats = ["AGENTS", "COMFYUI", "MODELS", "DEVCACHE", "CUSTOM"];
  const maxVal = Math.max(
    1,
    ...cats.map((c) => (catTotals[c] ? catTotals[c].bytes : 0))
  );

  cats.forEach((c) => {
    const el = document.getElementById(`spec-${c}`);
    if (!el) return;
    const bytes = catTotals[c] ? catTotals[c].bytes : 0;
    const ratio = bytes > 0 ? Math.max(0.18, bytes / maxVal) : 0.08;
    el.style.height = `${Math.min(100, Math.round(ratio * 100))}%`;
  });
}

/* ==========================================================================
   FILTERS, SORTING & SELECTION
========================================================================== */
function initFiltersAndButtons() {
  // Transport buttons
  document.getElementById("btn-smart-scan").addEventListener("click", () => runSmartScan());

  document.getElementById("btn-scan-custom").addEventListener("click", () => {
    const val = document.getElementById("input-custom-path").value;
    runCustomScan(val);
  });

  document.getElementById("input-custom-path").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      runCustomScan(e.target.value);
    }
  });

  document.getElementById("btn-pick-folder").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/pick-folder");
      const data = await res.json();
      if (data.path) {
        document.getElementById("input-custom-path").value = data.path;
        runCustomScan(data.path);
      }
    } catch (e) {
      console.error(e);
    }
  });

  // Auto-select safe green items
  document.getElementById("btn-select-green").addEventListener("click", () => {
    state.selectedIds.clear();
    state.allItems.forEach((item) => {
      if (item.safety === "green") {
        state.selectedIds.add(item.id);
      }
    });
    updateSelectionSummary();
    renderPlaylist();
    renderTreemap();
  });

  // Traffic Light cards
  document.querySelectorAll(".traffic-card").forEach((card) => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".traffic-card").forEach((c) => c.classList.remove("active"));
      card.classList.add("active");
      state.safetyFilter = card.getAttribute("data-safety") || "all";
      applyFilters();
    });
  });

  // Drive filter buttons
  document.querySelectorAll(".drive-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".drive-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.driveFilter = btn.getAttribute("data-drive") || "ALL";
      applyFilters();
    });
  });

  // Category radar chips
  document.querySelectorAll(".cat-btn").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".cat-btn").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.categoryFilter = chip.getAttribute("data-cat") || "ALL";
      applyFilters();
    });
  });

  // Age filter
  document.getElementById("select-age").addEventListener("change", (e) => {
    state.minAgeDays = parseInt(e.target.value, 10) || 0;
    applyFilters();
  });

  // Search & Sort
  document.getElementById("input-search").addEventListener("input", (e) => {
    state.searchQuery = (e.target.value || "").toLowerCase().trim();
    applyFilters();
  });

  document.getElementById("select-sort").addEventListener("change", (e) => {
    state.sortBy = e.target.value;
    applyFilters();
  });

  // Playlist footer selection helpers
  document.getElementById("btn-sel-all-visible").addEventListener("click", () => {
    state.filteredItems.forEach((item) => {
      if (item.safety !== "red") {
        state.selectedIds.add(item.id);
      }
    });
    updateSelectionSummary();
    renderPlaylist();
    renderTreemap();
  });

  document.getElementById("btn-sel-none").addEventListener("click", () => {
    state.selectedIds.clear();
    updateSelectionSummary();
    renderPlaylist();
    renderTreemap();
  });

  document.getElementById("btn-sel-invert").addEventListener("click", () => {
    state.filteredItems.forEach((item) => {
      if (item.safety === "red") return;
      if (state.selectedIds.has(item.id)) {
        state.selectedIds.delete(item.id);
      } else {
        state.selectedIds.add(item.id);
      }
    });
    updateSelectionSummary();
    renderPlaylist();
    renderTreemap();
  });

  // Treemap color mode buttons
  document.getElementById("btn-color-safety").addEventListener("click", () => {
    state.treemapColorMode = "safety";
    document.getElementById("btn-color-safety").classList.add("active");
    document.getElementById("btn-color-cat").classList.remove("active");
    renderTreemap();
  });

  document.getElementById("btn-color-cat").addEventListener("click", () => {
    state.treemapColorMode = "category";
    document.getElementById("btn-color-cat").classList.add("active");
    document.getElementById("btn-color-safety").classList.remove("active");
    renderTreemap();
  });

  // Clean buttons + Modal
  document.getElementById("btn-clean-recycle").addEventListener("click", () => openCleanModal("recycle"));
  document.getElementById("btn-clean-perm").addEventListener("click", () => openCleanModal("permanent"));
  document.getElementById("btn-modal-close").addEventListener("click", closeCleanModal);
  document.getElementById("btn-modal-cancel").addEventListener("click", closeCleanModal);
  document.getElementById("btn-modal-confirm").addEventListener("click", confirmAndExecuteClean);
}

function applyFilters() {
  // First compute drive + category + age + search matching items (before safety filter) so traffic light cards reflect active drive/radar
  const scopeItems = state.allItems.filter((item) => {
    if (state.driveFilter !== "ALL") {
      const itemDrive = (item.drive || (item.path ? item.path.slice(0, 2).toUpperCase() : ""));
      if (itemDrive !== state.driveFilter) return false;
    }
    if (state.categoryFilter !== "ALL" && item.category !== state.categoryFilter) return false;
    if (state.minAgeDays > 0 && (item.days_inactive || 0) < state.minAgeDays) return false;
    if (state.searchQuery) {
      const hay = `${item.name} ${item.path} ${item.kind} ${item.radar_name}`.toLowerCase();
      if (!hay.includes(state.searchQuery)) return false;
    }
    return true;
  });

  let scopeAll = 0;
  let scopeGreen = 0;
  let scopeYellow = 0;
  let scopeRed = 0;
  scopeItems.forEach((it) => {
    scopeAll += it.size_bytes;
    if (it.safety === "green") scopeGreen += it.size_bytes;
    else if (it.safety === "red") scopeRed += it.size_bytes;
    else scopeYellow += it.size_bytes;
  });

  document.getElementById("tot-all").textContent = formatBytes(scopeAll);
  document.getElementById("tot-green").textContent = formatBytes(scopeGreen);
  document.getElementById("tot-yellow").textContent = formatBytes(scopeYellow);
  document.getElementById("tot-red").textContent = formatBytes(scopeRed);

  const list = scopeItems.filter((item) => {
    if (state.safetyFilter !== "all" && item.safety !== state.safetyFilter) return false;
    return true;
  });

  const safetyOrder = { green: 1, yellow: 2, red: 3 };
  list.sort((a, b) => {
    if (state.sortBy === "size_desc") return b.size_bytes - a.size_bytes;
    if (state.sortBy === "age_desc") return (b.days_inactive || 0) - (a.days_inactive || 0);
    if (state.sortBy === "safety_asc") {
      const diff = (safetyOrder[a.safety] || 9) - (safetyOrder[b.safety] || 9);
      return diff !== 0 ? diff : b.size_bytes - a.size_bytes;
    }
    if (state.sortBy === "name_asc") return a.name.localeCompare(b.name);
    return 0;
  });

  state.filteredItems = list;
  state.playlistLimit = 250;
  document.getElementById("pl-count").textContent = String(list.length);
  updateSelectionSummary();
  renderPlaylist();
  renderTreemap();
}

function updateSelectionSummary() {
  let selBytes = 0;
  let selCount = 0;
  state.allItems.forEach((item) => {
    if (state.selectedIds.has(item.id)) {
      selBytes += item.size_bytes;
      selCount++;
    }
  });
  const human = formatBytes(selBytes);
  document.getElementById("lcd-selected-gb").textContent = human;
  document.getElementById("pl-selection-summary").textContent = `${selCount} SELECCIONADOS // ${human}`;
}

function findRowById(container, itemId) {
  const rows = container.querySelectorAll(".pl-row");
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].getAttribute("data-id") === itemId) {
      return rows[i];
    }
  }
  return null;
}

function syncRowSelectionDOM(itemId) {
  const container = document.getElementById("playlist-container");
  if (!container) return;
  container.querySelectorAll(".pl-row.highlighted").forEach((el) => el.classList.remove("highlighted"));
  const rowEl = findRowById(container, itemId);
  if (rowEl) {
    const isSel = state.selectedIds.has(itemId);
    rowEl.classList.toggle("selected", isSel);
    rowEl.classList.toggle("highlighted", state.highlightedId === itemId);
    const cb = rowEl.querySelector(".row-cb");
    if (cb) cb.checked = isSel;
  }
}

/* ==========================================================================
   WINAMP PLAYLIST RENDERER
========================================================================== */
function renderPlaylist() {
  const container = document.getElementById("playlist-container");
  container.innerHTML = "";

  if (state.filteredItems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "pl-empty";
    empty.textContent = "No hay archivos o cachés que coincidan con este filtro.";
    container.appendChild(empty);
    return;
  }

  const badgeIcon = { green: "🟢", yellow: "🟡", red: "🔒" };
  const slice = state.filteredItems.slice(0, state.playlistLimit);
  const frag = document.createDocumentFragment();

  slice.forEach((item, idx) => {
    const row = document.createElement("div");
    const isSel = state.selectedIds.has(item.id);
    const isHi = state.highlightedId === item.id;
    row.className = `pl-row safety-${item.safety}${isSel ? " selected" : ""}${isHi ? " highlighted" : ""}`;
    row.setAttribute("data-id", item.id);

    const trackNo = String(idx + 1).padStart(2, "0");
    const ageLabel = item.days_inactive === 0 ? "Hoy" : `${item.days_inactive}d inactivo`;

    row.innerHTML = `
      <div class="pl-check">
        ${
          item.safety === "red"
            ? `<span title="Protegido (No se puede borrar)">🔒</span>`
            : `<input type="checkbox" class="row-cb" ${isSel ? "checked" : ""} />`
        }
      </div>
      <div class="pl-track-num">${trackNo}.</div>
      <div class="pl-semaforo" title="${escapeHtml(item.kind)}">${badgeIcon[item.safety] || "🟡"}</div>
      <div class="pl-main-info">
        <div class="pl-title">${escapeHtml(item.icon || "📁")} ${escapeHtml(item.name)}</div>
        <div class="pl-sub">${escapeHtml(item.kind)} — ${escapeHtml(item.path)}</div>
      </div>
      <div class="pl-age">${ageLabel}</div>
      <div>
        <button class="pl-dir-btn" title="Mostrar en el Explorador de Windows">📂 DIR</button>
      </div>
      <div class="pl-size">${item.size_human}</div>
    `;

    // Toggle checkbox in-place when clicking row (0ms lag)
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("pl-dir-btn")) return;
      state.highlightedId = item.id;
      if (item.safety !== "red") {
        if (state.selectedIds.has(item.id)) {
          state.selectedIds.delete(item.id);
        } else {
          state.selectedIds.add(item.id);
        }
      }
      updateSelectionSummary();
      syncRowSelectionDOM(item.id);
      renderTreemap();
    });

    // Reveal in Explorer button
    const dirBtn = row.querySelector(".pl-dir-btn");
    dirBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch("/api/reveal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: item.path }),
      });
    });

    frag.appendChild(row);
  });

  if (state.filteredItems.length > state.playlistLimit) {
    const moreBtn = document.createElement("div");
    moreBtn.className = "pl-empty";
    moreBtn.style.cursor = "pointer";
    moreBtn.style.padding = "10px";
    moreBtn.style.color = "#00f0ff";
    moreBtn.style.fontWeight = "bold";
    const remaining = state.filteredItems.length - state.playlistLimit;
    moreBtn.textContent = `[ + MOSTRAR ${remaining} TRACKS RESTANTES (${state.filteredItems.length} TOTALES) ]`;
    moreBtn.addEventListener("click", () => {
      state.playlistLimit += 500;
      renderPlaylist();
    });
    frag.appendChild(moreBtn);
  }

  container.appendChild(frag);
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ==========================================================================
   WINDIRSTAT 3D CUSHION TREEMAP ENGINE (CANVAS)
========================================================================== */
function getBlockBaseColor(item) {
  if (state.treemapColorMode === "safety") {
    if (item.safety === "green") return [16, 185, 88];   // Emerald Green
    if (item.safety === "red") return [215, 48, 60];     // Protected Crimson
    return [225, 162, 18];                               // Amber Model Gold
  }
  // Category color mode
  const map = {
    AGENTS: [0, 184, 230],    // Cyber Cyan
    COMFYUI: [168, 85, 247],  // Neon Purple
    MODELS: [234, 158, 22],   // Gold / Orange
    DEVCACHE: [34, 197, 94],  // Matrix Green
    CUSTOM: [59, 130, 246],   // Royal Blue
  };
  return map[item.category] || [100, 140, 200];
}

function itemTreemapWeight(it) {
  return Math.pow(Math.max(1024, it.size_bytes), 0.72);
}

function computeBinaryTreemap(items, x, y, w, h, outRects) {
  if (!items || items.length === 0 || w <= 2 || h <= 2) return;
  if (items.length === 1) {
    outRects.push({ item: items[0], x, y, w, h });
    return;
  }

  const total = items.reduce((acc, it) => acc + itemTreemapWeight(it), 0);
  let half = 0;
  let splitIdx = 1;
  for (let i = 0; i < items.length; i++) {
    half += itemTreemapWeight(items[i]);
    if (half >= total / 2) {
      splitIdx = Math.max(1, i + 1);
      break;
    }
  }
  if (splitIdx >= items.length) splitIdx = items.length - 1;

  const leftItems = items.slice(0, splitIdx);
  const rightItems = items.slice(splitIdx);
  const leftSum = leftItems.reduce((acc, it) => acc + itemTreemapWeight(it), 0);
  const ratio = total > 0 ? Math.min(0.88, Math.max(0.12, leftSum / total)) : 0.5;

  if (w >= h) {
    const wLeft = Math.max(2, Math.min(w - 2, Math.floor(w * ratio)));
    computeBinaryTreemap(leftItems, x, y, wLeft, h, outRects);
    computeBinaryTreemap(rightItems, x + wLeft, y, w - wLeft, h, outRects);
  } else {
    const hTop = Math.max(2, Math.min(h - 2, Math.floor(h * ratio)));
    computeBinaryTreemap(leftItems, x, y, w, hTop, outRects);
    computeBinaryTreemap(rightItems, x, y + hTop, w, h - hTop, outRects);
  }
}

function renderTreemap() {
  const wrap = document.getElementById("treemap-wrap");
  const canvas = document.getElementById("treemap-canvas");
  if (!wrap || !canvas) return;

  const rect = wrap.getBoundingClientRect();
  const width = Math.max(100, Math.floor(rect.width));
  const height = Math.max(100, Math.floor(rect.height));
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#05080f";
  ctx.fillRect(0, 0, width, height);

  const visible = state.filteredItems.filter((i) => i.size_bytes > 0).slice(0, 85);
  state.treemapRects = [];

  if (visible.length === 0) {
    ctx.fillStyle = "#6e8bb5";
    ctx.font = "12px Consolas, monospace";
    ctx.fillText("Sin bloques para graficar en este filtro.", 20, 30);
    return;
  }

  computeBinaryTreemap(visible, 2, 2, width - 4, height - 4, state.treemapRects);

  state.treemapRects.forEach((r) => {
    draw3DCushionBlock(ctx, r);
  });
}

function draw3DCushionBlock(ctx, r) {
  const { item, x, y, w, h } = r;
  if (w < 3 || h < 3) return;

  const [cr, cg, cb] = getBlockBaseColor(item);
  const isSelected = state.selectedIds.has(item.id);
  const isHighlighted = state.highlightedId === item.id;

  // 2000s WinDirStat / SequoiaView 3D Cushion radial specular gradient
  const cx = x + w * 0.32;
  const cy = y + h * 0.28;
  const radius = Math.max(w, h) * 0.85;

  const grad = ctx.createRadialGradient(cx, cy, Math.max(1, radius * 0.04), x + w * 0.5, y + h * 0.5, radius);
  const hiR = Math.min(255, cr + 75);
  const hiG = Math.min(255, cg + 75);
  const hiB = Math.min(255, cb + 75);
  const loR = Math.max(0, Math.floor(cr * 0.26));
  const loG = Math.max(0, Math.floor(cg * 0.26));
  const loB = Math.max(0, Math.floor(cb * 0.26));

  grad.addColorStop(0, `rgb(${hiR}, ${hiG}, ${hiB})`);
  grad.addColorStop(0.48, `rgb(${cr}, ${cg}, ${cb})`);
  grad.addColorStop(1, `rgb(${loR}, ${loG}, ${loB})`);

  ctx.fillStyle = grad;
  ctx.fillRect(x + 1, y + 1, w - 2, h - 2);

  // 3D Outer Bevel Edges
  ctx.strokeStyle = `rgba(255, 255, 255, 0.38)`;
  ctx.beginPath();
  ctx.moveTo(x + 1, y + h - 1);
  ctx.lineTo(x + 1, y + 1);
  ctx.lineTo(x + w - 1, y + 1);
  ctx.stroke();

  ctx.strokeStyle = `rgba(0, 0, 0, 0.72)`;
  ctx.beginPath();
  ctx.moveTo(x + w - 1, y + 1);
  ctx.lineTo(x + w - 1, y + h - 1);
  ctx.lineTo(x + 1, y + h - 1);
  ctx.stroke();

  // Selection or Highlight Overlay
  if (isSelected) {
    ctx.strokeStyle = "#00ffcc";
    ctx.lineWidth = 2;
    ctx.strokeRect(x + 2, y + 2, Math.max(1, w - 4), Math.max(1, h - 4));
    ctx.lineWidth = 1;
  } else if (isHighlighted) {
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x + 1.5, y + 1.5, Math.max(1, w - 3), Math.max(1, h - 3));
    ctx.lineWidth = 1;
  }

  // Draw text label inside larger 3D cushions
  if (w > 54 && h > 26) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(x + 4, y + 3, w - 8, h - 6);
    ctx.clip();

    ctx.fillStyle = "#ffffff";
    ctx.shadowColor = "#000000";
    ctx.shadowBlur = 3;
    ctx.font = "bold 10px Tahoma, sans-serif";
    const prefix = isSelected ? "☑ " : item.safety === "red" ? "🔒 " : "";
    ctx.fillText(`${prefix}${item.name}`, x + 5, y + 14);

    if (h > 38) {
      ctx.fillStyle = "#e2f1ff";
      ctx.font = "10px Consolas, monospace";
      ctx.fillText(item.size_human, x + 5, y + 27);
    }
    ctx.restore();
  }
}

function initCanvasEvents() {
  const canvas = document.getElementById("treemap-canvas");
  if (!canvas) return;

  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const hit = state.treemapRects.find((r) => mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h);
    if (hit) {
      const it = hit.item;
      document.getElementById("insp-name").textContent =
        `${it.icon || "📁"} ${it.name} — [${it.size_human}] (${it.days_inactive}d sin tocar)`;
      document.getElementById("insp-path").textContent = `${it.kind} // ${it.path}`;
    }
  });

  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const hit = state.treemapRects.find((r) => mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h);
    if (!hit) return;

    const item = hit.item;
    state.highlightedId = item.id;
    if (item.safety !== "red") {
      if (state.selectedIds.has(item.id)) {
        state.selectedIds.delete(item.id);
      } else {
        state.selectedIds.add(item.id);
      }
    }

    updateSelectionSummary();
    syncRowSelectionDOM(item.id);
    renderTreemap();

    // Scroll playlist to that track
    const container = document.getElementById("playlist-container");
    const rowEl = container ? findRowById(container, item.id) : null;
    if (rowEl) {
      rowEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

/* ==========================================================================
   CLEANING MODAL (DRY-RUN + RECYCLE BIN / PERMANENT)
========================================================================== */
async function openCleanModal(mode) {
  const selectedItems = state.allItems.filter((i) => state.selectedIds.has(i.id) && i.safety !== "red");
  if (selectedItems.length === 0) {
    alert("Seleccioná primero uno o más archivos/cachés (🟢 o 🟡) en la Playlist o usando el botón [AUTO-SELECCIONAR SEGUROS].");
    return;
  }

  state.pendingCleanMode = mode;
  const modal = document.getElementById("clean-modal");
  const titleEl = document.getElementById("modal-title");
  const summaryEl = document.getElementById("modal-summary-text");
  const listEl = document.getElementById("modal-file-list");

  // Run dry-run on backend first
  const res = await fetch("/api/clean", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: selectedItems, mode, dry_run: true }),
  });
  const dry = await res.json();

  if (mode === "recycle") {
    titleEl.textContent = "♻️ ENVIAR A PAPELERA DE RECICLAJE // DRY-RUN";
    summaryEl.innerHTML = `
      <strong>Modo Seguro (Papelera de Windows):</strong> Se van a mover <strong>${dry.cleaned_count} ítems</strong> liberando <strong>${dry.freed_human}</strong>.<br/>
      Si necesitás recuperar alguno, podés restaurarlo desde la Papelera de Reciclaje.
    `;
  } else {
    titleEl.textContent = "🔥 BORRADO PERMANENTE DIRECTO // ¡ATENCIÓN!";
    summaryEl.innerHTML = `
      <strong style="color:#ff4d4d;">¡CUIDADO! Borrado Permanente sin pasar por la Papelera:</strong><br/>
      Se van a eliminar definitivamente <strong>${dry.cleaned_count} ítems</strong> (<strong>${dry.freed_human}</strong>). Ideal para modelos pesados que no entran en la Papelera.
    `;
  }

  listEl.innerHTML = selectedItems
    .map((it) => `<div>• [${escapeHtml(it.size_human)}] ${escapeHtml(it.name)} <br/><span style="color:#7d98bf">  ${escapeHtml(it.path)}</span></div>`)
    .join("<hr style='border:0;border-top:1px solid #1c2840;margin:4px 0;'/>");

  modal.classList.remove("hidden");
}

function closeCleanModal() {
  document.getElementById("clean-modal").classList.add("hidden");
}

async function confirmAndExecuteClean() {
  const selectedItems = state.allItems.filter((i) => state.selectedIds.has(i.id) && i.safety !== "red");
  if (selectedItems.length === 0) {
    closeCleanModal();
    return;
  }

  const btn = document.getElementById("btn-modal-confirm");
  btn.disabled = true;
  btn.textContent = "PROCESANDO...";

  try {
    const res = await fetch("/api/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: selectedItems,
        mode: state.pendingCleanMode,
        dry_run: false,
      }),
    });
    const out = await res.json();
    closeCleanModal();

    alert(
      `¡Limpieza completada!\n\n` +
      `• Ítems procesados: ${out.cleaned_count}\n` +
      `• Espacio liberado: ${out.freed_human}\n` +
      (out.errors && out.errors.length ? `• Avisos/Errores: ${out.errors.length}` : "")
    );

    // Re-scan to refresh totals
    runSmartScan();
  } catch (err) {
    alert(`Error durante la limpieza: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "✅ CONFIRMAR Y EJECUTAR";
  }
}
