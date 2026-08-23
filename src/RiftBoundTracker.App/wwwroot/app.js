const DOMAIN_COLOR = {
  Fury: "var(--c-fury)", Calm: "var(--c-calm)", Order: "var(--c-order)",
  Mind: "var(--c-mind)", Body: "var(--c-body)", Chaos: "var(--c-chaos)",
  Rainbow: "var(--c-rainbow)", Colorless: "var(--c-colorless)"
};
const DOMAIN_SCENE = {
  Fury: "domain_fury.jpg", Calm: "domain_calm.jpg", Order: "domain_order.jpg",
  Mind: "domain_mind.jpg", Body: "domain_body.jpg", Chaos: "domain_chaos.jpg",
  Rainbow: "domain_colorless.jpg", Colorless: "domain_colorless.jpg"
};
const DOMAIN_CREST = {
  Fury: "domain_fury.png", Calm: "domain_calm.png", Order: "domain_order.png",
  Mind: "domain_mind.png", Body: "domain_body.png", Chaos: "domain_chaos.png",
  Rainbow: "domain_colorless.png", Colorless: "domain_colorless.png"
};
const RARITY_COLOR = {
  Common: "var(--faint)", Uncommon: "var(--blue)", Rare: "var(--green)",
  Epic: "var(--violet)", Legendary: "var(--gold-bright)", Champion: "var(--orange)"
};
const RARITY_ASSET = {
  Common: "rarity_common.svg", Uncommon: "rarity_uncommon.svg", Rare: "rarity_rare.svg",
  Epic: "rarity_epic.svg", Promo: "rarity_promo.svg", Showcase: "rarity_showcase.svg",
  Legendary: "rarity_legendary.svg", Champion: "rarity_champion.svg",
  Overnumbered: "rarity_overnumbered.svg"
};
const CARD_TYPE_ASSET = {
  battlefield: "card_type_battlefield.svg", champion: "card_type_champion.svg",
  gear: "card_type_gear.svg", legend: "card_type_legend.svg", rune: "card_type_rune.svg",
  spell: "card_type_spell.svg", unit: "card_type_unit.svg"
};
// Champion is a Supertype on Unit rows (and rarely Legend), never a Type of its own —
// confirmed against the live catalog. Deck groups still want Champions split out from
// plain Units, so group by this derived key rather than raw card.type.
const TYPE_GROUP_ORDER = ["Legend", "Champion", "Unit", "Spell", "Gear", "Battlefield", "Rune"];
function groupKey(card) {
  if (card.type === "Unit" && card.supertype === "Champion") return "Champion";
  return card.type || "Other";
}
const PAGE_LABELS = {
  vault: ["Collection", "Your Vault"], decks: ["Builder", "Decks"],
  favorites: ["Saved Cards", "Favorites"], binder: ["Collection", "Trade Binder"],
  "price-checker": ["Pricing", "Price Checker"],
  analytics: ["Collection Insights", "Analytics"], rules: ["Reference", "Rules"],
  settings: ["Vault", "Settings"]
};

const RULES_QUICK_TOPICS = [
  { label: "Deckbuilding", query: "domain identity" },
  { label: "Combat", query: "combat" },
  { label: "Chains", query: "chain" },
  { label: "Reactions", query: "reaction" },
  { label: "Domains", query: "domain" },
  { label: "Keywords", mode: "glossary" },
  { label: "Errata", mode: "errata" },
  { label: "Tournament", query: "tournament" },
  { label: "Banned Cards", mode: "legality" }
];

const state = {
  page: "vault", setId: null, owned: "all", search: "", rarity: "", type: "",
  domain: "", sort: "num-asc", view: "grid", selectedCardId: null,
  sets: [], overview: null, prices: {}, decks: [], activeDeckId: null,
  activeDeck: null, deckSearchTimer: null, contextCardId: null,
  contextMenuX: 0, contextMenuY: 0,
  deckTab: "builder", discoverTab: "recommended", discoverSearch: "", discoverSection: "main",
  discoverVariantSelection: new Map(), discoverPage: 1, discoverPageSize: 25,
  discoverCache: { key: null, cards: [] },
  recommendedCache: { key: null, recs: [] },
  recommendedRowsById: new Map(),
  vaultFacetCache: { setId: undefined, cards: [] },
  legendPicker: { cards: [], search: "", ownedOnly: false, selectedBase: null, selectedVariantId: null, mode: "create" },
  cardTextSymbols: new Map(),
  priceQueue: { items: [], batchSize: 20, configured: false, provider: "JustTCG" },
  priceQueueIds: new Set(),
  rules: { mode: "search", query: "", results: [], glossary: [], errata: [], legality: [], selectedKind: null, selectedId: null, searchTimer: null },
  rulesPageMode: "search",
  localAiEnabled: false,
  updateStatus: null, updateFooterDismissed: false
};
const cardsById = new Map();
// Mass Add state: each resolved line is { id, card, quantity }. massAddLockedId is the line whose
// image stays pinned in the preview panel after a click; massAddHoverId is whichever line the
// mouse is currently over, which takes priority over the lock while the mouse is there.
let massAddLines = [];
let massAddLineSeq = 0;
let massAddLockedId = null;
let massAddHoverId = null;
let massAddSearchTimer = null;
let massAddSearchSeq = 0;
let massAddErrors = [];
let massAddDropdownGroups = [];
let massAddVariantQueue = [];
let massAddVariantMemory = new Map();
let catalogPoll = null;
let saveDeckTimer = null;

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

function domainName(value) {
  return Object.hasOwn(DOMAIN_SCENE, value) ? value : "Colorless";
}

function domainKey(value) {
  return domainName(value).toLowerCase();
}

// List-row backdrop is the card's own art (blurred/extended), not a shared per-domain scene -
// each row reads as that specific card at a glance instead of just its domain.
function cardListSceneMarkup(card, domains) {
  const crests = domains.slice(0, 2).map(value => {
    const name = domainName(value);
    return `<img src="/assets/domain-crests/${DOMAIN_CREST[name]}" alt="" aria-hidden="true" loading="lazy" decoding="async" />`;
  }).join("");
  return `<div class="list-domain-scene${domains[1] ? " dual-domain" : ""}" aria-hidden="true">
    <img class="list-domain-scene-art" src="${escapeHtml(cardImage(card))}" alt="" loading="lazy" decoding="async" />
    <span class="list-domain-scene-crests">${crests}</span>
  </div>`;
}

function cardDomainThemeClasses(domains) {
  const primary = domainKey(domains[0]);
  const secondary = domainKey(domains[1] || domains[0]);
  return ` row-domain-${primary} row-domain-secondary-${secondary}`;
}

function cardTypeAsset(card) {
  const type = `${card.supertype || ""} ${card.type || ""}`.toLowerCase();
  return Object.entries(CARD_TYPE_ASSET).find(([key]) => type.includes(key))?.[1] || null;
}

function listFacetMarkup(label, asset, kind) {
  return `<div class="list-card-facet ${kind}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">
    ${asset ? `<img src="/assets/riftbound-symbols/${asset}" alt="" aria-hidden="true" loading="lazy" />` : ""}
  </div>`;
}

function safeSymbolColor(value, fallback) {
  return /^(#[0-9a-f]{6}|transparent)$/i.test(value || "") ? value : fallback;
}

function descriptionText(card) {
  const source = card.textRich || card.textPlain || "";
  if (!source) return "";

  const doc = new DOMParser().parseFromString(`<body>${source}</body>`, "text/html");
  doc.body.querySelectorAll("br").forEach(br => br.replaceWith("\n"));
  doc.body.querySelectorAll("li").forEach(item => {
    item.prepend("\u2022 ");
    item.append("\n");
  });
  doc.body.querySelectorAll("p").forEach(paragraph => paragraph.append("\n"));
  return (doc.body.textContent || "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function keywordSymbolMarkup(content) {
  const normalized = content.trim().replace(/\s+\d+$/i, "").toLowerCase();
  if (normalized === "no text") return "";

  const definition = state.cardTextSymbols.get(`keyword:${normalized}`);
  if (definition?.kind === "separator") {
    const lines = normalized === ">>" ? 2 : 1;
    return `<span class="rules-divider double-${lines}" role="img" aria-label="then"></span>`;
  }
  if (!definition) return `<span class="rules-token-unknown">${escapeHtml(`[${content}]`)}</span>`;

  const foreground = safeSymbolColor(definition.foregroundColor, "#ffffff");
  const background = safeSymbolColor(definition.backgroundColor, "#777a78");
  const border = safeSymbolColor(definition.borderColor, background);
  return `<span class="rules-keyword" style="--keyword-fg:${foreground};--keyword-bg:${background};--keyword-border:${border}" title="${escapeHtml(definition.label)}">${escapeHtml(content.toUpperCase())}</span>`;
}

function inlineSymbolMarkup(token) {
  const definition = state.cardTextSymbols.get(token.toLowerCase());
  const safeAsset = /^\/assets\/riftbound-symbols\/[a-z0-9_-]+\.svg$/i.test(definition?.assetPath || "")
    ? definition.assetPath : "";
  if (!definition || !safeAsset) return `<span class="rules-token-unknown">${escapeHtml(token)}</span>`;
  return `<img class="rules-symbol rules-symbol-${escapeHtml(definition.kind)}" src="${escapeHtml(safeAsset)}" alt="${escapeHtml(definition.label)}" title="${escapeHtml(definition.label)}" />`;
}

function cardRulesMarkup(card) {
  const text = descriptionText(card);
  if (!text) return "";

  const pattern = /:rb_[a-z0-9_]+:|\[[^\]\r\n]+\]/gi;
  let result = "";
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    result += escapeHtml(text.slice(cursor, match.index));
    result += match[0].startsWith(":")
      ? inlineSymbolMarkup(match[0])
      : keywordSymbolMarkup(match[0].slice(1, -1));
    cursor = match.index + match[0].length;
  }
  result += escapeHtml(text.slice(cursor));
  return result;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.error || body.title || message;
    } catch { }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function loadCardTextSymbols() {
  const definitions = await api("/api/card-text-symbols");
  state.cardTextSymbols = new Map(definitions.map(definition => [definition.token.toLowerCase(), definition]));
}

function jsonOptions(method, body) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") params.set(key, value);
  });
  return params.toString();
}

function cardCode(card) {
  return card.collectorCode || String(card.collectorNumber || 0).padStart(3, "0");
}

function cardImage(card) {
  return card.localImagePath || card.imageUrl || "";
}

function cardImagePopout(card) {
  return `<button type="button" class="image-popout" data-fullscreen-card="${escapeHtml(card.id)}" title="View full-screen image" aria-label="View ${escapeHtml(card.name)} image full screen">${icon("maximize")}</button>`;
}

function registerCards(cards) {
  cards.forEach(card => cardsById.set(card.id, card));
}

function icon(name) {
  return `<i data-icon="${name}"></i>`;
}

function renderIcons(root = document) {
  window.RiftIcons?.render(root);
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value || 0);
}

function formatPriceChange(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  const amount = Number(value);
  const formatted = formatMoney(Math.abs(amount));
  return amount > 0 ? `+${formatted}` : amount < 0 ? `-${formatted}` : formatted;
}

function priceChangeClass(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount === 0) return "flat";
  return amount > 0 ? "up" : "down";
}

function compactPriceMarkup(price) {
  if (!price) return "";
  const title = `${price.provider || "Price"}: ${formatMoney(price.marketPrice)}`;
  return `<span class="price-label" title="${escapeHtml(title)}"><b>${formatMoney(price.marketPrice)}</b></span>`;
}

function priceTrendMarkup(label, value) {
  return `<span class="price-change ${priceChangeClass(value)}"><em>${escapeHtml(label)}</em><b>${formatPriceChange(value)}</b></span>`;
}

