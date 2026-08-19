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
  localAiEnabled: false
};
const cardsById = new Map();
let massEntries = [];
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

function domainSceneMarkup(domains) {
  const primary = domainName(domains[0]);
  const secondary = domains[1] ? domainName(domains[1]) : null;
  const crests = domains.slice(0, 2).map(value => {
    const name = domainName(value);
    return `<img src="/assets/domain-crests/${DOMAIN_CREST[name]}" alt="" aria-hidden="true" loading="lazy" decoding="async" />`;
  }).join("");
  return `<div class="list-domain-scene${secondary ? " dual-domain" : ""}" aria-hidden="true">
    <img class="list-domain-scene-art primary" src="/assets/domain-scenes/${DOMAIN_SCENE[primary]}" alt="" loading="lazy" decoding="async" />
    ${secondary ? `<img class="list-domain-scene-art secondary" src="/assets/domain-scenes/${DOMAIN_SCENE[secondary]}" alt="" loading="lazy" decoding="async" />` : ""}
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
            ? `<button class="binder-chip" data-binder-delta="-1" data-card-id="${escapeHtml(card.id)}" title="No longer offering this copy for trade — stays in your collection">Remove</button>
               <button class="binder-chip binder-chip-confirm" data-confirm-trade="${escapeHtml(card.id)}" title="Trade completed — removes this copy from your collection entirely">Confirm Trade</button>`
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
      ${domainSceneMarkup(domains)}
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
  await Promise.all([loadOverview(), refreshCurrentPage()]);
  refreshVisibleCardDetails(updated);
}

async function changeOwned(card, delta) {
  return setOwnedCount(card, card.ownedCount + delta);
}

async function changeFavorite(card) {
  const updated = await api(`/api/favorites/${encodeURIComponent(card.id)}`, jsonOptions("POST", { favorite: !card.isFavorite }));
  cardsById.set(updated.id, updated);
  await Promise.all([loadOverview(), refreshCurrentPage()]);
  refreshVisibleCardDetails(updated);
  toast(updated.isFavorite ? "Added to favorites" : "Removed from favorites");
}

async function changeBinder(card, delta) {
  if (card.ownedCount <= 0) return toast("Add a copy to your collection first", true);
  const next = Math.max(0, Math.min(card.ownedCount, (card.binderCount || 0) + delta));
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}`, jsonOptions("POST", { count: next }));
  cardsById.set(updated.id, updated);
  await Promise.all([loadOverview(), refreshCurrentPage()]);
  toast(`${card.name}: ${updated.binderCount} in binder`);
}

