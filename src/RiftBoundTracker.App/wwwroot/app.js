const RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Legendary"];
const DOMAIN_COLOR = {
  Fury: "var(--c-fury)", Calm: "var(--c-calm)", Order: "var(--c-order)",
  Mind: "var(--c-mind)", Body: "var(--c-body)", Chaos: "var(--c-chaos)",
  Colorless: "var(--c-colorless)"
};
// Simplified stand-ins for each domain's printed symbol (a spiky burst for Fury, a teardrop for
// Calm, an arrowhead for Mind, linked diamonds for Body, a four-blade pinwheel for Chaos, a
// swept wing for Order) — colored via currentColor so DOMAIN_COLOR still drives the hue.
const DOMAIN_ICON = {
  Fury: '<svg viewBox="0 0 16 16" width="12" height="12"><polygon points="8,0 9.8,6.2 16,8 9.8,9.8 8,16 6.2,9.8 0,8 6.2,6.2" fill="currentColor"/></svg>',
  Calm: '<svg viewBox="0 0 16 16" width="12" height="12"><path d="M8 1 C11.5 4.5 13.5 7.5 13.5 10 A5.5 5.5 0 0 1 2.5 10 C2.5 7.5 4.5 4.5 8 1 Z" fill="currentColor"/></svg>',
  Mind: '<svg viewBox="0 0 16 16" width="12" height="12"><path d="M1 8 L9.5 1 L7.5 8 L9.5 15 Z" fill="currentColor"/></svg>',
  Body: '<svg viewBox="0 0 16 16" width="12" height="12"><polygon points="4.5,8 6.8,5 9,8 6.8,11" fill="currentColor"/><polygon points="9,8 11.3,5 13.5,8 11.3,11" fill="currentColor"/></svg>',
  Chaos: '<svg viewBox="0 0 16 16" width="12" height="12"><g fill="currentColor"><path d="M8 8 Q8 2.5 3 2.5 Q3 7 8 8 Z"/><path d="M8 8 Q8 2.5 3 2.5 Q3 7 8 8 Z" transform="rotate(90 8 8)"/><path d="M8 8 Q8 2.5 3 2.5 Q3 7 8 8 Z" transform="rotate(180 8 8)"/><path d="M8 8 Q8 2.5 3 2.5 Q3 7 8 8 Z" transform="rotate(270 8 8)"/></g></svg>',
  Order: '<svg viewBox="0 0 16 16" width="12" height="12"><path d="M8 3 C6 3.5 2.5 5.5 1 9.5 C4 8.5 6.2 8.5 8 10.5 C9.8 8.5 12 8.5 15 9.5 C13.5 5.5 10 3.5 8 3 Z" fill="currentColor"/></svg>',
};
const RARITY_COLOR = {
  Common: "var(--text-faint)", Uncommon: "var(--c-body)", Rare: "var(--c-calm)",
  Epic: "var(--c-mind)", Legendary: "var(--c-order)"
};

const state = {
  setId: null,
  owned: "all",
  search: "",
  type: null,
  rarity: null,
  domain: null,
  sort: "num-asc",
};

