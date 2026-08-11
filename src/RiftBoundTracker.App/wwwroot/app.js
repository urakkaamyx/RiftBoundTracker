const RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Legendary"];
const DOMAIN_COLOR = {
  Fury: "var(--c-fury)", Calm: "var(--c-calm)", Order: "var(--c-order)",
  Mind: "var(--c-mind)", Body: "var(--c-body)", Chaos: "var(--c-chaos)",
  Colorless: "var(--c-colorless)"
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
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.status === 204 ? null : res.json();
}

function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  return p.toString();
}

async function loadSets() {
  const sets = await api("/api/sets");
  const el = document.getElementById("setList");
  el.innerHTML = "";

  const allItem = document.createElement("div");
  allItem.className = "set-item" + (state.setId === null ? " active" : "");
  allItem.innerHTML = `<span>All sets</span>`;
  allItem.addEventListener("click", () => { state.setId = null; onSetChanged(); });
  el.appendChild(allItem);

  sets.forEach(s => {
    const item = document.createElement("div");
    item.className = "set-item" + (state.setId === s.setId ? " active" : "");
    item.innerHTML = `<span>${s.setLabel || s.setId}</span><span class="n">${s.owned}/${s.total}</span>`;
    item.addEventListener("click", () => { state.setId = s.setId; onSetChanged(); });
    el.appendChild(item);
  });

  if (sets.length === 0) {
    const hint = document.createElement("div");
    hint.style.cssText = "font-size:12px;color:var(--text-faint);padding:4px;";
    hint.textContent = "No sets cached yet — sync one below.";
    el.appendChild(hint);
  }
}

function onSetChanged() {
  loadSets();
  loadFacets();
  loadStats();
  loadGrid();
}

function buildChips(containerId, values, current, onPick, colorMap) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  values.forEach(v => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.setAttribute("aria-pressed", String(v === current));
    if (colorMap) {
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
  buildChips("domainChips", domains, state.domain, v => { state.domain = v; loadGrid(); }, DOMAIN_COLOR);
}

async function loadStats() {
  const stats = await api(`/api/stats?${qs({ setId: state.setId })}`);
  document.getElementById("ownedLabel").textContent = stats.owned;
  document.getElementById("totalLabel").textContent = stats.total;
  const pct = stats.total ? Math.round((stats.owned / stats.total) * 100) : 0;
  document.getElementById("pctLabel").textContent = pct + "%";
  const ring = document.getElementById("ringProgress");
  const circumference = 2 * Math.PI * 22;
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
      <span class="num">${c.setId}·${String(c.collectorNumber).padStart(3, "0")}</span>
    </div>
  `;
  const stepper = document.createElement("div");
  stepper.className = "stepper";
  stepper.innerHTML = `<button data-act="dec" aria-label="Remove copy">−</button><span class="n">${c.ownedCount}</span><button data-act="inc" aria-label="Add copy">+</button>`;
  stepper.querySelector('[data-act="dec"]').addEventListener("click", () => setOwned(c.id, Math.max(0, c.ownedCount - 1)));
  stepper.querySelector('[data-act="inc"]').addEventListener("click", () => setOwned(c.id, c.ownedCount + 1));
  body.appendChild(stepper);
  card.appendChild(body);

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

document.getElementById("syncBtn").addEventListener("click", async () => {
  const input = document.getElementById("syncSetId");
  const setId = input.value.trim();
  if (!setId) return;
  const btn = document.getElementById("syncBtn");
  btn.disabled = true;
  btn.textContent = "Syncing…";
  try {
    const result = await api(`/api/sync/${encodeURIComponent(setId)}`, { method: "POST" });
    state.setId = result.setId;
    input.value = "";
    onSetChanged();
  } catch (err) {
    alert("Sync failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Sync";
  }
});

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

document.getElementById("openScan").addEventListener("click", () => {
  resetScanSheet();
  overlay.hidden = false;
});
document.getElementById("closeScan").addEventListener("click", () => { stopLiveScan(); overlay.hidden = true; });
overlay.addEventListener("click", e => { if (e.target === overlay) { stopLiveScan(); overlay.hidden = true; } });

function resetScanSheet() {
  stopLiveScan();
  scanFile.value = "";
  scanFileExisting.value = "";
  scanPreview.hidden = true;
  scanPreviewImg.style.display = "";
  matchList.innerHTML = "";
  ocrDebug.hidden = true;
  ocrDebug.textContent = "";
  manualNumber.value = "";
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
    scanStatus.textContent = "No match found. Try a closer, well-lit, right-side-up shot of the corner — or type the number below instead.";
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
        <div class="meta"><span class="num">${m.card.setId}·${String(m.card.collectorNumber).padStart(3, "0")}</span></div>
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
  const number = parseInt(manualNumber.value, 10);
  if (!number || number <= 0) return;

  scanPreview.hidden = false;
  scanPreviewImg.style.display = "none";
  scanPreviewImg.removeAttribute("src");
  ocrDebug.hidden = true;
  matchList.innerHTML = "";
  scanStatus.textContent = "Looking up…";

  try {
    const cards = await api(`/api/cards/lookup?${qs({ setId: state.setId, number })}`);
    renderScanResult({
      method: cards.length === 1 ? "manual" : cards.length > 1 ? "ocr-ambiguous" : "manual-none",
      matches: cards.map(card => ({ card, confidence: 100 })),
      debugOcrText: "",
    });
    if (cards.length === 0) {
      scanStatus.textContent = state.setId
        ? `No card #${number} found in ${state.setId}. Try "All sets" or sync the right set first.`
        : `No card numbered ${number} in any synced set.`;
    }
  } catch (err) {
    scanStatus.textContent = "Lookup failed: " + err.message;
  }
});