async function confirmTrade(card) {
  if (!confirm(`Confirm you traded away 1 copy of "${card.name}"? It will be removed from your collection.`)) return;
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}/confirm-trade`, jsonOptions("POST", { count: 1 }));
  cardsById.set(updated.id, updated);
  await Promise.all([loadOverview(), refreshCurrentPage()]);
  toast(`${card.name} traded — removed from your collection`);
}

async function setBinderAvailability(card, available) {
  if (card.ownedCount <= 0) return toast("Add a copy to your collection first", true);
  const count = available ? 1 : 0;
  const updated = await api(`/api/binder/${encodeURIComponent(card.id)}`, jsonOptions("POST", { count }));
  cardsById.set(updated.id, updated);
  await Promise.all([loadOverview(), refreshCurrentPage()]);
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
  const copies = cards.reduce((sum, card) => sum + card.binderCount, 0);
  document.getElementById("binderMeta").textContent = `${cards.length} card${cards.length === 1 ? "" : "s"} available to trade`;
  document.getElementById("binderEmpty").hidden = cards.length > 0;
  document.getElementById("binderValue").textContent = state.overview?.hasPricing ? formatMoney(state.overview.binderValue) : "Pricing not configured";
  document.getElementById("binderSummary").innerHTML = `
    <div><b>${cards.length}</b><span>Unique cards</span></div><div><b>${copies}</b><span>Total copies</span></div><div><b>${state.overview?.hasPricing ? formatMoney(state.overview.binderValue) : "--"}</b><span>Market value</span></div>`;
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
  root.querySelectorAll(".deck-row[data-hover-card]").forEach(row => row.addEventListener("click", event => {
    if (event.target.closest(".mini-stepper")) return;
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
  toast(result.updatedCards
    ? `${result.updatedCards} card${result.updatedCards === 1 ? "" : "s"} marked for trade`
    : "Every card in this deck was already marked for trade");
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
  // Runes are a separate resource pool played from their own Rune Deck, never drawn alongside
  // Main Deck cards — excluded here even though this app stores both in the same "main" section.
  const pool = state.activeDeck.cards
    .filter(row => row.section === "main" && row.card.type !== "Rune")
    .flatMap(row => Array.from({ length: row.quantity }, () => row.card));
  if (!pool.length) return toast("Add cards to the deck first", true);
  const draw = () => {
    const shuffled = [...pool].sort(() => Math.random() - .5).slice(0, Math.min(7, pool.length));
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
  const rulesSync = await api("/api/rules/status");
  document.getElementById("rulesSyncStatus").textContent = rulesSync.lastSuccessfulSyncAt
    ? `Last synced ${formatRelativeTime(rulesSync.lastSuccessfulSyncAt)}${rulesSync.lastSyncOk ? "" : ` — failed: ${rulesSync.lastError}`}.`
    : "Never synced yet — pulls the Core/Tournament Rules, errata, and banned-card list from playriftbound.com.";
  document.getElementById("rulesSyncFacts").innerHTML = rulesSync.lastSuccessfulSyncAt
    ? `<span>${rulesSync.rulesIndexed} rules</span><span>${rulesSync.keywordsIndexed} keywords</span><span>${rulesSync.errataIndexed} errata</span><span>${rulesSync.legalityEntriesIndexed} legality entries</span>`
    : "";
  const db = health.database;
  document.getElementById("databaseStatus").textContent = db
    ? `Database verified: ${db.integrity}. Protected collection totals are checked at startup.`
    : "Database is ready.";
  document.getElementById("databaseFacts").innerHTML = db ? `<span>${health.cards} cards now</span><span>${health.ownedCards} owned now</span><span>${health.ownedCopies} copies now</span>${db.lastBackupPath ? `<span>Last migration backup: ${escapeHtml(db.lastBackupPath.split(/[\\/]/).pop())}</span>` : ""}` : "";
  document.getElementById("currentVersion").textContent = server.version;
  document.getElementById("settingsVersion").textContent = server.version;
  document.querySelectorAll("#themeControl button").forEach(button => button.classList.toggle("active", button.dataset.themeValue === document.documentElement.dataset.theme));
}

async function refreshCatalog() {
  const buttons = [document.getElementById("refreshCatalogBtn"), document.getElementById("sidebarRefresh")];
  buttons.forEach(button => { if (button) button.disabled = true; });
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
        buttons.forEach(button => { if (button) button.disabled = false; });
        await Promise.all([loadSets(), loadOverview(), refreshCurrentPage()]);
        toast("Catalog refreshed");
      }
    }, 2000);
  } catch (err) {
    buttons.forEach(button => { if (button) button.disabled = false; });
    toast(err.message, true);
  }
}

function parseCardEntry(raw) {
  const text = raw.trim();
  const withSet = /^([A-Za-z]{2,4}|\*)[\s-]*([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)$/.exec(text);
  if (withSet) return { setId: withSet[1] === "*" ? null : withSet[1].toUpperCase(), code: withSet[2].toUpperCase() };
  const bare = /^([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)$/.exec(text);
  return bare ? { setId: state.setId, code: bare[1].toUpperCase() } : null;
}

async function previewMassAdd() {
  const root = document.getElementById("massAddResults");
  const lines = document.getElementById("massAddInput").value.split(/[\r\n,]+/).map(value => value.trim()).filter(Boolean);
  massEntries = [];
  root.innerHTML = "";
  for (const raw of lines) {
    const quantityMatch = /\s+[xX](\d+)\s*$/.exec(raw);
    const quantity = quantityMatch ? Math.max(1, Number(quantityMatch[1])) : 1;
    const parsed = parseCardEntry(quantityMatch ? raw.slice(0, quantityMatch.index) : raw);
    if (!parsed) { massEntries.push({ raw, error: "Could not parse" }); continue; }
    const cards = await api(`/api/cards/lookup?${queryString(parsed)}`);
    registerCards(cards);
    if (!cards.length) massEntries.push({ raw, error: "No match" });
    else cards.forEach(card => massEntries.push({ raw, card, quantity, selected: cards.length === 1 }));
  }
  root.innerHTML = massEntries.map((entry, index) => entry.error
    ? `<div class="result-row error">${escapeHtml(entry.raw)}: ${escapeHtml(entry.error)}</div>`
    : `<label class="result-row result-check"><img src="${escapeHtml(cardImage(entry.card))}" alt="" /><div><strong>${escapeHtml(entry.card.name)}</strong><span>${escapeHtml(entry.card.setId)}-${escapeHtml(cardCode(entry.card))} / +${entry.quantity}</span></div><input type="checkbox" data-mass-index="${index}" ${entry.selected ? "checked" : ""} /></label>`).join("");
  document.getElementById("massAddConfirm").hidden = !massEntries.some(entry => !entry.error);
}

async function confirmMassAdd() {
  document.querySelectorAll("[data-mass-index]").forEach(input => { massEntries[Number(input.dataset.massIndex)].selected = input.checked; });
  const selected = massEntries.filter(entry => entry.selected && !entry.error);
  for (const entry of selected) {
    await api(`/api/collection/${encodeURIComponent(entry.card.id)}`, jsonOptions("POST", { owned: entry.card.ownedCount + entry.quantity }));
  }
  closeModal("massAddModal");
  toast(`${selected.length} card entr${selected.length === 1 ? "y" : "ies"} added`);
  await Promise.all([loadOverview(), refreshCurrentPage()]);
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

function openChangelog(notes) {
  document.getElementById("changelogBody").innerHTML = renderChangelog(notes);
  showModal("changelogModal");
}

async function checkForUpdates() {
  const button = document.getElementById("checkUpdateBtn");
  const status = document.getElementById("updateStatus");
  button.disabled = true;
  status.textContent = "Checking for updates...";
  try {
    const result = await api("/api/update/check");
    if (!result.selfUpdateSupported) status.textContent = result.unsupportedReason;
    else if (!result.updateAvailable) status.textContent = `Version ${result.currentVersion} is current.`;
    else {
      status.innerHTML = `Version ${escapeHtml(result.latestVersion)} is available. <button class="command-btn gold" id="applyUpdate">Update and Restart</button> <button class="command-btn quiet" id="viewChangelog">View Changelog</button>`;
      document.getElementById("applyUpdate").onclick = () => applyUpdate();
      document.getElementById("viewChangelog").onclick = () => openChangelog(result.releaseNotes);
    }
  } catch (err) { status.textContent = err.message; }
  finally { button.disabled = false; }
}

function formatBytes(bytes) {
  if (!bytes) return "0 MB";
  return `${(bytes / 1e6).toFixed(0)} MB`;
}

// Sidebar dot next to the version number — a lightweight signal that doesn't require opening
// Settings just to find out. Checked on load and every 5 minutes after that; a background check
// like this must never surface errors to the user (e.g. no internet right now is normal, not a
// problem worth a toast), so failures are swallowed silently.
async function checkUpdateIndicator() {
  try {
    const result = await api("/api/update/check");
    document.getElementById("updateIndicator").hidden = !(result.selfUpdateSupported && result.updateAvailable);
  } catch {
    // Silent — see comment above.
  }
}

async function applyUpdate() {
  const status = document.getElementById("updateStatus");
  status.innerHTML = `Starting update...`;
  try {
    const started = await api("/api/update/apply", { method: "POST" });
    if (started.error) { status.textContent = started.error; return; }
  } catch (err) {
    status.textContent = err.message;
    return;
  }
  pollUpdateProgress();
}

async function pollUpdateProgress() {
  const status = document.getElementById("updateStatus");
  let progress;
  try {
    progress = await api("/api/update/progress");
  } catch {
    // The connection dropping here is expected once the app has restarted itself — nothing to
    // report, the new instance will already be starting up.
    status.innerHTML = `Restarting — the app will reopen automatically.`;
    return;
  }

  if (progress.phase === "downloading") {
    const pct = progress.totalBytes ? Math.round((progress.bytesDownloaded / progress.totalBytes) * 100) : 0;
    status.innerHTML = `Downloading update... ${pct}% (${formatBytes(progress.bytesDownloaded)} / ${formatBytes(progress.totalBytes)})
      <div class="progress-track"><span style="width:${pct}%"></span></div>`;
    setTimeout(pollUpdateProgress, 500);
  } else if (progress.phase === "extracting") {
    status.innerHTML = `Extracting update...<div class="progress-track"><span style="width:100%"></span></div>`;
    setTimeout(pollUpdateProgress, 500);
  } else if (progress.phase === "restarting") {
    status.innerHTML = `Restarting — the app will reopen automatically.<div class="progress-track"><span style="width:100%"></span></div>`;
    // No further poll: the process exits shortly after entering this phase, so the next request
    // would just fail — the "restarting" message is already the right thing to leave on screen.
  } else if (progress.phase === "error") {
    status.textContent = progress.error || "Update failed.";
  } else {
    setTimeout(pollUpdateProgress, 500);
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
  showModal("packImportModal");
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
    await Promise.all([loadOverview(), refreshCurrentPage()]);
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
    await Promise.all([loadOverview(), refreshCurrentPage()]);
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
    await Promise.all([loadOverview(), refreshCurrentPage()]);
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
  try {
    const status = await api("/api/rules/status");
    meta.textContent = status.lastSuccessfulSyncAt
      ? `${status.rulesIndexed} rules · ${status.keywordsIndexed} keywords · updated ${formatRelativeTime(status.lastSuccessfulSyncAt)}`
      : "Not synced yet — open Settings to sync the rules library.";
  } catch {
    meta.textContent = "Could not load rules library status.";
  }
  renderRulesQuickTopics();
  await loadLocalAiStatus();

  if (state.rules.mode === "glossary") await showRulesGlossary();
  else if (state.rules.mode === "errata") await showRulesErrata();
  else if (state.rules.mode === "legality") await showRulesLegality();
  else if (state.rules.query) await runRulesSearch(state.rules.query);
}

async function loadLocalAiStatus() {
  const data = await api("/api/rules/local-ai/models");
  state.localAiEnabled = data.enabled;
  state.localAiModels = data.models;
  const selected = data.models.find(m => m.selected);

  const toggleBtn = document.getElementById("toggleLocalAi");
  toggleBtn.textContent = data.enabled ? "Disable" : "Enable";
  toggleBtn.disabled = !data.enabled && !(selected && selected.present);

  document.getElementById("askRulesProviderStatus").textContent =
    data.enabled && selected
      ? `On — running ${selected.displayName} locally (${(selected.bytes / 1e9).toFixed(1)} GB).`
      : selected && selected.present
        ? "Off — Ask Rules will still answer from real rules evidence, just without a written-out summary."
        : "No model downloaded yet — pick one below. Ask Rules will still answer from real rules evidence either way.";

  renderLocalAiModelList();
}

function renderLocalAiModelList() {
  const root = document.getElementById("localAiModelList");
  root.innerHTML = state.localAiModels.map(m => {
    const sizeGb = (m.approxBytes / 1e9).toFixed(1);
    let action;
    if (state.downloadingModelId === m.id) {
      const p = state.localAiDownloadProgress || {};
      const pct = p.totalBytes ? Math.round((p.downloadedBytes / p.totalBytes) * 100) : 0;
      action = p.phase === "checking"
        ? `<span class="local-ai-model-status">Checking for the release…</span>`
        : `<div class="local-ai-model-progress">Downloading… ${pct}%<div class="progress-track"><span style="width:${pct}%"></span></div></div>`;
    } else if (m.present && m.selected) {
      action = `<span class="local-ai-model-badge">In use</span>`;
    } else if (m.present) {
      action = `<button type="button" class="command-btn quiet" data-select-model="${m.id}">Use this</button>`;
    } else {
      action = `<button type="button" class="command-btn quiet" data-download-model="${m.id}">Download (${sizeGb} GB)</button>`;
    }
    return `
      <div class="local-ai-model-row${m.selected ? " selected" : ""}">
        <div class="local-ai-model-copy">
          <b>${escapeHtml(m.displayName)}</b>
          <span>${escapeHtml(m.description)}</span>
        </div>
        <div class="local-ai-model-action">${action}</div>
      </div>`;
  }).join("");
  root.querySelectorAll("[data-download-model]").forEach(btn =>
    btn.addEventListener("click", () => downloadLocalAiModel(btn.dataset.downloadModel)));
  root.querySelectorAll("[data-select-model]").forEach(btn =>
    btn.addEventListener("click", () => selectLocalAiModel(btn.dataset.selectModel)));
}

async function selectLocalAiModel(modelId, { silent } = {}) {
  try {
    await api("/api/rules/local-ai/select-model", jsonOptions("POST", { modelId }));
    if (!silent) toast("Switched Ask Rules' local model.");
    await loadLocalAiStatus();
  } catch (err) {
    toast(err.message, true);
  }
}

async function downloadLocalAiModel(modelId) {
  state.downloadingModelId = modelId;
  state.localAiDownloadProgress = null;
  renderLocalAiModelList();
  try {
    await api("/api/rules/local-ai/download-model", jsonOptions("POST", { modelId }));
  } catch (err) {
    state.downloadingModelId = null;
    toast(err.message, true);
    renderLocalAiModelList();
    return;
  }
  pollLocalAiModelProgress(modelId);
}

async function pollLocalAiModelProgress(modelId) {
  let progress;
  try {
    progress = await api(`/api/rules/local-ai/model-progress?modelId=${encodeURIComponent(modelId)}`);
  } catch (err) {
    state.downloadingModelId = null;
    toast(err.message, true);
    renderLocalAiModelList();
    return;
  }

  if (progress.phase === "downloading" || progress.phase === "checking") {
    state.localAiDownloadProgress = progress;
    renderLocalAiModelList();
    setTimeout(() => pollLocalAiModelProgress(modelId), 500);
  } else if (progress.phase === "error") {
    state.downloadingModelId = null;
    toast(progress.error || "Model download failed.", true);
    renderLocalAiModelList();
  } else {
    // "done" (or any other terminal state) — a freshly downloaded model is the one you just asked
    // for, so make it the active selection instead of leaving it downloaded-but-unused.
    state.downloadingModelId = null;
    await selectLocalAiModel(modelId, { silent: true });
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
  try {
    const result = await api("/api/rules/ask", jsonOptions("POST", { question }));
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

  const chips = [
    ...result.keywords.map(k => `<span class="rule-chip">${escapeHtml(k.name)}</span>`),
    ...result.concepts.map(c => `<span class="rule-chip">${escapeHtml(c.name)}</span>`)
  ].join("");

  const cardNotes = result.cardNotes || [];
  const hasEvidence = result.sources.length > 0 || cardNotes.length > 0;
  const answerBlock = result.answerGenerated
    ? `<p class="ask-answer-text">${escapeHtml(result.answer)}</p>`
    : hasEvidence
      ? `<p class="ask-answer-note">Local AI answers are off (Settings → Ask Rules), so here's the most relevant official rules text directly.</p>`
      : `<p class="ask-answer-note">I didn't find any official rule, keyword, or clarification that covers this question. Try rephrasing with an official term, or browse the Rules search instead.</p>`;

  const ruleEvidenceRows = result.sources.map(s => `
    <div class="ask-evidence-row">
      <div class="ask-evidence-row-head">
        <button type="button" class="ask-evidence-rule-link" data-rule-popup="${s.ruleId}"><b>${escapeHtml(s.ruleNumber ? `Rule ${s.ruleNumber}` : s.document)}</b></button>
        <span class="authority-badge ${s.current ? "current" : "historical"}">${s.current ? "Current" : "Historical"} · ${escapeHtml(s.authority)}</span>
      </div>
      <p>${escapeHtml(s.title.startsWith("Rule ") ? s.snippet : s.title)}</p>
      <span>${escapeHtml(s.document)} — matched via ${s.matchedVia.map(escapeHtml).join(", ")}</span>
    </div>`).join("");

  const cardNoteLabels = { CardText: "Card Text", OfficialErrata: "Errata", CoreRules: "Card Status" };
  const cardEvidenceRows = cardNotes.map(c => `
    <div class="ask-evidence-row">
      <div class="ask-evidence-row-head">
        <b>${escapeHtml(c.cardName)}</b>
        <span class="authority-badge current">${escapeHtml(cardNoteLabels[c.authority] || "Card Status")}</span>
      </div>
      <p>${escapeHtml(c.note)}</p>
    </div>`).join("");

  root.innerHTML = `
    <div class="ask-answer-panel">
      <div class="ask-confidence-row">
        <h3>Answer</h3>
        <span class="confidence-badge ${confidenceClass}">${escapeHtml(confidenceLabel)}</span>
      </div>
      ${answerBlock}
      ${chips ? `<div class="rule-chip-row" style="margin-bottom:16px">${chips}</div>` : ""}
      ${hasEvidence ? `<div class="rule-detail-section" style="margin-top:0;padding-top:0;border-top:0"><h4>Why?</h4><div class="ask-evidence-list">${cardEvidenceRows}${ruleEvidenceRows}</div></div>` : ""}
    </div>`;
  renderIcons(root);
}