let cardsById = new Map();

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let message = `${path} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body?.error) message = body.error;
    } catch { /* not a JSON error body — keep the generic message */ }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  return p.toString();
}

// The actual printed collector code (e.g. "R01", "007A") when known — falls back to the bare
// zero-padded number for cards with a plain code (collectorCode is always populated by the
// server, but this stays defensive against any stale cached card object).
function cardCode(c) {
  return c.collectorCode || String(c.collectorNumber).padStart(3, "0");
}

async function loadSets() {
  const sets = await api("/api/sets");
  const el = document.getElementById("setTabs");
  el.innerHTML = "";

  const totalOwned = sets.reduce((n, s) => n + s.owned, 0);
  const totalAll = sets.reduce((n, s) => n + s.total, 0);

  const allTab = document.createElement("button");
  allTab.type = "button";
  allTab.className = "set-tab" + (state.setId === null ? " active" : "");
  allTab.innerHTML = `<span class="name">All sets</span><span class="n">${totalOwned}/${totalAll}</span>`;
  allTab.addEventListener("click", () => { state.setId = null; onSetChanged(); });
  el.appendChild(allTab);

  sets.forEach(s => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "set-tab" + (state.setId === s.setId ? " active" : "");
    tab.title = s.setLabel || s.setId;
    tab.innerHTML = `<span class="name">${s.setId}</span><span class="n">${s.owned}/${s.total}</span>`;
    tab.addEventListener("click", () => { state.setId = s.setId; onSetChanged(); });
    el.appendChild(tab);
  });

  if (sets.length === 0) {
    const hint = document.createElement("div");
    hint.className = "set-tabs-hint";
    hint.textContent = "Catalog is syncing — sets will appear here as they finish.";
    el.appendChild(hint);
  }
}

function onSetChanged() {
  loadSets();
  loadFacets();
  loadStats();
  loadGrid();
}

function buildChips(containerId, values, current, onPick, colorMap, iconMap) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  values.forEach(v => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.setAttribute("aria-pressed", String(v === current));
    if (iconMap && iconMap[v]) {
      const icon = document.createElement("span");
      icon.className = "dot dot-icon";
      icon.style.color = colorMap ? colorMap[v] : "var(--text-faint)";
      icon.innerHTML = iconMap[v];
      btn.appendChild(icon);
    } else if (colorMap) {
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = colorMap[v] || "var(--text-faint)";
      btn.appendChild(dot);
    }
    btn.appendChild(document.createTextNode(v));
    btn.addEventListener("click", () => onPick(v === current ? null : v));
    el.appendChild(btn);
  });
}

async function loadFacets() {
  const cards = await api(`/api/cards?${qs({ setId: state.setId })}`);
  const types = [...new Set(cards.map(c => c.type))].sort();
  const rarities = RARITY_ORDER.filter(r => cards.some(c => c.rarity === r));
  const domains = [...new Set(cards.flatMap(c => c.domains))].sort();

  buildChips("typeChips", types, state.type, v => { state.type = v; loadGrid(); });
  buildChips("rarityChips", rarities, state.rarity, v => { state.rarity = v; loadGrid(); });
  buildChips("domainChips", domains, state.domain, v => { state.domain = v; loadGrid(); }, DOMAIN_COLOR, DOMAIN_ICON);
}

async function loadStats() {
  const stats = await api(`/api/stats?${qs({ setId: state.setId })}`);
  document.getElementById("ownedLabel").textContent = stats.owned;
  document.getElementById("totalLabel").textContent = stats.total;
  const pct = stats.total ? Math.round((stats.owned / stats.total) * 100) : 0;
  document.getElementById("pctLabel").textContent = pct + "%";
  const ring = document.getElementById("ringProgress");
  const circumference = 2 * Math.PI * 16;
  ring.style.strokeDasharray = circumference;
  ring.style.strokeDashoffset = circumference * (1 - pct / 100);
}

async function loadGrid() {
  const cards = await api(`/api/cards?${qs({
    setId: state.setId, search: state.search, type: state.type,
    rarity: state.rarity, domain: state.domain, owned: state.owned, sort: state.sort,
  })}`);
  cardsById = new Map(cards.map(c => [c.id, c]));
  renderGrid(cards);
}

function renderGrid(cards) {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  document.getElementById("emptyState").hidden = cards.length > 0;
  document.getElementById("resultCount").textContent = cards.length;

  cards.forEach(c => grid.appendChild(renderCardTile(c)));
}

function renderCardTile(c) {
  const card = document.createElement("div");
  card.className = "card" + (c.ownedCount <= 0 ? " missing" : "") + (c.orientation === "landscape" ? " is-landscape" : "");

  const art = document.createElement("div");
  art.className = "art";

  const bar = document.createElement("div");
  bar.className = "domain-bar";
  (c.domains.length ? c.domains : ["Colorless"]).forEach(d => {
    const s = document.createElement("span");
    s.style.background = DOMAIN_COLOR[d] || "var(--c-colorless)";
    bar.appendChild(s);
  });
  art.appendChild(bar);

  const img = document.createElement("img");
  img.src = c.localImagePath || "";
  img.alt = c.name;
  img.loading = "lazy";
  art.appendChild(img);

  if (c.ownedCount <= 0) {
    const rib = document.createElement("div");
    rib.className = "ribbon";
    rib.textContent = "MISSING";
    art.appendChild(rib);
  } else {
    const badge = document.createElement("div");
    badge.className = "qty-badge";
    badge.textContent = "×" + c.ownedCount;
    art.appendChild(badge);
  }
  card.appendChild(art);

  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML = `
    <h4>${c.name}</h4>
    <div class="meta">
      <span class="rarity"><span class="dot" style="background:${RARITY_COLOR[c.rarity] || "var(--text-faint)"}"></span>${c.rarity}</span>
      <span class="num">${c.setId}·${cardCode(c)}</span>
    </div>
  `;
  const stepper = document.createElement("div");
  stepper.className = "stepper";
  stepper.innerHTML = `<button data-act="dec" aria-label="Remove copy">−</button><span class="n">${c.ownedCount}</span><button data-act="inc" aria-label="Add copy">+</button>`;
  stepper.querySelector('[data-act="dec"]').addEventListener("click", e => { e.stopPropagation(); setOwned(c.id, Math.max(0, c.ownedCount - 1)); });
  stepper.querySelector('[data-act="inc"]').addEventListener("click", e => { e.stopPropagation(); setOwned(c.id, c.ownedCount + 1); });
  body.appendChild(stepper);
  card.appendChild(body);

  card.addEventListener("click", () => openCardDetail(c.id));

  return card;
}

async function setOwned(cardId, owned) {
  const updated = await api(`/api/collection/${cardId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owned }),
  });
  cardsById.set(cardId, updated);
  renderGrid([...cardsById.values()]);
  loadStats();
  loadSets();
}

document.getElementById("ownedToggle").addEventListener("click", e => {
  const btn = e.target.closest("button[data-owned]");
  if (!btn) return;
  [...e.currentTarget.children].forEach(b => b.setAttribute("aria-pressed", "false"));
  btn.setAttribute("aria-pressed", "true");
  state.owned = btn.dataset.owned;
  loadGrid();
});

let searchTimer;
document.getElementById("search").addEventListener("input", e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.search = e.target.value.trim(); loadGrid(); }, 250);
});

document.getElementById("sort").addEventListener("change", e => { state.sort = e.target.value; loadGrid(); });

/* ---------------- Catalog sync status ---------------- */
const catalogStatusBody = document.getElementById("catalogStatusBody");
const refreshCatalogBtn = document.getElementById("refreshCatalogBtn");
let catalogPollTimer = null;