function formatRelativeTime(iso) {
  if (!iso) return "Never";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function toast(message, error = false) {
  const item = document.createElement("div");
  item.className = `toast${error ? " error" : ""}`;
  item.textContent = message;
  document.getElementById("toastRegion").appendChild(item);
  setTimeout(() => item.remove(), 3600);
}

function showModal(id) {
  document.getElementById(id).hidden = false;
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.hidden = true;
  if (id === "scanModal") stopLiveScan();
  if (id === "imageViewer") document.body.classList.remove("image-viewer-open");
  if (id === "massAddVariantModal" && massAddVariantQueue.length) cancelMassAddVariantQueue();
  if (id === "addCollectionModal") packImportLoaded = false; // refetch next open so owned counts stay current
}

function openFullscreenCardImage(cardId) {
  const card = cardsById.get(cardId);
  if (!card) return;
  const image = document.getElementById("imageViewerImage");
  image.src = cardImage(card);
  image.alt = card.name;
  document.getElementById("imageViewerName").textContent = card.name;
  document.getElementById("imageViewerCode").textContent = `${card.setId}-${cardCode(card)}`;
  document.body.classList.add("image-viewer-open");
  showModal("imageViewer");
}

function closeCardContextMenu() {
  const menu = document.getElementById("cardContextMenu");
  menu.hidden = true;
  state.contextCardId = null;
}

function positionCardContextMenu(x, y) {
  const menu = document.getElementById("cardContextMenu");
  const edge = 8;
  menu.hidden = false;
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  const bounds = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(edge, Math.min(x, window.innerWidth - bounds.width - edge))}px`;
  menu.style.top = `${Math.max(edge, Math.min(y, window.innerHeight - bounds.height - edge))}px`;
}

function contextMenuHeader(card) {
  return `<div class="context-card-head"><strong>${escapeHtml(card.name)}</strong><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}</span></div>`;
}

function contextMenuItem(action, iconName, label, meta = "", disabled = false) {
  return `<button type="button" class="context-menu-item" role="menuitem" data-context-action="${action}"${disabled ? " disabled" : ""}>${icon(iconName)}<span>${escapeHtml(label)}</span>${meta ? `<small>${escapeHtml(meta)}</small>` : ""}</button>`;
}

function showCardContextMenu(card, x, y) {
  const menu = document.getElementById("cardContextMenu");
  const price = state.prices[card.id];
  state.contextCardId = card.id;
  state.contextMenuX = x;
  state.contextMenuY = y;
  menu.innerHTML = `${contextMenuHeader(card)}
    ${contextMenuItem("view", "eye", "View Card")}
    ${contextMenuItem("search-name", "search", "Search by Name", "All Sets")}
    ${contextMenuItem("pricing", "dollar", "View Pricing", price ? formatMoney(price.marketPrice) : "--")}
    ${contextMenuItem(
      "price-queue",
      "list-plus",
      state.priceQueueIds.has(card.id) ? "Remove from Price Checker" : "Add to Price Checker",
      state.priceQueueIds.has(card.id) ? "Queued" : (!card.tcgplayerId ? "No pricing ID" : ""),
      !state.priceQueueIds.has(card.id) && !card.tcgplayerId)}
    <div class="context-menu-separator"></div>
    ${contextMenuItem("add-copy", "plus-circle", "Add Copy", `Owned ${card.ownedCount}`)}
    ${contextMenuItem("remove-copy", "minus", "Remove Copy", "", card.ownedCount <= 0)}
    ${contextMenuItem("favorite", "star", card.isFavorite ? "Remove Favorite" : "Add to Favorites")}
    ${contextMenuItem("trade", "book-open", card.binderCount > 0 ? "Remove from Trade" : "Mark for Trade", "", card.ownedCount <= 0)}
    <div class="context-menu-separator"></div>
    ${contextMenuItem("decks", "layers", "Add to Deck...", state.decks.length ? `${state.decks.length}` : "None")}
    ${contextMenuItem("copy-id", "copy", "Copy Card ID", `${card.setId}-${cardCode(card)}`)}`;
  renderIcons(menu);
  positionCardContextMenu(x, y);
  menu.querySelector("button:not(:disabled)")?.focus();
}

function showContextDeckChoices(card) {
  const menu = document.getElementById("cardContextMenu");
  menu.innerHTML = `${contextMenuHeader(card)}
    ${contextMenuItem("back", "chevron-left", "Back")}
    <div class="context-menu-separator"></div>
    <div class="context-deck-list">${state.decks.length
      ? state.decks.map(deck => `<button type="button" class="context-menu-item" role="menuitem" data-context-deck="${deck.id}">${icon("layers")}<span>${escapeHtml(deck.name)}</span><small>${(deck.mainCount || 0) + (deck.sideboardCount || 0)}</small></button>`).join("")
      : `<div class="context-menu-empty">Create a deck first</div>`}</div>`;
  renderIcons(menu);
  positionCardContextMenu(state.contextMenuX, state.contextMenuY);
  menu.querySelector("button:not(:disabled)")?.focus();
}

function openCardContextSection(card, selector) {
  closeCardContextMenu();
  openCard(card.id);
  if (!selector) return;
  setTimeout(() => {
    const root = window.matchMedia("(max-width: 1180px)").matches
      ? document.getElementById("mobileCardDetail")
      : document.getElementById("cardInspector");
    const section = root.querySelector(selector);
    section?.scrollIntoView({ behavior: "smooth", block: "center" });
    section?.classList.add("context-highlight");
    setTimeout(() => section?.classList.remove("context-highlight"), 1100);
  }, 50);
}

async function copyCardId(card) {
  const value = `${card.setId}-${cardCode(card)}`;
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    const input = document.createElement("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  toast(`${value} copied`);
}

async function addContextCardToDeck(card, deckId) {
  const deck = state.decks.find(item => item.id === deckId);
  if (!deck) return;
  const detail = await api(`/api/decks/${deckId}`);
  const existing = detail.cards.find(row => row.cardId === card.id && row.section === "main");
  await api(`/api/decks/${deckId}/cards`, jsonOptions("POST", {
    cardId: card.id, quantity: (existing?.quantity || 0) + 1, section: "main"
  }));
  state.decks = await api("/api/decks");
  toast(`${card.name} added to ${deck.name}`);
}

async function handleCardContextAction(action) {
  const card = cardsById.get(state.contextCardId);
  if (!card) return closeCardContextMenu();
  if (action === "back") return showCardContextMenu(card, state.contextMenuX, state.contextMenuY);
  if (action === "decks") return showContextDeckChoices(card);
  closeCardContextMenu();
  if (action === "view") return openCardContextSection(card);
  if (action === "search-name") return searchCardNameAcrossSets(card);
  if (action === "pricing") return openCardContextSection(card, ".inspector-price");
  if (action === "price-queue") return setPriceQueue(card, !state.priceQueueIds.has(card.id));
  if (action === "add-copy") return changeOwned(card, 1);
  if (action === "remove-copy") return changeOwned(card, -1);
  if (action === "favorite") return changeFavorite(card);
  if (action === "trade") return setBinderAvailability(card, card.binderCount <= 0);
  if (action === "copy-id") return copyCardId(card);
}

function searchCardNameAcrossSets(card) {
  state.setId = null;
  state.search = card.name;
  state.owned = "all";
  state.rarity = "";
  state.type = "";
  state.domain = "";
  document.getElementById("globalSearch").value = card.name;
  document.querySelectorAll(".vault-tab").forEach(tab =>
    tab.classList.toggle("active", tab.dataset.owned === "all"));
  renderSetNavigation();
  navigate("vault");
}

const NAV_STATE_KEY = "riftbound-nav-state";

// Remembers which page/deck/tab/set the user was on so a refresh (or the WebView2 shell
// reloading after a self-update) lands back where they were instead of resetting to Vault.
// Session-scoped deliberately — a genuinely fresh app launch still starts at Vault.
function saveNavState() {
  try {
    sessionStorage.setItem(NAV_STATE_KEY, JSON.stringify({
      page: state.page, activeDeckId: state.activeDeckId, deckTab: state.deckTab,
      setId: state.setId, owned: state.owned
    }));
  } catch { /* storage unavailable (e.g. private mode) — non-fatal, just skip persistence */ }
}

function restoreNavState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(NAV_STATE_KEY) || "null");
    if (!saved) return;
    if (PAGE_LABELS[saved.page]) state.page = saved.page;
    if (typeof saved.activeDeckId === "number") state.activeDeckId = saved.activeDeckId;
    if (saved.deckTab === "builder" || saved.deckTab === "analysis") state.deckTab = saved.deckTab;
    if (typeof saved.setId === "string" || saved.setId === null) state.setId = saved.setId;
    if (typeof saved.owned === "string") state.owned = saved.owned;
  } catch { /* corrupt/missing entry — fall back to defaults */ }
}

function navigate(page) {
  if (!PAGE_LABELS[page]) return;
  state.page = page;
  document.querySelectorAll(".page").forEach(el => el.classList.toggle("active", el.id === `page-${page}`));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.page === page));
  document.getElementById("globalSearchWrap").hidden = page !== "vault";
  document.getElementById("pageEyebrow").textContent = PAGE_LABELS[page][0];
  document.getElementById("pageTitle").textContent = PAGE_LABELS[page][1];
  document.getElementById("sidebar").classList.remove("open");
  saveNavState();
  renderUpdateFooter();
  refreshCurrentPage().catch(err => toast(err.message, true));
}

async function refreshCurrentPage() {
  switch (state.page) {
    case "vault": await loadVault(); break;
    case "decks": await loadDecks(); break;
    case "favorites": await loadFavorites(); break;
    case "binder": await loadBinder(); break;
    case "price-checker": await loadPriceChecker(); break;
    case "analytics": await loadAnalytics(); break;
    case "rules": await loadRules(); break;
    case "settings": await loadSettings(); break;
  }
}

// The refresh every collection-mutating action needs after it completes: overview + per-set
// counts must be fully written to `state` BEFORE refreshCurrentPage() re-renders the active page,
// since page renderers (renderVaultHero in particular) read state.overview directly. Calling this
// as `Promise.all([loadOverview(), refreshCurrentPage()])` (the old pattern, still worth knowing
// about since it's an easy mistake to reintroduce) ran both concurrently — refreshCurrentPage()
// could read `state.overview` before the concurrently-running loadOverview() had finished writing
// it, so the set-hero banner (Owned/Missing/Completion%) rendered with pre-mutation numbers. A real
// pack import (25 cards added) reproduced this directly: the sidebar's total-owned count updated
// correctly (loadOverview alone has nothing to race against) but the set-hero banner stayed at
// 0/0%. loadSets() was also missing entirely from every one of these call sites, so the sidebar's
// per-set counts (e.g. "Origins 99/352") never updated after any collection change, not just a
// pack import — same root cause (a refresh step nobody added), just easier to notice in bulk.
async function refreshAfterCollectionChange() {
  // Deck Builder's Discover panel caches its card list by {tab, search} (see renderDiscoverResults)
  // so switching tabs/paging doesn't re-fetch a huge catalog query on every deck render. But that
  // cached array holds full card objects with a stale ownedCount, and every deck re-render re-wires
  // the panel, which calls registerCards(cachedCards) — clobbering the just-updated cardsById entry
  // right back to its pre-change value. Reproduced directly: clicking Acquired on a card already
  // visible in the (still-open) Discover panel updated the deck row correctly but silently reverted
  // cardsById, so a second Acquired click recomputed the same target quantity as the first. Dropping
  // both caches here forces a fresh fetch on the next render, whenever ownership actually changed.
  state.discoverCache = { key: null, cards: [] };
  state.recommendedCache = { key: null, recs: [] };
  await Promise.all([loadSets(), loadOverview()]);
  await refreshCurrentPage();
}

async function loadSets() {
  state.sets = await api("/api/sets");
  renderSetNavigation();
}

function renderSetNavigation() {
  const root = document.getElementById("setNav");
  const total = state.sets.reduce((sum, set) => sum + set.total, 0);
  const owned = state.sets.reduce((sum, set) => sum + set.owned, 0);
  const rows = [{ setId: null, setLabel: "All Sets", total, owned }, ...state.sets];
  root.innerHTML = rows.map(set => `
    <button class="set-nav-item${state.setId === set.setId ? " active" : ""}" data-set-id="${escapeHtml(set.setId || "")}">
      <span class="set-code">${escapeHtml(set.setId || "ALL")}</span>
      <span class="set-name">${escapeHtml(set.setLabel || set.setId)}</span>
      <b>${set.owned}/${set.total}</b>
    </button>`).join("");
}

async function loadOverview() {
  state.overview = await api("/api/analytics");
  const overview = state.overview;
  const completion = overview.totalCards ? Math.round(overview.ownedCards * 100 / overview.totalCards) : 0;
  document.getElementById("sidebarProgressPct").textContent = `${completion}%`;
  document.getElementById("sidebarProgressBar").style.width = `${completion}%`;
  document.getElementById("sidebarOwned").textContent = overview.ownedCards;
  document.getElementById("sidebarTotal").textContent = overview.totalCards;
  document.getElementById("navDeckCount").textContent = overview.decks || "";
  document.getElementById("navFavoriteCount").textContent = overview.favoriteCards || "";
  document.getElementById("navBinderCount").textContent = overview.binderCards || "";
  document.getElementById("tabAllCount").textContent = overview.totalCards;
  document.getElementById("tabOwnedCount").textContent = overview.ownedCards;
  document.getElementById("tabMissingCount").textContent = overview.missingCards;
  document.getElementById("tabFavoriteCount").textContent = overview.favoriteCards;
  document.getElementById("tabTokenCount").textContent = overview.tokenCards;
}

async function loadPrices() {
  state.prices = await api("/api/pricing/latest");
}

async function loadPriceQueue(renderPage = true) {
  state.priceQueue = await api("/api/pricing/queue");
  state.priceQueueIds = new Set(state.priceQueue.items.map(item => item.card.id));
  registerCards(state.priceQueue.items.map(item => item.card));
  document.getElementById("navPriceQueueCount").textContent = state.priceQueue.items.length || "";
  if (renderPage && state.page === "price-checker") renderPriceChecker();
  return state.priceQueue;
}

async function loadVault() {
  // The facet query (rarity/type/domain dropdown options + hero art) only depends on which
  // cards exist in the selected set — never on ownership — so it doesn't need to be re-fetched
  // on every add/remove click, just when the set changes. Re-fetching the full catalog (up to
  // 1300+ rows) on every stepper click was the actual source of the reported Vault lag.
  let facetCards;
  if (state.vaultFacetCache.setId === state.setId) {
    facetCards = state.vaultFacetCache.cards;
  } else {
    facetCards = await api(`/api/cards?${queryString({ setId: state.setId })}`);
    state.vaultFacetCache = { setId: state.setId, cards: facetCards };
  }
  registerCards(facetCards);
  updateFacetOptions(facetCards);

  let cards;
  if (state.owned === "favorites") {
    cards = facetCards.filter(card => card.isFavorite);
    cards = applyClientFilters(cards);
  } else {
    cards = await api(`/api/cards?${queryString({
      setId: state.setId, search: state.search, type: state.type, rarity: state.rarity,
      domain: state.domain, owned: state.owned, sort: state.sort
    })}`);
  }
  cards = applyPriceSort(cards);
  registerCards(cards);
  renderVaultHero(facetCards);
  renderCardGrid(document.getElementById("vaultGrid"), cards);
  document.getElementById("vaultResultCount").textContent = `${cards.length} card${cards.length === 1 ? "" : "s"}`;
  document.getElementById("vaultResultMeta").textContent = state.search ? `matching "${state.search}"` : "in your catalog";

  if (state.selectedCardId && cardsById.has(state.selectedCardId))
    renderInspector(cardsById.get(state.selectedCardId));
}

function applyPriceSort(cards) {
  if (state.sort !== "price-asc" && state.sort !== "price-desc") return cards;
  const direction = state.sort === "price-asc" ? 1 : -1;
  return [...cards].sort((a, b) => {
    const aPrice = Number(state.prices[a.id]?.marketPrice);
    const bPrice = Number(state.prices[b.id]?.marketPrice);
    const aPriced = Number.isFinite(aPrice) && aPrice > 0;
    const bPriced = Number.isFinite(bPrice) && bPrice > 0;
    if (aPriced !== bPriced) return aPriced ? -1 : 1;
    if (aPriced && aPrice !== bPrice) return (aPrice - bPrice) * direction;
    return a.collectorNumber - b.collectorNumber || a.name.localeCompare(b.name);
  });
}

function applyClientFilters(cards) {
  const search = state.search.toLowerCase();
  return cards.filter(card =>
    (!search || card.name.toLowerCase().includes(search) || card.id.toLowerCase().includes(search) || cardCode(card).toLowerCase().includes(search)) &&
    (!state.type || card.type === state.type) &&
    (!state.rarity || card.rarity === state.rarity) &&
    (!state.domain || card.domains.includes(state.domain)))
    .sort((a, b) => state.sort === "name-asc" ? a.name.localeCompare(b.name) : a.collectorNumber - b.collectorNumber);
}

function updateFacetOptions(cards) {
  setSelectOptions("rarityFilter", [...new Set(cards.map(card => card.rarity).filter(Boolean))].sort(), state.rarity, "All rarities");
  setSelectOptions("typeFilter", [...new Set(cards.map(card => card.type).filter(Boolean))].sort(), state.type, "All types");
  setSelectOptions("domainFilter", [...new Set(cards.flatMap(card => card.domains || []))].sort(), state.domain, "All domains");
}

function setSelectOptions(id, values, current, emptyLabel) {
  const select = document.getElementById(id);
  select.innerHTML = `<option value="">${emptyLabel}</option>` + values.map(value =>
    `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`).join("");
}

function renderVaultHero(facetCards) {
  const set = state.setId ? state.overview?.sets.find(item => item.setId === state.setId) : null;
  const total = set?.total ?? state.overview?.totalCards ?? facetCards.length;
  const owned = set?.owned ?? state.overview?.ownedCards ?? facetCards.filter(card => card.ownedCount > 0).length;
  const completion = total ? Math.round(owned * 100 / total) : 0;
  const hero = document.getElementById("setHero");
  const image = facetCards.find(card => cardImage(card))?.localImagePath;
  hero.style.backgroundImage = image ? `url("${encodeURI(image)}")` : "none";
  document.getElementById("setEmblem").textContent = state.setId || "ALL";
  document.getElementById("setHeroTitle").textContent = set?.setLabel || (state.setId || "All Sets");
  document.getElementById("setHeroMeta").textContent = state.setId ? `${total} cards in this set` : "Your complete Riftbound catalog";
  document.getElementById("setOwnedCount").textContent = owned;
  document.getElementById("setMissingCount").textContent = Math.max(0, total - owned);
  document.getElementById("setCompletion").textContent = `${completion}%`;
  document.getElementById("setRing").style.strokeDashoffset = 120 * (1 - completion / 100);
}

function cardTile(card, context) {
  const domains = card.domains?.length ? card.domains : ["Colorless"];
  const price = state.prices[card.id];
  return `
    <article class="card-tile${card.ownedCount <= 0 ? " missing" : ""}${state.selectedCardId === card.id ? " selected" : ""}" data-card-open="${escapeHtml(card.id)}">
      <div class="card-art${card.orientation === "landscape" ? " landscape" : ""}">
        <div class="card-domain">${domains.map(domain => `<span style="background:${DOMAIN_COLOR[domain] || DOMAIN_COLOR.Colorless}"></span>`).join("")}</div>
        <img src="${escapeHtml(cardImage(card))}" alt="${escapeHtml(card.name)}" loading="lazy" />
        ${cardImagePopout(card)}
        ${card.binderCount > 0 ? `<span class="trade-banner">Trading</span>` : ""}
        ${card.energy != null ? `<span class="energy-badge">${card.energy}</span>` : ""}
        <button class="favorite-fab${card.isFavorite ? " active" : ""}" data-favorite-card="${escapeHtml(card.id)}" title="${card.isFavorite ? "Remove from favorites" : "Add to favorites"}">${icon("star")}</button>
        ${card.ownedCount > 0 ? `<span class="owned-badge">x${card.ownedCount}</span>` : `<span class="missing-badge">MISSING</span>`}
      </div>
      <div class="card-body">
        <h3>${escapeHtml(card.name)}</h3>
        <div class="card-meta"><span><i class="rarity-gem" style="background:${RARITY_COLOR[card.rarity] || "var(--faint)"}"></i>${escapeHtml(card.rarity || card.type)}</span><span class="card-meta-end"><span class="card-code">${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}</span>${compactPriceMarkup(price)}</span></div>
        <div class="card-actions">
          <div class="mini-stepper"><button data-owned-delta="-1" data-card-id="${escapeHtml(card.id)}" aria-label="Remove copy">-</button><span>${card.ownedCount}</span><button data-owned-delta="1" data-card-id="${escapeHtml(card.id)}" aria-label="Add copy">+</button></div>
          ${context === "binderGrid"
            ? `<button class="binder-chip icon-btn" data-binder-delta="-1" data-card-id="${escapeHtml(card.id)}" title="No longer offering this copy for trade — stays in your collection" aria-label="Remove from Trade Binder"><i data-icon="trash"></i></button>
               <button class="binder-chip binder-chip-confirm icon-btn" data-confirm-trade="${escapeHtml(card.id)}" title="Trade completed — removes this copy from your collection entirely" aria-label="Confirm Trade"><i data-icon="repeat"></i></button>`
            : card.ownedCount > 0
              ? `<label class="card-trade-toggle" title="Mark this card as available for trade"><span>Trade</span><input type="checkbox" data-card-trade-toggle="${escapeHtml(card.id)}"${card.binderCount > 0 ? " checked" : ""} /><i aria-hidden="true"></i></label>`
              : ""}
        </div>
      </div>
    </article>`;
}

function cardListRow(card) {
  const domains = card.domains?.length ? card.domains : ["Colorless"];
  const price = state.prices[card.id];
  const cardType = [card.supertype, card.type].filter(Boolean).join(" ") || "Card";
  const rarity = card.rarity || "Unknown";
  return `
    <article class="card-list-row${cardDomainThemeClasses(domains)}${card.ownedCount <= 0 ? " missing" : ""}${state.selectedCardId === card.id ? " selected" : ""}" data-card-open="${escapeHtml(card.id)}">
      ${cardListSceneMarkup(card, domains)}
      <div class="card-art list-card-art${card.orientation === "landscape" ? " landscape" : ""}">
        <div class="card-domain">${domains.map(domain => `<span style="background:${DOMAIN_COLOR[domain] || DOMAIN_COLOR.Colorless}"></span>`).join("")}</div>
        <img src="${escapeHtml(cardImage(card))}" alt="${escapeHtml(card.name)}" loading="lazy" />
        ${cardImagePopout(card)}
        <button class="favorite-fab${card.isFavorite ? " active" : ""}" data-favorite-card="${escapeHtml(card.id)}" title="${card.isFavorite ? "Remove from favorites" : "Add to favorites"}">${icon("star")}</button>
      </div>
      <div class="list-card-info">
        <h3>${escapeHtml(card.name)}</h3>
      </div>
      <div class="list-card-set"><b>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}</b><span>${escapeHtml(card.setLabel || card.setId)}</span></div>
      <div class="list-card-rarity">${listFacetMarkup(rarity, RARITY_ASSET[rarity] || null, "rarity")}</div>
      <div class="list-card-type">${listFacetMarkup(cardType, cardTypeAsset(card), "type")}</div>
      <div class="list-card-owned"><span class="list-mobile-label">Owned</span><div class="mini-stepper"><button data-owned-delta="-1" data-card-id="${escapeHtml(card.id)}" aria-label="Remove copy">-</button><span>${card.ownedCount}</span><button data-owned-delta="1" data-card-id="${escapeHtml(card.id)}" aria-label="Add copy">+</button></div></div>
      <div class="list-card-trade">${card.ownedCount > 0
        ? `<label class="card-trade-toggle" title="Mark this card as available for trade"><span>Trade</span><input type="checkbox" data-card-trade-toggle="${escapeHtml(card.id)}"${card.binderCount > 0 ? " checked" : ""} /><i aria-hidden="true"></i></label>`
        : `<span class="list-empty">--</span>`}</div>
      <div class="list-card-price"><span class="list-mobile-label">Market</span><b${price ? ` title="${escapeHtml(`${price.provider || "Price"}: ${formatMoney(price.marketPrice)}`)}"` : ""}>${price ? formatMoney(price.marketPrice) : "--"}</b></div>
    </article>`;
}

function renderCardGrid(root, cards) {
  const isList = state.view === "list" && root.id === "vaultGrid";
  root.classList.toggle("list-view", isList);
  root.innerHTML = isList
    ? `<div class="card-list-header" aria-hidden="true"><span></span><span>Card</span><span class="list-head-set">Set</span><span>Rarity</span><span>Type</span><span>Owned</span><span>Trade</span><span>Market</span></div>${cards.map(cardListRow).join("")}`
    : cards.map(card => cardTile(card, root.id)).join("");
  renderIcons(root);
}

function renderInspector(card) {
  state.selectedCardId = card.id;
  const root = document.getElementById("cardInspector");
  root.innerHTML = cardDetailMarkup(card, false);
  renderIcons(root);
  wireInspector(root, card);
  document.querySelectorAll("[data-card-open]").forEach(el => el.classList.toggle("selected", el.dataset.cardOpen === card.id));
}

function cardDetailMarkup(card, mobile) {
  const price = state.prices[card.id];
  const domains = card.domains?.length ? card.domains : ["Colorless"];
  const deckOptions = state.decks.map(deck => `<option value="${deck.id}">${escapeHtml(deck.name)}</option>`).join("");
  return `
    <div class="inspector-card-art${card.orientation === "landscape" ? " landscape" : ""}"><img src="${escapeHtml(cardImage(card))}" alt="${escapeHtml(card.name)}" /><button class="favorite-fab${card.isFavorite ? " active" : ""}" data-favorite-card="${escapeHtml(card.id)}" title="${card.isFavorite ? "Remove from favorites" : "Add to favorites"}">${icon("star")}</button>${cardImagePopout(card)}</div>
    <div class="inspector-head"><h2>${escapeHtml(card.name)}</h2><p>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))} / ${escapeHtml(card.rarity)}</p></div>
    <div class="inspector-commands">
      <div class="owned-editor">
        <span>Owned</span>
        <button type="button" data-inspector-owned-delta="-1" aria-label="Remove one owned copy" title="Remove one copy"${card.ownedCount <= 0 ? " disabled" : ""}>${icon("minus")}</button>
        <input type="number" min="0" step="1" inputmode="numeric" value="${card.ownedCount}" data-inspector-owned-input aria-label="Owned copies" />
        <button type="button" data-inspector-owned-delta="1" aria-label="Add one owned copy" title="Add one copy">${icon("plus")}</button>
      </div>
      <label class="trade-toggle" title="Mark this card as available for trade"><span>Trade</span><input type="checkbox" data-inspector-binder-toggle${card.binderCount > 0 ? " checked" : ""}${card.ownedCount <= 0 ? " disabled" : ""} /><i aria-hidden="true"></i></label>
    </div>
    <div class="inspector-stats">
      <span>Type</span><b>${escapeHtml([card.supertype, card.type].filter(Boolean).join(" "))}</b>
      <span>Domain</span><b>${escapeHtml(domains.join(" / "))}</b>
      ${card.energy != null ? `<span>Energy</span><b>${card.energy}</b>` : ""}
      ${card.might != null ? `<span>Might</span><b>${card.might}</b>` : ""}
      ${card.power != null ? `<span>Power</span><b>${card.power}</b>` : ""}
      ${card.artist ? `<span>Artist</span><b>${escapeHtml(card.artist)}</b>` : ""}
    </div>
    ${card.textRich || card.textPlain ? `<div class="inspector-rules">${cardRulesMarkup(card)}</div>` : ""}
    ${deckOptions ? `<div class="inline-form"><select data-deck-picker>${deckOptions}</select><button class="command-btn" data-add-to-deck>Add to Deck</button></div>` : ""}
    <div class="inspector-price">
      <div class="inspector-price-current">
        <span>Current Price</span>
        <b>${price
          ? `${price.sourceUrl ? `<a href="${escapeHtml(price.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(price.provider)}</a>` : `<span>${escapeHtml(price.provider)}</span>`}<i>:</i><strong>${formatMoney(price.marketPrice)}</strong>`
          : `<span>riftbound.gg</span><i>:</i><strong>--</strong>`}</b>
      </div>
      <div class="price-change-grid">${priceTrendMarkup("24 hrs", price?.change24Hours)}${priceTrendMarkup("7 days", price?.change7Days)}</div>
      <small>${price ? `${escapeHtml(price.printing || "Market")} price / Updated ${formatRelativeTime(price.capturedAt)}` : "No Riftbound.gg price is available for this printing"}</small>
      <div class="price-history" data-price-history="${escapeHtml(card.id)}"><span class="loading-line">Loading price history…</span></div>
    </div>
  `;
}

function priceHistoryChartMarkup(history) {
  const width = 320, height = 96, padX = 6, padY = 10;
  if (history.length < 2) {
    return `<div class="price-history-empty">Not enough price history yet — check back after a few more syncs.</div>`;
  }
  const values = history.map(p => p.marketPrice);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - padX * 2) / (history.length - 1);
  const points = history.map((p, i) => {
    const x = padX + i * stepX;
    const y = padY + (height - padY * 2) * (1 - (p.marketPrice - min) / span);
    return [x, y];
  });
  const linePath = points.map((pt, i) => `${i === 0 ? "M" : "L"}${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${height - padY} L${points[0][0].toFixed(1)},${height - padY} Z`;
  return `
    <svg class="price-history-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Price history chart">
      <path d="${areaPath}" class="price-history-area"></path>
      <path d="${linePath}" class="price-history-line"></path>
    </svg>`;
}

function priceHistoryStatsMarkup(history) {
  const values = history.map(p => p.marketPrice);
  const min = Math.min(...values), max = Math.max(...values);
  const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
  const first = values[0], last = values[values.length - 1];
  const changePct = first ? ((last - first) / first) * 100 : 0;
  return `
    <div class="price-history-stats">
      <div><span>Low</span><b>${formatMoney(min)}</b></div>
      <div><span>Average</span><b>${formatMoney(avg)}</b></div>
      <div><span>High</span><b>${formatMoney(max)}</b></div>
      <div><span>Period Change</span><b class="${priceChangeClass(last - first)}">${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%</b></div>
    </div>`;
}

async function loadPriceHistory(root, card) {
  const container = root.querySelector(`[data-price-history="${CSS.escape(card.id)}"]`);
  if (!container) return;
  try {
    const history = await api(`/api/pricing/history/${encodeURIComponent(card.id)}?days=90`);
    if (!root.isConnected || !root.querySelector(`[data-price-history="${CSS.escape(card.id)}"]`)) return;
    if (!history.length) {
      container.innerHTML = `<div class="price-history-empty">No price history recorded yet for this card.</div>`;
      return;
    }
    container.innerHTML = `<div class="price-history-head">Price History <span>Last ${Math.min(90, Math.ceil((Date.now() - new Date(history[0].capturedAt).getTime()) / 86400000))} days</span></div>${priceHistoryChartMarkup(history)}${priceHistoryStatsMarkup(history)}`;
  } catch {
    container.innerHTML = `<div class="price-history-empty">Couldn't load price history.</div>`;
  }
}

function wireInspector(root, card) {
  const currentCard = () => cardsById.get(card.id) || card;
  loadPriceHistory(root, card);
  root.querySelectorAll("[data-inspector-owned-delta]").forEach(button => button.addEventListener("click", () =>
    changeOwned(currentCard(), Number(button.dataset.inspectorOwnedDelta)).catch(err => toast(err.message, true))));
  const ownedInput = root.querySelector("[data-inspector-owned-input]");
  let ownedSaveTimer;
  let lastRequestedQuantity = ownedInput?.value;
  const saveOwnedInput = () => {
    clearTimeout(ownedSaveTimer);
    if (!ownedInput || ownedInput.value === lastRequestedQuantity) return;
    lastRequestedQuantity = ownedInput.value;
    setOwnedCount(currentCard(), ownedInput.value).catch(err => {
      lastRequestedQuantity = String(currentCard().ownedCount);
      toast(err.message, true);
      refreshVisibleCardDetails(currentCard());
    });
  };
  ownedInput?.addEventListener("input", () => {
    clearTimeout(ownedSaveTimer);
    ownedSaveTimer = setTimeout(saveOwnedInput, 500);
  });
  ownedInput?.addEventListener("change", saveOwnedInput);
  ownedInput?.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); saveOwnedInput(); ownedInput.blur(); }
  });
  root.querySelector("[data-inspector-binder-toggle]")?.addEventListener("change", event =>
    setBinderAvailability(currentCard(), event.target.checked).catch(err => toast(err.message, true)));
  root.querySelector("[data-add-to-deck]")?.addEventListener("click", async () => {
    const deckId = Number(root.querySelector("[data-deck-picker]").value);
    const detail = await api(`/api/decks/${deckId}`);
    const existing = detail.cards.find(row => row.cardId === card.id && row.section === "main");
    await setDeckCard(deckId, card.id, (existing?.quantity || 0) + 1, "main");
    toast(`${card.name} added to deck`);
  });
}

async function openCard(cardId) {
  const card = cardsById.get(cardId);
  if (!card) return;
  if (window.matchMedia("(max-width: 1180px)").matches) {
    const root = document.getElementById("mobileCardDetail");
    root.dataset.cardId = card.id;
    root.innerHTML = cardDetailMarkup(card, true);
    renderIcons(root);
    wireInspector(root, card);
    showModal("cardDetailModal");
  } else {
    renderInspector(card);
  }
}

function refreshVisibleCardDetails(card) {
  if (state.selectedCardId === card.id) renderInspector(card);
  const modal = document.getElementById("cardDetailModal");
  const root = document.getElementById("mobileCardDetail");
  if (!modal.hidden && root.dataset.cardId === card.id) {
    root.innerHTML = cardDetailMarkup(card, true);
    renderIcons(root);
    wireInspector(root, card);
  }
}

async function setOwnedCount(card, ownedCount) {
  const parsed = Number(ownedCount);
  const next = Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : card.ownedCount;
  if (next === card.ownedCount) return refreshVisibleCardDetails(card);
  const updated = await api(`/api/collection/${encodeURIComponent(card.id)}`, jsonOptions("POST", { owned: next }));
  cardsById.set(updated.id, updated);
  toast(`${card.name}: ${updated.ownedCount} owned`);
  await refreshAfterCollectionChange();
  refreshVisibleCardDetails(updated);
}

async function changeOwned(card, delta) {
  return setOwnedCount(card, card.ownedCount + delta);
}

async function changeFavorite(card) {
  const updated = await api(`/api/favorites/${encodeURIComponent(card.id)}`, jsonOptions("POST", { favorite: !card.isFavorite }));
  cardsById.set(updated.id, updated);
  await refreshAfterCollectionChange();
  refreshVisibleCardDetails(updated);
  toast(updated.isFavorite ? "Added to favorites" : "Removed from favorites");
}

async function changeBinder(card, delta) {
  if (card.ownedCount <= 0) return toast("Add a copy to your collection first", true);
  const next = Math.max(0, Math.min(card.ownedCount, (card.binderCount || 0) + delta));
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}`, jsonOptions("POST", { count: next }));
  cardsById.set(updated.id, updated);
  await refreshAfterCollectionChange();
  toast(`${card.name}: ${updated.binderCount} in binder`);
}

async function confirmTrade(card) {
  if (!confirm(`Confirm you traded away 1 copy of "${card.name}"? It will be removed from your collection.`)) return;
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}/confirm-trade`, jsonOptions("POST", { count: 1 }));
  cardsById.set(updated.id, updated);
  await refreshAfterCollectionChange();
  toast(`${card.name} traded — removed from your collection`);
}

async function confirmTradeAll() {
  const cards = state.binderCards || [];
  if (!cards.length) return;
  const copies = cards.reduce((sum, card) => sum + card.binderCount, 0);
  if (!confirm(`Confirm you traded away all ${cards.length} card${cards.length === 1 ? "" : "s"} (${copies} cop${copies === 1 ? "y" : "ies"}) in your Trade Binder? They'll be removed from your collection.`)) return;
  const result = await api("/api/binder/confirm-all", jsonOptions("POST", {}));
  await refreshAfterCollectionChange();
  toast(`${result.confirmedCards} card${result.confirmedCards === 1 ? "" : "s"} traded — ${result.confirmedCopies} cop${result.confirmedCopies === 1 ? "y" : "ies"} removed from your collection`);
}

