const DOMAIN_COLOR = {
  Fury: "var(--c-fury)", Calm: "var(--c-calm)", Order: "var(--c-order)",
  Mind: "var(--c-mind)", Body: "var(--c-body)", Chaos: "var(--c-chaos)",
  Colorless: "var(--c-colorless)"
};
const RARITY_COLOR = {
  Common: "var(--faint)", Uncommon: "var(--blue)", Rare: "var(--green)",
  Epic: "var(--violet)", Legendary: "var(--gold-bright)", Champion: "var(--orange)"
};
const PAGE_LABELS = {
  vault: ["Collection", "Your Vault"], decks: ["Builder", "Decks"],
  favorites: ["Saved Cards", "Favorites"], binder: ["Collection", "Trade Binder"],
  "price-checker": ["Pricing", "Price Checker"],
  analytics: ["Collection Insights", "Analytics"], settings: ["Vault", "Settings"]
};

const state = {
  page: "vault", setId: null, owned: "all", search: "", rarity: "", type: "",
  domain: "", sort: "num-asc", view: "grid", selectedCardId: null,
  sets: [], overview: null, prices: {}, decks: [], activeDeckId: null,
  activeDeck: null, deckSearchTimer: null, contextCardId: null,
  contextMenuX: 0, contextMenuY: 0,
  priceQueue: { items: [], batchSize: 20, configured: false, provider: "JustTCG" },
  priceQueueIds: new Set()
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
  const title = `${price.provider || "Price"}: ${formatMoney(price.marketPrice)} | 24 hrs ${formatPriceChange(price.change24Hours)} | 7 days ${formatPriceChange(price.change7Days)}`;
  return `<span class="price-label" title="${escapeHtml(title)}"><b>${formatMoney(price.marketPrice)}</b><small class="${priceChangeClass(price.change24Hours)}">24h ${formatPriceChange(price.change24Hours)}</small><small class="${priceChangeClass(price.change7Days)}">7d ${formatPriceChange(price.change7Days)}</small></span>`;
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

function navigate(page) {
  if (!PAGE_LABELS[page]) return;
  state.page = page;
  document.querySelectorAll(".page").forEach(el => el.classList.toggle("active", el.id === `page-${page}`));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.page === page));
  document.getElementById("pageEyebrow").textContent = PAGE_LABELS[page][0];
  document.getElementById("pageTitle").textContent = PAGE_LABELS[page][1];
  document.getElementById("sidebar").classList.remove("open");
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
  const facetCards = await api(`/api/cards?${queryString({ setId: state.setId })}`);
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
        <div class="card-meta"><span><i class="rarity-gem" style="background:${RARITY_COLOR[card.rarity] || "var(--faint)"}"></i>${escapeHtml(card.rarity || card.type)}</span><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))}</span></div>
        <div class="card-actions">
          <div class="mini-stepper"><button data-owned-delta="-1" data-card-id="${escapeHtml(card.id)}" aria-label="Remove copy">-</button><span>${card.ownedCount}</span><button data-owned-delta="1" data-card-id="${escapeHtml(card.id)}" aria-label="Add copy">+</button></div>
          ${context === "binderGrid"
            ? `<button class="binder-chip" data-binder-delta="-1" data-card-id="${escapeHtml(card.id)}" title="Remove one copy from Trade Binder">Remove</button>`
            : card.ownedCount > 0
              ? `<label class="card-trade-toggle" title="Mark this card as available for trade"><span>Trade</span><input type="checkbox" data-card-trade-toggle="${escapeHtml(card.id)}"${card.binderCount > 0 ? " checked" : ""} /><i aria-hidden="true"></i></label>`
              : ""}
          ${compactPriceMarkup(price)}
        </div>
      </div>
    </article>`;
}

function renderCardGrid(root, cards) {
  root.classList.toggle("list-view", state.view === "list" && root.id === "vaultGrid");
  root.innerHTML = cards.map(card => cardTile(card, root.id)).join("");
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
    ${card.textPlain ? `<div class="inspector-rules">${escapeHtml(card.textPlain)}</div>` : ""}
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
    </div>
  `;
}