function formatRelativeTime(iso) {
  if (!iso) return null;
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

async function pollCatalogStatus() {
  let status;
  try {
    status = await api("/api/sync/status");
  } catch (err) {
    catalogStatusBody.textContent = "Couldn't load sync status: " + err.message;
    return;
  }

  if (status.running) {
    catalogStatusBody.innerHTML = `
      <span class="available">Syncing ${escapeHtml(status.currentSet || "")}…</span>
      <div class="notes">${status.setsDone}/${status.setsTotal} sets · ${status.cardsDone} cards</div>
    `;
    refreshCatalogBtn.disabled = true;
    if (!catalogPollTimer) catalogPollTimer = setInterval(pollCatalogStatus, 2000);
  } else {
    const relative = formatRelativeTime(status.lastSyncedAt);
    catalogStatusBody.textContent = status.lastSyncedAt
      ? `${status.totalCards} cards across ${status.totalSets} sets — synced ${relative}`
      : "Not synced yet.";
    refreshCatalogBtn.disabled = false;
    if (catalogPollTimer) { clearInterval(catalogPollTimer); catalogPollTimer = null; }
    onSetChanged();
  }
}

refreshCatalogBtn.addEventListener("click", async () => {
  refreshCatalogBtn.disabled = true;
  try {
    await api("/api/sync/refresh", { method: "POST" });
  } catch (err) {
    catalogStatusBody.textContent = "Refresh failed: " + err.message;
    refreshCatalogBtn.disabled = false;
    return;
  }
  pollCatalogStatus();
});

pollCatalogStatus();

/* ---------------- Quick add by ID ---------------- */
const quickAddInput = document.getElementById("quickAddInput");
const quickAddBtn = document.getElementById("quickAddBtn");

// "code" is the printed collector code, letters and all (e.g. "45", "R01", "007A") — matched on
// the server against the actual card code rather than just the bare number, so set+code entries
// like "VEN-R01" resolve to the right card instead of colliding with "VEN-001". A bare code with
// no set token searches every set already (when no set tab is active it's forwarded as-is with no
// setId filter) — "*-045"/"* 045" is an explicit override to search every set even while a
// specific set tab IS active, surfacing every "045" across the whole catalog as ambiguous matches.
function parseQuickAddInput(raw) {
  const cleaned = raw.trim();
  const withSet = /^([A-Za-z]{2,4}|\*)[\s-]*([A-Za-z]?\d{1,3}[A-Za-z]?)$/.exec(cleaned);
  if (withSet) return { setId: withSet[1] === "*" ? null : withSet[1].toUpperCase(), code: withSet[2].toUpperCase() };
  const bare = /^([A-Za-z]?\d{1,3}[A-Za-z]?)$/.exec(cleaned);
  if (bare) return { setId: state.setId, code: bare[1].toUpperCase() };
  return null;
}

async function quickAdd() {
  const parsed = parseQuickAddInput(quickAddInput.value);
  if (!parsed) {
    alert('Type a card code (e.g. "45" or "R01") or set + code (e.g. "OGN-045" or "VEN-R01").');
    return;
  }

  quickAddBtn.disabled = true;
  try {
    const cards = await api(`/api/cards/lookup?${qs({ setId: parsed.setId, code: parsed.code })}`);
    if (cards.length === 1) {
      await setOwned(cards[0].id, (cards[0].ownedCount || 0) + 1);
      quickAddInput.value = "";
      quickAddBtn.textContent = "Added ✓";
      setTimeout(() => { quickAddBtn.textContent = "Add"; }, 1200);
    } else if (cards.length > 1) {
      resetScanSheet();
      overlay.hidden = false;
      manualNumber.value = parsed.code;
      if (parsed.setId) manualSetCode.value = parsed.setId;
      document.getElementById("manualLookupBtn").click();
    } else {
      alert(parsed.setId
        ? `No card ${parsed.code} found in ${parsed.setId}.`
        : `No card ${parsed.code} in any synced set.`);
    }
  } catch (err) {
    alert("Quick add failed: " + err.message);
  } finally {
    quickAddBtn.disabled = false;
  }
}

quickAddBtn.addEventListener("click", quickAdd);
quickAddInput.addEventListener("keydown", e => { if (e.key === "Enter") quickAdd(); });

/* ---------------- Mass add ---------------- */
const massAddOverlay = document.getElementById("massAddOverlay");
const massAddInput = document.getElementById("massAddInput");
const massAddPreviewBtn = document.getElementById("massAddPreviewBtn");
const massAddConfirmBtn = document.getElementById("massAddConfirmBtn");
const massAddResults = document.getElementById("massAddResults");

let massAddEntries = [];

document.getElementById("openMassAdd").addEventListener("click", () => {
  resetMassAdd();
  massAddOverlay.hidden = false;
  massAddInput.focus();
});
document.getElementById("closeMassAdd").addEventListener("click", () => { massAddOverlay.hidden = true; });
massAddOverlay.addEventListener("click", e => { if (e.target === massAddOverlay) massAddOverlay.hidden = true; });

function resetMassAdd() {
  massAddInput.value = "";
  massAddResults.innerHTML = "";
  massAddEntries = [];
  massAddConfirmBtn.hidden = true;
  massAddPreviewBtn.hidden = false;
  massAddPreviewBtn.disabled = false;
}

// Editing the list after a preview invalidates it — force a fresh preview rather than confirming
// against stale lookups.
massAddInput.addEventListener("input", () => {
  massAddResults.innerHTML = "";
  massAddEntries = [];
  massAddConfirmBtn.hidden = true;
  massAddPreviewBtn.hidden = false;
});

function parseMassAddLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return null;

  const qtyMatch = /[xX](\d+)\s*$/.exec(trimmed);
  const qty = qtyMatch ? parseInt(qtyMatch[1], 10) : 1;
  const base = qtyMatch ? trimmed.slice(0, qtyMatch.index).trim() : trimmed;

  const parsed = parseQuickAddInput(base);
  return parsed ? { raw: trimmed, setId: parsed.setId, code: parsed.code, qty } : { raw: trimmed, error: true };
}

async function previewMassAdd() {
  const lines = massAddInput.value
    .split(/\r?\n/)
    .flatMap(line => line.split(","))
    .map(parseMassAddLine)
    .filter(Boolean);
  if (lines.length === 0) return;

  massAddPreviewBtn.disabled = true;
  massAddResults.innerHTML = "";

  for (const entry of lines) {
    if (entry.error) {
      entry.status = "error";
      entry.message = `couldn't parse (try "OGN-045" or "45")`;
    } else {
      try {
        const cards = await api(`/api/cards/lookup?${qs({ setId: entry.setId, code: entry.code })}`);
        if (cards.length === 1) {
          entry.status = "ok";
          entry.card = cards[0];
          entry.selected = true;
        } else if (cards.length > 1) {
          // Genuinely ambiguous (e.g. "001" matches a card in every set) — list every match as
          // its own pickable row instead of dead-ending with an error telling the user to retype.
          entry.status = "ambiguous";
          entry.candidates = cards;
          entry.selectedIds = new Set();
        } else {
          entry.status = "error";
          entry.message = "no matching card found";
        }
      } catch (err) {
        entry.status = "error";
        entry.message = err.message;
      }
    }
  }

  massAddEntries = lines;
  massAddPreviewBtn.disabled = false;
  renderMassAddPreview();
}