async function setBinderAvailability(card, available) {
  if (card.ownedCount <= 0) return toast("Add a copy to your collection first", true);
  const count = available ? 1 : 0;
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}`, jsonOptions("POST", { count }));
  cardsById.set(updated.id, updated);
  await refreshAfterCollectionChange();
  refreshVisibleCardDetails(updated);
  toast(available ? `${card.name} marked for trade` : `${card.name} removed from Trade Binder`);
}

async function loadFavorites() {
  const cards = await api("/api/favorites");
  registerCards(cards);
  document.getElementById("favoriteMeta").textContent = `${cards.length} saved card${cards.length === 1 ? "" : "s"}`;
  document.getElementById("favoritesEmpty").hidden = cards.length > 0;
  renderCardGrid(document.getElementById("favoritesGrid"), cards);
}

async function loadBinder() {
  const cards = await api("/api/binder");
  registerCards(cards);
  state.binderCards = cards;
  const copies = cards.reduce((sum, card) => sum + card.binderCount, 0);
  document.getElementById("binderMeta").textContent = `${cards.length} card${cards.length === 1 ? "" : "s"} available to trade`;
  document.getElementById("binderEmpty").hidden = cards.length > 0;
  document.getElementById("binderValue").textContent = state.overview?.hasPricing ? formatMoney(state.overview.binderValue) : "Pricing not configured";
  document.getElementById("binderSummary").innerHTML = `
    <div><b>${cards.length}</b><span>Unique cards</span></div><div><b>${copies}</b><span>Total copies</span></div><div><b>${state.overview?.hasPricing ? formatMoney(state.overview.binderValue) : "--"}</b><span>Market value</span></div>`;
  document.getElementById("tradeAllBtn").disabled = cards.length === 0;
  renderCardGrid(document.getElementById("binderGrid"), cards);
}

async function loadPriceChecker() {
  await Promise.all([loadPriceQueue(false), loadPrices()]);
  renderPriceChecker();
}

function renderPriceChecker() {
  const queue = state.priceQueue;
  const items = queue.items || [];
  const batchSize = queue.batchSize || 20;
  const nextCount = Math.min(items.length, batchSize);
  const openSlots = Math.max(0, batchSize - nextCount);
  const requestCount = Math.ceil(items.length / batchSize);

  document.getElementById("priceQueueMeta").textContent = `${items.length} card${items.length === 1 ? "" : "s"} queued`;
  document.getElementById("priceBatchCount").textContent = `${nextCount} / ${batchSize}`;
  document.getElementById("priceBatchProgress").style.width = `${nextCount * 100 / batchSize}%`;
  document.getElementById("priceQueueSlots").textContent = openSlots;
  document.getElementById("priceQueueRequests").textContent = requestCount;
  document.getElementById("priceQueueProvider").textContent = queue.configured ? queue.provider : "Key required";
  document.getElementById("priceQueueEmpty").hidden = items.length > 0;
  document.getElementById("clearPriceQueue").disabled = items.length === 0;
  const checkButton = document.getElementById("checkPriceQueue");
  checkButton.disabled = items.length === 0 || !queue.configured;
  checkButton.title = queue.configured ? "Check up to 20 queued cards" : "Add a pricing API key in Settings";

  const root = document.getElementById("priceQueueList");
  root.innerHTML = items.map((item, index) => {
    const card = item.card;
    const price = state.prices[card.id];
    const batchNumber = Math.floor(index / batchSize) + 1;
    return `<div class="price-queue-row" data-card-open="${escapeHtml(card.id)}">
      <span class="price-queue-position">${String(index + 1).padStart(2, "0")}</span>
      <div class="price-queue-art${card.orientation === "landscape" ? " landscape" : ""}"><img src="${escapeHtml(cardImage(card))}" alt="" loading="lazy" />${cardImagePopout(card)}</div>
      <div class="price-queue-card"><strong>${escapeHtml(card.name)}</strong><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))} / ${escapeHtml(card.rarity || card.type)}</span><small>Queued ${formatRelativeTime(item.queuedAt)}</small></div>
      <div class="price-queue-price"><span>Market</span><b>${price ? formatMoney(price.marketPrice) : "--"}</b><small>${price ? formatRelativeTime(price.capturedAt) : "Not checked"}</small></div>
      <span class="price-queue-batch${batchNumber === 1 ? " active" : ""}">Batch ${batchNumber}</span>
      <button class="icon-btn" data-price-queue-remove="${escapeHtml(card.id)}" title="Remove from Price Checker" aria-label="Remove ${escapeHtml(card.name)} from Price Checker">${icon("trash")}</button>
    </div>`;
  }).join("");
  renderIcons(root);
}

async function setPriceQueue(card, queued) {
  await api(`/api/pricing/queue/${encodeURIComponent(card.id)}`, jsonOptions("POST", { queued }));
  await loadPriceQueue();
  toast(queued ? `${card.name} added to Price Checker` : `${card.name} removed from Price Checker`);
}

async function clearPriceQueue() {
  if (!state.priceQueue.items.length || !confirm("Clear every card from the Price Checker queue?")) return;
  const result = await api("/api/pricing/queue", { method: "DELETE" });
  await loadPriceQueue();
  toast(`${result.removed} queued card${result.removed === 1 ? "" : "s"} removed`);
}

async function checkPriceQueue() {
  const button = document.getElementById("checkPriceQueue");
  button.disabled = true;
  button.innerHTML = `${icon("refresh")}Checking...`;
  renderIcons(button);
  try {
    const result = await api("/api/pricing/queue/check", { method: "POST" });
    await Promise.all([loadPriceQueue(false), loadPrices(), loadOverview()]);
    renderPriceChecker();
    toast(`${result.pricedCards} of ${result.requestedCards} cards priced`);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.innerHTML = `${icon("refresh")}Check Next Batch`;
    renderIcons(button);
    button.disabled = state.priceQueue.items.length === 0 || !state.priceQueue.configured;
  }
}

async function loadDecks() {
  state.decks = await api("/api/decks");
  document.getElementById("deckLibraryMeta").textContent = `${state.decks.length} deck${state.decks.length === 1 ? "" : "s"}`;
  document.getElementById("navDeckCount").textContent = state.decks.length || "";
  if (state.activeDeckId && !state.decks.some(deck => deck.id === state.activeDeckId)) state.activeDeckId = null;
  if (!state.activeDeckId && state.decks.length) state.activeDeckId = state.decks[0].id;
  renderDeckList();
  if (!state.activeDeckId) {
    state.activeDeck = null;
    document.getElementById("deckWorkspace").innerHTML = `<div class="empty-workspace">${icon("layers")}<h2>Create your first deck</h2><button class="command-btn gold" data-new-deck>New Deck</button></div>`;
    renderIcons(document.getElementById("deckWorkspace"));
    return;
  }
  state.activeDeck = await api(`/api/decks/${state.activeDeckId}`);
  registerCards(state.activeDeck.cards.map(row => row.card));
  renderDeckWorkspace();
}

function renderDeckList() {
  const root = document.getElementById("deckList");
  root.innerHTML = state.decks.map(deck => `
    <button class="deck-list-item${deck.id === state.activeDeckId ? " active" : ""}" data-deck-id="${deck.id}">
      <span class="deck-cover">${deck.coverImagePath ? `<img src="${escapeHtml(deck.coverImagePath)}" alt="" />` : ""}</span>
      <span class="deck-list-copy"><strong>${escapeHtml(deck.name)}</strong><span>${deck.mainCount} main / ${deck.missingCount} missing</span></span>
    </button>`).join("");
}

// Pure aggregation over a deck's cards + the shared price cache — single source of truth
// reused by both the Deck Summary sparkline and the full Analysis tab.
function computeDeckStats(cards, prices) {
  const energyCurve = new Array(8).fill(0); // index 0-6 individual energy costs, 7 = "7+"
  const typeCounts = new Map();
  const domainCounts = new Map();
  let full = 0, partial = 0, missing = 0, missingCost = 0;
  const missingRows = [];

  for (const row of cards) {
    const card = row.card;
    if (typeof card.energy === "number") energyCurve[Math.max(0, Math.min(7, card.energy))] += row.quantity;

    const type = groupKey(card);
    typeCounts.set(type, (typeCounts.get(type) || 0) + row.quantity);

    const domains = card.domains?.length ? card.domains : ["Colorless"];
    for (const domain of domains) {
      const name = domainName(domain);
      domainCounts.set(name, (domainCounts.get(name) || 0) + row.quantity);
    }

    if (row.owned <= 0) missing++;
    else if (row.missing > 0) partial++;
    else full++;

    if (row.missing > 0) {
      const unitPrice = Number(prices[card.id]?.marketPrice) || 0;
      const cost = unitPrice * row.missing;
      missingCost += cost;
      missingRows.push({ card, missing: row.missing, unitPrice, cost });
    }
  }

  const typeTotal = [...typeCounts.values()].reduce((sum, n) => sum + n, 0) || 1;
  const typeDistribution = TYPE_GROUP_ORDER.filter(type => typeCounts.has(type))
    .map(type => ({ label: type, count: typeCounts.get(type), pct: typeCounts.get(type) * 100 / typeTotal }));

  const domainTotal = [...domainCounts.values()].reduce((sum, n) => sum + n, 0) || 1;
  const domainBalance = [...domainCounts.entries()].sort((a, b) => b[1] - a[1])
    .map(([label, count]) => ({ label, count, pct: count * 100 / domainTotal }));

  return {
    energyCurve, typeDistribution, domainBalance,
    completion: { full, partial, missing },
    missingCost,
    mostExpensiveMissing: missingRows.sort((a, b) => b.cost - a.cost).slice(0, 4)
  };
}

function deckSummaryMarkup(detail) {
  const summary = detail.summary;
  const legend = detail.cards.find(row => row.card.type === "Legend")?.card;
  const domains = legend?.domains?.length ? legend.domains : [];
  const stats = computeDeckStats(detail.cards, state.prices);
  const maxEnergy = Math.max(1, ...stats.energyCurve);
  const totalCards = summary.mainCount + summary.sideboardCount;
  const ownedPct = totalCards ? Math.round(summary.ownedCount * 100 / totalCards) : 0;
  return `
    <aside class="deck-summary">
      <button type="button" class="command-btn quiet deck-change-legend" id="changeLegendBtn">${icon("refresh")}Change Legend</button>
      ${legend
        ? `<h3>${escapeHtml(legend.name)}</h3><div class="deck-summary-domains">${domains.map(d => `<span style="color:${DOMAIN_COLOR[domainName(d)] || "var(--c-colorless)"}">${escapeHtml(domainName(d))}</span>`).join(" &middot; ")}</div>`
        : `<h3>No Legend</h3>`}
      <div class="analytics-progress deck-summary-completion"><span style="width:${ownedPct}%"></span></div>
      <span class="deck-summary-completion-label">${ownedPct}% complete</span>
      <div class="mini-curve">${stats.energyCurve.map(count => `<span class="mini-curve-bar" style="height:${count ? Math.max(8, count * 100 / maxEnergy) : 2}%"></span>`).join("")}</div>
      <div class="deck-summary-dots">
        <div class="deck-summary-dot-row"><span class="dot full"></span>Fully Owned<b>${stats.completion.full}</b></div>
        <div class="deck-summary-dot-row"><span class="dot partial"></span>Partially Owned<b>${stats.completion.partial}</b></div>
        <div class="deck-summary-dot-row"><span class="dot missing"></span>Missing<b>${stats.completion.missing}</b></div>
      </div>
      <div class="deck-summary-cost"><span>Estimated Missing Cost</span><b>${formatMoney(stats.missingCost)}</b></div>
      <button type="button" class="command-btn deck-view-analysis" id="viewAnalysisBtn">${icon("chart")}View Analysis</button>
    </aside>`;
}

function energyCurveChartMarkup(energyCurve) {
  const max = Math.max(1, ...energyCurve);
  const labels = ["0", "1", "2", "3", "4", "5", "6", "7+"];
  return `<div class="energy-curve-chart">${energyCurve.map((count, i) => `
    <div class="energy-curve-col"><span class="energy-curve-count">${count || ""}</span><span class="energy-curve-bar" style="height:${count ? Math.max(6, count * 100 / max) : 2}%"></span><label>${labels[i]}</label></div>`).join("")}</div>`;
}

function countDistributionMarkup(rows, colorFor) {
  return `<div class="distribution-list">${rows.map(row => `
    <div class="distribution-row"><span>${escapeHtml(row.label)}</span><div class="distribution-bar"><span style="width:${row.pct}%;background:${colorFor ? colorFor(row) : "var(--gold)"}"></span></div><b>${row.count}</b></div>`).join("")}</div>`;
}

function renderDeckAnalysis(root, detail) {
  const stats = computeDeckStats(detail.cards, state.prices);
  const totalQty = detail.cards.reduce((sum, row) => sum + row.quantity, 0) || 1;
  const weightedEnergy = detail.cards.reduce((sum, row) =>
    sum + (typeof row.card.energy === "number" ? row.card.energy * row.quantity : 0), 0);
  const totalUnique = detail.cards.length || 1;
  const completePct = Math.round(stats.completion.full * 100 / totalUnique);
  root.innerHTML = `
    <div class="deck-analysis analytics-grid">
      <div class="analytics-panel">
        <div class="panel-head"><h2>Energy Curve</h2><span>Avg ${(weightedEnergy / totalQty).toFixed(1)}</span></div>
        ${energyCurveChartMarkup(stats.energyCurve)}
      </div>
      <div class="analytics-panel">
        <div class="panel-head"><h2>Card Type Distribution</h2></div>
        ${stats.typeDistribution.length ? countDistributionMarkup(stats.typeDistribution) : `<span class="loading-line">Deck is empty</span>`}
      </div>
      <div class="analytics-panel">
        <div class="panel-head"><h2>Collection Completion</h2><span>${completePct}%</span></div>
        <div class="analytics-progress"><span style="width:${completePct}%"></span></div>
        <div class="distribution-list" style="margin-top:12px">
          <div class="distribution-row"><span>Fully owned</span><div></div><b>${stats.completion.full}</b></div>
          <div class="distribution-row"><span>Partially owned</span><div></div><b>${stats.completion.partial}</b></div>
          <div class="distribution-row"><span>Missing</span><div></div><b>${stats.completion.missing}</b></div>
        </div>
      </div>
      <div class="analytics-panel">
        <div class="panel-head"><h2>Domain Balance</h2></div>
        ${stats.domainBalance.length ? countDistributionMarkup(stats.domainBalance, row => DOMAIN_COLOR[row.label] || "var(--c-colorless)") : `<span class="loading-line">Deck is empty</span>`}
      </div>
      <div class="analytics-panel"><div class="panel-head"><h2>Community Comparison</h2></div><div id="deckCommunityComparison"></div></div>
      <div class="analytics-panel">
        <div class="panel-head"><h2>Cost &amp; Ownership Insights</h2></div>
        <div class="distribution-list">
          <div class="distribution-row"><span>Fully owned cards</span><div></div><b>${stats.completion.full}</b></div>
          <div class="distribution-row"><span>Partially owned cards</span><div></div><b>${stats.completion.partial}</b></div>
          <div class="distribution-row"><span>Missing cards</span><div></div><b>${stats.completion.missing}</b></div>
        </div>
        <div class="deck-summary-cost" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-soft);"><span>Estimated missing cost</span><b>${formatMoney(stats.missingCost)}</b></div>
      </div>
      <div class="analytics-panel"><div class="panel-head"><h2>Top Recommended Upgrades</h2></div><div id="deckTopUpgrades"></div></div>
      <div class="analytics-panel wide">
        <div class="panel-head"><h2>Most Expensive Missing Cards</h2></div>
        <div class="valuable-list">${stats.mostExpensiveMissing.length ? stats.mostExpensiveMissing.map(row => `
          <div class="valuable-row"><div class="valuable-art"><img src="${escapeHtml(cardImage(row.card))}" alt="" />${cardImagePopout(row.card)}</div><div><strong>${escapeHtml(row.card.name)}</strong><span>${row.missing} missing</span></div><b>${formatMoney(row.cost)}</b></div>`).join("")
          : `<span class="loading-line">Nothing missing &mdash; deck is complete</span>`}</div>
      </div>
    </div>`;
  renderIcons(root);
  renderEmptyPanel(document.getElementById("deckCommunityComparison"), {
    icon: "chart", title: "No community data yet", body: "Community deck comparisons aren't synced yet."
  });
  renderEmptyPanel(document.getElementById("deckTopUpgrades"), {
    icon: "star", title: "No community data yet", body: "Upgrade suggestions need synced tournament data."
  });
  loadCommunityAnalysis(detail).catch(err => toast(err.message, true));
}

async function loadCommunityAnalysis(detail) {
  const legendRow = detail.cards.find(row => row.card.type === "Legend");
  if (!legendRow) return;

  const recs = await api(`/api/decks/${detail.summary.id}/recommendations?${queryString({ legendCardId: legendRow.cardId })}`);
  const comparisonEl = document.getElementById("deckCommunityComparison");
  const upgradesEl = document.getElementById("deckTopUpgrades");
  if (!comparisonEl || !upgradesEl || !recs.length) return;

  registerCards(recs.map(r => r.card));

  const comparisonRows = recs
    .filter(r => r.currentDeckQuantity < Math.round(r.averageCopies))
    .slice(0, 8);
  comparisonEl.innerHTML = comparisonRows.length
    ? comparisonRows.map(r => `
      <div class="distribution-row"><span>${escapeHtml(r.card.name)}</span><div class="distribution-bar"><span style="width:${r.inclusionRate}%;background:var(--gold)"></span></div><b>${r.inclusionRate}%</b></div>`).join("")
    : `<span class="loading-line">Your deck matches the community build closely.</span>`;

  const upgrades = recs.filter(r => r.currentDeckQuantity === 0).slice(0, 5);
  upgradesEl.innerHTML = upgrades.length
    ? upgrades.map(r => {
        const price = state.prices[r.card.id]?.marketPrice;
        const status = r.ownedCount > 0 ? "Owned" : (price != null ? formatMoney(price) : "Missing");
        return `
      <div class="valuable-row"><div class="valuable-art"><img src="${escapeHtml(cardImage(r.card))}" alt="" />${cardImagePopout(r.card)}</div><div><strong>${escapeHtml(r.card.name)}</strong><span>${r.inclusionRate}% of decks &middot; avg ${r.averageCopies}x</span></div><b class="${r.ownedCount > 0 ? "owned" : "missing"}">${status}</b></div>`;
      }).join("")
    : `<span class="loading-line">No missing staples &mdash; deck already has the community's top picks.</span>`;
  renderIcons(comparisonEl);
  renderIcons(upgradesEl);
}

function renderDeckWorkspace() {
  const root = document.getElementById("deckWorkspace");
  const detail = state.activeDeck;
  const summary = detail.summary;
  const sectionCards = detail.cards.filter(row => row.section === state.discoverSection);
  const groups = [...new Set(sectionCards.map(row => groupKey(row.card)))]
    .sort((a, b) => {
      const ai = TYPE_GROUP_ORDER.indexOf(a), bi = TYPE_GROUP_ORDER.indexOf(b);
      return (ai === -1 ? TYPE_GROUP_ORDER.length : ai) - (bi === -1 ? TYPE_GROUP_ORDER.length : bi);
    });
  const ownedPct = summary.mainCount + summary.sideboardCount
    ? Math.round(summary.ownedCount * 100 / (summary.mainCount + summary.sideboardCount)) : 0;
  root.innerHTML = `
    <section class="deck-header">
      <div class="deck-hero-art">${summary.coverImagePath ? `<img src="${escapeHtml(summary.coverImagePath)}" alt="" />` : ""}</div>
      <div class="deck-header-copy">
        <div class="deck-title-row"><input id="activeDeckName" value="${escapeHtml(summary.name)}" aria-label="Deck name" /><button class="icon-btn" id="saveDeckMeta" title="Save deck">${icon("save")}</button></div>
        <textarea id="activeDeckDescription" aria-label="Deck description" placeholder="Deck description">${escapeHtml(summary.description)}</textarea>
        <div class="deck-stat-row">
          <div class="deck-stat"><b>${summary.mainCount}</b><span>Main deck</span></div>
          <div class="deck-stat"><b>${summary.sideboardCount}</b><span>Sideboard</span></div>
          <div class="deck-stat"><b>${summary.uniqueCards}</b><span>Unique</span></div>
          <div class="deck-stat"><b>${summary.missingCount}</b><span>Missing</span></div>
          <div class="deck-stat"><b>${ownedPct}%</b><span>Ready</span></div>
        </div>
        <div class="deck-actions"><button class="command-btn" id="testDrawBtn">${icon("shuffle")}Test Draw</button><button class="command-btn quiet" id="exportDeckBtn">${icon("download")}Export</button><button class="command-btn quiet" id="markDeckTradeBtn" title="Mark every card in this deck as available in your Trade Binder">${icon("book-open")}Mark for Trade</button><button class="command-btn quiet" id="deleteDeckBtn">${icon("trash")}Delete</button></div>
      </div>
    </section>
    <div class="deck-tabs">
      <button class="deck-tab${state.deckTab === "builder" ? " active" : ""}" data-deck-tab="builder">Builder</button>
      <button class="deck-tab${state.deckTab === "analysis" ? " active" : ""}" data-deck-tab="analysis">Analysis</button>
    </div>
    <div id="deckTabBody"></div>`;
  renderIcons(root);
  if (state.deckTab === "analysis") {
    renderDeckAnalysis(document.getElementById("deckTabBody"), detail);
  } else {
    document.getElementById("deckTabBody").innerHTML = `
      <div class="deck-builder">
        ${deckSummaryMarkup(detail)}
        <div class="deck-card-list">
          <div class="deck-section-tabs">
            <button type="button" class="deck-section-tab${state.discoverSection === "main" ? " active" : ""}" data-deck-section="main">Main Deck<b>${summary.mainCount}</b></button>
            <button type="button" class="deck-section-tab${state.discoverSection === "sideboard" ? " active" : ""}" data-deck-section="sideboard">Sideboard<b>${summary.sideboardCount}</b></button>
          </div>
          ${groups.length ? groups.map(group => deckGroupMarkup(group, sectionCards.filter(row => groupKey(row.card) === group))).join("") : `<div class="page-empty"><h2>${state.discoverSection === "main" ? "Main deck" : "Sideboard"} is empty</h2></div>`}
        </div>
        ${discoverPanelMarkup()}
      </div>`;
    renderIcons(root);
  }
  wireDeckWorkspace();
}

function ownershipPill(row) {
  if (row.owned <= 0) return `<span class="ownership-badge missing" title="${row.missing} missing">${row.missing}</span>`;
  if (row.missing > 0) return `<span class="ownership-badge partial" title="${row.owned}/${row.quantity} owned, ${row.missing} missing">${row.missing}</span>`;
  return `<span class="ownership-badge full" title="Fully owned">${icon("check")}</span>`;
}

function showDeckRowPopup(cardId, event) {
  const card = cardsById.get(cardId);
  if (!card) return;
  const popup = document.getElementById("deckRowPopup");
  popup.innerHTML = `<img src="${escapeHtml(cardImage(card))}" alt="" />`;
  popup.hidden = false;
  positionDeckRowPopup(event);
}

function positionDeckRowPopup(event) {
  const popup = document.getElementById("deckRowPopup");
  if (popup.hidden) return;
  const margin = 16;
  const width = popup.offsetWidth || 260;
  const height = popup.offsetHeight || 363;
  // Anchor the popup's bottom-left corner near the cursor: it opens up and to the right.
  let x = event.clientX + margin;
  if (x + width > window.innerWidth - 8) x = event.clientX - margin - width; // flip left if no room on the right
  let y = event.clientY - height - margin;
  if (y < 8) y = event.clientY + margin; // flip below if no room above
  y = Math.max(8, Math.min(y, window.innerHeight - height - 8));
  popup.style.left = `${x}px`;
  popup.style.top = `${y}px`;
}

function hideDeckRowPopup() {
  document.getElementById("deckRowPopup").hidden = true;
}