// Lets a cited rule in Ask Rules' "Why?" list be read in place instead of forcing a trip to the
// Rules tab and a manual re-search for the same rule number.
async function showRulePopup(ruleId) {
  const heading = document.getElementById("rulePopupHeading");
  const body = document.getElementById("rulePopupBody");
  heading.textContent = "Loading...";
  body.innerHTML = `<div class="loading-line" style="padding:20px">Loading...</div>`;
  showModal("rulePopupModal");
  try {
    const detail = await api(`/api/rules/${ruleId}`);
    const r = detail.rule;
    heading.textContent = r.ruleNumber ? `Rule ${r.ruleNumber}` : (r.title || "Rule Detail");
    body.innerHTML = `
      <div class="rule-detail-head">
        ${r.ruleNumber ? `<span class="rule-detail-number">${escapeHtml(r.ruleNumber)}</span>` : "<span></span>"}
        <span class="authority-badge ${r.isCurrent ? "current" : "historical"}">${r.isCurrent ? "Current" : "Historical"} · ${escapeHtml(r.authority)}</span>
      </div>
      ${detail.parent ? `<p class="rule-detail-breadcrumb">${escapeHtml(detail.parent.title ? detail.parent.title : `Part of ${detail.parent.ruleNumber || ""}`)}</p>` : ""}
      ${r.title ? `<h2>${escapeHtml(r.title)}</h2><p class="rule-detail-text">${escapeHtml(r.text)}</p>` : `<p class="rule-detail-text" style="font-size:13px">${escapeHtml(r.text)}</p>`}
      ${detail.keywords.length ? `<div class="rule-detail-section"><h4>Keywords</h4><div class="rule-chip-row">${detail.keywords.map(k => `<span class="rule-chip">${escapeHtml(k.name)}</span>`).join("")}</div></div>` : ""}`;
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

async function syncRulesData() {
  const button = document.getElementById("syncRulesBtn");
  button.disabled = true;
  try {
    const result = await api("/api/rules/sync", { method: "POST" });
    toast(result.ok
      ? `Synced ${result.documentsUpdated} documents, ${result.rulesIndexed} rules`
      : `Sync failed: ${result.error}`, !result.ok);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    await loadSettings();
  }
}

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
  document.getElementById("openMassAdd").addEventListener("click", () => showModal("massAddModal"));
  document.getElementById("openPackImport").addEventListener("click", () => openPackImportModal().catch(err => toast(err.message, true)));
  document.getElementById("packImportList").addEventListener("click", event => {
    const row = event.target.closest("[data-pack-key]");
    if (row) previewPack(row).catch(err => toast(err.message, true));
  });
  document.getElementById("packPreviewHeader").addEventListener("click", event => {
    if (event.target.closest("#confirmImportPackBtn")) confirmImportPack().catch(err => toast(err.message, true));
    if (event.target.closest("#confirmRemovePackBtn")) confirmRemovePack().catch(err => toast(err.message, true));
  });
  document.getElementById("massAddPreview").addEventListener("click", previewMassAdd);
  document.getElementById("massAddConfirm").addEventListener("click", confirmMassAdd);
  document.getElementById("openConnection").addEventListener("click", openConnection);
  document.getElementById("updateIndicator").addEventListener("click", () => navigate("settings"));
  ["sidebarRefresh", "refreshCatalogBtn"].forEach(id => document.getElementById(id).addEventListener("click", refreshCatalog));
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
  document.getElementById("syncRulesBtn").addEventListener("click", syncRulesData);
  document.getElementById("rulesModeTabs").addEventListener("click", event => {
    const button = event.target.closest("[data-rules-mode]");
    if (button) setRulesPageMode(button.dataset.rulesMode);
  });
  document.getElementById("askRulesBtn").addEventListener("click", askRulesQuestion);
  document.getElementById("askRulesResult").addEventListener("click", event => {
    const button = event.target.closest("[data-rule-popup]");
    if (button) showRulePopup(Number(button.dataset.rulePopup));
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
    const id = Number(button.dataset.resultId);
    const kind = button.dataset.resultKind;
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
  document.getElementById("checkUpdateBtn").addEventListener("click", checkForUpdates);
  document.querySelectorAll("#themeControl button").forEach(button => button.addEventListener("click", () => setTheme(button.dataset.themeValue)));
  document.getElementById("openScan").addEventListener("click", () => { setScanMode("add"); resetScanner(); showModal("scanModal"); });
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
    document.getElementById("settingsVersion").textContent = server.version;
    document.querySelectorAll(".vault-tab").forEach(item => item.classList.toggle("active", item.dataset.owned === state.owned));
    navigate(state.page);
  } catch (err) {
    toast(`Vault startup failed: ${err.message}`, true);
  }
  checkUpdateIndicator();
  setInterval(checkUpdateIndicator, 5 * 60 * 1000);
}

init();