function renderMassAddPreview() {
  massAddResults.innerHTML = "";

  massAddEntries.forEach(entry => {
    if (entry.status === "ok") {
      const row = document.createElement("label");
      row.className = "mass-add-row mass-add-ok";
      const newCount = (entry.card.ownedCount || 0) + entry.qty;
      row.innerHTML = `<input type="checkbox" ${entry.selected ? "checked" : ""} />
        <span>${entry.raw} — ${entry.card.name} (own ${entry.card.ownedCount || 0} → ${newCount})</span>`;
      row.querySelector("input").addEventListener("change", e => {
        entry.selected = e.target.checked;
        updateMassAddConfirmButton();
      });
      entry.el = row;
      massAddResults.appendChild(row);
    } else if (entry.status === "ambiguous") {
      const group = document.createElement("div");
      group.className = "mass-add-group";

      const header = document.createElement("div");
      header.className = "mass-add-row mass-add-group-header";
      header.textContent = `${entry.raw} — matches ${entry.candidates.length} cards, pick the ones you mean:`;
      group.appendChild(header);

      entry.candidateEls = new Map();
      entry.candidates.forEach(card => {
        const sub = document.createElement("label");
        sub.className = "mass-add-row mass-add-subrow";
        const newCount = (card.ownedCount || 0) + entry.qty;
        sub.innerHTML = `<input type="checkbox" />
          <span>${card.setId}·${cardCode(card)} — ${card.name} (own ${card.ownedCount || 0} → ${newCount})</span>`;
        sub.querySelector("input").addEventListener("change", e => {
          if (e.target.checked) entry.selectedIds.add(card.id);
          else entry.selectedIds.delete(card.id);
          updateMassAddConfirmButton();
        });
        entry.candidateEls.set(card.id, sub);
        group.appendChild(sub);
      });

      entry.el = group;
      massAddResults.appendChild(group);
    } else {
      const row = document.createElement("div");
      row.className = "mass-add-row mass-add-fail";
      row.textContent = `${entry.raw} — ${entry.message}`;
      entry.el = row;
      massAddResults.appendChild(row);
    }
  });

  massAddConfirmBtn.hidden = !massAddEntries.some(e => e.status === "ok" || e.status === "ambiguous");
  updateMassAddConfirmButton();
}

function countMassAddSelected() {
  let n = 0;
  for (const entry of massAddEntries) {
    if (entry.status === "ok" && entry.selected) n++;
    if (entry.status === "ambiguous") n += entry.selectedIds.size;
  }
  return n;
}

function updateMassAddConfirmButton() {
  const n = countMassAddSelected();
  massAddConfirmBtn.textContent = n ? `Add ${n} card${n === 1 ? "" : "s"}` : "Add";
  massAddConfirmBtn.disabled = n === 0;
}

async function confirmMassAdd() {
  if (countMassAddSelected() === 0) return;

  massAddConfirmBtn.disabled = true;
  massAddPreviewBtn.hidden = true;

  for (const entry of massAddEntries) {
    if (entry.status === "ok" && entry.selected) {
      try {
        await setOwned(entry.card.id, (entry.card.ownedCount || 0) + entry.qty);
        entry.el.querySelector("span").textContent = `${entry.raw} — added ${entry.qty} × ${entry.card.name} ✓`;
        entry.el.classList.remove("mass-add-ok");
        entry.el.classList.add("mass-add-added");
        entry.el.querySelector("input")?.remove();
      } catch (err) {
        entry.el.querySelector("span").textContent = `${entry.raw} — error: ${err.message}`;
        entry.el.classList.add("mass-add-fail");
      }
    } else if (entry.status === "ambiguous") {
      for (const card of entry.candidates) {
        if (!entry.selectedIds.has(card.id)) continue;
        const sub = entry.candidateEls.get(card.id);
        try {
          await setOwned(card.id, (card.ownedCount || 0) + entry.qty);
          sub.querySelector("span").textContent = `${card.setId}·${cardCode(card)} — added ${entry.qty} × ${card.name} ✓`;
          sub.classList.remove("mass-add-subrow");
          sub.classList.add("mass-add-added");
          sub.querySelector("input")?.remove();
        } catch (err) {
          sub.querySelector("span").textContent = `${card.setId}·${cardCode(card)} — error: ${err.message}`;
          sub.classList.add("mass-add-fail");
        }
      }
    }
  }

  massAddConfirmBtn.hidden = true;
  loadGrid();
  loadFacets();
}

massAddPreviewBtn.addEventListener("click", previewMassAdd);
massAddConfirmBtn.addEventListener("click", confirmMassAdd);

/* ---------------- Scan overlay ---------------- */
const overlay = document.getElementById("scanOverlay");
const scanFile = document.getElementById("scanFile");
const scanFileExisting = document.getElementById("scanFileExisting");
const scanPreview = document.getElementById("scanPreview");
const scanPreviewImg = document.getElementById("scanPreviewImg");
const scanStatus = document.getElementById("scanStatus");
const matchList = document.getElementById("matchList");
const ocrDebug = document.getElementById("ocrDebug");
const manualNumber = document.getElementById("manualNumber");
const manualSetCode = document.getElementById("manualSetCode");

document.getElementById("openScan").addEventListener("click", () => {
  resetScanSheet();
  overlay.hidden = false;
});
document.getElementById("closeScan").addEventListener("click", () => { stopLiveScan(); overlay.hidden = true; });
overlay.addEventListener("click", e => { if (e.target === overlay) { stopLiveScan(); overlay.hidden = true; } });

function resetScanSheet() {
  stopLiveScan();
  resetTabs();
  scanFile.value = "";
  scanFileExisting.value = "";
  scanPreview.hidden = true;
  scanPreviewImg.style.display = "";
  matchList.innerHTML = "";
  ocrDebug.hidden = true;
  ocrDebug.textContent = "";
  manualNumber.value = "";
  manualSetCode.value = "";
}

// Best-effort client-side guess used only to pre-fill the manual correction fields when a scan
// comes back with no confident match — not authoritative, the server does the real parsing.
function guessFromOcrText(text) {
  if (!text) return { code: null, setCode: null };
  const codeMatch = /([A-Za-z]?\d{1,3}[A-Za-z]?)\s*[\/\\|]?\s*\d{0,3}/.exec(text);
  const setMatch = /\b([A-Z]{2,4})\b/.exec(text);
  return {
    code: codeMatch ? codeMatch[1].toUpperCase() : null,
    setCode: setMatch ? setMatch[1] : null,
  };
}