// Recommended-tab rows get a stats popup instead of the plain image popup other Discover tabs
// use — the whole point of that tab is "why is this recommended", not "what does it look like".
function showRecommendationPopup(cardId, event) {
  const rec = state.recommendedRowsById?.get(cardId);
  if (!rec) return;
  const popup = document.getElementById("deckRowPopup");
  popup.innerHTML = `
    <div class="rec-popup">
      <strong>${escapeHtml(rec.card.name)}</strong>
      <div class="rec-popup-stat"><span>Played in</span><b>${rec.inclusionRate}% of decks</b></div>
      <div class="rec-popup-stat"><span>Sample size</span><b>${rec.deckCount} / ${rec.totalDecks} decks</b></div>
      <div class="rec-popup-stat"><span>Average copies</span><b>${rec.averageCopies}x</b></div>
      <div class="rec-popup-stat"><span>Usually in</span><b>${rec.section === "sideboard" ? "Sideboard" : "Main Deck"}</b></div>
      <div class="rec-popup-stat"><span>You own</span><b>${rec.ownedCount}</b></div>
      ${rec.tournaments.length ? `<div class="rec-popup-tournaments"><span>Seen in</span><ul>${rec.tournaments.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</ul></div>` : ""}
    </div>`;
  popup.hidden = false;
  positionDeckRowPopup(event);
}

function deckGroupMarkup(group, rows) {
  const count = rows.reduce((sum, row) => sum + row.quantity, 0);
  return `<section class="deck-group"><div class="deck-group-head"><span>${escapeHtml(group)}</span><b>${count}</b></div>${rows.map(row => `
    <div class="deck-row" data-hover-card="${escapeHtml(row.cardId)}">
      <img class="deck-row-bust" src="${escapeHtml(cardImage(row.card))}" alt="" aria-hidden="true" />
      <div class="deck-row-copy"><strong>${escapeHtml(row.card.name)}</strong><span>${escapeHtml(row.card.setId)}-${escapeHtml(cardCode(row.card))} / ${escapeHtml(row.section)}</span></div>
      ${row.missing > 0
        ? `<button type="button" class="deck-row-acquire" data-acquire-card="${escapeHtml(row.cardId)}" title="Add 1 copy of this card to your Vault">Acquired</button>`
        : `<span class="deck-row-acquire-slot"></span>`}
      ${ownershipPill(row)}
      <div class="mini-stepper"><button data-deck-qty="${row.quantity - 1}" data-card-id="${escapeHtml(row.cardId)}" data-section="${row.section}">-</button><span>${row.quantity}</span><button data-deck-qty="${row.quantity + 1}" data-card-id="${escapeHtml(row.cardId)}" data-section="${row.section}">+</button></div>
    </div>`).join("")}</section>`;
}

function wireDeckWorkspace() {
  const root = document.getElementById("deckWorkspace");
  const save = () => saveDeckMetadata().catch(err => toast(err.message, true));
  root.querySelector("#saveDeckMeta")?.addEventListener("click", save);
  root.querySelector("#activeDeckName")?.addEventListener("change", save);
  root.querySelector("#activeDeckDescription")?.addEventListener("change", save);
  root.querySelector("#deleteDeckBtn")?.addEventListener("click", deleteActiveDeck);
  root.querySelector("#exportDeckBtn")?.addEventListener("click", openExportModal);
  root.querySelector("#testDrawBtn")?.addEventListener("click", openTestHand);
  root.querySelector("#markDeckTradeBtn")?.addEventListener("click", () => markDeckForTrade().catch(err => toast(err.message, true)));
  root.querySelector("#changeLegendBtn")?.addEventListener("click", openChangeLegendModal);
  root.querySelector("#viewAnalysisBtn")?.addEventListener("click", () => {
    state.deckTab = "analysis";
    saveNavState();
    renderDeckWorkspace();
  });
  root.querySelectorAll("[data-deck-qty]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.cardId, Number(button.dataset.deckQty), button.dataset.section)));
  root.querySelectorAll("[data-acquire-card]").forEach(button => button.addEventListener("click", event => {
    event.stopPropagation();
    // Disable immediately, before the async call — a second real click landing before this one's
    // response updates cardsById would otherwise read the same pre-click ownedCount and compute the
    // same target quantity as the first click, silently doing nothing. The re-render this triggers
    // replaces this button outright (removed once fully owned, or a fresh enabled one otherwise), so
    // there's no separate re-enable path needed for the success case — only the catch needs one.
    if (button.disabled) return;
    button.disabled = true;
    const card = cardsById.get(button.dataset.acquireCard);
    if (!card) { button.disabled = false; return; }
    changeOwned(card, 1).catch(err => { toast(err.message, true); button.disabled = false; });
  }));
  root.querySelectorAll(".deck-row[data-hover-card]").forEach(row => row.addEventListener("click", event => {
    if (event.target.closest(".mini-stepper, .deck-row-acquire")) return;
    openFullscreenCardImage(row.dataset.hoverCard);
  }));
  root.querySelectorAll("[data-deck-tab]").forEach(button => button.addEventListener("click", () => {
    state.deckTab = button.dataset.deckTab;
    saveNavState();
    renderDeckWorkspace();
  }));
  root.querySelectorAll("[data-deck-section]").forEach(button => button.addEventListener("click", () => {
    state.discoverSection = button.dataset.deckSection;
    renderDeckWorkspace();
  }));
  wireDiscoverPanel();
}

async function saveDeckMetadata() {
  const name = document.getElementById("activeDeckName").value.trim();
  const description = document.getElementById("activeDeckDescription").value.trim();
  await api(`/api/decks/${state.activeDeckId}`, jsonOptions("PUT", { name, description, format: state.activeDeck.summary.format }));
  toast("Deck saved");
  await loadDecks();
}

const DISCOVER_TABS = [
  { id: "recommended", label: "Recommended" },
  { id: "collection", label: "My Collection" },
  { id: "all", label: "All Cards" },
  { id: "missing", label: "Missing" }
];

function discoverPanelMarkup() {
  return `
    <aside class="discover-panel">
      <div class="discover-tabs">${DISCOVER_TABS.map(tab => `<button class="discover-tab${state.discoverTab === tab.id ? " active" : ""}" data-discover-tab="${tab.id}">${escapeHtml(tab.label)}</button>`).join("")}</div>
      <input id="discoverSearch" placeholder="Search by name or number" value="${escapeHtml(state.discoverSearch)}" />
      <div class="discover-pagination" id="discoverPagination"></div>
      <div class="discover-section-hint">Adding to <b>${state.discoverSection === "main" ? "Main Deck" : "Sideboard"}</b></div>
      <div class="discover-results" id="discoverResults"></div>
    </aside>`;
}

function discoverCardRow(card, group) {
  const existing = state.activeDeck.cards.find(row => row.cardId === card.id && row.section === state.discoverSection);
  const qty = existing?.quantity || 0;
  const hasVariants = group && group.variants.length > 1;
  return `
    <div class="deck-search-row${card.ownedCount > 0 ? " owned" : ""}" data-hover-card="${escapeHtml(card.id)}">
      <div class="deck-search-art"><img src="${escapeHtml(cardImage(card))}" alt="" />${cardImagePopout(card)}</div>
      <div><strong>${escapeHtml(hasVariants ? group.baseName : card.name)}</strong><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))} / own ${card.ownedCount}</span></div>
      ${qty > 0
        ? `<div class="mini-stepper"><button data-discover-qty="${qty - 1}" data-card-id="${escapeHtml(card.id)}">-</button><span>${qty}</span><button data-discover-qty="${qty + 1}" data-card-id="${escapeHtml(card.id)}">+</button></div>`
        : `<button class="icon-btn" data-discover-add="${escapeHtml(card.id)}">${icon("plus")}</button>`}
    </div>`;
}

function discoverGroupMarkup(group) {
  if (group.variants.length === 1) return discoverCardRow(group.variants[0]);
  const selectedId = state.discoverVariantSelection.get(group.baseName) || group.variants[0].id;
  const card = group.variants.find(v => v.id === selectedId) || group.variants[0];
  return `
    <div class="discover-group-wrap">
      ${discoverCardRow(card, group)}
      <div class="discover-variant-strip">${group.variants.map(v => {
        const caution = discoverVariantCaution(v);
        return `
        <button type="button" class="discover-variant-seg${v.id === card.id ? " active" : ""}${v.ownedCount > 0 ? " owned" : ""}" data-discover-group="${escapeHtml(group.baseName)}" data-discover-variant="${escapeHtml(v.id)}" title="${caution === "not-owned" ? "Not owned" : caution === "not-enough" ? `Only own ${v.ownedCount}, not enough for the deck` : `Owned (${v.ownedCount})`}">
          ${caution ? `<span class="discover-variant-caution ${caution}">${icon("alert-triangle")}</span>` : ""}
          ${escapeHtml(legendVariantLabel(v, group.variants))}
        </button>`;
      }).join("")}</div>
    </div>`;
}

// Red = don't own this print at all. Orange = own some copies, but fewer than this deck
// currently wants (only meaningful when the variant is actually in the deck).
function discoverVariantCaution(v) {
  if (v.ownedCount <= 0) return "not-owned";
  const existing = state.activeDeck.cards.find(row => row.cardId === v.id && row.section === state.discoverSection);
  const deckQty = existing?.quantity || 0;
  if (deckQty > 0 && v.ownedCount < deckQty) return "not-enough";
  return null;
}

// Implementation-neutral placeholder used by any not-yet-implemented module (Recommended
// discovery tab today; Analysis' Community Comparison / Top Recommended Upgrades once the
// TopDeck.gg-backed recommendation endpoint lands).
function renderEmptyPanel(container, { icon: iconName, title, body }) {
  container.innerHTML = `<div class="seam-empty">${icon(iconName)}<h4>${escapeHtml(title)}</h4><p>${escapeHtml(body)}</p></div>`;
  renderIcons(container);
}

function recommendationRow(rec) {
  const card = rec.card;
  const existing = state.activeDeck.cards.find(row => row.cardId === card.id && row.section === state.discoverSection);
  const qty = existing?.quantity || 0;
  return `
    <div class="deck-search-row${rec.ownedCount > 0 ? " owned" : ""}" data-hover-rec="${escapeHtml(card.id)}">
      <div class="deck-search-art"><img src="${escapeHtml(cardImage(card))}" alt="" />${cardImagePopout(card)}</div>
      <div><strong>${escapeHtml(card.name)}</strong><span>${rec.inclusionRate}% of decks &middot; avg ${rec.averageCopies}x &middot; own ${rec.ownedCount}</span></div>
      ${qty > 0
        ? `<div class="mini-stepper"><button data-discover-qty="${qty - 1}" data-card-id="${escapeHtml(card.id)}">-</button><span>${qty}</span><button data-discover-qty="${qty + 1}" data-card-id="${escapeHtml(card.id)}">+</button></div>`
        : `<button class="icon-btn" data-discover-add="${escapeHtml(card.id)}">${icon("plus")}</button>`}
    </div>`;
}

async function renderRecommendedTab(root) {
  const legendRow = state.activeDeck.cards.find(row => row.card.type === "Legend");
  if (!legendRow) {
    renderEmptyPanel(root, { icon: "star", title: "No Legend yet", body: "Choose a Legend for this deck first." });
    return;
  }
  const cacheKey = `${state.activeDeckId}|${legendRow.cardId}`;
  let recs;
  if (state.recommendedCache.key === cacheKey) {
    recs = state.recommendedCache.recs;
  } else {
    try {
      recs = await api(`/api/decks/${state.activeDeckId}/recommendations?${queryString({ legendCardId: legendRow.cardId })}`);
    } catch (err) {
      renderEmptyPanel(root, { icon: "star", title: "Couldn't load recommendations", body: err.message });
      return;
    }
    state.recommendedCache = { key: cacheKey, recs };
  }
  if (!recs.length) {
    renderEmptyPanel(root, {
      icon: "star", title: "No community data yet",
      body: `Sync tournament data in Settings, or nobody's reported a ${legendRow.card.name.split(" - ")[0]} deck yet.`
    });
    return;
  }
  registerCards(recs.map(r => r.card));
  // Match on the full printed name so "shen" matches "Shen, Eye of Twilight", "eye of twilight"
  // matches it too, and any variant suffix (e.g. "(Metal)") is searchable the same way.
  const search = state.discoverSearch.trim().toLowerCase();
  const filtered = search ? recs.filter(r => r.card.name.toLowerCase().includes(search)) : recs;
  if (!filtered.length) {
    renderEmptyPanel(root, { icon: "search", title: "No cards found", body: "Try a different search." });
    return;
  }
  state.recommendedRowsById = new Map(filtered.map(r => [r.card.id, r]));
  root.innerHTML = filtered.map(recommendationRow).join("");
  renderIcons(root);
  root.querySelectorAll("[data-discover-add]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.discoverAdd, 1, state.discoverSection)));
  root.querySelectorAll("[data-discover-qty]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.cardId, Number(button.dataset.discoverQty), state.discoverSection)));
}

async function renderDiscoverResults() {
  const root = document.getElementById("discoverResults");
  const pageRoot = document.getElementById("discoverPagination");
  if (!root) return;
  if (state.discoverTab === "recommended") {
    if (pageRoot) pageRoot.innerHTML = "";
    await renderRecommendedTab(root);
    return;
  }
  const owned = state.discoverTab === "collection" ? "owned" : state.discoverTab === "missing" ? "missing" : "";
  const search = state.discoverSearch.trim();
  // Deck add/remove/qty changes re-render this panel constantly but never change which cards
  // match the current search/tab — only re-fetch the (potentially 1000+ row) catalog query when
  // the actual filter criteria changed, not on every deck mutation.
  const cacheKey = `${state.discoverTab}|${search}`;
  let cards;
  if (state.discoverCache.key === cacheKey) {
    cards = state.discoverCache.cards;
  } else {
    cards = await api(`/api/cards?${queryString({ search, owned, sort: "name-asc" })}`);
    state.discoverCache = { key: cacheKey, cards };
  }
  registerCards(cards);
  if (!cards.length) {
    if (pageRoot) pageRoot.innerHTML = "";
    renderEmptyPanel(root, { icon: "search", title: "No cards found", body: "Try a different search." });
    return;
  }
  const allGroups = groupLegendVariants(cards);
  const pageSize = state.discoverPageSize;
  const totalPages = Math.max(1, Math.ceil(allGroups.length / pageSize));
  state.discoverPage = Math.min(Math.max(1, state.discoverPage), totalPages);
  const start = (state.discoverPage - 1) * pageSize;
  const groups = allGroups.slice(start, start + pageSize);
  root.innerHTML = groups.map(discoverGroupMarkup).join("");
  if (pageRoot) pageRoot.innerHTML = discoverPaginationMarkup(allGroups.length, totalPages);
  renderIcons(root);
  renderIcons(pageRoot);
  root.querySelectorAll("[data-discover-add]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.discoverAdd, 1, state.discoverSection)));
  root.querySelectorAll("[data-discover-qty]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.cardId, Number(button.dataset.discoverQty), state.discoverSection)));
  root.querySelectorAll("[data-discover-variant]").forEach(button => button.addEventListener("click", () => {
    state.discoverVariantSelection.set(button.dataset.discoverGroup, button.dataset.discoverVariant);
    renderDiscoverResults().catch(err => toast(err.message, true));
  }));
  pageRoot?.querySelectorAll("[data-discover-page]").forEach(button => button.addEventListener("click", () => {
    state.discoverPage = Number(button.dataset.discoverPage);
    renderDiscoverResults().catch(err => toast(err.message, true));
  }));
  pageRoot?.querySelector("#discoverPageSize")?.addEventListener("change", event => {
    state.discoverPageSize = Number(event.target.value);
    state.discoverPage = 1;
    renderDiscoverResults().catch(err => toast(err.message, true));
  });
}

function discoverPaginationMarkup(total, totalPages) {
  const page = state.discoverPage;
  return `
    <label class="discover-page-size">Show
      <select id="discoverPageSize">${[10, 25, 50, 100].map(n =>
        `<option value="${n}"${n === state.discoverPageSize ? " selected" : ""}>${n}</option>`).join("")}</select>
    </label>
    <div class="discover-page-nav">
      <button type="button" class="icon-btn" data-discover-page="${page - 1}"${page <= 1 ? " disabled" : ""}>&lsaquo;</button>
      <span>${page}/${totalPages} &middot; ${total}</span>
      <button type="button" class="icon-btn" data-discover-page="${page + 1}"${page >= totalPages ? " disabled" : ""}>&rsaquo;</button>
    </div>`;
}

function wireDiscoverPanel() {
  const root = document.getElementById("deckWorkspace");
  const refresh = () => renderDiscoverResults().catch(err => toast(err.message, true));
  root.querySelectorAll("[data-discover-tab]").forEach(button => button.addEventListener("click", () => {
    state.discoverTab = button.dataset.discoverTab;
    state.discoverPage = 1;
    root.querySelectorAll("[data-discover-tab]").forEach(item => item.classList.toggle("active", item === button));
    refresh();
  }));
  root.querySelector("#discoverSearch")?.addEventListener("input", event => {
    state.discoverSearch = event.target.value;
    state.discoverPage = 1;
    clearTimeout(state.deckSearchTimer);
    state.deckSearchTimer = setTimeout(refresh, 220);
  });
  refresh();
}

async function setDeckCard(deckId, cardId, quantity, section) {
  // The POST response already IS the fresh DeckDetailDto — no need to re-fetch it via loadDecks().
  // Only the sidebar deck list (counts change) needs a lightweight refresh alongside it.
  state.activeDeck = await api(`/api/decks/${deckId}/cards`, jsonOptions("POST", { cardId, quantity, section }));
  registerCards(state.activeDeck.cards.map(row => row.card));
  await refreshDeckSidebar();
  renderDeckWorkspace();
}

async function refreshDeckSidebar() {
  state.decks = await api("/api/decks");
  document.getElementById("deckLibraryMeta").textContent = `${state.decks.length} deck${state.decks.length === 1 ? "" : "s"}`;
  document.getElementById("navDeckCount").textContent = state.decks.length || "";
  renderDeckList();
}

async function deleteActiveDeck() {
  if (!confirm(`Delete "${state.activeDeck.summary.name}"?`)) return;
  await api(`/api/decks/${state.activeDeckId}`, { method: "DELETE" });
  state.activeDeckId = null;
  state.activeDeck = null;
  toast("Deck deleted");
  await Promise.all([loadDecks(), loadOverview()]);
}

async function markDeckForTrade() {
  if (!confirm(`Mark every card in "${state.activeDeck.summary.name}" as available in your Trade Binder?`)) return;
  const result = await api(`/api/decks/${state.activeDeckId}/mark-as-trade`, jsonOptions("POST", {}));
  const parts = [];
  if (result.updatedCards) parts.push(`${result.updatedCards} card${result.updatedCards === 1 ? "" : "s"} marked for trade`);
  else if (!result.notOwnedCards) parts.push("Every card in this deck was already marked for trade");
  if (result.notOwnedCards) parts.push(`${result.notOwnedCards} card${result.notOwnedCards === 1 ? " isn't" : "s aren't"} owned, so ${result.notOwnedCards === 1 ? "it can't" : "they can't"} be marked`);
  toast(parts.join(". "));
  await loadOverview();
}

function openExportModal() {
  state.exportFormat = state.exportFormat || "riftkeep";
  showModal("exportModal");
  refreshExportPreview();
}

async function fetchExportText(format) {
  const response = await fetch(`/api/decks/${state.activeDeckId}/export?${queryString({ format })}`);
  if (!response.ok) throw new Error("Deck export failed");
  return response.text();
}

async function refreshExportPreview() {
  const root = document.getElementById("exportModal");
  root.querySelectorAll("[data-export-preview]").forEach(button =>
    button.classList.toggle("active", button.dataset.exportPreview === state.exportFormat));
  const preview = document.getElementById("exportPreview");
  preview.value = "Loading...";
  try {
    preview.value = await fetchExportText(state.exportFormat);
  } catch (err) {
    preview.value = "";
    toast(err.message, true);
  }
}

async function exportActiveDeck(format) {
  let contents;
  try {
    contents = await fetchExportText(format);
  } catch (err) {
    return toast(err.message, true);
  }
  const blob = new Blob([contents], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const base = state.activeDeck.summary.name.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "deck";
  const link = document.createElement("a");
  link.href = url;
  link.download = format === "riftatlas" ? `${base}-riftatlas.txt` : `${base}.txt`;
  link.click();
  URL.revokeObjectURL(url);
  toast("Deck exported");
}

function openTestHand() {
  // Runes and Battlefields are both separate resource pools (Rune Deck / Battlefield pool), never
  // drawn alongside Main Deck cards — excluded here even though this app stores all three in the
  // same "main" section.
  const pool = state.activeDeck.cards
    .filter(row => row.section === "main" && row.card.type !== "Rune" && row.card.type !== "Battlefield")
    .flatMap(row => Array.from({ length: row.quantity }, () => row.card));
  if (!pool.length) return toast("Add cards to the deck first", true);
  const draw = () => {
    const shuffled = [...pool].sort(() => Math.random() - .5).slice(0, Math.min(4, pool.length));
    const root = document.getElementById("testHand");
    root.innerHTML = shuffled.map(card => `<div class="test-hand-card"><img src="${escapeHtml(cardImage(card))}" alt="${escapeHtml(card.name)}" title="${escapeHtml(card.name)}" />${cardImagePopout(card)}</div>`).join("");
    renderIcons(root);
  };
  draw();
  document.getElementById("redrawHand").onclick = draw;
  showModal("testHandModal");
}

async function loadAnalytics() {
  await loadOverview();
  const data = state.overview;
  registerCards(data.mostValuable.map(row => row.card));
  document.getElementById("analyticsKpis").innerHTML = [
    ["archive", data.ownedCards, "Unique owned"], ["layers", data.ownedCopies, "Total copies"],
    ["dollar", data.hasPricing ? formatMoney(data.collectionValue) : "--", "Collection value"],
    ["check", `${data.readyDecks}/${data.decks}`, "Decks ready"]
  ].map(([name, value, label]) => `<div class="kpi"><div class="kpi-icon">${icon(name)}</div><div><b>${value}</b><span>${label}</span></div></div>`).join("");

  document.getElementById("setCompletionMeta").textContent = `${data.ownedCards}/${data.totalCards} cards`;
  document.getElementById("analyticsSets").innerHTML = data.sets.map(set => `
    <div class="set-progress-row"><span class="set-code">${escapeHtml(set.setId)}</span><div><span>${escapeHtml(set.setLabel || set.setId)}</span><div class="analytics-progress"><span style="width:${set.completion}%"></span></div></div><b>${Math.round(set.completion)}%</b></div>`).join("");
  renderDistribution("analyticsRarities", data.rarities, row => RARITY_COLOR[row.label] || "var(--gold)");
  renderDistribution("analyticsDomains", data.domains, row => DOMAIN_COLOR[row.label] || "var(--c-colorless)");
  document.getElementById("pricingState").textContent = data.hasPricing ? "Live Riftbound.gg prices" : "Pricing unavailable";
  document.getElementById("valuableCards").innerHTML = data.mostValuable.length ? data.mostValuable.map(row => `
    <div class="valuable-row"><div class="valuable-art"><img src="${escapeHtml(cardImage(row.card))}" alt="" />${cardImagePopout(row.card)}</div><div><strong>${escapeHtml(row.card.name)}</strong><span>${row.card.ownedCount} copies at ${formatMoney(row.unitPrice)}</span></div><b>${formatMoney(row.collectionValue)}</b></div>`).join("") : `<span class="loading-line">No price snapshots yet</span>`;
  document.getElementById("deckReadiness").innerHTML = data.deckReadiness.length ? data.deckReadiness.map(deck => {
    const total = deck.mainCount + deck.sideboardCount;
    const pct = total ? Math.round(deck.ownedCount * 100 / total) : 0;
    return `<div class="readiness-row"><div><strong>${escapeHtml(deck.name)}</strong><b>${pct}%</b></div><div class="analytics-progress"><span style="width:${pct}%"></span></div></div>`;
  }).join("") : `<span class="loading-line">No decks yet</span>`;
  renderIcons(document.getElementById("page-analytics"));
}

function renderDistribution(id, rows, color) {
  document.getElementById(id).innerHTML = rows.map(row => `
    <div class="distribution-row"><span>${escapeHtml(row.label)}</span><div class="distribution-bar"><span style="width:${row.cards ? row.owned * 100 / row.cards : 0}%;background:${typeof color === "function" ? color(row) : color}"></span></div><b>${row.owned}/${row.cards}</b></div>`).join("");
}

async function loadSettings() {
  const [sync, pricing, topdeck, health, server] = await Promise.all([
    api("/api/sync/status"), api("/api/pricing/status"), api("/api/topdeck/status"), api("/api/health"),
    api("/api/server-info")
  ]);
  document.getElementById("catalogStatus").textContent = sync.running
    ? `Syncing ${sync.currentSet || "catalog"}: ${sync.setsDone}/${sync.setsTotal} sets`
    : `${sync.totalCards} cards across ${sync.totalSets} sets. Last synced ${formatRelativeTime(sync.lastSyncedAt)}.`;
  document.getElementById("catalogFacts").innerHTML = state.sets
    .map(set => `<span>${escapeHtml(set.setId)} ${set.owned}/${set.total}</span>`).join("");
  document.getElementById("pricingStatus").textContent = pricing.configured
    ? `Riftbound.gg live pricing enabled. ${pricing.provider} snapshots configured (${pricing.source}, ${pricing.keyHint}).`
    : "Riftbound.gg live pricing enabled. JustTCG snapshots are optional.";
  document.getElementById("topdeckStatus").textContent = topdeck.configured
    ? `Key configured (${topdeck.source}, ${topdeck.keyHint}).`
    : "Add your own TopDeck.gg key to pull community tournament decklists.";
  const communitySync = await api("/api/community-decks/status");
  document.getElementById("communitySyncStatus").textContent = !communitySync.configured
    ? "Add a TopDeck.gg key above, then sync to enable the Recommended tab."
    : communitySync.lastSyncAt
      ? `Last synced ${formatRelativeTime(communitySync.lastSyncAt)}${communitySync.lastSyncOk ? "" : ` — failed: ${communitySync.lastError}`}.`
      : "Never synced yet.";
  document.getElementById("communitySyncFacts").innerHTML = communitySync.lastSyncAt
    ? `<span>${communitySync.tournamentCount} tournaments</span><span>${communitySync.deckCount} decks</span><span>${communitySync.unresolvedCardCount} unresolved cards</span>`
    : "";
  const db = health.database;
  document.getElementById("databaseStatus").textContent = db
    ? `Database verified: ${db.integrity}. Protected collection totals are checked at startup.`
    : "Database is ready.";
  document.getElementById("databaseFacts").innerHTML = db ? `<span>${health.cards} cards now</span><span>${health.ownedCards} owned now</span><span>${health.ownedCopies} copies now</span>${db.lastBackupPath ? `<span>Last migration backup: ${escapeHtml(db.lastBackupPath.split(/[\\/]/).pop())}</span>` : ""}` : "";
  document.getElementById("currentVersion").textContent = server.version;
  document.querySelectorAll("#themeControl button").forEach(button => button.classList.toggle("active", button.dataset.themeValue === document.documentElement.dataset.theme));
}

async function refreshCatalog() {
  const button = document.getElementById("refreshCatalogBtn");
  button.disabled = true;
  try {
    await api("/api/sync/refresh", { method: "POST" });
    toast("Catalog refresh started");
    if (catalogPoll) clearInterval(catalogPoll);
    catalogPoll = setInterval(async () => {
      const status = await api("/api/sync/status");
      const statusEl = document.getElementById("catalogStatus");
      if (statusEl) statusEl.textContent = status.running ? `Syncing ${status.currentSet || "catalog"}: ${status.setsDone}/${status.setsTotal} sets` : "Catalog refresh complete.";
      if (!status.running) {
        clearInterval(catalogPoll); catalogPoll = null;
        button.disabled = false;
        await refreshAfterCollectionChange();
        toast("Catalog refreshed");
      }
    }, 2000);
  } catch (err) {
    button.disabled = false;
    toast(err.message, true);
  }
}

function parseCardEntry(raw) {
  const text = raw.trim();
  // Leading "{qty} " (RiftKeep deck-export format, e.g. "3 SFD-001 Against the Odds") is captured
  // here too, with any trailing card-name text after the code simply ignored — the same shape
  // DeckService.cs's ImportLinePattern matches server-side for deck import, so a pasted decklist
  // and a bare card code both parse through this one pattern.
  const withSet = /^(?:(?<qty>\d{1,2})\s*[xX]?\s+)?(?<set>[A-Za-z]{2,4}|\*)[\s-]+(?<code>[A-Za-z]{0,2}\d{1,3}[A-Za-z]?)\b/.exec(text);
  if (withSet) {
    return {
      setId: withSet.groups.set === "*" ? null : withSet.groups.set.toUpperCase(),
      code: withSet.groups.code.toUpperCase(),
      quantity: withSet.groups.qty ? Math.max(1, Number(withSet.groups.qty)) : null,
    };
  }
  const bare = /^([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)$/.exec(text);
  return bare ? { setId: state.setId, code: bare[1].toUpperCase(), quantity: null } : null;
}

// A deck code is a single unbroken run of base32 characters — mirrors
// RiftAtlasDeckCodeService.LooksLikeDeckCode server-side, just enough to route the paste to the
// decode endpoint instead of the line-by-line parser below (which would otherwise report the
// whole blob as one big "Could not parse" line).
function looksLikeDeckCode(text) {
  const trimmed = text.trim();
  if (trimmed.length < 8 || /\s/.test(trimmed)) return false;
  return /^[A-Za-z2-7]+$/.test(trimmed);
}

// "Add to Collection+" — one modal, three tabs (Mass Add / Scan Card / Import Pack). Scan Card
// hands off to the standalone scanModal instead of embedding the camera UI here, since that modal
// is also reused by Check Price (see setScanMode) and its live-camera lifecycle isn't safe to
// duplicate into a second DOM location.
let packImportLoaded = false; // avoid refetching the pack list every time the tab is reselected

function openAddCollectionModal(tab) {
  showModal("addCollectionModal");
  switchAddCollectionTab(tab || "massAdd");
}

function switchAddCollectionTab(tab) {
  document.querySelectorAll("#addCollectionModal .add-collection-tabs [data-add-tab]").forEach(button =>
    button.classList.toggle("active", button.dataset.addTab === tab));
  document.querySelectorAll("#addCollectionModal .add-collection-panel").forEach(panel => {
    const isActive = panel.dataset.addPanel === tab;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
  // Reopening after an accidental backdrop click / Escape shouldn't wipe an in-progress list —
  // only start fresh if there's nothing left over from before.
  if (tab === "massAdd" && !massAddLines.length) resetMassAdd();
  if (tab === "pack" && !packImportLoaded) {
    packImportLoaded = true;
    openPackImportModal().catch(err => toast(err.message, true));
  }
}

// Mass Add — a growing list of resolved "pill" lines, built either by picking a live search
// result one at a time or by pasting a whole decklist/deck code at once (same parsers as before).
// Hovering a pill previews it big on the right; clicking pins that preview until another pill is
// clicked. Every network call in here is its own try/catch specifically so one bad line (an
// unmatched card, a transient fetch failure) can never silently stop the rest of a batch the way
// the previous single unguarded loop could.

function resetMassAdd() {
  massAddLines = [];
  massAddLockedId = null;
  massAddHoverId = null;
  massAddErrors = [];
  massAddDropdownGroups = [];
  massAddVariantQueue = [];
  massAddVariantMemory.clear();
  clearTimeout(massAddSearchTimer);
  massAddSearchSeq++;
  const input = document.getElementById("massAddEntryInput");
  if (input) input.value = "";
  const dropdown = document.getElementById("massAddDropdown");
  if (dropdown) { dropdown.hidden = true; dropdown.innerHTML = ""; }
  renderMassAddLines();
  renderMassAddPreview();
  updateMassAddSummary();
  renderMassAddErrors();
}

// Toasts fade after a few seconds, which loses the picture on a big paste with several bad lines —
// every per-line failure also lands here so the full error list stays visible in the modal.
function logMassAddError(message) {
  massAddErrors.push(message);
  renderMassAddErrors();
}

function renderMassAddErrors() {
  const box = document.getElementById("massAddErrors");
  if (!box) return;
  if (!massAddErrors.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = `
    <div class="mass-add-errors-head">
      <span>${massAddErrors.length} error${massAddErrors.length === 1 ? "" : "s"}</span>
      <button type="button" id="massAddErrorsClear">Clear</button>
    </div>
    <div class="mass-add-errors-list">${massAddErrors.map(msg => `<div class="mass-add-errors-row">${escapeHtml(msg)}</div>`).join("")}</div>`;
}

function updateMassAddSummary() {
  const count = massAddLines.length;
  const total = massAddLines.reduce((sum, line) => sum + line.quantity, 0);
  document.getElementById("massAddSummary").textContent = count
    ? `${count} card${count === 1 ? "" : "s"}, ${total} cop${total === 1 ? "y" : "ies"}`
    : "";
  document.getElementById("massAddConfirm").disabled = count === 0;
}

function renderMassAddLines() {
  const root = document.getElementById("massAddLines");
  if (!massAddLines.length) {
    root.innerHTML = `<div class="mass-add-lines-empty">No cards added yet — start typing below, or paste a decklist / deck code.</div>`;
    return;
  }
  root.innerHTML = massAddLines.map(line => `
    <div class="mass-add-line${line.id === massAddLockedId ? " locked" : ""}" data-mass-line="${escapeHtml(line.id)}">
      <img src="${escapeHtml(cardImage(line.card))}" alt="" loading="lazy" />
      <span class="mass-add-line-id">[${escapeHtml(line.card.setId)}-${escapeHtml(cardCode(line.card))}]</span>
      <span class="mass-add-line-name">${escapeHtml(line.card.name)}</span>
      <div class="mini-stepper">
        <button type="button" data-mass-qty-delta="-1" data-mass-line-target="${escapeHtml(line.id)}" aria-label="Decrease quantity">-</button>
        <span>${line.quantity}</span>
        <button type="button" data-mass-qty-delta="1" data-mass-line-target="${escapeHtml(line.id)}" aria-label="Increase quantity">+</button>
      </div>
      <button type="button" class="mass-add-line-remove" data-mass-remove="${escapeHtml(line.id)}" aria-label="Remove line">${icon("x")}</button>
    </div>`).join("");
  renderIcons(root);
}

function renderMassAddPreview() {
  const panel = document.getElementById("massAddPreviewPanel");
  const activeId = massAddHoverId ?? massAddLockedId;
  const line = massAddLines.find(l => l.id === activeId);
  if (!line) {
    panel.innerHTML = `<div class="mass-add-preview-empty"><i data-icon="image"></i><span>Hover or click a line to preview it here.</span></div>`;
    renderIcons(panel);
    return;
  }
  const variants = line.variants && line.variants.length > 1 ? line.variants : null;
  panel.innerHTML = `
    <div class="mass-add-preview-card">
      <div class="mass-add-preview-heading">
        <span class="mass-add-preview-heading-add">Add ${line.quantity} to Collection</span>
        <span class="mass-add-preview-heading-owned">${line.card.ownedCount} in Vault</span>
      </div>
      ${variants ? `<div class="legend-variation-strip">${variants.map(v => `
        <button type="button" class="legend-variation-seg${v.id === line.card.id ? " active" : ""}" data-mass-variant-target="${escapeHtml(line.id)}" data-mass-variant="${escapeHtml(v.id)}" title="${escapeHtml(v.name)}">
          <img src="${escapeHtml(cardImage(v))}" alt="" />
          <span>${escapeHtml(legendVariantLabel(v, variants))}</span>
        </button>`).join("")}</div>` : ""}
      <div class="mass-add-preview-art">
        <img src="${escapeHtml(cardImage(line.card))}" alt="${escapeHtml(line.card.name)}" />
        ${line.card.ownedCount > 0 ? `<span class="legend-owned-badge" title="Already own ${line.card.ownedCount}">${icon("check")}</span>` : `<span class="legend-not-owned-banner">Not Owned</span>`}
      </div>
      <div class="mass-add-preview-name"><b>${escapeHtml(line.card.name)}</b><span>${escapeHtml(line.card.setId)}-${escapeHtml(cardCode(line.card))}</span></div>
      ${line.id === massAddLockedId ? `<span class="mass-add-preview-lock">${icon("check")} Locked</span>` : ""}
      <div class="mass-add-preview-qty">
        <label>Quantity</label>
        <div class="mini-stepper">
          <button type="button" data-mass-qty-delta="-1" data-mass-line-target="${escapeHtml(line.id)}" aria-label="Decrease quantity">-</button>
          <span>${line.quantity}</span>
          <button type="button" data-mass-qty-delta="1" data-mass-line-target="${escapeHtml(line.id)}" aria-label="Increase quantity">+</button>
        </div>
      </div>
    </div>`;
  renderIcons(panel);
}

function setMassAddQuantity(lineId, delta) {
  const line = massAddLines.find(l => l.id === lineId);
  if (!line) return;
  line.quantity = Math.max(1, Math.min(99, line.quantity + delta));
  renderMassAddLines();
  renderMassAddPreview();
  updateMassAddSummary();
}

function removeMassAddLine(lineId) {
  massAddLines = massAddLines.filter(l => l.id !== lineId);
  if (massAddLockedId === lineId) massAddLockedId = null;
  if (massAddHoverId === lineId) massAddHoverId = null;
  renderMassAddLines();
  renderMassAddPreview();
  updateMassAddSummary();
}

// `variants` is the full sibling-printing list a card was picked from (e.g. both "Riptide Rex"
// reprints) — kept on the line so the big preview can offer the same BASE/alt-printing strip the
// Legend picker uses, letting a mis-picked printing be corrected after the fact without redoing
// the whole entry.
function addMassAddLine(card, quantity, variants) {
  const qty = quantity && quantity > 0 ? Math.min(99, quantity) : 1;
  const siblingSet = variants && variants.length > 1 ? variants : null;
  const existing = massAddLines.find(l => l.card.id === card.id);
  if (existing) {
    existing.quantity = Math.min(99, existing.quantity + qty);
    if (siblingSet) existing.variants = siblingSet;
    massAddLockedId = existing.id;
  } else {
    const line = { id: `m${++massAddLineSeq}`, card, quantity: qty, variants: siblingSet };
    massAddLines.push(line);
    massAddLockedId = line.id;
  }
  renderMassAddLines();
  renderMassAddPreview();
  updateMassAddSummary();
}

function switchMassAddLineVariant(lineId, variantId) {
  const line = massAddLines.find(l => l.id === lineId);
  if (!line || !line.variants) return;
  const variant = line.variants.find(v => v.id === variantId);
  if (!variant || variant.id === line.card.id) return;
  line.card = variant;
  renderMassAddLines();
  renderMassAddPreview();
}

// Splits a trailing " x3" style quantity off the live-typed search text, so "Blade Fervor x3"
// both searches for "Blade Fervor" and applies quantity 3 to whatever gets picked.
function parseMassAddEntryText(raw) {
  const text = (raw || "").trim();
  const qtyMatch = /\s+[xX](\d{1,2})\s*$/.exec(text);
  return qtyMatch
    ? { searchText: text.slice(0, qtyMatch.index).trim(), quantity: Math.max(1, Number(qtyMatch[1])) }
    : { searchText: text, quantity: null };
}

function scheduleMassAddSearch() {
  clearTimeout(massAddSearchTimer);
  massAddSearchTimer = setTimeout(runMassAddSearch, 160);
}

async function runMassAddSearch() {
  const input = document.getElementById("massAddEntryInput");
  const dropdown = document.getElementById("massAddDropdown");
  const { searchText } = parseMassAddEntryText(input.value);
  if (searchText.length < 2) {
    dropdown.hidden = true;
    dropdown.innerHTML = "";
    return;
  }
  const seq = ++massAddSearchSeq;
  let cards;
  try {
    cards = await api(`/api/cards?${queryString({ search: searchText, sort: "name-asc" })}`);
  } catch (err) {
    if (seq !== massAddSearchSeq) return; // a newer keystroke already superseded this search
    dropdown.hidden = false;
    dropdown.innerHTML = `<div class="mass-add-dropdown-empty">${escapeHtml(err.message)}</div>`;
    return;
  }
  if (seq !== massAddSearchSeq) return;
  registerCards(cards);
  // Group same-name reprints into one tile — picking a grouped tile opens the printing picker
  // instead of listing every variant as its own separate row.
  renderMassAddDropdown(groupLegendVariants(cards).slice(0, 24));
}

function renderMassAddDropdown(groups) {
  const dropdown = document.getElementById("massAddDropdown");
  dropdown.hidden = false;
  massAddDropdownGroups = groups;
  if (!groups.length) {
    dropdown.innerHTML = `<div class="mass-add-dropdown-empty">No matching cards</div>`;
    return;
  }
  dropdown.innerHTML = `<div class="mass-add-dropdown-grid">${groups.map((group, index) => {
    const card = group.variants[0];
    return `
    <button type="button" class="mass-add-dropdown-item" data-mass-pick-group="${index}">
      <img src="${escapeHtml(cardImage(card))}" alt="" loading="lazy" />
      <span class="mass-add-dropdown-item-text"><span class="mass-add-dropdown-item-id">[${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}]</span><span class="mass-add-dropdown-item-name">${escapeHtml(group.baseName)}</span></span>
      ${group.variants.length > 1 ? `<span class="mass-add-dropdown-item-count">${group.variants.length}</span>` : ""}
    </button>`;
  }).join("")}</div>`;
}

function selectMassAddGroup(index) {
  const group = massAddDropdownGroups[index];
  if (!group) return;
  const input = document.getElementById("massAddEntryInput");
  const { quantity } = parseMassAddEntryText(input.value);
  const qty = quantity && quantity > 0 ? quantity : 1;
  input.value = "";
  clearTimeout(massAddSearchTimer);
  massAddSearchSeq++; // discard any in-flight search response for the text that was just replaced
  const dropdown = document.getElementById("massAddDropdown");
  dropdown.hidden = true;
  dropdown.innerHTML = "";
  massAddDropdownGroups = [];
  if (group.variants.length === 1) {
    addMassAddLine(group.variants[0], qty);
  } else {
    // useMemory: false — picking from the live dropdown is a deliberate, individual choice each
    // time (e.g. wanting a second, *different* printing of a card already on the list), so it
    // must always show the picker. Silently reusing the last answer here (as bulk paste does)
    // made a second distinct variant impossible to add at all — reported as issue #2.
    queueMassAddVariantChoice(group, qty, false);
    flushMassAddVariantQueue();
  }
  input.focus();
}

// A same-name group with more than one real printing (e.g. two "Riptide Rex" reprints) can't be
// auto-resolved — queued here so the printing-picker popup can ask once per distinct base name.
// Repeat occurrences of a base name already answered this session reuse that answer silently
// (useMemory: true, the bulk-paste path's default) so a paste with the same ambiguous card on
// several lines only prompts once — but interactive picking (the live dropdown) opts out, since
// there the whole point can be choosing a different variant than last time.
function queueMassAddVariantChoice(group, quantity, useMemory = true) {
  const remembered = useMemory ? massAddVariantMemory.get(group.baseName) : null;
  if (remembered) {
    const variant = group.variants.find(v => v.id === remembered);
    if (variant) { addMassAddLine(variant, quantity, group.variants); return; }
  }
  massAddVariantQueue.push({ group, quantity });
}

function flushMassAddVariantQueue() {
  const modal = document.getElementById("massAddVariantModal");
  if (massAddVariantQueue.length && modal.hidden) showNextMassAddVariantPrompt();
}

function showNextMassAddVariantPrompt() {
  const next = massAddVariantQueue[0];
  if (!next) { closeModal("massAddVariantModal"); return; }
  const { group, quantity } = next;
  document.getElementById("massAddVariantTitle").textContent = `${group.baseName} ×${quantity}`;
  document.getElementById("massAddVariantProgress").textContent =
    massAddVariantQueue.length > 1 ? `${massAddVariantQueue.length} left to resolve` : "";
  const grid = document.getElementById("massAddVariantGrid");
  grid.innerHTML = group.variants.map(v => `
    <button type="button" class="mass-add-variant-tile" data-variant-pick="${escapeHtml(v.id)}">
      <img src="${escapeHtml(cardImage(v))}" alt="" />
      <span>${escapeHtml(legendVariantLabel(v, group.variants))}</span>
      ${v.ownedCount > 0 ? `<em>${icon("check")} own ${v.ownedCount}</em>` : ""}
    </button>`).join("");
  renderIcons(grid);
  showModal("massAddVariantModal");
}

function resolveMassAddVariantPrompt(variantId) {
  const next = massAddVariantQueue.shift();
  if (!next) return;
  if (variantId) {
    const variant = next.group.variants.find(v => v.id === variantId);
    if (variant) {
      massAddVariantMemory.set(next.group.baseName, variantId);
      addMassAddLine(variant, next.quantity, next.group.variants);
    }
  } else {
    logMassAddError(`${next.group.baseName} ×${next.quantity} skipped — add it manually below`);
  }
  if (massAddVariantQueue.length) showNextMassAddVariantPrompt();
  else closeModal("massAddVariantModal");
}

function cancelMassAddVariantQueue() {
  massAddVariantQueue.forEach(item => logMassAddError(`${item.group.baseName} ×${item.quantity} skipped — add it manually below`));
  massAddVariantQueue = [];
}

// Pasting a whole decklist or a RiftAtlas deck code resolves every line in one go, the same way
// the old single big textarea did — reusing the exact same parsers (parseCardEntry/looksLikeDeckCode)
// so every previously-supported paste format still works here.
async function bulkAddMassAddText(raw) {
  if (looksLikeDeckCode(raw)) {
    let decoded;
    try {
      decoded = await api("/api/decks/decode-code", jsonOptions("POST", { contents: raw.trim() }));
    } catch (err) {
      toast(err.message, true);
      return;
    }
    for (const entry of decoded.entries) {
      const label = `${entry.setId}-${entry.code}`;
      try {
        const cards = await api(`/api/cards/lookup?${queryString({ setId: entry.setId, code: entry.code })}`);
        registerCards(cards);
        if (!cards.length) logMassAddError(`No match: ${label}`);
        else if (cards.length > 1) logMassAddError(`${label} is ambiguous — add it manually below`);
        else addMassAddLine(cards[0], entry.quantity);
      } catch (err) {
        logMassAddError(`${label}: ${err.message}`);
      }
    }
    return;
  }
  // Newline-only, not comma-separated — a comma split broke on real card names that contain their
  // own comma (e.g. "Kennen, Keeper of Balance"). Matches DeckService.cs's own import parser.
  const lines = raw.split(/[\r\n]+/).map(value => value.trim()).filter(Boolean);
  for (const line of lines) {
    // RiftKeep deck exports mark section boundaries with "# main" / "# sideboard" comment lines —
    // meaningless here (Mass Add only tracks owned counts, not deck sections).
    if (line.startsWith("#")) continue;
    const quantityMatch = /\s+[xX](\d+)\s*$/.exec(line);
    const trailingQuantity = quantityMatch ? Math.max(1, Number(quantityMatch[1])) : null;
    const entryText = quantityMatch ? line.slice(0, quantityMatch.index).trim() : line;
    const parsed = parseCardEntry(entryText);
    const quantity = trailingQuantity ?? parsed?.quantity ?? 1;
    try {
      let cards;
      let ambiguous = false;
      if (parsed) {
        cards = await api(`/api/cards/lookup?${queryString({ setId: parsed.setId, code: parsed.code })}`);
      } else {
        // Not code-shaped — fall back to a name search (same endpoint the live dropdown uses), so
        // pasted decklists of plain card names ("Blade Fervor x3") resolve just like typed entries.
        cards = await api(`/api/cards?${queryString({ search: entryText, sort: "name-asc" })}`);
        const exact = cards.filter(c => c.name.toLowerCase() === entryText.toLowerCase());
        if (exact.length === 1) cards = exact;
        else if (cards.length > 1) ambiguous = true;
      }
      registerCards(cards);
      if (!cards.length) {
        logMassAddError(`No match: ${line}`);
      } else if (ambiguous || cards.length > 1) {
        // Multiple hits for a plain name are usually just reprints of the one card sharing an
        // identical name (e.g. two "Riptide Rex" printings) — group them, and only fall back to a
        // hard error if the search actually matched genuinely different cards.
        const groups = groupLegendVariants(cards);
        if (groups.length === 1) queueMassAddVariantChoice(groups[0], quantity);
        else logMassAddError(`${line} is ambiguous — add it manually below`);
      } else {
        addMassAddLine(cards[0], quantity);
      }
    } catch (err) {
      logMassAddError(`${line}: ${err.message}`);
    }
  }
  flushMassAddVariantQueue();
}

function handleMassAddPaste(event) {
  const text = event.clipboardData?.getData("text") || "";
  if (!text.includes("\n") && !looksLikeDeckCode(text)) return; // a single card/code — let normal typing-search handle it
  event.preventDefault();
  bulkAddMassAddText(text);
}

async function confirmMassAdd() {
  const button = document.getElementById("massAddConfirm");
  button.disabled = true;
  const lines = [...massAddLines];
  const failedLineIds = new Set();
  let succeeded = 0;
  for (const line of lines) {
    try {
      await api(`/api/collection/${encodeURIComponent(line.card.id)}`, jsonOptions("POST", { owned: line.card.ownedCount + line.quantity }));
      succeeded++;
    } catch (err) {
      failedLineIds.add(line.id);
      logMassAddError(`${line.card.name}: ${err.message}`);
    }
  }
  if (failedLineIds.size) {
    // Only the lines that actually failed stay in the list — nothing succeeded is left behind to
    // be re-submitted, and nothing failed is silently lost. The modal stays open so it's visible.
    massAddLines = massAddLines.filter(line => failedLineIds.has(line.id));
    if (massAddLockedId && !failedLineIds.has(massAddLockedId)) massAddLockedId = null;
    if (massAddHoverId && !failedLineIds.has(massAddHoverId)) massAddHoverId = null;
    renderMassAddLines();
    renderMassAddPreview();
    updateMassAddSummary();
    toast(`${succeeded} added, ${failedLineIds.size} failed`, true);
  } else {
    resetMassAdd(); // fully submitted — clear so a later reopen starts fresh instead of resubmitting
    closeModal("addCollectionModal");
    toast(`${succeeded} card${succeeded === 1 ? "" : "s"} added`);
  }
  button.disabled = massAddLines.length === 0;
  if (succeeded) await refreshAfterCollectionChange();
}

async function openConnection() {
  showModal("connectionModal");
  state.connectionMode = state.connectionMode || "lan";
  await renderConnectionTab();
}

async function renderConnectionTab() {
  const root = document.getElementById("connectionBody");
  const mode = state.connectionMode;
  root.innerHTML = `
    <div class="segmented connection-mode-toggle">
      <button type="button" data-mode="lan" class="${mode === "lan" ? "active" : ""}">LAN</button>
      <button type="button" data-mode="wan" class="${mode === "wan" ? "active" : ""}">WAN</button>
    </div>
    <div id="connectionModeBody"><div class="loading-line">Loading...</div></div>`;
  root.querySelectorAll("[data-mode]").forEach(btn => btn.addEventListener("click", () => {
    state.connectionMode = btn.dataset.mode;
    renderConnectionTab();
  }));
  if (mode === "lan") await renderLanConnection();
  else await renderWanConnection();
}

async function renderLanConnection() {
  const body = document.getElementById("connectionModeBody");
  try {
    const info = await api("/api/connection-info");
    if (!info.available) { body.textContent = "No LAN address detected."; return; }
    body.innerHTML = `<div class="connection-qr"><img src="/api/connection-qr.png?t=${Date.now()}" alt="Phone connection QR code" /></div><div class="connection-url"><input value="${escapeHtml(info.url)}" readonly /><button class="command-btn" id="copyConnection">Copy</button></div><p class="settings-hint">Only reachable from devices on this same Wi-Fi network.</p>`;
    document.getElementById("copyConnection").onclick = async () => { await navigator.clipboard.writeText(info.url); toast("Connection URL copied"); };
  } catch (err) { body.textContent = err.message; }
}

async function renderWanConnection() {
  const body = document.getElementById("connectionModeBody");
  try {
    renderWanStatus(await api("/api/remote-access/status"));
  } catch (err) { body.textContent = err.message; }
}

function renderWanStatus(status) {
  const body = document.getElementById("connectionModeBody");
  if (status.active && status.url) {
    body.innerHTML = `
      <div class="connection-qr"><img src="/api/remote-access-qr.png?t=${Date.now()}" alt="Remote access QR code" /></div>
      <div class="connection-url"><input value="${escapeHtml(status.url)}" readonly /><button class="command-btn" id="copyWan">Copy</button></div>
      <p class="settings-hint">Reachable from anywhere, not just this Wi-Fi network — anyone with this link can open your vault. Stop it when you're done.</p>
      <button type="button" class="command-btn quiet" id="stopWan">Stop Remote Access</button>`;
    document.getElementById("copyWan").onclick = async () => { await navigator.clipboard.writeText(status.url); toast("Remote access URL copied"); };
    document.getElementById("stopWan").onclick = async () => {
      await api("/api/remote-access/stop", { method: "POST" });
      await renderWanConnection();
    };
  } else if (!status.installed) {
    body.innerHTML = `
      <p class="settings-hint">Remote access uses <b>ngrok</b> to create a temporary public link to this app. It isn't installed on this machine yet.</p>
      <ol class="connection-walkthrough">
        <li>Download and install ngrok from <b>ngrok.com/download</b>.</li>
        <li>Sign up for a free ngrok account, then copy your authtoken from its dashboard.</li>
        <li>Open a terminal and run: <code>ngrok config add-authtoken &lt;your token&gt;</code></li>
        <li>Come back here and press Start.</li>
      </ol>
      <button type="button" class="command-btn gold" id="startWan">I've done this — Start Remote Access</button>`;
    document.getElementById("startWan").onclick = startWanConnection;
  } else {
    body.innerHTML = `
      <p class="settings-hint">Creates a temporary public link to this app, reachable from anywhere — not just this Wi-Fi network. Anyone with the link can open your vault, so only share it with people you trust, and stop it when you're done.</p>
      ${status.error ? `<p class="ask-answer-note">${escapeHtml(status.error)}</p>` : ""}
      <button type="button" class="command-btn gold" id="startWan">Start Remote Access</button>`;
    document.getElementById("startWan").onclick = startWanConnection;
  }
}

async function startWanConnection() {
  const body = document.getElementById("connectionModeBody");
  body.innerHTML = `<div class="loading-line">Starting tunnel... this can take a few seconds.</div>`;
  try {
    renderWanStatus(await api("/api/remote-access/start", jsonOptions("POST", {})));
  } catch (err) { body.textContent = err.message; }
}

function renderChangelog(notes) {
  if (!notes || !notes.trim()) return "<p>No release notes for this version.</p>";
  const html = [];
  let list = null;
  const closeList = () => { if (list) { html.push("</ul>"); list = null; } };
  for (const rawLine of notes.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) { closeList(); continue; }
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) { closeList(); html.push(`<h4>${escapeHtml(heading[1])}</h4>`); continue; }
    const item = line.match(/^[-*]\s+(.*)$/);
    if (item) {
      if (!list) { html.push("<ul>"); list = true; }
      html.push(`<li>${escapeHtml(item[1])}</li>`);
      continue;
    }
    closeList();
    html.push(`<p>${escapeHtml(line)}</p>`);
  }
  closeList();
  return html.join("");
}

async function checkForUpdates() {
  const button = document.getElementById("updateFooterCheck");
  if (button) button.disabled = true;
  setUpdateFooterMessage("Checking for updates...");
  try {
    state.updateStatus = await api("/api/update/check");
  } catch (err) {
    setUpdateFooterMessage(err.message);
    if (button) button.disabled = false;
    return;
  }
  if (button) button.disabled = false;
  renderUpdateFooter();
}

function formatBytes(bytes) {
  if (!bytes) return "0 MB";
  return `${(bytes / 1e6).toFixed(0)} MB`;
}

// Checked on load and every 5 minutes after that; a background check like this must never surface
// errors to the user (e.g. no internet right now is normal, not a problem worth a toast), so
// failures are swallowed silently and just leave state.updateStatus as whatever it was before.
async function checkUpdateIndicator() {
  try {
    state.updateStatus = await api("/api/update/check");
    renderUpdateFooter();
  } catch {
    // Silent — see comment above.
  }
}

// Footer shown site-wide once an update is confirmed available, and permanently on the Settings
// page regardless (so Settings always has a real, current answer to "am I up to date" without
// needing to press Check first). Dismissing only suppresses the site-wide pop-up for this session —
// Settings ignores the dismissed flag entirely, since "always shows there" was the explicit point.
function renderUpdateFooter() {
  const footer = document.getElementById("updateFooter");
  const onSettings = state.page === "settings";
  const s = state.updateStatus;

  if (!s) {
    footer.hidden = !onSettings;
    document.body.classList.toggle("has-update-footer", !footer.hidden);
    if (!onSettings) return;
  }

  const available = s && s.selfUpdateSupported && s.updateAvailable;
  const shouldShow = onSettings || (available && !state.updateFooterDismissed);
  footer.hidden = !shouldShow;
  document.body.classList.toggle("has-update-footer", shouldShow);
  if (!shouldShow) return;

  document.getElementById("updateFooterDismiss").hidden = onSettings;
  const applyBtn = document.getElementById("updateFooterApply");
  const titleEl = document.getElementById("updateFooterTitle");
  const subtitleEl = document.getElementById("updateFooterSubtitle");

  if (!s) {
    titleEl.textContent = "Checking for updates...";
    subtitleEl.textContent = "";
    applyBtn.hidden = true;
  } else if (!s.selfUpdateSupported) {
    titleEl.textContent = "Self-update unavailable";
    subtitleEl.textContent = s.unsupportedReason || "";
    applyBtn.hidden = true;
  } else if (available) {
    titleEl.textContent = `Version ${s.latestVersion} is available`;
    subtitleEl.textContent = `You're on ${s.currentVersion}`;
    applyBtn.hidden = false;
  } else {
    titleEl.textContent = "You're up to date";
    subtitleEl.textContent = `Version ${s.currentVersion}`;
    applyBtn.hidden = true;
  }
}

function setUpdateFooterMessage(text) {
  document.getElementById("updateFooter").hidden = false;
  document.body.classList.add("has-update-footer");
  document.getElementById("updateFooterTitle").textContent = text;
  document.getElementById("updateFooterSubtitle").textContent = "";
  document.getElementById("updateFooterApply").hidden = true;
}

function dismissUpdateFooter() {
  state.updateFooterDismissed = true;
  renderUpdateFooter();
}

async function applyUpdate() {
  setUpdateFooterMessage("Starting update...");
  try {
    const started = await api("/api/update/apply", { method: "POST" });
    if (started.error) { setUpdateFooterMessage(started.error); return; }
  } catch (err) {
    setUpdateFooterMessage(err.message);
    return;
  }
  pollUpdateProgress();
}

async function pollUpdateProgress() {
  let progress;
  try {
    progress = await api("/api/update/progress");
  } catch {
    // The connection dropping here is expected once the app has restarted itself — nothing to
    // report, the new instance will already be starting up.
    setUpdateFooterMessage("Restarting — the app will reopen automatically.");
    return;
  }

  if (progress.phase === "downloading") {
    const pct = progress.totalBytes ? Math.round((progress.bytesDownloaded / progress.totalBytes) * 100) : 0;
    setUpdateFooterMessage(`Downloading update... ${pct}% (${formatBytes(progress.bytesDownloaded)} / ${formatBytes(progress.totalBytes)})`);
    setTimeout(pollUpdateProgress, 500);
  } else if (progress.phase === "extracting") {
    setUpdateFooterMessage("Extracting update...");
    setTimeout(pollUpdateProgress, 500);
  } else if (progress.phase === "restarting") {
    setUpdateFooterMessage("Restarting — the app will reopen automatically.");
    // No further poll: the process exits shortly after entering this phase, so the next request
    // would just fail — the "restarting" message is already the right thing to leave on screen.
  } else if (progress.phase === "error") {
    setUpdateFooterMessage(progress.error || "Update failed.");
  } else {
    setTimeout(pollUpdateProgress, 500);
  }
}

async function openPatchNotes() {
  document.getElementById("changelogBody").innerHTML = `<div class="loading-line">Loading patch notes...</div>`;
  showModal("changelogModal");
  try {
    const entries = await api("/api/update/patch-notes");
    const combined = entries.map(e => `## ${e.version}\n${e.notes || ""}`).join("\n\n");
    document.getElementById("changelogBody").innerHTML = renderChangelog(combined);
  } catch (err) {
    document.getElementById("changelogBody").innerHTML = `<p class="ask-answer-note">${escapeHtml(err.message)}</p>`;
  }
}

async function loadLegendPicker() {
  const mode = state.legendPicker.mode || "create";
  state.legendPicker = { cards: [], search: "", ownedOnly: false, selectedBase: null, selectedVariantId: null, mode };
  document.getElementById("legendSearch").value = "";
  document.getElementById("legendOwnedOnly").checked = false;
  renderLegendDetail(null);
  await refreshLegendPicker();
}

async function refreshLegendPicker() {
  const cards = await api(`/api/cards?${queryString({ type: "Legend", owned: state.legendPicker.ownedOnly ? "owned" : "", sort: "name-asc" })}`);
  registerCards(cards);
  state.legendPicker.cards = cards;
  renderLegendGrid();
}

// Different prints of the same Legend (Metal, Overnumbered, Signature, Starter, ...) share a
// base name with the variant called out in a trailing "(...)" — e.g. "Ahri - Nine-Tailed Fox"
// vs "Ahri - Nine-Tailed Fox (Metal)". Cards with no parenthetical are their own single-print group.
function legendBaseName(name) {
  const idx = name.indexOf(" (");
  return idx === -1 ? name : name.slice(0, idx);
}

// Most reprints are distinguished by a "(Metal)"-style suffix, but a handful of Legends (mostly
// an OPP organized-play promo sharing its name with the plain OGN rare, e.g. "Darius - Hand of
// Noxus") have two variants with the exact same name and no suffix at all — label those by set
// code instead of letting them both read as an indistinguishable "Base".
const VARIANT_SUFFIX_ABBR = {
  "Alternate Art": "ALT",
  "Launch Exclusive": "EXL",
  Signature: "SIG",
  Metal: "MTL",
  Overnumbered: "OVN",
  Starter: "STR",
  Ultimate: "ULT"
};

function legendVariantLabel(card, siblings) {
  const match = card.name.match(/\(([^)]+)\)/);
  if (match) return VARIANT_SUFFIX_ABBR[match[1]] || match[1];
  const collides = siblings.some(v => v.id !== card.id && v.name === card.name);
  return collides ? card.setId : "Base";
}

function groupLegendVariants(cards) {
  const groups = new Map();
  for (const card of cards) {
    const key = legendBaseName(card.name);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(card);
  }
  return [...groups.entries()].map(([baseName, variants]) => ({
    baseName,
    // Shortest (base-print) name first so it's the default representative/selection.
    variants: variants.sort((a, b) => a.name.length - b.name.length || a.name.localeCompare(b.name))
  }));
}

function legendGroupTile(group) {
  const card = group.variants[0];
  const owned = group.variants.some(v => v.ownedCount > 0);
  return `
    <button type="button" class="legend-picker-card${state.legendPicker.selectedBase === group.baseName ? " selected" : ""}" data-legend-base="${escapeHtml(group.baseName)}">
      <div class="legend-picker-art">
        <img src="${escapeHtml(cardImage(card))}" alt="" />
        ${group.variants.length > 1 ? `<span class="legend-variant-count">${group.variants.length}</span>` : ""}
        ${owned ? `<span class="legend-owned-badge">${icon("check")}</span>` : ""}
      </div>
      <strong>${escapeHtml(group.baseName)}</strong>
    </button>`;
}

function renderLegendGrid() {
  const search = state.legendPicker.search.trim().toLowerCase();
  const cards = search ? state.legendPicker.cards.filter(card => card.name.toLowerCase().includes(search)) : state.legendPicker.cards;
  const groups = groupLegendVariants(cards);
  const root = document.getElementById("legendPickerGrid");
  root.innerHTML = groups.length ? groups.map(legendGroupTile).join("")
    : `<div class="seam-empty">${icon("search")}<h4>No legends found</h4></div>`;
  renderIcons(root);
}

function selectLegendGroup(baseName) {
  const group = groupLegendVariants(state.legendPicker.cards).find(g => g.baseName === baseName);
  if (!group) return;
  state.legendPicker.selectedBase = baseName;
  state.legendPicker.selectedVariantId = group.variants[0].id;
  document.querySelectorAll("#legendPickerGrid [data-legend-base]").forEach(button =>
    button.classList.toggle("selected", button.dataset.legendBase === baseName));
  renderLegendDetail(group);
}

function legendVariationStripMarkup(group, activeCard) {
  return `<div class="legend-variation-strip">${group.variants.map(v => `
    <button type="button" class="legend-variation-seg${v.id === activeCard.id ? " active" : ""}" data-legend-variant="${escapeHtml(v.id)}" title="${escapeHtml(v.name)}">
      <img src="${escapeHtml(cardImage(v))}" alt="" />
      <span>${escapeHtml(legendVariantLabel(v, group.variants))}</span>
    </button>`).join("")}</div>`;
}

function renderLegendDetail(group) {
  const root = document.getElementById("legendDetailPanel");
  const modal = document.getElementById("legendPickerModal");
  if (!group) {
    root.innerHTML = `<div class="seam-empty">${icon("layers")}<h4>Select a Legend</h4><p>Choose a card to see details.</p></div>`;
    renderIcons(root);
    if (modal) modal.dataset.domainGlow = "";
    return;
  }
  const selectedCard = group.variants.find(v => v.id === state.legendPicker.selectedVariantId) || group.variants[0];
  root.innerHTML = `
    ${group.variants.length > 1 ? legendVariationStripMarkup(group, selectedCard) : ""}
    <div id="legendDetailBody"></div>`;
  renderIcons(root);
  renderLegendDetailBody(group, selectedCard);

  root.querySelectorAll("[data-legend-variant]").forEach(seg => {
    const variant = group.variants.find(v => v.id === seg.dataset.legendVariant);
    if (!variant) return;
    // Hovering previews that print in the panel below without committing to it; clicking commits
    // the selection (updates state + the active segment) and leaving the strip reverts the
    // preview back to whatever is actually selected.
    seg.addEventListener("mouseenter", () => renderLegendDetailBody(group, variant));
    seg.addEventListener("mouseleave", () => {
      const current = group.variants.find(v => v.id === state.legendPicker.selectedVariantId) || group.variants[0];
      renderLegendDetailBody(group, current);
    });
    seg.addEventListener("click", () => {
      state.legendPicker.selectedVariantId = variant.id;
      root.querySelectorAll("[data-legend-variant]").forEach(s => s.classList.toggle("active", s === seg));
      renderLegendDetailBody(group, variant);
    });
  });
}

function renderLegendDetailBody(group, card) {
  const root = document.getElementById("legendDetailBody");
  if (!root) return;
  const modal = document.getElementById("legendPickerModal");
  const domains = card.domains?.length ? card.domains : [];
  root.innerHTML = `
    <div class="legend-detail-art">
      <img src="${escapeHtml(cardImage(card))}" alt="" />
      ${cardImagePopout(card)}
      ${card.ownedCount <= 0 ? `<span class="legend-not-owned-banner">Not Owned</span>` : ""}
    </div>
    <h3>${escapeHtml(group.baseName)}</h3>
    <div class="legend-detail-domains">${domains.map(d => `<span style="color:${DOMAIN_COLOR[domainName(d)] || "var(--c-colorless)"}">${escapeHtml(domainName(d))}</span>`).join(" &middot; ")}</div>
    <button type="button" class="command-btn gold legend-build-btn" id="buildDeckBtn">${state.legendPicker.mode === "change" ? "Use" : "Build With"} ${escapeHtml(group.baseName.split(",")[0])}</button>`;
  renderIcons(root);
  document.getElementById("buildDeckBtn").addEventListener("click", () => {
    const action = state.legendPicker.mode === "change" ? changeDeckLegend(card) : createDeckWithLegend(card);
    action.catch(err => toast(err.message, true));
  });
  if (modal) modal.dataset.domainGlow = domains.length ? domainKey(domains[0]) : "";
}

async function createDeckWithLegend(legend) {
  const created = await api("/api/decks", jsonOptions("POST", { name: legend.name, description: "", coverCardId: legend.id }));
  state.activeDeckId = created.summary.id;
  saveNavState();
  await setDeckCard(created.summary.id, legend.id, 1, "main");
  closeModal("deckModal");
  await loadOverview();
  toast(`${legend.name} deck created`);
}

async function importDeck() {
  const name = document.getElementById("importDeckName").value.trim() || "Imported Deck";
  const contents = document.getElementById("importDeckContents").value;
  const result = await api("/api/decks/import", jsonOptions("POST", { name, format: "Standard", contents }));
  state.activeDeckId = result.deckId;
  const resultEl = document.getElementById("importDeckResult");
  if (result.unmatchedLines.length) {
    resultEl.innerHTML = `<p>${result.addedLines} lines added. ${result.unmatchedLines.length} lines did not match:</p>
      <ul class="import-unmatched-list">${result.unmatchedLines.map(line => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`;
  } else {
    resultEl.textContent = `${result.addedLines} lines added.`;
  }
  await Promise.all([loadDecks(), loadOverview()]);
  if (!result.unmatchedLines.length) closeModal("importDeckModal");
}

async function openPackImportModal() {
  document.getElementById("packImportResult").innerHTML = "";
  resetPackPreview();
  const listEl = document.getElementById("packImportList");
  listEl.innerHTML = `<div class="loading-line" style="padding:20px">Loading packs...</div>`;
  try {
    const packs = await api("/api/premade-packs");
    listEl.innerHTML = packs.map(p => `
      <div class="pack-import-row" data-pack-key="${escapeHtml(p.key)}" data-pack-name="${escapeHtml(p.name)}">
        <div>
          <b>${escapeHtml(p.name)}</b>
          <span>${escapeHtml(p.wave)} · ${p.cardCount} cards</span>
        </div>
        <button type="button" class="command-btn quiet">Preview</button>
      </div>`).join("");
  } catch (err) {
    listEl.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load packs</h2><span>${escapeHtml(err.message)}</span></div>`;
  }
  renderIcons(listEl);
}

let currentPackPreview = null; // { key, name, cards } — the pack currently shown in the preview panel, awaiting confirmation
let lastPackImport = null; // { packName, undoEntries } — cleared once undone or a new import runs

function resetPackPreview() {
  currentPackPreview = null;
  document.getElementById("packPreviewHeader").innerHTML = "";
  document.getElementById("packPreviewList").innerHTML = `<div class="pack-preview-empty"><i data-icon="archive"></i><span>Click a pack to preview its cards here.</span></div>`;
  renderIcons(document.getElementById("packPreviewList"));
}

function packPreviewCardMarkup(card, quantity) {
  return `
    <div class="pack-preview-card">
      <div class="pack-preview-card-art">
        <img src="${escapeHtml(cardImage(card))}" alt="${escapeHtml(card.name)}" loading="lazy" />
        ${cardImagePopout(card)}
      </div>
      <div class="pack-preview-card-info">
        <b title="${escapeHtml(card.name)}">${escapeHtml(card.name)}</b>
        <span>${escapeHtml(card.supertype ? `${card.supertype} ${card.type}` : card.type)} · ${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}</span>
        <span class="pack-preview-qty">x${quantity}</span>
      </div>
    </div>`;
}

// One physical-count bucket per TYPE_GROUP_ORDER category (Legend/Champion/Unit/Spell/Gear/
// Battlefield/Rune) — sums quantity, not unique-card count, so "12" under the rune symbol means
// 12 total rune cards in the box, not "2 different rune entries".
function packTypeCounts(cards) {
  const counts = {};
  for (const { card, quantity } of cards) {
    const key = groupKey(card);
    counts[key] = (counts[key] || 0) + quantity;
  }
  return counts;
}

function packPreviewHeaderMarkup(name, cards) {
  const counts = packTypeCounts(cards);
  const chips = TYPE_GROUP_ORDER.filter(t => counts[t]).map(t => {
    const asset = CARD_TYPE_ASSET[t.toLowerCase()];
    return `<span class="pack-type-count" title="${escapeHtml(t)}">
      ${asset ? `<img src="/assets/riftbound-symbols/${asset}" alt="${escapeHtml(t)}" />` : ""}
      ${counts[t]}
    </span>`;
  }).join("");
  return `
    <div class="pack-preview-header-top">
      <b>${escapeHtml(name)}</b>
      <div class="pack-preview-header-actions">
        <button type="button" class="command-btn quiet" id="confirmRemovePackBtn" title="Subtract this pack's cards from your collection">Remove</button>
        <button type="button" class="command-btn gold" id="confirmImportPackBtn">Import</button>
      </div>
    </div>
    <div class="pack-preview-type-counts">${chips}</div>`;
}

async function previewPack(row) {
  const key = row.dataset.packKey;
  const name = row.dataset.packName;
  document.getElementById("packImportResult").innerHTML = "";
  document.getElementById("packPreviewHeader").innerHTML = "";
  const listEl = document.getElementById("packPreviewList");
  listEl.innerHTML = `<div class="loading-line" style="padding:20px">Loading preview...</div>`;
  try {
    const result = await api(`/api/premade-packs/${encodeURIComponent(key)}/preview`);
    currentPackPreview = { key, name, cards: result.cards };
    document.getElementById("packPreviewHeader").innerHTML = packPreviewHeaderMarkup(name, result.cards);
    renderIcons(document.getElementById("packPreviewHeader"));
    if (!result.cards.length) {
      listEl.innerHTML = `<div class="pack-preview-empty"><i data-icon="alert-triangle"></i><span>None of this pack's cards matched the catalog.</span></div>`;
    } else {
      registerCards(result.cards.map(c => c.card));
      listEl.innerHTML = result.cards.map(c => packPreviewCardMarkup(c.card, c.quantity)).join("");
    }
    if (result.unmatchedCards.length) {
      document.getElementById("packImportResult").innerHTML =
        `<p>${result.unmatchedCards.length} card${result.unmatchedCards.length === 1 ? "" : "s"} in this pack didn't match the catalog:</p>
         <ul class="import-unmatched-list">${result.unmatchedCards.map(c => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`;
    }
  } catch (err) {
    listEl.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load preview</h2><span>${escapeHtml(err.message)}</span></div>`;
  }
  renderIcons(listEl);
}

async function confirmImportPack() {
  if (!currentPackPreview) return;
  const { key, name } = currentPackPreview;
  const button = document.getElementById("confirmImportPackBtn");
  const resultEl = document.getElementById("packImportResult");
  button.disabled = true;
  resultEl.innerHTML = `<div class="loading-line" style="padding:12px 0">Adding cards...</div>`;
  lastPackImport = null;
  try {
    const result = await api(`/api/premade-packs/${encodeURIComponent(key)}/import`, jsonOptions("POST"));
    const undoBtn = result.appliedCards.length
      ? `<button type="button" class="command-btn quiet" id="undoPackImportBtn">Undo</button>` : "";
    if (result.unmatchedCards.length) {
      resultEl.innerHTML = `<p>${result.addedCards} cards added. ${result.unmatchedCards.length} card names did not match:</p>
        <ul class="import-unmatched-list">${result.unmatchedCards.map(c => `<li>${escapeHtml(c)}</li>`).join("")}</ul>
        <div class="pack-import-result-actions">${undoBtn}</div>`;
    } else {
      resultEl.innerHTML = `<p>${result.addedCards} cards added to your collection.</p>
        <div class="pack-import-result-actions">${undoBtn}</div>`;
    }
    if (result.appliedCards.length) {
      lastPackImport = {
        packName: name,
        undoEntries: result.appliedCards.map(a => ({ cardId: a.card.id, quantity: a.quantity })),
      };
    }
    document.getElementById("undoPackImportBtn")?.addEventListener("click", undoPackImport);
    await refreshAfterCollectionChange();
  } catch (err) {
    resultEl.innerHTML = `<p class="ask-answer-note">${escapeHtml(err.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

async function confirmRemovePack() {
  if (!currentPackPreview) return;
  const { key, name } = currentPackPreview;
  if (!confirm(`Subtract every card in "${name}" from your collection? This can't be undone.`)) return;
  const button = document.getElementById("confirmRemovePackBtn");
  const resultEl = document.getElementById("packImportResult");
  button.disabled = true;
  resultEl.innerHTML = `<div class="loading-line" style="padding:12px 0">Removing cards...</div>`;
  lastPackImport = null;
  try {
    const result = await api(`/api/premade-packs/${encodeURIComponent(key)}/remove`, jsonOptions("POST"));
    resultEl.innerHTML = `<p>${result.addedCards} cards subtracted from your collection.</p>`;
    await refreshAfterCollectionChange();
  } catch (err) {
    resultEl.innerHTML = `<p class="ask-answer-note">${escapeHtml(err.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

async function undoPackImport() {
  if (!lastPackImport) return;
  const { packName, undoEntries } = lastPackImport;
  const undoBtn = document.getElementById("undoPackImportBtn");
  if (undoBtn) undoBtn.disabled = true;
  try {
    await api("/api/premade-packs/undo", jsonOptions("POST", { appliedCards: undoEntries }));
    lastPackImport = null;
    document.getElementById("packImportResult").innerHTML = `<p>Undone — ${packName} was removed from your collection.</p>`;
    resetPackPreview();
    await refreshAfterCollectionChange();
  } catch (err) {
    toast(err.message, true);
    if (undoBtn) undoBtn.disabled = false;
  }
}

/* Scanner */
const scan = {
  stream: null, timer: null, inFlight: false, hitPending: false,
  voteKey: null, voteCount: 0, canvas: document.createElement("canvas"),
  facingMode: "environment", deviceId: null, cameras: [], starting: false, switching: false, generation: 0,
  mode: "add" // "add" (default — Scan Card from Vault) or "price" (Check Price — never touches collection)
};

function setScanMode(mode) {
  scan.mode = mode;
  document.getElementById("scanModalEyebrow").textContent = mode === "price" ? "Price Checker" : "Scanner";
  document.getElementById("scanModalTitle").textContent = mode === "price" ? "Check a Card's Price" : "Scan a Card";
}

function openScanPriceDetail(card) {
  closeModal("scanModal");
  openCardContextSection(card, ".inspector-price");
}

function resetScanner() {
  stopLiveScan();
  scan.hitPending = false; scan.voteKey = null; scan.voteCount = 0;
  document.getElementById("liveStatus").textContent = "Align the printed Card ID inside the box";
  document.getElementById("liveReadoutText").textContent = "...";
  document.getElementById("liveHit").innerHTML = "";
  document.getElementById("scanPreview").hidden = true;
  document.getElementById("matchList").innerHTML = "";
  document.getElementById("ocrDebug").hidden = true;
  document.getElementById("manualSetCode").value = state.setId || "";
  document.getElementById("manualNumber").value = "";
}

async function handleScanFile(file) {
  if (!file) return;
  const preview = document.getElementById("scanPreview");
  preview.hidden = false;
  document.getElementById("scanPreviewImg").src = URL.createObjectURL(file);
  document.getElementById("scanStatus").textContent = "Reading card...";
  const form = new FormData();
  form.append("photo", file);
  if (state.setId) form.append("setId", state.setId);
  try { renderScanResult(await api("/api/scan", { method: "POST", body: form })); }
  catch (err) { document.getElementById("scanStatus").textContent = err.message; }
}

function renderScanResult(result) {
  const root = document.getElementById("matchList");
  const status = document.getElementById("scanStatus");
  const debug = document.getElementById("ocrDebug");
  const text = (result.debugOcrText || "").trim();
  debug.hidden = !text || result.method === "ocr";
  debug.textContent = text;
  registerCards(result.matches.map(match => match.card));
  if (!result.matches.length) {
    status.textContent = "No confident match. Try another image or use manual lookup.";
    root.innerHTML = "";
    return;
  }
  status.textContent = result.matches.length === 1 ? "Card matched" : "Choose the correct card";
  const isPriceMode = scan.mode === "price";
  const actionLabel = isPriceMode ? "Check Price" : "Add";
  const actionAttr = isPriceMode ? "data-scan-price" : "data-scan-add";
  root.innerHTML = result.matches.map(match => `<div class="result-row"><div class="result-card-art"><img src="${escapeHtml(cardImage(match.card))}" alt="" />${cardImagePopout(match.card)}</div><div><strong>${escapeHtml(match.card.name)}</strong><span>${escapeHtml(match.card.setId)}-${escapeHtml(cardCode(match.card))} / ${match.confidence}%</span></div><button class="command-btn gold" ${actionAttr}="${escapeHtml(match.card.id)}">${actionLabel}</button></div>`).join("");
  renderIcons(root);
  if (isPriceMode) {
    root.querySelectorAll("[data-scan-price]").forEach(button => button.addEventListener("click", () =>
      openScanPriceDetail(cardsById.get(button.dataset.scanPrice))));
  } else {
    root.querySelectorAll("[data-scan-add]").forEach(button => button.addEventListener("click", async () => {
      await changeOwned(cardsById.get(button.dataset.scanAdd), 1);
      root.innerHTML = "";
      status.textContent = "Card added";
    }));
  }
}

async function manualLookup() {
  const setId = document.getElementById("manualSetCode").value.trim().toUpperCase();
  const code = document.getElementById("manualNumber").value.trim().toUpperCase();
  if (!code) return;
  const cards = await api(`/api/cards/lookup?${queryString({ setId, code })}`);
  renderScanResult({ method: cards.length === 1 ? "manual" : "ocr-ambiguous", matches: cards.map(card => ({ card, confidence: 100 })), debugOcrText: "" });
}

async function requestCameraStream(deviceId, facingMode) {
  const video = { width: { ideal: 1920 }, height: { ideal: 1080 } };
  if (deviceId) video.deviceId = { exact: deviceId };
  else video.facingMode = { ideal: facingMode };
  return navigator.mediaDevices.getUserMedia({ video, audio: false });
}

async function activateLiveStream(stream) {
  scan.stream = stream;
  const track = stream.getVideoTracks()[0];
  try {
    const capabilities = track?.getCapabilities?.();
    if (capabilities?.focusMode?.includes("continuous"))
      await track.applyConstraints({ advanced: [{ focusMode: "continuous" }] });
  } catch { }
  const settings = track?.getSettings?.() || {};
  scan.deviceId = settings.deviceId || scan.deviceId;
  scan.facingMode = settings.facingMode || scan.facingMode;
  try {
    scan.cameras = (await navigator.mediaDevices.enumerateDevices())
      .filter(device => device.kind === "videoinput" && device.deviceId);
  } catch { scan.cameras = []; }
  const video = document.getElementById("liveVideo");
  video.srcObject = stream;
  await video.play().catch(() => { });
  document.getElementById("liveScanBtn").hidden = true;
  document.getElementById("liveScanView").hidden = false;
  document.getElementById("liveStatus").textContent = "Align the printed Card ID inside the box";
  scan.voteKey = null; scan.voteCount = 0; scan.hitPending = false;
  scan.generation++;
  scan.inFlight = false;
  if (scan.timer) clearInterval(scan.timer);
  captureLiveFrame();
  scan.timer = setInterval(captureLiveFrame, 600);
}

async function startLiveScan() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) return toast("Live camera requires the HTTPS phone connection", true);
  if (scan.stream || scan.starting) return;
  scan.starting = true;
  const button = document.getElementById("liveScanBtn");
  button.disabled = true;
  const requestGeneration = scan.generation;
  try {
    let stream;
    try { stream = await requestCameraStream(scan.deviceId, scan.facingMode); }
    catch (err) {
      if (!scan.deviceId) throw err;
      scan.deviceId = null;
      stream = await requestCameraStream(null, scan.facingMode);
    }
    if (requestGeneration !== scan.generation) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    await activateLiveStream(stream);
  } catch (err) {
    if (requestGeneration === scan.generation) toast(err.message, true);
  } finally {
    scan.starting = false;
    button.disabled = false;
  }
}

function releaseLiveStream() {
  if (scan.timer) clearInterval(scan.timer);
  scan.timer = null;
  if (scan.stream) scan.stream.getTracks().forEach(track => track.stop());
  scan.stream = null;
  scan.generation++;
  scan.inFlight = false;
  const video = document.getElementById("liveVideo");
  if (video) video.srcObject = null;
}

function stopLiveScan() {
  releaseLiveStream();
  document.getElementById("liveScanView").hidden = true;
  document.getElementById("liveScanBtn").hidden = false;
}

async function flipLiveCamera() {
  if (!scan.stream || scan.switching) return;
  scan.switching = true;
  const button = document.getElementById("flipCamera");
  button.disabled = true;
  const previousDeviceId = scan.stream.getVideoTracks()[0]?.getSettings?.().deviceId || scan.deviceId;
  const previousFacingMode = scan.facingMode;
  let targetDeviceId = null;
  let targetFacingMode = previousFacingMode === "environment" ? "user" : "environment";

  try {
    let cameras = [];
    try {
      cameras = (await navigator.mediaDevices.enumerateDevices())
        .filter(device => device.kind === "videoinput" && device.deviceId);
    } catch { }
    scan.cameras = cameras;
    if (cameras.length > 1) {
      const currentIndex = cameras.findIndex(device => device.deviceId === previousDeviceId);
      targetDeviceId = cameras[(currentIndex + 1 + cameras.length) % cameras.length].deviceId;
    }

    document.getElementById("liveStatus").textContent = "Switching camera...";
    releaseLiveStream();
    const requestGeneration = scan.generation;
    const stream = await requestCameraStream(targetDeviceId, targetFacingMode);
    if (requestGeneration !== scan.generation) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    scan.deviceId = targetDeviceId;
    scan.facingMode = targetFacingMode;
    await activateLiveStream(stream);
    const activeDeviceId = stream.getVideoTracks()[0]?.getSettings?.().deviceId;
    if (!targetDeviceId && previousDeviceId && activeDeviceId === previousDeviceId)
      toast("No other camera is available", true);
  } catch (err) {
    if (!document.getElementById("scanModal").hidden) {
      scan.deviceId = previousDeviceId;
      scan.facingMode = previousFacingMode;
      const fallbackGeneration = scan.generation;
      try {
        const fallbackStream = await requestCameraStream(previousDeviceId, previousFacingMode);
        if (fallbackGeneration !== scan.generation) fallbackStream.getTracks().forEach(track => track.stop());
        else await activateLiveStream(fallbackStream);
      }
      catch { stopLiveScan(); }
      toast(err.message || "Unable to switch cameras", true);
    }
  } finally {
    scan.switching = false;
    button.disabled = false;
  }
}

function liveScanSourceRect(video) {
  const guide = document.getElementById("liveScanGuide");
  if (!guide || !video.videoWidth || !video.videoHeight) return null;

  const videoRect = video.getBoundingClientRect();
  const guideRect = guide.getBoundingClientRect();
  const coverScale = Math.max(videoRect.width / video.videoWidth, videoRect.height / video.videoHeight);
  const renderedWidth = video.videoWidth * coverScale;
  const renderedHeight = video.videoHeight * coverScale;
  const cropOffsetX = (renderedWidth - videoRect.width) / 2;
  const cropOffsetY = (renderedHeight - videoRect.height) / 2;
  const x = (guideRect.left - videoRect.left + cropOffsetX) / coverScale;
  const y = (guideRect.top - videoRect.top + cropOffsetY) / coverScale;
  const width = guideRect.width / coverScale;
  const height = guideRect.height / coverScale;
  const safeX = Math.max(0, Math.min(video.videoWidth - 1, x));
  const safeY = Math.max(0, Math.min(video.videoHeight - 1, y));
  return {
    x: safeX,
    y: safeY,
    width: Math.max(1, Math.min(video.videoWidth - safeX, width)),
    height: Math.max(1, Math.min(video.videoHeight - safeY, height))
  };
}

async function captureLiveFrame() {
  const video = document.getElementById("liveVideo");
  if (scan.inFlight || scan.hitPending || video.readyState < 2) return;
  scan.inFlight = true;
  const generation = scan.generation;
  const source = liveScanSourceRect(video);
  if (!source) { scan.inFlight = false; return; }
  scan.canvas.width = Math.round(source.width);
  scan.canvas.height = Math.round(source.height);
  scan.canvas.getContext("2d").drawImage(
    video, source.x, source.y, source.width, source.height,
    0, 0, scan.canvas.width, scan.canvas.height);
  scan.canvas.toBlob(async blob => {
    if (!blob || generation !== scan.generation) { scan.inFlight = false; return; }
    const form = new FormData();
    form.append("photo", blob, "card-id.jpg");
    form.append("fast", "true");
    form.append("cardIdOnly", "true");
    try {
      const result = await api("/api/scan", { method: "POST", body: form });
      if (generation !== scan.generation) return;
      const candidate = result.method === "ocr" && result.matches.length === 1 ? result.matches[0] : null;
      document.getElementById("liveReadoutText").textContent = candidate
        ? `${candidate.card.setId}-${cardCode(candidate.card)}`
        : (result.debugOcrText || "Nothing legible yet").replace(/\s+/g, " ").slice(0, 70);
      const key = candidate?.card.id || null;
      if (key && key === scan.voteKey) scan.voteCount++; else { scan.voteKey = key; scan.voteCount = key ? 1 : 0; }
      const votesRequired = candidate?.confidence >= 95 ? 2 : 3;
      if (candidate && scan.voteCount >= votesRequired) showLiveHit(candidate);
    } catch { }
    finally { scan.inFlight = false; }
  }, "image/jpeg", .84);
}

function showLiveHit(match) {
  scan.hitPending = true;
  registerCards([match.card]);
  const root = document.getElementById("liveHit");
  const isPriceMode = scan.mode === "price";
  const actionLabel = isPriceMode ? "Check Price" : "Add";
  root.innerHTML = `<div class="result-row"><div class="result-card-art"><img src="${escapeHtml(cardImage(match.card))}" alt="" />${cardImagePopout(match.card)}</div><div><strong>${escapeHtml(match.card.name)}</strong><span>${escapeHtml(match.card.setId)}-${escapeHtml(cardCode(match.card))}</span></div><button class="command-btn gold" id="liveAdd">${actionLabel}</button></div>`;
  renderIcons(root);
  document.getElementById("liveStatus").textContent = "Card matched";
  document.getElementById("liveAdd").onclick = isPriceMode ? () => openScanPriceDetail(match.card) : async () => {
    await changeOwned(match.card, 1);
    root.innerHTML = "";
    scan.hitPending = false; scan.voteKey = null; scan.voteCount = 0;
    document.getElementById("liveStatus").textContent = "Align the printed Card ID inside the box";
  };
  setTimeout(() => {
    if (!scan.hitPending) return;
    root.innerHTML = "";
    scan.hitPending = false; scan.voteKey = null; scan.voteCount = 0;
    document.getElementById("liveStatus").textContent = "Align the printed Card ID inside the box";
  }, 4500);
}

// ---- Rules ----------------------------------------------------------------

async function loadRules() {
  const meta = document.getElementById("rulesLibraryMeta");
  // Rules Browser (search/glossary/errata/legality) is on the old EF-backed catalog and isn't
  // wired to the rules engine sidecar yet — see the backend's own note on why (ID-scheme
  // mismatch, not a quick swap). Ask Rules itself (below) is fully on the new engine already.
  meta.textContent = "Browsing rules directly is being rebuilt on the new rules engine — Ask Rules already uses it below.";
  renderRulesQuickTopics();
  await loadLocalAiStatus();

  if (state.rules.mode === "glossary") await showRulesGlossary();
  else if (state.rules.mode === "errata") await showRulesErrata();
  else if (state.rules.mode === "legality") await showRulesLegality();
  else if (state.rules.query) await runRulesSearch(state.rules.query);
}

async function loadLocalAiStatus() {
  const data = await api("/api/rules/engine/status");
  state.localAiEnabled = data.enabled;
  state.rulesEngineStatus = data.engine;

  const toggleBtn = document.getElementById("toggleLocalAi");
  toggleBtn.textContent = data.enabled ? "Disable" : "Enable";
  toggleBtn.disabled = false;

  document.getElementById("askRulesProviderStatus").textContent = !data.enabled
    ? "Off — turn Ask Rules on below to get answers from the rules engine."
    : data.engine.running
      ? "On — the rules engine is running."
      : data.engine.installed
        ? "On — the rules engine will start on your next question."
        : "On — the rules engine hasn't been downloaded yet.";

  renderRulesEngineStatus();
}

function renderRulesEngineStatus() {
  const root = document.getElementById("localAiModelList");
  const engine = state.rulesEngineStatus || {};
  if (!state.localAiEnabled) {
    root.innerHTML = "";
    return;
  }

  if (engine.phase === "downloading" || engine.phase === "checking") {
    const pct = engine.totalBytes ? Math.round((engine.downloadedBytes / engine.totalBytes) * 100) : 0;
    root.innerHTML = engine.phase === "checking"
      ? `<span class="local-ai-model-status">Checking for the rules engine release…</span>`
      : `<div class="local-ai-model-progress">Downloading the rules engine… ${pct}%<div class="progress-track"><span style="width:${pct}%"></span></div></div>`;
    return;
  }

  const action = engine.installed
    ? `<span class="local-ai-model-badge">${engine.running ? "Running" : "Ready"}</span>`
    : `<button type="button" class="command-btn quiet" id="downloadRulesEngineBtn">Download</button>`;
  root.innerHTML = `
    <div class="local-ai-model-row">
      <div class="local-ai-model-copy">
        <b>RiftKeep Rules Engine</b>
        <span>${engine.installed ? "Deterministic rules engine, downloaded and ready." : "Not downloaded yet — needed for Ask Rules to answer."}</span>
      </div>
      <div class="local-ai-model-action">${action}</div>
    </div>`;
  const downloadBtn = document.getElementById("downloadRulesEngineBtn");
  if (downloadBtn) downloadBtn.addEventListener("click", downloadRulesEngine);
}

async function downloadRulesEngine() {
  try {
    await api("/api/rules/engine/download", jsonOptions("POST", {}));
  } catch (err) {
    toast(err.message, true);
    return;
  }
  pollRulesEngineProgress();
}

async function pollRulesEngineProgress() {
  let data;
  try {
    data = await api("/api/rules/engine/status");
  } catch (err) {
    toast(err.message, true);
    return;
  }
  state.rulesEngineStatus = data.engine;
  renderRulesEngineStatus();
  if (data.engine.phase === "downloading" || data.engine.phase === "checking") {
    setTimeout(pollRulesEngineProgress, 500);
  } else if (data.engine.phase === "error") {
    toast(data.engine.error || "Rules engine download failed.", true);
  } else if (data.engine.phase === "done") {
    toast("Rules engine downloaded.");
  }
}

function renderRulesQuickTopics() {
  const root = document.getElementById("rulesQuickTopics");
  root.innerHTML = RULES_QUICK_TOPICS.map(t => `
    <button type="button" class="rules-topic-btn${state.rules.mode === t.mode ? " active" : ""}" data-topic-label="${escapeHtml(t.label)}">${escapeHtml(t.label)}</button>`).join("");
}

function ruleResultRowMarkup({ id, kind, badgeNumber, title, subtitle, badgeText, badgeClass }) {
  return `
    <button type="button" class="rule-hit" data-result-kind="${kind}" data-result-id="${id}">
      <div>
        ${badgeNumber ? `<span class="rule-hit-number">${escapeHtml(badgeNumber)}</span>` : ""}
        <strong>${escapeHtml(title)}</strong>
        ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
      </div>
      ${badgeText ? `<span class="authority-badge ${badgeClass || "historical"}">${escapeHtml(badgeText)}</span>` : "<span></span>"}
    </button>`;
}

function renderRulesResultList(items, metaText, mapFn) {
  const root = document.getElementById("rulesResults");
  const rows = items.map(mapFn).map(ruleResultRowMarkup).join("");
  root.innerHTML = `<div class="rules-results-meta">${escapeHtml(metaText)}</div>${rows ||
    `<div class="page-empty"><i data-icon="search"></i><h2>Nothing here</h2></div>`}`;
  renderIcons(root);
}

function markActiveResult(id) {
  document.querySelectorAll("#rulesResults .rule-hit").forEach(button =>
    button.classList.toggle("active", button.dataset.resultId === String(id)));
}

async function runRulesSearch(query) {
  state.rules.query = query;
  state.rules.mode = "search";
  renderRulesQuickTopics();
  const root = document.getElementById("rulesResults");
  if (!query.trim()) {
    root.innerHTML = `<div class="page-empty"><i data-icon="search"></i><h2>Search for a rule</h2><span>Try a rule number, a keyword like "exhaust", or a card name.</span></div>`;
    document.getElementById("rulesDetail").innerHTML = `<div class="page-empty"><i data-icon="book-open"></i><h2>Select a result</h2></div>`;
    renderIcons(root);
    renderIcons(document.getElementById("rulesDetail"));
    return;
  }
  root.innerHTML = `<div class="loading-line" style="padding:20px">Searching...</div>`;
  try {
    const response = await api(`/api/rules/search?${queryString({ q: query })}`);
    renderRulesResultList(response.results, `${response.total} result${response.total === 1 ? "" : "s"}`, r => ({
      id: r.ruleId, kind: "rule", badgeNumber: r.ruleNumber, title: r.title,
      subtitle: [r.section, r.document.title].filter(Boolean).join(" · "),
      badgeText: r.document.current ? "Current" : "Historical", badgeClass: r.document.current ? "current" : "historical"
    }));
    if (response.results.length) {
      await selectRuleResult(response.results[0].ruleId);
      markActiveResult(response.results[0].ruleId);
    } else {
      const detail = document.getElementById("rulesDetail");
      detail.innerHTML = `<div class="page-empty"><i data-icon="search"></i><h2>No matches</h2><span>Try a different search term.</span></div>`;
      renderIcons(detail);
    }
  } catch (err) {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Search failed</h2><span>${escapeHtml(err.message)}</span></div>`;
    renderIcons(root);
  }
}

async function selectRuleResult(id) {
  const root = document.getElementById("rulesDetail");
  root.innerHTML = `<div class="loading-line">Loading...</div>`;
  try {
    renderRuleDetail(await api(`/api/rules/${id}`));
    markActiveResult(id);
  } catch {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load rule</h2></div>`;
    renderIcons(root);
  }
}

function ruleLinkMarkup(r) {
  return `<button type="button" class="rule-detail-link" data-rule-goto="${r.id}"><b>${escapeHtml(r.ruleNumber || "")}</b>${escapeHtml(r.title || r.text.slice(0, 90))}</button>`;
}

function renderRuleDetail(detail) {
  const root = document.getElementById("rulesDetail");
  const r = detail.rule;
  root.innerHTML = `
    <div class="rule-detail-head">
      ${r.ruleNumber ? `<span class="rule-detail-number">${escapeHtml(r.ruleNumber)}</span>` : "<span></span>"}
      <span class="authority-badge ${r.isCurrent ? "current" : "historical"}">${r.isCurrent ? "Current" : "Historical"} · ${escapeHtml(r.authority)}</span>
    </div>
    ${detail.parent ? `<p class="rule-detail-breadcrumb">${escapeHtml(detail.parent.title ? detail.parent.title : `Part of ${detail.parent.ruleNumber || ""}`)}</p>` : ""}
    ${r.title ? `<h2>${escapeHtml(r.title)}</h2><p class="rule-detail-text">${escapeHtml(r.text)}</p>` : `<p class="rule-detail-text" style="font-size:13px">${escapeHtml(r.text)}</p>`}
    ${detail.keywords.length ? `<div class="rule-detail-section"><h4>Keywords</h4><div class="rule-chip-row">${detail.keywords.map(k => `<button type="button" class="rule-chip" data-keyword-goto="${k.id}">${escapeHtml(k.name)}</button>`).join("")}</div></div>` : ""}
    ${detail.children.length ? `<div class="rule-detail-section"><h4>Sub-Rules</h4><div class="rule-detail-link-list">${detail.children.map(ruleLinkMarkup).join("")}</div></div>` : ""}
    ${detail.references.length ? `<div class="rule-detail-section"><h4>Related Rules</h4><div class="rule-detail-link-list">${detail.references.map(ruleLinkMarkup).join("")}</div></div>` : ""}
    ${detail.referencedBy.length ? `<div class="rule-detail-section"><h4>Referenced By</h4><div class="rule-detail-link-list">${detail.referencedBy.map(ruleLinkMarkup).join("")}</div></div>` : ""}
    <div class="rule-detail-nav">
      <button type="button" class="command-btn quiet" ${detail.previous ? `data-rule-goto="${detail.previous.id}"` : "disabled"}>&larr; Previous</button>
      <button type="button" class="command-btn quiet" ${detail.next ? `data-rule-goto="${detail.next.id}"` : "disabled"}>Next &rarr;</button>
    </div>`;
  renderIcons(root);
}

async function showRulesGlossary() {
  state.rules.mode = "glossary";
  state.rules.query = "";
  document.getElementById("rulesSearchInput").value = "";
  renderRulesQuickTopics();
  const root = document.getElementById("rulesResults");
  root.innerHTML = `<div class="loading-line" style="padding:20px">Loading glossary...</div>`;
  try {
    const keywords = await api("/api/rules/keywords");
    state.rules.glossary = keywords;
    renderRulesResultList(keywords, `${keywords.length} keywords`, k => ({
      id: k.id, kind: "keyword", title: k.name, subtitle: k.category || ""
    }));
    if (keywords.length) await selectKeywordResult(keywords[0].id);
  } catch {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load glossary</h2></div>`;
    renderIcons(root);
  }
}

async function selectKeywordResult(id) {
  const root = document.getElementById("rulesDetail");
  root.innerHTML = `<div class="loading-line">Loading...</div>`;
  try {
    renderKeywordDetail(await api(`/api/rules/keywords/${id}`));
    markActiveResult(id);
  } catch {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load keyword</h2></div>`;
    renderIcons(root);
  }
}

function renderKeywordDetail(detail) {
  const root = document.getElementById("rulesDetail");
  root.innerHTML = `
    <div class="rule-detail-head"><span class="rule-detail-number">${escapeHtml(detail.category || "Keyword")}</span></div>
    <h2>${escapeHtml(detail.name)}</h2>
    ${detail.canonicalRule
      ? `<p class="rule-detail-text">${escapeHtml(detail.canonicalRule.text)}</p><div class="rule-detail-section"><button type="button" class="command-btn quiet" data-rule-goto="${detail.canonicalRule.id}">View Rule ${escapeHtml(detail.canonicalRule.ruleNumber || "")}</button></div>`
      : `<p class="rule-detail-text">No official rule text is directly linked to this keyword yet.</p>`}
    ${detail.aliases.length ? `<div class="rule-detail-section"><h4>Also Known As</h4><div class="rule-chip-row">${detail.aliases.map(a => `<span class="rule-chip">${escapeHtml(a)}</span>`).join("")}</div></div>` : ""}
    ${detail.mentionedIn.length ? `<div class="rule-detail-section"><h4>Related Rules</h4><div class="rule-detail-link-list">${detail.mentionedIn.slice(0, 12).map(ruleLinkMarkup).join("")}</div></div>` : ""}
    ${detail.cards.length ? `<div class="rule-detail-section"><h4>Cards Using ${escapeHtml(detail.name)}</h4><div class="rule-chip-row">${detail.cards.slice(0, 20).map(c => `<span class="rule-chip">${escapeHtml(c.name)}</span>`).join("")}${detail.cards.length > 20 ? `<span class="rule-chip">+${detail.cards.length - 20} more</span>` : ""}</div></div>` : ""}`;
  renderIcons(root);
}

async function showRulesErrata() {
  state.rules.mode = "errata";
  state.rules.query = "";
  document.getElementById("rulesSearchInput").value = "";
  renderRulesQuickTopics();
  const root = document.getElementById("rulesResults");
  root.innerHTML = `<div class="loading-line" style="padding:20px">Loading errata...</div>`;
  try {
    const entries = await api("/api/rules/errata");
    state.rules.errata = entries;
    renderRulesResultList(entries, `${entries.length} errata entries`, e => ({
      id: e.id, kind: "errata", title: e.cardName, subtitle: e.cardId ? "" : "Unresolved card name"
    }));
    if (entries.length) selectErrataResult(entries[0].id);
  } catch {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load errata</h2></div>`;
    renderIcons(root);
  }
}

function selectErrataResult(id) {
  const entry = state.rules.errata.find(e => e.id === id);
  const root = document.getElementById("rulesDetail");
  if (!entry) return;
  root.innerHTML = `
    <div class="rule-detail-head"><span class="authority-badge current">Official Errata</span></div>
    <h2>${escapeHtml(entry.cardName)}</h2>
    <div class="rule-errata-block">
      <div class="old-text"><h5>Old Text</h5>${escapeHtml(entry.originalText || "—")}</div>
      <div class="new-text"><h5>New Text</h5>${escapeHtml(entry.correctedText || "—")}</div>
    </div>`;
  renderIcons(root);
  markActiveResult(id);
}

async function showRulesLegality() {
  state.rules.mode = "legality";
  state.rules.query = "";
  document.getElementById("rulesSearchInput").value = "";
  renderRulesQuickTopics();
  const root = document.getElementById("rulesResults");
  root.innerHTML = `<div class="loading-line" style="padding:20px">Loading banned list...</div>`;
  try {
    const entries = await api("/api/rules/legality");
    state.rules.legality = entries;
    renderRulesResultList(entries, `${entries.length} banned entries`, e => ({
      id: e.id, kind: "legality", title: e.cardName, subtitle: e.format, badgeText: e.status
    }));
    if (entries.length) selectLegalityResult(entries[0].id);
  } catch {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load banned list</h2></div>`;
    renderIcons(root);
  }
}

function selectLegalityResult(id) {
  const entry = state.rules.legality.find(e => e.id === id);
  const root = document.getElementById("rulesDetail");
  if (!entry) return;
  root.innerHTML = `
    <div class="rule-detail-head"><span class="authority-badge historical">${escapeHtml(entry.status)}</span></div>
    <h2>${escapeHtml(entry.cardName)}</h2>
    <p class="rule-detail-text">Not legal in ${escapeHtml(entry.format)}.</p>`;
  renderIcons(root);
  markActiveResult(id);
}

function setRulesPageMode(mode) {
  state.rulesPageMode = mode;
  document.querySelectorAll("#rulesModeTabs button").forEach(b => b.classList.toggle("active", b.dataset.rulesMode === mode));
  document.getElementById("rulesSearchMode").hidden = mode !== "search";
  document.getElementById("rulesAskMode").hidden = mode !== "ask";
}

async function askRulesQuestion() {
  const input = document.getElementById("askRulesInput");
  const question = input.value.trim();
  const root = document.getElementById("askRulesResult");
  if (!question) return;
  const button = document.getElementById("askRulesBtn");
  button.disabled = true;
  root.innerHTML = `<div class="loading-line" style="padding:20px">Checking the rules...</div>`;
  // The Tournament Rules checkbox is the only way tournament/format context reaches the engine -
  // it never guesses this from the question's own wording. Prepending this exact phrase is what
  // the engine's routing patch keys off of, so it's a stable, deliberate flag, not a hint.
  const tournamentContext = document.getElementById("askRulesTournament").checked;
  const engineQuestion = tournamentContext ? `In a tournament: ${question}` : question;
  try {
    const result = await api("/api/rules/ask", jsonOptions("POST", { question: engineQuestion }));
    renderAskRulesResult(result);
  } catch (err) {
    root.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Couldn't answer that</h2><span>${escapeHtml(err.message)}</span></div>`;
    renderIcons(root);
  } finally {
    button.disabled = false;
  }
}

function renderAskRulesResult(result) {
  const root = document.getElementById("askRulesResult");
  const confidenceClass = result.confidence.toLowerCase();
  const confidenceLabel = result.confidence.replace(/([a-z])([A-Z])/g, "$1 $2");

  const clarifying = result.clarifyingQuestions || [];
  const cardNotes = result.cardNotes || [];
  const sources = result.sources || [];
  const hasEvidence = sources.length > 0 || cardNotes.length > 0;

  const answerBlock = result.answerGenerated
    ? `<p class="ask-answer-text">${escapeHtml(result.answer)}</p>`
    : `<p class="ask-answer-note">The rules engine doesn't have a proven answer for this yet. Try rephrasing with an official term, or check Settings → Ask Rules to make sure it's turned on.</p>`;

  // The engine declines to guess a missing fact — it asks for it instead. Showing that request
  // directly (rather than silently treating the answer as final) is the same fail-closed
  // discipline the backend itself follows.
  const clarifyingBlock = clarifying.length
    ? `<div class="rule-detail-section" style="margin-top:0;padding-top:0;border-top:0"><h4>Needs more detail</h4><ul class="ask-clarify-list">${clarifying.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ul></div>`
    : "";

  const cardEvidenceRows = cardNotes.map(c => `
    <div class="ask-evidence-row">
      <div class="ask-evidence-row-head">
        <b>${escapeHtml(c.name)}</b>
        <span class="authority-badge current">Card Text</span>
      </div>
      <p>${escapeHtml(c.text || "")}</p>
    </div>`).join("");

  const ruleEvidenceRows = sources.map(s => `
    <div class="ask-evidence-row">
      <div class="ask-evidence-row-head">
        <button type="button" class="ask-evidence-rule-link" data-rule-popup="${escapeHtml(s.family || "core")}/${escapeHtml(s.ruleId)}"><b>Rule ${escapeHtml(s.ruleId)}</b></button>
      </div>
      <p>${escapeHtml(s.text)}</p>
    </div>`).join("");

  root.innerHTML = `
    <div class="ask-answer-panel">
      <div class="ask-confidence-row">
        <h3>Answer</h3>
        <span class="confidence-badge ${confidenceClass}">${escapeHtml(confidenceLabel)}</span>
      </div>
      ${answerBlock}
      ${clarifyingBlock}
      ${hasEvidence ? `<div class="rule-detail-section" style="margin-top:0;padding-top:0;border-top:0"><h4>Why?</h4><div class="ask-evidence-list">${cardEvidenceRows}${ruleEvidenceRows}</div></div>` : ""}
    </div>`;
  renderIcons(root);
}

// Lets a cited rule in Ask Rules' "Why?" list be read in place instead of forcing a trip to the
// Rules tab and a manual re-search for the same rule number.
async function showRulePopup(familyAndRuleId) {
  const heading = document.getElementById("rulePopupHeading");
  const body = document.getElementById("rulePopupBody");
  heading.textContent = "Loading...";
  body.innerHTML = `<div class="loading-line" style="padding:20px">Loading...</div>`;
  showModal("rulePopupModal");
  try {
    const [family, ruleId] = familyAndRuleId.split("/");
    const r = await api(`/api/rules/detail/${encodeURIComponent(family)}/${encodeURIComponent(ruleId)}`);
    heading.textContent = `Rule ${r.ruleId}`;
    body.innerHTML = `
      <div class="rule-detail-head">
        <span class="rule-detail-number">${escapeHtml(r.ruleId)}</span>
        ${r.majorSectionTitle ? `<span class="authority-badge current">${escapeHtml(r.majorSectionTitle)}</span>` : "<span></span>"}
      </div>
      <p class="rule-detail-text">${escapeHtml(r.text)}</p>
      ${r.exampleText ? `<p class="rule-detail-text" style="font-size:13px">${escapeHtml(r.exampleText)}</p>` : ""}`;
    renderIcons(body);
  } catch (err) {
    heading.textContent = "Rule Detail";
    body.innerHTML = `<div class="page-empty"><i data-icon="alert-triangle"></i><h2>Could not load rule</h2><span>${escapeHtml(err.message)}</span></div>`;
    renderIcons(body);
  }
}

async function toggleLocalAi() {
  const button = document.getElementById("toggleLocalAi");
  button.disabled = true;
  try {
    const result = await api("/api/rules/local-ai/configure", jsonOptions("POST", { enabled: !state.localAiEnabled }));
    toast(result.enabled ? "Local AI answers enabled" : "Local AI answers disabled");
    await loadLocalAiStatus();
  } catch (err) {
    toast(err.message, true);
    button.disabled = false;
  }
}

function openPurgeDataModal() {
  document.querySelectorAll("#purgeDataModal [data-purge-key]").forEach(input => { input.checked = false; });
  const confirmInput = document.getElementById("purgeConfirmInput");
  confirmInput.value = "";
  updatePurgeConfirmState();
  showModal("purgeDataModal");
}

function updatePurgeConfirmState() {
  const anyChecked = !!document.querySelector("#purgeDataModal [data-purge-key]:checked");
  const typedResetConfirmation = document.getElementById("purgeConfirmInput").value.trim().toUpperCase() === "RESET";
  document.getElementById("confirmPurgeBtn").disabled = !(anyChecked && typedResetConfirmation);
}

async function confirmPurgeData() {
  const button = document.getElementById("confirmPurgeBtn");
  const options = {};
  document.querySelectorAll("#purgeDataModal [data-purge-key]").forEach(input => {
    options[input.dataset.purgeKey] = input.checked;
  });
  button.disabled = true;
  try {
    const result = await api("/api/settings/purge", jsonOptions("POST", options));
    const parts = [];
    if (result.ownedCardsReset) parts.push(`${result.ownedCardsReset} owned counts`);
    if (result.binderCardsReset) parts.push(`${result.binderCardsReset} binder entries`);
    if (result.favoritesCleared) parts.push(`${result.favoritesCleared} favorites`);
    if (result.notesCleared) parts.push(`${result.notesCleared} notes`);
    if (result.decksDeleted) parts.push(`${result.decksDeleted} decks`);
    if (result.priceSnapshotsDeleted) parts.push(`${result.priceSnapshotsDeleted} price snapshots`);
    if (result.priceQueueCleared) parts.push(`${result.priceQueueCleared} queued cards`);
    toast(parts.length ? `Reset: ${parts.join(", ")}` : "Nothing needed resetting.");
    closeModal("purgeDataModal");
    location.reload();
  } catch (err) {
    toast(err.message, true);
    button.disabled = false;
  }
}

// Bug Report — files a real GitHub Issue via a scoped write-only token the backend holds. The
// screenshot never goes through that API call at all (GitHub has no way to attach a binary image
// to an issue except through its website's own session-authenticated upload, regardless of token
// scope) — instead it's copied to the OS clipboard and the new issue opens in the browser, so one
// Ctrl+V drops it into a comment.
let bugReportAttachedBlob = null;

function resetBugReportForm() {
  bugReportAttachedBlob = null;
  document.getElementById("bugReportTitle").value = "";
  document.getElementById("bugReportDescription").value = "";
  document.getElementById("bugReportScreenshotInput").value = "";
  document.getElementById("bugReportStatus").textContent = "";
  renderBugReportScreenshotPreview();
}

function renderBugReportScreenshotPreview() {
  const preview = document.getElementById("bugReportScreenshotPreview");
  if (!bugReportAttachedBlob) {
    preview.innerHTML = `<i data-icon="image"></i><span>None attached — one will be captured automatically when you submit, or attach your own below.</span>`;
    renderIcons(preview);
    return;
  }
  const url = URL.createObjectURL(bugReportAttachedBlob);
  preview.innerHTML = `<img src="${url}" alt="Attached screenshot" />`;
}

async function fetchAutoScreenshot() {
  const response = await fetch("/api/bug-report/screenshot");
  if (response.status === 204 || !response.ok) return null;
  return response.blob();
}

async function copyBlobToClipboard(blob) {
  try {
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    return true;
  } catch {
    return false; // Clipboard permissions can vary — the issue still gets filed either way.
  }
}

async function submitBugReport() {
  const button = document.getElementById("bugReportSubmit");
  const status = document.getElementById("bugReportStatus");
  const title = document.getElementById("bugReportTitle").value.trim();
  const description = document.getElementById("bugReportDescription").value.trim();
  if (!title || !description) {
    status.textContent = "Title and description are both required.";
    return;
  }

  button.disabled = true;
  status.textContent = "Submitting...";
  try {
    let screenshot = bugReportAttachedBlob;
    if (!screenshot) {
      status.textContent = "Capturing a screenshot...";
      screenshot = await fetchAutoScreenshot();
    }
    if (!screenshot) {
      status.textContent = "Couldn't capture a screenshot automatically — please attach one below.";
      button.disabled = false;
      return;
    }

    status.textContent = "Filing the issue...";
    const result = await api("/api/bug-report", jsonOptions("POST", { title, description }));
    if (!result.ok) {
      status.textContent = result.message;
      button.disabled = false;
      return;
    }

    const copied = await copyBlobToClipboard(screenshot);
    if (result.issueUrl) {
      await api("/api/open-external", jsonOptions("POST", { url: result.issueUrl })).catch(() => {});
    }
    closeModal("bugReportModal");
    toast(copied
      ? "Issue filed — screenshot copied to your clipboard. Paste it (Ctrl+V) into a comment on the page that just opened."
      : "Issue filed — couldn't copy the screenshot to your clipboard, so attach it manually on the page that just opened.");
  } catch (err) {
    status.textContent = err.message;
  } finally {
    button.disabled = false;
  }
}

// Frontend errors land in the same rolling log file the backend writes to, so a bug report always
// carries both sides of a failure — best-effort and silent on its own failure, since a broken
// logger must never itself throw during error handling.
function logClientError(message, stack) {
  api("/api/logs/client", jsonOptions("POST", { message, stack: stack || "", url: location.href })).catch(() => {});
}
window.addEventListener("error", event => logClientError(event.message, event.error?.stack));
window.addEventListener("unhandledrejection", event => logClientError(String(event.reason), event.reason?.stack));

function wireEvents() {
  document.addEventListener("mouseover", event => {
    const row = event.target.closest("[data-hover-card]");
    if (row && !row.contains(event.relatedTarget)) showDeckRowPopup(row.dataset.hoverCard, event);
    const rec = event.target.closest("[data-hover-rec]");
    if (rec && !rec.contains(event.relatedTarget)) showRecommendationPopup(rec.dataset.hoverRec, event);
  });
  document.addEventListener("mousemove", event => {
    if (event.target.closest("[data-hover-card], [data-hover-rec]")) positionDeckRowPopup(event);
  });
  document.addEventListener("mouseout", event => {
    const row = event.target.closest("[data-hover-card], [data-hover-rec]");
    if (row && !row.contains(event.relatedTarget)) hideDeckRowPopup();
  });
  document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click", () => navigate(button.dataset.page)));
  document.getElementById("mobileMenu").addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
  document.getElementById("setNav").addEventListener("click", event => {
    const button = event.target.closest("[data-set-id]"); if (!button) return;
    state.setId = button.dataset.setId || null; renderSetNavigation(); navigate("vault");
  });
  document.querySelectorAll(".vault-tab").forEach(button => button.addEventListener("click", () => {
    // Token cards use their own rarity/type/domain values (Battlefield/Gear/Marker, Colorless)
    // that don't overlap with a normal card's — a filter left over from browsing regular cards
    // would just produce an empty, confusing result the moment either tab is entered or left.
    if (button.dataset.owned === "tokens" || state.owned === "tokens") {
      state.rarity = state.type = state.domain = "";
      document.getElementById("rarityFilter").value = document.getElementById("typeFilter").value = document.getElementById("domainFilter").value = "";
    }
    state.owned = button.dataset.owned;
    document.querySelectorAll(".vault-tab").forEach(item => item.classList.toggle("active", item === button));
    saveNavState();
    loadVault().catch(err => toast(err.message, true));
  }));
  [["rarityFilter", "rarity"], ["typeFilter", "type"], ["domainFilter", "domain"], ["sortFilter", "sort"]].forEach(([id, key]) =>
    document.getElementById(id).addEventListener("change", event => { state[key] = event.target.value; loadVault(); }));
  document.getElementById("clearFilters").addEventListener("click", () => {
    state.rarity = state.type = state.domain = "";
    document.getElementById("rarityFilter").value = document.getElementById("typeFilter").value = document.getElementById("domainFilter").value = "";
    loadVault();
  });
  document.querySelectorAll(".view-toggle").forEach(button => button.addEventListener("click", () => {
    state.view = button.dataset.view;
    document.querySelectorAll(".view-toggle").forEach(item => item.classList.toggle("active", item === button));
    loadVault().catch(err => toast(err.message, true));
  }));
  let searchTimer;
  document.getElementById("globalSearch").addEventListener("input", event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.search = event.target.value.trim(); navigate("vault"); }, 220);
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); document.getElementById("globalSearch").focus(); }
    if (event.key === "Escape") {
      closeCardContextMenu();
      document.querySelectorAll(".modal-layer:not([hidden])").forEach(modal => closeModal(modal.id));
    }
  });
  document.addEventListener("contextmenu", event => {
    const tile = event.target.closest("[data-card-open]");
    if (!tile) return closeCardContextMenu();
    const card = cardsById.get(tile.dataset.cardOpen);
    if (!card) return;
    event.preventDefault();
    showCardContextMenu(card, event.clientX, event.clientY);
  });
  document.getElementById("cardContextMenu").addEventListener("keydown", event => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...event.currentTarget.querySelectorAll("button:not(:disabled)")];
    if (!buttons.length) return;
    const current = buttons.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : event.key === 'ArrowDown' ? (current + 1) % buttons.length
        : (current - 1 + buttons.length) % buttons.length;
    buttons[next].focus();
  });
  document.getElementById("cardContextMenu").addEventListener("click", event => {
    event.stopPropagation();
    const deckButton = event.target.closest("[data-context-deck]");
    if (deckButton) {
      const card = cardsById.get(state.contextCardId);
      closeCardContextMenu();
      if (card) addContextCardToDeck(card, Number(deckButton.dataset.contextDeck)).catch(err => toast(err.message, true));
      return;
    }
    const action = event.target.closest("[data-context-action]");
    if (action) handleCardContextAction(action.dataset.contextAction).catch(err => toast(err.message, true));
  });
  document.addEventListener("click", event => {
    if (!event.target.closest("#cardContextMenu")) closeCardContextMenu();
    const imagePopout = event.target.closest("[data-fullscreen-card]");
    if (imagePopout) { event.preventDefault(); event.stopPropagation(); openFullscreenCardImage(imagePopout.dataset.fullscreenCard); return; }
    if (event.target.closest(".card-trade-toggle")) { event.stopPropagation(); return; }
    const owned = event.target.closest("[data-owned-delta]");
    if (owned) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(owned.dataset.cardId); if (card) changeOwned(card, Number(owned.dataset.ownedDelta)); return; }
    const favorite = event.target.closest("[data-favorite-card]");
    if (favorite) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(favorite.dataset.favoriteCard); if (card) changeFavorite(card); return; }
    const binder = event.target.closest("[data-binder-delta]");
    if (binder) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(binder.dataset.cardId); if (card) changeBinder(card, Number(binder.dataset.binderDelta)); return; }
    const confirmTradeBtn = event.target.closest("[data-confirm-trade]");
    if (confirmTradeBtn) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(confirmTradeBtn.dataset.confirmTrade); if (card) confirmTrade(card).catch(err => toast(err.message, true)); return; }
    const priceQueueRemove = event.target.closest("[data-price-queue-remove]");
    if (priceQueueRemove) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(priceQueueRemove.dataset.priceQueueRemove); if (card) setPriceQueue(card, false).catch(err => toast(err.message, true)); return; }
    const card = event.target.closest("[data-card-open]");
    if (card) { openCard(card.dataset.cardOpen); return; }
    const deck = event.target.closest("[data-deck-id]");
    if (deck) { state.activeDeckId = Number(deck.dataset.deckId); saveNavState(); loadDecks(); return; }
    if (event.target.closest("[data-new-deck]")) openNewDeckModal();
  });
  document.addEventListener("change", event => {
    const toggle = event.target.closest("[data-card-trade-toggle]");
    if (!toggle) return;
    const card = cardsById.get(toggle.dataset.cardTradeToggle);
    if (!card) return;
    setBinderAvailability(card, toggle.checked).catch(err => {
      toggle.checked = !toggle.checked;
      toast(err.message, true);
    });
  });
  window.addEventListener("resize", closeCardContextMenu);
  window.addEventListener("scroll", event => {
    if (event.target instanceof Element && event.target.closest("#cardContextMenu")) return;
    closeCardContextMenu();
  }, true);
  document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => closeModal(button.dataset.close)));
  document.querySelectorAll(".modal-layer").forEach(layer => layer.addEventListener("click", event => { if (event.target === layer) closeModal(layer.id); }));
  document.querySelectorAll("[data-export-preview]").forEach(button => button.addEventListener("click", () => {
    state.exportFormat = button.dataset.exportPreview;
    refreshExportPreview();
  }));
  document.getElementById("confirmExportBtn")?.addEventListener("click", () => exportActiveDeck(state.exportFormat));
  document.getElementById("openAddCollection").addEventListener("click", () => openAddCollectionModal("massAdd"));
  document.querySelector("#addCollectionModal .add-collection-tabs").addEventListener("click", event => {
    const tab = event.target.closest("[data-add-tab]");
    if (tab) switchAddCollectionTab(tab.dataset.addTab);
  });
  document.getElementById("launchScanFromAdd").addEventListener("click", () => {
    closeModal("addCollectionModal");
    setScanMode("add");
    resetScanner();
    showModal("scanModal");
  });
  document.getElementById("openBugReport").addEventListener("click", () => {
    resetBugReportForm();
    showModal("bugReportModal");
  });
  document.getElementById("bugReportAttachBtn").addEventListener("click", () =>
    document.getElementById("bugReportScreenshotInput").click());
  document.getElementById("bugReportScreenshotInput").addEventListener("change", event => {
    const file = event.target.files?.[0];
    if (!file) return;
    bugReportAttachedBlob = file;
    renderBugReportScreenshotPreview();
  });
  document.getElementById("bugReportSubmit").addEventListener("click", submitBugReport);
  document.getElementById("packImportList").addEventListener("click", event => {
    const row = event.target.closest("[data-pack-key]");
    if (row) previewPack(row).catch(err => toast(err.message, true));
  });
  document.getElementById("packPreviewHeader").addEventListener("click", event => {
    if (event.target.closest("#confirmImportPackBtn")) confirmImportPack().catch(err => toast(err.message, true));
    if (event.target.closest("#confirmRemovePackBtn")) confirmRemovePack().catch(err => toast(err.message, true));
  });
  document.getElementById("massAddConfirm").addEventListener("click", () => confirmMassAdd().catch(err => toast(err.message, true)));

  const massAddEntryInput = document.getElementById("massAddEntryInput");
  massAddEntryInput.addEventListener("input", scheduleMassAddSearch);
  massAddEntryInput.addEventListener("paste", handleMassAddPaste);
  massAddEntryInput.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      document.getElementById("massAddDropdown").hidden = true;
    } else if (event.key === "Enter") {
      event.preventDefault();
      const firstPick = document.querySelector("#massAddDropdown [data-mass-pick-group]");
      if (firstPick) selectMassAddGroup(Number(firstPick.dataset.massPickGroup));
    }
  });
  document.getElementById("massAddDropdown").addEventListener("click", event => {
    const pick = event.target.closest("[data-mass-pick-group]");
    if (pick) selectMassAddGroup(Number(pick.dataset.massPickGroup));
  });
  document.getElementById("massAddLines").addEventListener("click", event => {
    const remove = event.target.closest("[data-mass-remove]");
    if (remove) { removeMassAddLine(remove.dataset.massRemove); return; }
    const qty = event.target.closest("[data-mass-qty-delta]");
    if (qty) { setMassAddQuantity(qty.dataset.massLineTarget, Number(qty.dataset.massQtyDelta)); return; }
    const line = event.target.closest("[data-mass-line]");
    if (line) { massAddLockedId = line.dataset.massLine; renderMassAddLines(); renderMassAddPreview(); }
  });
  document.getElementById("massAddLines").addEventListener("mouseover", event => {
    const line = event.target.closest("[data-mass-line]");
    const id = line?.dataset.massLine ?? null;
    if (id === massAddHoverId) return;
    massAddHoverId = id;
    renderMassAddPreview();
  });
  document.getElementById("massAddLines").addEventListener("mouseleave", () => {
    if (massAddHoverId === null) return;
    massAddHoverId = null;
    renderMassAddPreview();
  });
  document.getElementById("massAddPreviewPanel").addEventListener("click", event => {
    const qty = event.target.closest("[data-mass-qty-delta]");
    if (qty) { setMassAddQuantity(qty.dataset.massLineTarget, Number(qty.dataset.massQtyDelta)); return; }
    const variant = event.target.closest("[data-mass-variant]");
    if (variant) switchMassAddLineVariant(variant.dataset.massVariantTarget, variant.dataset.massVariant);
  });
  document.getElementById("massAddErrors").addEventListener("click", event => {
    if (event.target.closest("#massAddErrorsClear")) { massAddErrors = []; renderMassAddErrors(); }
  });
  document.getElementById("massAddVariantGrid").addEventListener("click", event => {
    const pick = event.target.closest("[data-variant-pick]");
    if (pick) resolveMassAddVariantPrompt(pick.dataset.variantPick);
  });
  document.getElementById("massAddVariantSkip").addEventListener("click", () => resolveMassAddVariantPrompt(null));
  document.addEventListener("click", event => {
    if (!event.target.closest(".mass-add-entry")) document.getElementById("massAddDropdown").hidden = true;
  });
  document.getElementById("openConnection").addEventListener("click", openConnection);
  document.getElementById("updateIndicator").addEventListener("click", () => navigate("settings"));
  document.getElementById("refreshCatalogBtn").addEventListener("click", refreshCatalog);
  ["newDeckBtn", "emptyNewDeck"].forEach(id => document.getElementById(id).addEventListener("click", openNewDeckModal));
  document.getElementById("legendSearch").addEventListener("input", event => {
    state.legendPicker.search = event.target.value;
    renderLegendGrid();
  });
  document.getElementById("legendOwnedOnly").addEventListener("change", event => {
    state.legendPicker.ownedOnly = event.target.checked;
    refreshLegendPicker().catch(err => toast(err.message, true));
  });
  document.getElementById("legendPickerGrid").addEventListener("click", event => {
    const button = event.target.closest("[data-legend-base]");
    if (button) selectLegendGroup(button.dataset.legendBase);
  });
  document.getElementById("importDeckBtn").addEventListener("click", () => showModal("importDeckModal"));
  document.getElementById("confirmImportDeck").addEventListener("click", importDeck);
  document.getElementById("savePricingKey").addEventListener("click", savePricingKey);
  document.getElementById("clearPricingKey").addEventListener("click", clearPricingKey);
  document.getElementById("saveTopdeckKey").addEventListener("click", saveTopdeckKey);
  document.getElementById("clearTopdeckKey").addEventListener("click", clearTopdeckKey);
  document.getElementById("syncCommunityBtn").addEventListener("click", syncCommunityData);
  document.getElementById("openPurgeData").addEventListener("click", openPurgeDataModal);
  document.getElementById("purgeConfirmInput").addEventListener("input", updatePurgeConfirmState);
  document.querySelectorAll("#purgeDataModal [data-purge-key]").forEach(input =>
    input.addEventListener("change", updatePurgeConfirmState));
  document.getElementById("confirmPurgeBtn").addEventListener("click", confirmPurgeData);
  document.getElementById("rulesModeTabs").addEventListener("click", event => {
    const button = event.target.closest("[data-rules-mode]");
    if (button) setRulesPageMode(button.dataset.rulesMode);
  });
  document.getElementById("askRulesBtn").addEventListener("click", askRulesQuestion);
  document.getElementById("askRulesResult").addEventListener("click", event => {
    const button = event.target.closest("[data-rule-popup]");
    if (button) showRulePopup(button.dataset.rulePopup);
  });
  document.getElementById("askRulesInput").addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") askRulesQuestion();
  });
  document.getElementById("toggleLocalAi").addEventListener("click", toggleLocalAi);
  document.getElementById("rulesSearchInput").addEventListener("input", event => {
    clearTimeout(state.rules.searchTimer);
    const value = event.target.value;
    state.rules.searchTimer = setTimeout(() => runRulesSearch(value), 250);
  });
  document.getElementById("rulesQuickTopics").addEventListener("click", event => {
    const button = event.target.closest("[data-topic-label]");
    if (!button) return;
    const topic = RULES_QUICK_TOPICS.find(t => t.label === button.dataset.topicLabel);
    if (!topic) return;
    if (topic.mode === "glossary") showRulesGlossary().catch(err => toast(err.message, true));
    else if (topic.mode === "errata") showRulesErrata().catch(err => toast(err.message, true));
    else if (topic.mode === "legality") showRulesLegality().catch(err => toast(err.message, true));
    else {
      document.getElementById("rulesSearchInput").value = topic.query;
      runRulesSearch(topic.query).catch(err => toast(err.message, true));
    }
  });
  document.getElementById("rulesResults").addEventListener("click", event => {
    const button = event.target.closest("[data-result-id]");
    if (!button) return;
    const kind = button.dataset.resultKind;
    // Rule/keyword results use legacy numeric IDs; errata/legality use string IDs (e.g.
    // "origins-errata:006") — coercing those through Number() turned every one into NaN, so a
    // click always missed on the find(e => e.id === id) lookup and silently did nothing.
    const id = kind === "rule" || kind === "keyword" ? Number(button.dataset.resultId) : button.dataset.resultId;
    if (kind === "rule") selectRuleResult(id);
    else if (kind === "keyword") selectKeywordResult(id);
    else if (kind === "errata") selectErrataResult(id);
    else if (kind === "legality") selectLegalityResult(id);
  });
  document.getElementById("rulesDetail").addEventListener("click", event => {
    const ruleBtn = event.target.closest("[data-rule-goto]");
    if (ruleBtn) { selectRuleResult(Number(ruleBtn.dataset.ruleGoto)); return; }
    const keywordBtn = event.target.closest("[data-keyword-goto]");
    if (keywordBtn) selectKeywordResult(Number(keywordBtn.dataset.keywordGoto));
  });
  document.getElementById("refreshTrackedPrices").addEventListener("click", () => refreshPrices(false));
  document.getElementById("refreshAllPrices").addEventListener("click", () => refreshPrices(true));
  document.getElementById("clearPriceQueue").addEventListener("click", () => clearPriceQueue().catch(err => toast(err.message, true)));
  document.getElementById("checkPriceQueue").addEventListener("click", checkPriceQueue);
  document.getElementById("priceQueueSettings").addEventListener("click", () => navigate("settings"));
  document.getElementById("tradeAllBtn").addEventListener("click", () => confirmTradeAll().catch(err => toast(err.message, true)));
  document.getElementById("updateFooterCheck").addEventListener("click", checkForUpdates);
  document.getElementById("updateFooterApply").addEventListener("click", applyUpdate);
  document.getElementById("updateFooterPatchNotes").addEventListener("click", openPatchNotes);
  document.getElementById("updateFooterDismiss").addEventListener("click", dismissUpdateFooter);
  document.querySelectorAll("#themeControl button").forEach(button => button.addEventListener("click", () => setTheme(button.dataset.themeValue)));
  document.getElementById("openCheckPrice").addEventListener("click", () => { setScanMode("price"); resetScanner(); showModal("scanModal"); });
  document.getElementById("closeScan").addEventListener("click", () => closeModal("scanModal"));
  document.querySelectorAll("[data-scan-tab]").forEach(button => button.addEventListener("click", () => {
    stopLiveScan();
    document.querySelectorAll("[data-scan-tab]").forEach(item => item.classList.toggle("active", item === button));
    document.querySelectorAll("[data-scan-panel]").forEach(panel => panel.classList.toggle("active", panel.dataset.scanPanel === button.dataset.scanTab));
  }));
  document.getElementById("scanFile").addEventListener("change", event => handleScanFile(event.target.files[0]));
  document.getElementById("scanFileExisting").addEventListener("change", event => handleScanFile(event.target.files[0]));
  document.getElementById("manualLookupBtn").addEventListener("click", manualLookup);
  document.getElementById("liveScanBtn").addEventListener("click", startLiveScan);
  document.getElementById("flipCamera").addEventListener("click", flipLiveCamera);
}