function wireInspector(root, card) {
  const currentCard = () => cardsById.get(card.id) || card;
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

function renderDeckWorkspace() {
  const root = document.getElementById("deckWorkspace");
  const detail = state.activeDeck;
  const summary = detail.summary;
  const groups = [...new Set(detail.cards.map(row => row.card.type || "Other"))];
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
        <div class="deck-actions"><button class="command-btn" id="testDrawBtn">${icon("shuffle")}Test Draw</button><button class="command-btn quiet" id="exportDeckBtn">${icon("download")}Export</button><button class="command-btn quiet" id="deleteDeckBtn">${icon("trash")}Delete</button></div>
      </div>
    </section>
    <div class="deck-builder">
      <div class="deck-card-list">
        ${groups.length ? groups.map(group => deckGroupMarkup(group, detail.cards.filter(row => (row.card.type || "Other") === group))).join("") : `<div class="page-empty"><h2>Deck is empty</h2></div>`}
      </div>
      <aside class="deck-search-panel"><h3>Add Cards</h3><input id="deckCardSearch" placeholder="Search by name or number" /><div class="segmented" id="deckSectionPicker"><button class="active" data-section="main">Main</button><button data-section="sideboard">Sideboard</button></div><div class="deck-search-results" id="deckSearchResults"></div></aside>
    </div>`;
  renderIcons(root);
  wireDeckWorkspace();
}

function deckGroupMarkup(group, rows) {
  const count = rows.reduce((sum, row) => sum + row.quantity, 0);
  return `<section class="deck-group"><div class="deck-group-head"><span>${escapeHtml(group)}</span><b>${count}</b></div>${rows.map(row => `
    <div class="deck-row">
      <div class="deck-row-art"><img src="${escapeHtml(cardImage(row.card))}" alt="" />${cardImagePopout(row.card)}</div>
      <div class="deck-row-copy"><strong>${escapeHtml(row.card.name)}</strong><span>${escapeHtml(row.card.setId)}-${escapeHtml(cardCode(row.card))} / ${escapeHtml(row.section)}</span></div>
      <span class="deck-owned${row.missing > 0 ? " missing" : ""}">${row.missing > 0 ? `${row.missing} missing` : `${row.owned} owned`}</span>
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
  root.querySelector("#exportDeckBtn")?.addEventListener("click", exportActiveDeck);
  root.querySelector("#testDrawBtn")?.addEventListener("click", openTestHand);
  root.querySelectorAll("[data-deck-qty]").forEach(button => button.addEventListener("click", () =>
    setDeckCard(state.activeDeckId, button.dataset.cardId, Number(button.dataset.deckQty), button.dataset.section)));
  let section = "main";
  root.querySelectorAll("#deckSectionPicker button").forEach(button => button.addEventListener("click", () => {
    section = button.dataset.section;
    root.querySelectorAll("#deckSectionPicker button").forEach(item => item.classList.toggle("active", item === button));
  }));
  root.querySelector("#deckCardSearch")?.addEventListener("input", event => {
    clearTimeout(state.deckSearchTimer);
    state.deckSearchTimer = setTimeout(() => searchDeckCards(event.target.value, section), 220);
  });
}

async function saveDeckMetadata() {
  const name = document.getElementById("activeDeckName").value.trim();
  const description = document.getElementById("activeDeckDescription").value.trim();
  await api(`/api/decks/${state.activeDeckId}`, jsonOptions("PUT", { name, description, format: state.activeDeck.summary.format }));
  toast("Deck saved");
  await loadDecks();
}

async function searchDeckCards(search, section) {
  const root = document.getElementById("deckSearchResults");
  if (!search.trim()) { root.innerHTML = ""; return; }
  const cards = await api(`/api/cards?${queryString({ search: search.trim(), sort: "name-asc" })}`);
  registerCards(cards);
  root.innerHTML = cards.slice(0, 30).map(card => `
    <div class="deck-search-row"><div class="deck-search-art"><img src="${escapeHtml(cardImage(card))}" alt="" />${cardImagePopout(card)}</div><div><strong>${escapeHtml(card.name)}</strong><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))} / own ${card.ownedCount}</span></div><button class="icon-btn" data-add-deck-card="${escapeHtml(card.id)}" data-section="${section}">${icon("plus")}</button></div>`).join("");
  renderIcons(root);
  root.querySelectorAll("[data-add-deck-card]").forEach(button => button.addEventListener("click", async () => {
    const existing = state.activeDeck.cards.find(row => row.cardId === button.dataset.addDeckCard && row.section === button.dataset.section);
    await setDeckCard(state.activeDeckId, button.dataset.addDeckCard, (existing?.quantity || 0) + 1, button.dataset.section);
  }));
}

async function setDeckCard(deckId, cardId, quantity, section) {
  state.activeDeck = await api(`/api/decks/${deckId}/cards`, jsonOptions("POST", { cardId, quantity, section }));
  await loadDecks();
}

async function deleteActiveDeck() {
  if (!confirm(`Delete "${state.activeDeck.summary.name}"?`)) return;
  await api(`/api/decks/${state.activeDeckId}`, { method: "DELETE" });
  state.activeDeckId = null;
  state.activeDeck = null;
  toast("Deck deleted");
  await Promise.all([loadDecks(), loadOverview()]);
}

async function exportActiveDeck() {
  const response = await fetch(`/api/decks/${state.activeDeckId}/export`);
  if (!response.ok) return toast("Deck export failed", true);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${state.activeDeck.summary.name.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "deck"}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

function openTestHand() {
  const pool = state.activeDeck.cards
    .filter(row => row.section === "main")
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
  const [sync, pricing, health, connection, server] = await Promise.all([
    api("/api/sync/status"), api("/api/pricing/status"), api("/api/health"),
    api("/api/connection-info"), api("/api/server-info")
  ]);
  document.getElementById("catalogStatus").textContent = sync.running
    ? `Syncing ${sync.currentSet || "catalog"}: ${sync.setsDone}/${sync.setsTotal} sets`
    : `${sync.totalCards} cards across ${sync.totalSets} sets. Last synced ${formatRelativeTime(sync.lastSyncedAt)}.`;
  document.getElementById("pricingStatus").textContent = pricing.configured
    ? `Riftbound.gg live pricing enabled. ${pricing.provider} snapshots configured (${pricing.source}, ${pricing.keyHint}).`
    : "Riftbound.gg live pricing enabled. JustTCG snapshots are optional.";
  const db = health.database;
  document.getElementById("databaseStatus").textContent = db
    ? `Database verified: ${db.integrity}. Protected collection totals are checked at startup.`
    : "Database is ready.";
  document.getElementById("databaseFacts").innerHTML = db ? `<span>${health.cards} cards now</span><span>${health.ownedCards} owned now</span><span>${health.ownedCopies} copies now</span>${db.lastBackupPath ? `<span>Last migration backup: ${escapeHtml(db.lastBackupPath.split(/[\\/]/).pop())}</span>` : ""}` : "";
  document.getElementById("connectionSettingsStatus").textContent = connection.available ? connection.url : "No LAN address detected.";
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

async function quickAdd() {
  const input = document.getElementById("quickAddInput");
  const parsed = parseCardEntry(input.value);
  const root = document.getElementById("quickAddResult");
  if (!parsed) { root.innerHTML = `<div class="result-row error">Enter a card code such as OGN-045 or VEN-R01.</div>`; return; }
  const cards = await api(`/api/cards/lookup?${queryString(parsed)}`);
  registerCards(cards);
  if (!cards.length) { root.innerHTML = `<div class="result-row error">No matching card found.</div>`; return; }
  root.innerHTML = cards.map(card => `<div class="result-row"><div class="result-card-art"><img src="${escapeHtml(cardImage(card))}" alt="" />${cardImagePopout(card)}</div><div><strong>${escapeHtml(card.name)}</strong><span>${escapeHtml(card.setId)}-${escapeHtml(cardCode(card))} / own ${card.ownedCount}</span></div><button class="command-btn gold" data-quick-add-card="${escapeHtml(card.id)}">Add</button></div>`).join("");
  renderIcons(root);
  root.querySelectorAll("[data-quick-add-card]").forEach(button => button.addEventListener("click", async () => {
    await changeOwned(cardsById.get(button.dataset.quickAddCard), 1);
    input.value = "";
    closeModal("quickAddModal");
  }));
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
  const root = document.getElementById("connectionBody");
  root.innerHTML = `<div class="loading-line">Loading...</div>`;
  showModal("connectionModal");
  try {
    const info = await api("/api/connection-info");
    if (!info.available) { root.textContent = "No LAN address detected."; return; }
    root.innerHTML = `<div class="connection-qr"><img src="/api/connection-qr.png?t=${Date.now()}" alt="Phone connection QR code" /></div><div class="connection-url"><input value="${escapeHtml(info.url)}" readonly /><button class="command-btn" id="copyConnection">Copy</button></div>`;
    document.getElementById("copyConnection").onclick = async () => { await navigator.clipboard.writeText(info.url); toast("Connection URL copied"); };
  } catch (err) { root.textContent = err.message; }
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
      status.innerHTML = `Version ${escapeHtml(result.latestVersion)} is available. <button class="command-btn gold" id="applyUpdate">Update and Restart</button>`;
      document.getElementById("applyUpdate").onclick = async () => {
        await api("/api/update/apply", { method: "POST" });
        status.textContent = "Installing update...";
      };
    }
  } catch (err) { status.textContent = err.message; }
  finally { button.disabled = false; }
}

async function createDeck() {
  const name = document.getElementById("deckNameInput").value.trim() || "New Deck";
  const format = document.getElementById("deckFormatInput").value;
  const description = document.getElementById("deckDescriptionInput").value.trim();
  const created = await api("/api/decks", jsonOptions("POST", { name, format, description }));
  state.activeDeckId = created.summary.id;
  closeModal("deckModal");
  await Promise.all([loadDecks(), loadOverview()]);
  toast("Deck created");
}

async function importDeck() {
  const name = document.getElementById("importDeckName").value.trim() || "Imported Deck";
  const contents = document.getElementById("importDeckContents").value;
  const result = await api("/api/decks/import", jsonOptions("POST", { name, format: "Standard", contents }));
  state.activeDeckId = result.deckId;
  document.getElementById("importDeckResult").textContent = result.unmatchedLines.length
    ? `${result.addedLines} lines added. ${result.unmatchedLines.length} lines did not match.`
    : `${result.addedLines} lines added.`;
  await Promise.all([loadDecks(), loadOverview()]);
  if (!result.unmatchedLines.length) closeModal("importDeckModal");
}

/* Scanner */
const scan = {
  stream: null, timer: null, inFlight: false, hitPending: false,
  voteKey: null, voteCount: 0, canvas: document.createElement("canvas")
};

function resetScanner() {
  stopLiveScan();
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
  root.innerHTML = result.matches.map(match => `<div class="result-row"><div class="result-card-art"><img src="${escapeHtml(cardImage(match.card))}" alt="" />${cardImagePopout(match.card)}</div><div><strong>${escapeHtml(match.card.name)}</strong><span>${escapeHtml(match.card.setId)}-${escapeHtml(cardCode(match.card))} / ${match.confidence}%</span></div><button class="command-btn gold" data-scan-add="${escapeHtml(match.card.id)}">Add</button></div>`).join("");
  renderIcons(root);
  root.querySelectorAll("[data-scan-add]").forEach(button => button.addEventListener("click", async () => {
    await changeOwned(cardsById.get(button.dataset.scanAdd), 1);
    root.innerHTML = "";
    status.textContent = "Card added";
  }));
}

async function manualLookup() {
  const setId = document.getElementById("manualSetCode").value.trim().toUpperCase();
  const code = document.getElementById("manualNumber").value.trim().toUpperCase();
  if (!code) return;
  const cards = await api(`/api/cards/lookup?${queryString({ setId, code })}`);
  renderScanResult({ method: cards.length === 1 ? "manual" : "ocr-ambiguous", matches: cards.map(card => ({ card, confidence: 100 })), debugOcrText: "" });
}

async function startLiveScan() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) return toast("Live camera requires the HTTPS phone connection", true);
  try { scan.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); }
  catch (err) { return toast(err.message, true); }
  const video = document.getElementById("liveVideo");
  video.srcObject = scan.stream;
  document.getElementById("liveScanBtn").hidden = true;
  document.getElementById("liveScanView").hidden = false;
  scan.voteKey = null; scan.voteCount = 0; scan.hitPending = false;
  scan.timer = setInterval(captureLiveFrame, 850);
}

function stopLiveScan() {
  if (scan.timer) clearInterval(scan.timer);
  scan.timer = null;
  if (scan.stream) scan.stream.getTracks().forEach(track => track.stop());
  scan.stream = null;
  const video = document.getElementById("liveVideo");
  if (video) video.srcObject = null;
  document.getElementById("liveScanView").hidden = true;
  document.getElementById("liveScanBtn").hidden = false;
}

async function captureLiveFrame() {
  const video = document.getElementById("liveVideo");
  if (scan.inFlight || scan.hitPending || video.readyState < 2) return;
  scan.inFlight = true;
  const scale = Math.min(1, 900 / Math.max(video.videoWidth, video.videoHeight));
  scan.canvas.width = Math.round(video.videoWidth * scale);
  scan.canvas.height = Math.round(video.videoHeight * scale);
  scan.canvas.getContext("2d").drawImage(video, 0, 0, scan.canvas.width, scan.canvas.height);
  scan.canvas.toBlob(async blob => {
    if (!blob) { scan.inFlight = false; return; }
    const form = new FormData(); form.append("photo", blob, "frame.jpg"); form.append("fast", "true");
    if (state.setId) form.append("setId", state.setId);
    try {
      const result = await api("/api/scan", { method: "POST", body: form });
      document.getElementById("liveReadoutText").textContent = (result.debugOcrText || "Nothing legible yet").replace(/\s+/g, " ").slice(0, 70);
      const candidate = result.method === "ocr" && result.matches.length === 1 ? result.matches[0] : null;
      const key = candidate?.card.id || null;
      if (key && key === scan.voteKey) scan.voteCount++; else { scan.voteKey = key; scan.voteCount = key ? 1 : 0; }
      if (candidate && scan.voteCount >= 3) showLiveHit(candidate);
    } catch { }
    finally { scan.inFlight = false; }
  }, "image/jpeg", .84);
}

function showLiveHit(match) {
  scan.hitPending = true;
  registerCards([match.card]);
  const root = document.getElementById("liveHit");
  root.innerHTML = `<div class="result-row"><div class="result-card-art"><img src="${escapeHtml(cardImage(match.card))}" alt="" />${cardImagePopout(match.card)}</div><div><strong>${escapeHtml(match.card.name)}</strong><span>${escapeHtml(match.card.setId)}-${escapeHtml(cardCode(match.card))}</span></div><button class="command-btn gold" id="liveAdd">Add</button></div>`;
  renderIcons(root);
  document.getElementById("liveStatus").textContent = "Card matched";
  document.getElementById("liveAdd").onclick = async () => {
    await changeOwned(match.card, 1);
    root.innerHTML = "";
    scan.hitPending = false; scan.voteKey = null; scan.voteCount = 0;
    document.getElementById("liveStatus").textContent = "Point the camera at a card";
  };
  setTimeout(() => { if (scan.hitPending) { root.innerHTML = ""; scan.hitPending = false; scan.voteKey = null; scan.voteCount = 0; } }, 4500);
}

function wireEvents() {
  document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click", () => navigate(button.dataset.page)));
  document.getElementById("mobileMenu").addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
  document.getElementById("setNav").addEventListener("click", event => {
    const button = event.target.closest("[data-set-id]"); if (!button) return;
    state.setId = button.dataset.setId || null; renderSetNavigation(); navigate("vault");
  });
  document.querySelectorAll(".vault-tab").forEach(button => button.addEventListener("click", () => {
    state.owned = button.dataset.owned;
    document.querySelectorAll(".vault-tab").forEach(item => item.classList.toggle("active", item === button));
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
    document.getElementById("vaultGrid").classList.toggle("list-view", state.view === "list");
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
    const priceQueueRemove = event.target.closest("[data-price-queue-remove]");
    if (priceQueueRemove) { event.preventDefault(); event.stopPropagation(); const card = cardsById.get(priceQueueRemove.dataset.priceQueueRemove); if (card) setPriceQueue(card, false).catch(err => toast(err.message, true)); return; }
    const card = event.target.closest("[data-card-open]");
    if (card) { openCard(card.dataset.cardOpen); return; }
    const deck = event.target.closest("[data-deck-id]");
    if (deck) { state.activeDeckId = Number(deck.dataset.deckId); loadDecks(); return; }
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
  document.getElementById("openQuickAdd").addEventListener("click", () => { document.getElementById("quickAddResult").innerHTML = ""; showModal("quickAddModal"); setTimeout(() => document.getElementById("quickAddInput").focus(), 0); });
  document.getElementById("quickAddBtn").addEventListener("click", quickAdd);
  document.getElementById("quickAddInput").addEventListener("keydown", event => { if (event.key === "Enter") quickAdd(); });
  document.getElementById("openMassAdd").addEventListener("click", () => showModal("massAddModal"));
  document.getElementById("massAddPreview").addEventListener("click", previewMassAdd);
  document.getElementById("massAddConfirm").addEventListener("click", confirmMassAdd);
  ["openConnection", "settingsConnection"].forEach(id => document.getElementById(id).addEventListener("click", openConnection));
  ["sidebarRefresh", "refreshCatalogBtn"].forEach(id => document.getElementById(id).addEventListener("click", refreshCatalog));
  ["newDeckBtn", "emptyNewDeck"].forEach(id => document.getElementById(id).addEventListener("click", openNewDeckModal));
  document.getElementById("saveDeckBtn").addEventListener("click", createDeck);
  document.getElementById("importDeckBtn").addEventListener("click", () => showModal("importDeckModal"));
  document.getElementById("confirmImportDeck").addEventListener("click", importDeck);
  document.getElementById("savePricingKey").addEventListener("click", savePricingKey);
  document.getElementById("clearPricingKey").addEventListener("click", clearPricingKey);
  document.getElementById("refreshTrackedPrices").addEventListener("click", () => refreshPrices(false));
  document.getElementById("refreshAllPrices").addEventListener("click", () => refreshPrices(true));
  document.getElementById("clearPriceQueue").addEventListener("click", () => clearPriceQueue().catch(err => toast(err.message, true)));
  document.getElementById("checkPriceQueue").addEventListener("click", checkPriceQueue);
  document.getElementById("priceQueueSettings").addEventListener("click", () => navigate("settings"));
  document.getElementById("checkUpdateBtn").addEventListener("click", checkForUpdates);
  document.querySelectorAll("#themeControl button").forEach(button => button.addEventListener("click", () => setTheme(button.dataset.themeValue)));
  document.getElementById("openScan").addEventListener("click", () => { resetScanner(); showModal("scanModal"); });
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
}

function openNewDeckModal() {
  document.getElementById("deckNameInput").value = "";
  document.getElementById("deckDescriptionInput").value = "";
  document.getElementById("deckFormatInput").value = "Standard";
  showModal("deckModal");
  setTimeout(() => document.getElementById("deckNameInput").focus(), 0);
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
  try {
    const [server] = await Promise.all([api("/api/server-info"), loadSets(), loadPrices(), loadPriceQueue(), loadOverview(), loadDecks()]);
    document.getElementById("currentVersion").textContent = server.version;
    document.getElementById("settingsVersion").textContent = server.version;
    await loadVault();
  } catch (err) {
    toast(`Vault startup failed: ${err.message}`, true);
  }
}

init();