async function handleScanFile(file) {
  if (!file) return;

  scanPreview.hidden = false;
  scanPreviewImg.style.display = "";
  scanPreviewImg.src = URL.createObjectURL(file);
  scanStatus.textContent = "Reading card…";
  matchList.innerHTML = "";
  ocrDebug.hidden = true;

  const form = new FormData();
  form.append("photo", file);
  if (state.setId) form.append("setId", state.setId);

  try {
    const result = await api("/api/scan", { method: "POST", body: form });
    renderScanResult(result);
  } catch (err) {
    scanStatus.textContent = "Scan failed: " + err.message;
  }
}

scanFile.addEventListener("change", () => handleScanFile(scanFile.files[0]));
scanFileExisting.addEventListener("change", () => handleScanFile(scanFileExisting.files[0]));

function renderScanResult(result) {
  const cleanOcr = (result.debugOcrText || "").trim();
  if (result.method !== "ocr" && cleanOcr) {
    ocrDebug.hidden = false;
    ocrDebug.textContent = "What we read off the photo:\n" + cleanOcr;
  } else {
    ocrDebug.hidden = true;
  }

  if (result.matches.length === 0) {
    scanStatus.textContent = "No match found. Try a closer, well-lit, right-side-up shot of the corner — or adjust the number/set below.";
    const guess = guessFromOcrText(cleanOcr);
    if (guess.code && !manualNumber.value) manualNumber.value = guess.code;
    if (guess.setCode && !manualSetCode.value) manualSetCode.value = guess.setCode;
    return;
  }

  scanStatus.textContent = result.method === "ocr" || result.method === "manual"
    ? "Matched by card number:"
    : result.method === "ocr-ambiguous"
      ? "Number matched more than one card — pick the right one:"
      : "Couldn't read the number confidently — closest art matches (verify before adding):";

  matchList.innerHTML = "";
  result.matches.forEach(m => {
    const row = document.createElement("div");
    row.className = "match-row";
    row.innerHTML = `
      <img src="${m.card.localImagePath || ""}" alt="${m.card.name}" />
      <div class="info">
        <h4>${m.card.name}</h4>
        <div class="meta"><span class="num">${m.card.setId}·${cardCode(m.card)}</span></div>
      </div>
      <div class="conf">${m.confidence}%</div>
    `;
    row.addEventListener("click", async () => {
      scanStatus.textContent = `Adding ${m.card.name}…`;
      await setOwned(m.card.id, (m.card.ownedCount || 0) + 1);
      scanStatus.textContent = `✓ Added ${m.card.name}. Scan another, or close.`;
      matchList.innerHTML = "";
      setTimeout(resetScanSheet, 900);
    });
    matchList.appendChild(row);
  });
}

document.getElementById("manualLookupBtn").addEventListener("click", async () => {
  const code = manualNumber.value.trim().toUpperCase();
  if (!code) return;
  const setCode = manualSetCode.value.trim().toUpperCase() || state.setId;

  scanPreview.hidden = false;
  scanPreviewImg.style.display = "none";
  scanPreviewImg.removeAttribute("src");
  ocrDebug.hidden = true;
  matchList.innerHTML = "";
  scanStatus.textContent = "Looking up…";

  try {
    const cards = await api(`/api/cards/lookup?${qs({ setId: setCode, code })}`);
    renderScanResult({
      method: cards.length === 1 ? "manual" : cards.length > 1 ? "ocr-ambiguous" : "manual-none",
      matches: cards.map(card => ({ card, confidence: 100 })),
      debugOcrText: "",
    });
    if (cards.length === 0) {
      scanStatus.textContent = setCode
        ? `No card ${code} found in ${setCode}. Try clearing the set field or check the number.`
        : `No card ${code} in the catalog.`;
    }
  } catch (err) {
    scanStatus.textContent = "Lookup failed: " + err.message;
  }
});

/* ---------------- Scan tabs ---------------- */
const tabButtons = [...document.querySelectorAll(".tab-btn")];
const tabPanels = {
  live: document.getElementById("tabPanelLive"),
  photo: document.getElementById("tabPanelPhoto"),
  upload: document.getElementById("tabPanelUpload"),
};
let activeTab = "live";

tabButtons.forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

function switchTab(tab) {
  if (tab === activeTab) return;
  if (activeTab === "live") stopLiveScan();

  activeTab = tab;
  tabButtons.forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.tab === tab)));
  for (const [name, panel] of Object.entries(tabPanels)) panel.hidden = name !== tab;
}

function resetTabs() {
  activeTab = "live";
  tabButtons.forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.tab === "live")));
  for (const [name, panel] of Object.entries(tabPanels)) panel.hidden = name !== "live";
}

/* ---------------- Live camera scan ---------------- */
const liveScanBtn = document.getElementById("liveScanBtn");
const liveScanView = document.getElementById("liveScanView");
const liveVideo = document.getElementById("liveVideo");
const liveStatus = document.getElementById("liveStatus");
const liveHit = document.getElementById("liveHit");
const liveReadoutText = document.getElementById("liveReadoutText");
const liveCanvas = document.createElement("canvas");

let liveStream = null;
let liveInterval = null;
let liveInFlight = false;
let liveHitPending = false;

// Temporal voting: a single fast/low-res frame is unreliable, but the live loop fires roughly
// every 800ms while pointed at the same card, so require a few consecutive frames to agree on the
// same card before surfacing a match — trades a little latency for far fewer wrong hits.
const LIVE_VOTE_THRESHOLD = 3;
let liveVoteKey = null;
let liveVoteCount = 0;

liveScanBtn.addEventListener("click", startLiveScan);

async function startLiveScan() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    await warnInsecureContext();
    return;
  }

  try {
    liveStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
  } catch (err) {
    alert("Couldn't access the camera: " + err.message);
    return;
  }

  liveVideo.srcObject = liveStream;
  liveScanBtn.hidden = true;
  liveScanView.hidden = false;
  liveHit.hidden = true;
  liveHitPending = false;
  liveVoteKey = null;
  liveVoteCount = 0;
  liveReadoutText.textContent = "—";
  setLiveStatus("Point the camera at a card…", true);

  liveInterval = setInterval(captureLiveFrame, 800);
}