function openNewDeckModal() {
  state.legendPicker.mode = "create";
  showModal("deckModal");
  loadLegendPicker().catch(err => toast(err.message, true));
  setTimeout(() => document.getElementById("legendSearch").focus(), 0);
}

function openChangeLegendModal() {
  state.legendPicker.mode = "change";
  showModal("deckModal");
  loadLegendPicker().catch(err => toast(err.message, true));
  setTimeout(() => document.getElementById("legendSearch").focus(), 0);
}

async function changeDeckLegend(newLegend) {
  const oldLegendRow = state.activeDeck.cards.find(row => row.card.type === "Legend");
  if (oldLegendRow && oldLegendRow.cardId !== newLegend.id) {
    await api(`/api/decks/${state.activeDeckId}/cards`, jsonOptions("POST", { cardId: oldLegendRow.cardId, quantity: 0, section: oldLegendRow.section }));
  }
  await setDeckCard(state.activeDeckId, newLegend.id, 1, "main");
  await api(`/api/decks/${state.activeDeckId}`, jsonOptions("PUT", { coverCardId: newLegend.id }));
  closeModal("deckModal");
  await loadDecks();
  toast(`Legend changed to ${newLegend.name}`);
}

async function savePricingKey() {
  const apiKey = document.getElementById("pricingKey").value.trim();
  if (!apiKey) return;
  await api("/api/pricing/configure", jsonOptions("POST", { apiKey }));
  document.getElementById("pricingKey").value = "";
  toast("Pricing key saved locally");
  await loadSettings();
}