/* ---------------- Live camera scan ---------------- */
const liveScanBtn = document.getElementById("liveScanBtn");
const liveScanView = document.getElementById("liveScanView");
const liveVideo = document.getElementById("liveVideo");
const liveStatus = document.getElementById("liveStatus");
const liveHit = document.getElementById("liveHit");
const stopLiveBtn = document.getElementById("stopLiveBtn");
const scanOptions = document.getElementById("scanOptions");
const liveReadoutText = document.getElementById("liveReadoutText");
const liveCanvas = document.createElement("canvas");

let liveStream = null;
let liveInterval = null;
let liveInFlight = false;
let liveHitPending = false;

liveScanBtn.addEventListener("click", startLiveScan);
stopLiveBtn.addEventListener("click", stopLiveScan);

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
  scanOptions.hidden = true;
  liveScanBtn.hidden = true;
  liveScanView.hidden = false;
  liveHit.hidden = true;
  liveHitPending = false;
  liveReadoutText.textContent = "—";
  setLiveStatus("Point the camera at a card…", true);

  liveInterval = setInterval(captureLiveFrame, 800);
}

function stopLiveScan() {
  if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
  if (liveStream) { liveStream.getTracks().forEach(t => t.stop()); liveStream = null; }
  liveVideo.srcObject = null;
  liveHitPending = false;
  liveHit.hidden = true;
  liveHit.innerHTML = "";
  liveReadoutText.textContent = "—";
  liveScanView.hidden = true;
  liveScanBtn.hidden = false;
  scanOptions.hidden = false;
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
  if (!["ocr", "manual"].includes(result.method) || result.matches.length !== 1) {
    setLiveStatus("Scanning…", true);
    return;
  }

  const match = result.matches[0];
  liveHitPending = true;
  setLiveStatus("Found a match", false);
  liveHit.hidden = false;
  liveHit.innerHTML = `
    <img src="${match.card.localImagePath || ""}" alt="${match.card.name}" />
    <div class="info">
      <h4>${match.card.name}</h4>
      <div class="num">${match.card.setId}·${String(match.card.collectorNumber).padStart(3, "0")} — own ${match.card.ownedCount}</div>
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

/* ---------------- Init ---------------- */
(async function init() {
  const sets = await api("/api/sets");
  if (sets.length > 0) state.setId = sets[0].setId;
  await loadSets();
  await loadFacets();
  await loadStats();
  await loadGrid();
})();