function stopLiveScan() {
  if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
  if (liveStream) { liveStream.getTracks().forEach(t => t.stop()); liveStream = null; }
  liveVideo.srcObject = null;
  liveHitPending = false;
  liveVoteKey = null;
  liveVoteCount = 0;
  liveHit.hidden = true;
  liveHit.innerHTML = "";
  liveReadoutText.textContent = "—";
  liveScanView.hidden = true;
  liveScanBtn.hidden = false;
}

function cleanOcrSnippet(text) {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "(nothing legible yet)";
  return cleaned.length > 50 ? cleaned.slice(0, 50) + "…" : cleaned;
}

function setLiveStatus(text, pulsing) {
  liveStatus.innerHTML = (pulsing ? '<span class="pulse"></span>' : "") + text;
}

async function captureLiveFrame() {
  if (liveInFlight || liveHitPending || liveVideo.readyState < 2) return;

  liveInFlight = true;
  const maxDim = 900;
  const scale = Math.min(1, maxDim / Math.max(liveVideo.videoWidth, liveVideo.videoHeight));
  liveCanvas.width = Math.round(liveVideo.videoWidth * scale);
  liveCanvas.height = Math.round(liveVideo.videoHeight * scale);
  liveCanvas.getContext("2d").drawImage(liveVideo, 0, 0, liveCanvas.width, liveCanvas.height);

  liveCanvas.toBlob(async blob => {
    if (!blob) { liveInFlight = false; return; }
    const form = new FormData();
    form.append("photo", blob, "frame.jpg");
    form.append("fast", "true");
    if (state.setId) form.append("setId", state.setId);

    try {
      const result = await api("/api/scan", { method: "POST", body: form });
      handleLiveResult(result);
    } catch {
      // transient network hiccup — just try again next tick
    } finally {
      liveInFlight = false;
    }
  }, "image/jpeg", 0.85);
}

function handleLiveResult(result) {
  liveReadoutText.textContent = cleanOcrSnippet(result.debugOcrText);

  if (liveHitPending) return;

  const isCandidate = ["ocr", "manual"].includes(result.method) && result.matches.length === 1;
  const key = isCandidate ? result.matches[0].card.id : null;

  if (key && key === liveVoteKey) {
    liveVoteCount++;
  } else {
    liveVoteKey = key;
    liveVoteCount = key ? 1 : 0;
  }

  if (!key || liveVoteCount < LIVE_VOTE_THRESHOLD) {
    setLiveStatus("Scanning…", true);
    return;
  }

  const match = result.matches[0];
  liveHitPending = true;
  liveVoteKey = null;
  liveVoteCount = 0;
  setLiveStatus("Found a match", false);
  liveHit.hidden = false;
  liveHit.innerHTML = `
    <img src="${match.card.localImagePath || ""}" alt="${match.card.name}" />
    <div class="info">
      <h4>${match.card.name}</h4>
      <div class="num">${match.card.setId}·${cardCode(match.card)} — own ${match.card.ownedCount}</div>
    </div>
    <button class="btn primary" id="liveAddBtn">Add +1</button>
  `;
  document.getElementById("liveAddBtn").addEventListener("click", async () => {
    await setOwned(match.card.id, (match.card.ownedCount || 0) + 1);
    resumeLiveScan(`Added ${match.card.name}`);
  });

  // If left untouched, resume scanning on its own so a stale suggestion doesn't block the next card.
  setTimeout(() => { if (liveHitPending) resumeLiveScan(); }, 4500);
}

function resumeLiveScan(flashMessage) {
  liveHitPending = false;
  liveHit.hidden = true;
  liveHit.innerHTML = "";
  setLiveStatus(flashMessage ? `${flashMessage} — scanning…` : "Point the camera at a card…", true);
}

async function warnInsecureContext() {
  try {
    const info = await api("/api/server-info");
    const httpsUrl = `https://${location.hostname}:${info.httpsPort}`;
    alert(`Live camera needs a secure (HTTPS) connection.\n\nOpen this app at:\n${httpsUrl}\n\n(Your browser will warn about the self-signed certificate the first time — tap Advanced, then Proceed.)`);
  } catch {
    alert("Live camera needs a secure (HTTPS) connection. Try opening this app over https:// instead.");
  }
}

/* ---------------- Update check ---------------- */
const updateStatus = document.getElementById("updateStatus");
const checkUpdateBtn = document.getElementById("checkUpdateBtn");
const currentVersionEl = document.getElementById("currentVersion");