async function clearPricingKey() {
  await api("/api/pricing/configure", { method: "DELETE" });
  toast("Stored pricing key removed");
  await loadSettings();
}

async function saveTopdeckKey() {
  const apiKey = document.getElementById("topdeckKey").value.trim();
  if (!apiKey) return;
  await api("/api/topdeck/configure", jsonOptions("POST", { apiKey }));
  document.getElementById("topdeckKey").value = "";
  toast("TopDeck key saved locally");
  await loadSettings();
}

async function clearTopdeckKey() {
  await api("/api/topdeck/configure", { method: "DELETE" });
  toast("Stored TopDeck key removed");
  await loadSettings();
}

async function syncCommunityData() {
  const button = document.getElementById("syncCommunityBtn");
  button.disabled = true;
  try {
    const result = await api("/api/community-decks/sync", jsonOptions("POST", { days: 30 }));
    toast(result.ok
      ? `Synced ${result.tournamentCount} tournaments, ${result.deckCount} decks`
      : `Sync failed: ${result.error}`, !result.ok);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    await loadSettings();
  }
}

async function refreshPrices(includeAllCards) {
  const button = document.getElementById(includeAllCards ? "refreshAllPrices" : "refreshTrackedPrices");
  button.disabled = true;
  const original = button.textContent;
  button.textContent = includeAllCards ? "Refreshing catalog..." : "Refreshing...";
  try {
    const result = await api("/api/pricing/refresh", jsonOptions("POST", { includeAllCards }));
    await Promise.all([loadPrices(), loadOverview()]);
    toast(`${result.snapshotsSaved} price snapshots saved`);
    await refreshCurrentPage();
  } catch (err) { toast(err.message, true); }
  finally { button.disabled = false; button.textContent = original; renderIcons(button); }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("riftbound-theme", theme);
  document.querySelectorAll("#themeControl button").forEach(button => button.classList.toggle("active", button.dataset.themeValue === theme));
}

async function init() {
  wireEvents();
  renderIcons(document);
  restoreNavState();
  try {
    const [server] = await Promise.all([api("/api/server-info"), loadCardTextSymbols(), loadSets(), loadPrices(), loadPriceQueue(), loadOverview(), loadDecks()]);
    document.getElementById("currentVersion").textContent = server.version;
    document.querySelectorAll(".vault-tab").forEach(item => item.classList.toggle("active", item.dataset.owned === state.owned));
    navigate(state.page);
  } catch (err) {
    toast(`Vault startup failed: ${err.message}`, true);
  }
  checkUpdateIndicator();
  setInterval(checkUpdateIndicator, 5 * 60 * 1000);
}

init();