checkUpdateBtn.addEventListener("click", checkForUpdate);

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Keyed by the keyword text lowercased with any trailing " N" stripped (so "Assault 2" and
// "Assault" share a style). Colors reuse the app's existing domain palette rather than inventing
// a second color language, grouped loosely by what each keyword does (offense, defense, growth…).
const KEYWORD_STYLE = {
  empower: "kw-amber", empowered: "kw-amber", level: "kw-amber",
  deflect: "kw-blue", tank: "kw-blue",
  assault: "kw-fury", burn: "kw-fury", hunt: "kw-fury",
  ambush: "kw-mind", flow: "kw-mind",
  recycle: "kw-body",
  exhaust: "kw-gray", tap: "kw-gray",
};
const ICON_STYLE = { energy: "icon-amber", might: "icon-fury", power: "icon-order", exhaust: "icon-gray" };

// Small shape glyphs standing in for the printed symbols — a diamond for Energy, a sword for
// Might, a hexagon (Riftbound's rune/domain shape) for Power and Rune costs, a rotate arrow for
// Exhaust — colored via currentColor so the surrounding badge class controls the color.
const ICON_SVG = {
  energy: '<svg viewBox="0 0 16 16" width="11" height="11"><polygon points="8,1 15,8 8,15 1,8" fill="currentColor"/></svg>',
  might: '<svg viewBox="0 0 16 16" width="11" height="11"><path d="M2.5 13.5 9 7M11 2l3 3-2 2-3-3zM7.5 8.5l2 2-1.5 1.5-2-2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  power: '<svg viewBox="0 0 16 16" width="11" height="11"><polygon points="8,1 14.5,4.6 14.5,11.4 8,15 1.5,11.4 1.5,4.6" fill="currentColor"/></svg>',
  rune: '<svg viewBox="0 0 16 16" width="11" height="11"><polygon points="8,1 14.5,4.6 14.5,11.4 8,15 1.5,11.4 1.5,4.6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
  exhaust: '<svg viewBox="0 0 16 16" width="11" height="11"><path d="M13 3.2A6 6 0 1 0 14.5 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M13.2 0.2v4h-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function keywordStyle(label) {
  const key = label.toLowerCase().replace(/\s*\d+$/, "").trim();
  return KEYWORD_STYLE[key] || "kw-default";
}
function iconStyle(kind) {
  if (kind.startsWith("rune")) return "icon-gray";
  return ICON_STYLE[kind.split(" ")[0]] || "icon-default";
}
function iconGlyph(kind) {
  const base = kind.startsWith("rune") ? "rune" : kind.split(" ")[0];
  return ICON_SVG[base] || "";
}

// Rules text from the API embeds two inline token styles the real card art renders as badges
// instead of literal text: [Keyword] tags (Empower, Deflect, Assault 2…) and :rb_xxx_n: resource/
// icon tokens (:rb_energy_5:, :rb_might:, :rb_rune_rainbow:…). Some strings also carry an
// already-HTML-escaped "&gt;" from the source data, which escapeHtml() would otherwise double
// escape into a literal "&amp;gt;". This turns that raw text into the same badge-and-pill shape
// the card itself uses, giving each keyword/icon kind its own color instead of one flat style.
function formatCardText(raw) {
  if (!raw) return "";
  const decoded = raw.replace(/&gt;/g, ">").replace(/&lt;/g, "<").replace(/&amp;/g, "&");
  const parts = decoded.split(/(\[[^\]]+\]|:rb_[a-z0-9_]+:)/gi);

  const out = [];
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    const kw = /^\[([^\]]+)\]$/.exec(part);
    if (kw) {
      // A keyword directly followed by a numbered resource token ("[Empower] :rb_energy_5:") is
      // one combined badge on the printed card ("EMPOWER 5"), not a tag plus a floating cost pill
      // — merge them when only whitespace separates the two.
      const gapIsSpace = parts[i + 1] === undefined || /^\s*$/.test(parts[i + 1]);
      const nextIcon = gapIsSpace ? /^:rb_(.+):$/i.exec(parts[i + 2] || "") : null;
      const num = nextIcon ? /^(.*)_(\d+)$/.exec(nextIcon[1]) : null;
      if (num) {
        out.push(`<span class="kw-badge ${keywordStyle(kw[1])}">${escapeHtml(kw[1])} ${escapeHtml(num[2])}</span>`);
        i += 2;
        continue;
      }
      out.push(`<span class="kw-badge ${keywordStyle(kw[1])}">${escapeHtml(kw[1])}</span>`);
      continue;
    }

    const icon = /^:rb_(.+):$/i.exec(part);
    if (icon) {
      const num = /^(.*)_(\d+)$/.exec(icon[1]);
      const kind = (num ? num[1] : icon[1]).replace(/_/g, " ");
      const glyph = iconGlyph(kind);
      // A numbered token (energy cost, etc.) shows the glyph plus the number, the way the
      // printed card shows a numeral inside its icon. An un-numbered token (might, rune…) has no
      // number to pair it with, so the glyph alone stands in for the word, with the name as a
      // hover tooltip for anyone unsure what it means.
      const label = num ? escapeHtml(num[2]) : (glyph ? "" : escapeHtml(kind));
      out.push(`<span class="icon-tok ${iconStyle(kind)}" title="${escapeHtml(kind)}">${glyph}${label}</span>`);
      continue;
    }

    out.push(escapeHtml(part));
  }
  return out.join("");
}

async function checkForUpdate() {
  checkUpdateBtn.disabled = true;
  checkUpdateBtn.textContent = "Checking…";
  updateStatus.hidden = false;
  updateStatus.innerHTML = "Checking for updates…";

  try {
    const result = await api("/api/update/check");
    currentVersionEl.textContent = result.currentVersion;

    if (!result.selfUpdateSupported) {
      updateStatus.innerHTML = `<span>${escapeHtml(result.unsupportedReason || "Self-update isn't available in this environment.")}</span>`;
    } else if (result.updateAvailable) {
      const notes = result.releaseNotes ? `<div class="notes">${escapeHtml(result.releaseNotes)}</div>` : "";
      updateStatus.innerHTML = `
        <span class="available">Update available: v${escapeHtml(result.latestVersion)}</span>
        ${notes}
        <button class="btn primary" id="applyUpdateBtn">Update & Restart</button>
      `;
      document.getElementById("applyUpdateBtn").addEventListener("click", applyUpdate);
    } else {
      updateStatus.innerHTML = `<span>You're up to date (v${escapeHtml(result.currentVersion)}).</span>`;
    }
  } catch (err) {
    updateStatus.innerHTML = `<span>Couldn't check for updates: ${escapeHtml(err.message)}</span>`;
  } finally {
    checkUpdateBtn.disabled = false;
    checkUpdateBtn.textContent = "Check for updates";
  }
}

async function applyUpdate() {
  const btn = document.getElementById("applyUpdateBtn");
  btn.disabled = true;
  btn.textContent = "Updating…";

  try {
    await api("/api/update/apply", { method: "POST" });
    updateStatus.innerHTML = `<span class="available">Downloading and installing — this can take a couple of minutes (Windows scans new files the first time). Reload this page once it's back.</span>`;
  } catch (err) {
    updateStatus.innerHTML = `<span>Update failed: ${escapeHtml(err.message)}</span>`;
  }
}

/* ---------------- Theme toggle ---------------- */
const themeToggle = document.getElementById("themeToggle");
const iconSun = themeToggle.querySelector(".icon-sun");
const iconMoon = themeToggle.querySelector(".icon-moon");

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("riftbound-theme", theme);
  const isDark = theme === "dark";
  iconSun.hidden = isDark;
  iconMoon.hidden = !isDark;
  themeToggle.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
}

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  setTheme(current === "dark" ? "light" : "dark");
});

setTheme(document.documentElement.getAttribute("data-theme"));

/* ---------------- Connection QR ---------------- */
const connectionOverlay = document.getElementById("connectionOverlay");
const connectionBody = document.getElementById("connectionBody");
const connectionStatus = document.getElementById("connectionStatus");

document.getElementById("openConnection").addEventListener("click", async () => {
  connectionOverlay.hidden = false;
  connectionStatus.hidden = false;
  connectionStatus.textContent = "Loading…";
  document.querySelectorAll(".connection-qr, .connection-hint, .connection-url-row").forEach(el => el.remove());

  try {
    const info = await api("/api/connection-info");
    if (!info.available) {
      connectionStatus.textContent = "No LAN address detected — check your network connection.";
      return;
    }

    connectionStatus.hidden = true;

    const qr = document.createElement("div");
    qr.className = "connection-qr";
    qr.innerHTML = `<img src="/api/connection-qr.png?t=${Date.now()}" alt="QR code for ${info.url}" />`;
    connectionBody.appendChild(qr);

    const hint = document.createElement("div");
    hint.className = "connection-hint";
    hint.innerHTML = `Scan with your phone's camera on the <b>same Wi-Fi</b> to open the app. This is the <b>HTTPS</b> link — needed for live camera scanning. Your browser will warn about the certificate the first time; tap <b>Advanced → Proceed</b>.`;
    connectionBody.appendChild(hint);

    const urlRow = document.createElement("div");
    urlRow.className = "connection-url-row";
    urlRow.innerHTML = `<input readonly value="${info.url}" /><button id="copyConnectionUrl">Copy</button>`;
    connectionBody.appendChild(urlRow);

    document.getElementById("copyConnectionUrl").addEventListener("click", async e => {
      await navigator.clipboard.writeText(info.url);
      e.target.textContent = "Copied";
      setTimeout(() => { e.target.textContent = "Copy"; }, 1500);
    });
  } catch (err) {
    connectionStatus.hidden = false;
    connectionStatus.textContent = "Couldn't load connection info: " + err.message;
  }
});

document.getElementById("closeConnection").addEventListener("click", () => { connectionOverlay.hidden = true; });
connectionOverlay.addEventListener("click", e => { if (e.target === connectionOverlay) connectionOverlay.hidden = true; });

/* ---------------- Card detail ---------------- */
const detailOverlay = document.getElementById("cardDetailOverlay");
const detailName = document.getElementById("detailName");
const detailBody = document.getElementById("detailBody");

function openCardDetail(cardId) {
  const card = cardsById.get(cardId);
  if (!card) return;
  detailOverlay.hidden = false;
  renderCardDetail(card);
}

function renderCardDetail(c) {
  detailName.textContent = c.name;

  const domains = c.domains.length ? c.domains : ["Colorless"];
  const stats = [
    { k: "Energy", v: c.energy },
    { k: "Might", v: c.might },
    { k: "Power", v: c.power },
  ].filter(s => s.v !== null && s.v !== undefined);

  detailBody.innerHTML = `
    <div class="detail-art-col">
      <div class="detail-art${c.orientation === "landscape" ? " is-landscape" : ""}${c.ownedCount <= 0 ? " is-missing" : ""}">
        <div class="domain-bar">${domains.map(d => `<span style="background:${DOMAIN_COLOR[d] || "var(--c-colorless)"}"></span>`).join("")}</div>
        <img src="${c.localImagePath || ""}" alt="${escapeHtml(c.name)}" />
      </div>
      <div class="detail-owned">
        <span class="lbl">You own</span>
        <div class="stepper">
          <button data-act="dec" aria-label="Remove copy">−</button>
          <span class="n">${c.ownedCount}</span>
          <button data-act="inc" aria-label="Add copy">+</button>
        </div>
      </div>
    </div>
    <div class="detail-info">
      <div class="detail-meta-row">
        <span class="num">${escapeHtml(c.setLabel || c.setId)} · ${c.setId}-${cardCode(c)}</span>
        <span class="rarity"><span class="dot" style="background:${RARITY_COLOR[c.rarity] || "var(--text-faint)"}"></span>${escapeHtml(c.rarity)}</span>
      </div>
      <div class="detail-type">${c.supertype ? `<b>${escapeHtml(c.supertype)}</b> ` : ""}${escapeHtml(c.type)}</div>
      <div class="detail-domains">${domains.map(d => `<span class="chip"><span class="dot dot-icon" style="color:${DOMAIN_COLOR[d] || "var(--c-colorless)"}">${DOMAIN_ICON[d] || ""}</span>${escapeHtml(d)}</span>`).join("")}</div>
      ${stats.length ? `<div class="detail-stats">${stats.map(s => `<div class="detail-stat"><span class="v">${s.v}</span><span class="k">${s.k}</span></div>`).join("")}</div>` : ""}
      ${c.textPlain ? `<div class="detail-text">${formatCardText(c.textPlain)}</div>` : ""}
      ${c.flavour ? `<div class="detail-flavor">${escapeHtml(c.flavour)}</div>` : ""}
      ${c.artist ? `<div class="detail-artist">Illustrated by ${escapeHtml(c.artist)}</div>` : ""}
    </div>
  `;

  detailBody.querySelector('[data-act="dec"]').addEventListener("click", async () => {
    await setOwned(c.id, Math.max(0, c.ownedCount - 1));
    renderCardDetail(cardsById.get(c.id));
  });
  detailBody.querySelector('[data-act="inc"]').addEventListener("click", async () => {
    await setOwned(c.id, c.ownedCount + 1);
    renderCardDetail(cardsById.get(c.id));
  });
}

document.getElementById("closeDetail").addEventListener("click", () => { detailOverlay.hidden = true; });
detailOverlay.addEventListener("click", e => { if (e.target === detailOverlay) detailOverlay.hidden = true; });
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !detailOverlay.hidden) detailOverlay.hidden = true;
});

/* ---------------- Init ---------------- */
(async function init() {
  await loadSets();
  await loadFacets();
  await loadStats();
  await loadGrid();

  try {
    const info = await api("/api/server-info");
    currentVersionEl.textContent = info.version;
  } catch { /* version display is best-effort */ }
})();
