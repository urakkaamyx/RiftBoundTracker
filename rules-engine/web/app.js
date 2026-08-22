"use strict";

const state = {
  view: "ask",
  search: { query: "", kind: "", offset: 0, limit: 20, hasMore: false, results: [] },
  status: null,
  sources: null,
  recentQuestions: []
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function node(tag, options = {}) {
  const el = document.createElement(tag);
  if (options.className) el.className = options.className;
  if (options.text !== undefined && options.text !== null) el.textContent = String(options.text);
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([key, value]) => {
      if (value !== undefined && value !== null) el.setAttribute(key, String(value));
    });
  }
  return el;
}

function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function appendTextSection(parent, label, value) {
  if (value === undefined || value === null || value === "") return;
  const section = node("section", { className: "detail-section" });
  section.append(node("div", { className: "detail-label", text: label }));
  section.append(node("div", { className: "detail-text", text: value }));
  parent.append(section);
}

function announce(message) {
  $("#global-status").textContent = message || "";
}

function setPanelState(id, message, isError = false) {
  const el = $(id);
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("is-error");
    return;
  }
  el.hidden = false;
  el.textContent = message;
  el.classList.toggle("is-error", Boolean(isError));
}

async function api(path, options = {}) {
  const request = {
    method: options.method || "GET",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    credentials: "same-origin"
  };
  if (options.body !== undefined) {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(path, request);
  } catch (_err) {
    throw new Error("RiftKeep could not reach the local rules service.");
  }
  let payload;
  try {
    payload = await response.json();
  } catch (_err) {
    throw new Error(`The rules service returned an unreadable response (${response.status}).`);
  }
  if (!response.ok || payload.ok === false) {
    const message = payload && payload.error && payload.error.message ? payload.error.message : `Request failed (${response.status}).`;
    const err = new Error(message);
    err.status = response.status;
    err.code = payload && payload.error ? payload.error.code : "request_failed";
    err.details = payload && payload.error ? payload.error.details : {};
    throw err;
  }
  return payload;
}

function setView(view, focusMain = true) {
  state.view = view;
  $$("[data-view-panel]").forEach((panel) => {
    const active = panel.dataset.viewPanel === view;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  $$("[data-view]").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (focusMain) $("#main-content").focus({ preventScroll: true });
  if (view === "sources" && !state.sources) loadSources();
}

function verdictClass(value) {
  const text = String(value || "").toLowerCase();
  if (text === "yes" || text === "true" || text === "allowed") return "is-yes";
  if (text === "no" || text === "false" || text.includes("cannot")) return "is-no";
  if (text === "conditional" || text === "insufficient" || text === "unknown") return "is-conditional";
  return "";
}

function clarificationText(item) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") return item.question || item.text || item.fact || "Additional game-state information is required.";
  return String(item || "");
}

async function openEvidence(evidenceId) {
  const dialog = $("#evidence-dialog");
  const body = $("#evidence-body");
  clear(body);
  body.append(node("p", { className: "detail-text", text: `Loading ${evidenceId}…` }));
  if (!dialog.open) dialog.showModal();
  try {
    const payload = await api(`/v1/evidence/${encodeURIComponent(evidenceId)}`);
    const ev = payload.evidence || {};
    clear(body);
    appendTextSection(body, "Evidence ID", ev.evidenceId || evidenceId);
    appendTextSection(body, "Type", ev.kind);
    appendTextSection(body, "Rule", ev.ruleId);
    appendTextSection(body, "Card", ev.name || ev.cardName);
    appendTextSection(body, "Question", ev.question);
    appendTextSection(body, "Heading", ev.heading);
    appendTextSection(body, "Authoritative text", ev.text || ev.effectiveText || ev.newText);
    appendTextSection(body, "Example", ev.exampleText);
    appendTextSection(body, "Previous text", ev.oldText);
    appendTextSection(body, "Source", ev.sourceId);
    appendTextSection(body, "Effective", ev.effectiveFrom || ev.published);
    if (Array.isArray(ev.domains) && ev.domains.length) appendTextSection(body, "Domains", ev.domains.join(", "));
  } catch (err) {
    clear(body);
    body.append(node("p", { className: "detail-text", text: err.message }));
  }
}

function citationButton(evidenceId) {
  const button = node("button", { className: "citation-button", text: evidenceId, attrs: { type: "button" } });
  button.addEventListener("click", () => openEvidence(evidenceId));
  return button;
}

function renderIssue(issue) {
  const card = node("article", { className: "issue-card" });
  const top = node("div", { className: "issue-top" });
  const title = node("div");
  title.append(node("h3", { text: issue.question || `Issue ${(issue.index ?? 0) + 1}` }));
  if (issue.interpretedQuestion && issue.interpretedQuestion !== issue.question) {
    title.append(node("p", { className: "issue-conclusion", text: `Interpreted as: ${issue.interpretedQuestion}` }));
  }
  const verdict = node("span", { className: `verdict-badge ${verdictClass(issue.verdict || issue.status)}`, text: issue.verdict || issue.status || "Pending" });
  top.append(title, verdict);
  card.append(top);
  if (issue.conclusion) card.append(node("p", { className: "issue-conclusion", text: issue.conclusion }));

  const clarifications = Array.isArray(issue.clarifyingQuestions) ? issue.clarifyingQuestions : [];
  if (clarifications.length) {
    const box = node("div", { className: "clarification-box" });
    box.append(node("strong", { text: "RiftKeep needs one more fact" }));
    const list = node("ul", { className: "clarification-list" });
    clarifications.forEach((item) => list.append(node("li", { text: clarificationText(item) })));
    box.append(list);
    card.append(box);
  }

  const citations = Array.isArray(issue.citations) ? issue.citations : [];
  if (citations.length) {
    const row = node("div", { className: "citation-row", attrs: { "aria-label": "Supporting evidence" } });
    citations.forEach((id) => row.append(citationButton(id)));
    card.append(row);
  }
  const proof = issue.proof || {};
  const meta = node("p", { className: "result-snippet", text: proof.verified ? "Proof verified by the deterministic backend." : "Proof is not verified; RiftKeep will not treat this as a final proven ruling." });
  card.append(meta);
  return card;
}

function rememberQuestion(question) {
  const cleanQuestion = String(question || "").trim();
  if (!cleanQuestion) return;
  state.recentQuestions = [cleanQuestion, ...state.recentQuestions.filter((q) => q !== cleanQuestion)].slice(0, 5);
  try { localStorage.setItem("riftkeep.recentQuestions", JSON.stringify(state.recentQuestions)); } catch (_err) { /* convenience only */ }
  renderRecent();
}

function renderRecent() {
  const wrap = $("#recent-wrap");
  const list = $("#recent-list");
  clear(list);
  if (!state.recentQuestions.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  state.recentQuestions.forEach((question) => {
    const button = node("button", { className: "recent-chip", text: question, attrs: { type: "button", title: question } });
    button.addEventListener("click", () => {
      $("#ask-question").value = question;
      $("#ask-question").focus();
    });
    list.append(button);
  });
}

async function submitAsk(question) {
  const input = $("#ask-question");
  const submit = $("#ask-submit");
  const panel = $("#answer-panel");
  const issueList = $("#issue-list");
  submit.disabled = true;
  input.setAttribute("aria-busy", "true");
  panel.hidden = true;
  setPanelState("#ask-state", "Checking current authority, card text, and proof dependencies…");
  try {
    const payload = await api("/v1/ask", { method: "POST", body: { question } });
    rememberQuestion(question);
    clear(issueList);
    $("#answer-text").textContent = payload.answer || payload.deterministicAnswer || "RiftKeep returned no player-facing answer.";
    const issues = Array.isArray(payload.issues) ? payload.issues : [];
    issues.forEach((issue) => issueList.append(renderIssue(issue)));
    const verified = issues.length > 0 && issues.every((issue) => issue.proof && issue.proof.verified);
    const proofBadge = $("#answer-proof");
    proofBadge.textContent = verified ? "Proof verified" : "Needs context / proof";
    proofBadge.classList.toggle("is-good", verified);
    panel.hidden = false;
    setPanelState("#ask-state", "");
    announce(verified ? "Ruling loaded and proof verified." : "Ruling loaded; additional context or proof may be required.");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setPanelState("#ask-state", err.message, true);
    announce(`Ask Rules failed: ${err.message}`);
  } finally {
    submit.disabled = false;
    input.removeAttribute("aria-busy");
  }
}

function resultText(item) {
  return item.text || item.effectiveText || item.question || item.heading || "";
}

function resultTitle(item) {
  if (item.kind === "rule") return item.ruleId ? `Rule ${item.ruleId}` : (item.title || "Rule");
  if (item.kind === "card") return item.name || item.title || item.cardId || "Card";
  return item.title || item.heading || item.question || item.evidenceId || item.id || "Result";
}

function renderSearchResults(payload) {
  const list = $("#search-results");
  clear(list);
  const results = Array.isArray(payload.results) ? payload.results : [];
  state.search.results = results;
  state.search.hasMore = Boolean(payload.hasMore);
  $("#search-summary").textContent = `${payload.returned || results.length} result${results.length === 1 ? "" : "s"} · offset ${payload.offset || 0}`;
  if (!results.length) {
    list.append(node("div", { className: "state-panel", text: "No indexed rules, cards, or current rulings matched that query." }));
  }
  results.forEach((item, index) => {
    const button = node("button", { className: "result-item", attrs: { type: "button", "data-result-index": index } });
    const meta = node("div", { className: "result-meta" });
    meta.append(node("span", { className: "kind-badge", text: item.kind || "result" }));
    if (item.sourceId) meta.append(node("span", { className: "result-snippet", text: item.sourceId }));
    button.append(meta, node("div", { className: "result-title", text: resultTitle(item) }));
    const snippet = resultText(item);
    if (snippet) button.append(node("div", { className: "result-snippet", text: snippet }));
    button.addEventListener("click", () => selectSearchResult(item, button));
    list.append(button);
  });
  const pager = $("#search-pager");
  pager.hidden = !results.length || (state.search.offset === 0 && !state.search.hasMore);
  $("#search-prev").disabled = state.search.offset === 0;
  $("#search-next").disabled = !state.search.hasMore;
  $("#search-page-label").textContent = `Results ${state.search.offset + 1}–${state.search.offset + results.length}`;
}

async function selectSearchResult(item, button) {
  $$(".result-item").forEach((x) => x.classList.remove("is-selected"));
  button.classList.add("is-selected");
  const panel = $("#detail-panel");
  clear(panel);
  panel.append(node("p", { className: "detail-text", text: "Loading authoritative detail…" }));
  try {
    let payload;
    if (item.kind === "card" && (item.cardId || item.name)) {
      payload = await api(`/v1/cards/${encodeURIComponent(item.cardId || item.name)}`);
      renderCardDetail(panel, payload);
    } else if (item.kind === "rule" && item.ruleId) {
      const family = String(item.id || "").startsWith("tournament:") || String(item.sourceId || "").includes("tournament") ? "tournament" : "core";
      payload = await api(`/v1/rules/${family}/${encodeURIComponent(item.ruleId)}`);
      renderRuleDetail(panel, payload);
    } else if (item.evidenceId) {
      payload = await api(`/v1/evidence/${encodeURIComponent(item.evidenceId)}`);
      renderEvidenceDetail(panel, payload.evidence || {});
    } else {
      clear(panel);
      appendTextSection(panel, item.kind || "Result", resultTitle(item));
      appendTextSection(panel, "Text", resultText(item));
      appendTextSection(panel, "Source", item.sourceId);
    }
    panel.focus({ preventScroll: true });
  } catch (err) {
    clear(panel);
    panel.append(node("p", { className: "detail-text", text: err.message }));
  }
}

function addMetaGrid(parent, entries) {
  const filtered = entries.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!filtered.length) return;
  const grid = node("div", { className: "meta-grid" });
  filtered.forEach(([label, value]) => {
    const cell = node("div", { className: "meta-cell" });
    cell.append(node("span", { text: label }), node("strong", { text: Array.isArray(value) ? value.join(", ") : value }));
    grid.append(cell);
  });
  parent.append(grid);
}

function renderCardDetail(panel, payload) {
  clear(panel);
  const card = (payload.matches || [])[0];
  if (!card) {
    panel.append(node("p", { text: "No exact card detail was returned." }));
    return;
  }
  appendTextSection(panel, "Card", card.name);
  addMetaGrid(panel, [["Printing", card.id], ["Set", card.setLabel || card.setId], ["Collector", card.collectorCode], ["Type", [card.supertype, card.type].filter(Boolean).join(" ")], ["Domains", card.domains], ["Rarity", card.rarity]]);
  appendTextSection(panel, "Effective text", card.effectiveText || "(No rules text)");
  appendTextSection(panel, "Text authority", card.textSource);
  const citation = card.citationId;
  if (citation) {
    const row = node("div", { className: "citation-row" });
    row.append(citationButton(citation));
    panel.append(row);
  }
  const variants = payload.gameplayVariants || [];
  if (variants.length > 1) appendTextSection(panel, "Gameplay printings", variants.map((x) => `${x.id} · ${x.setLabel || x.setId}`).join("\n"));
  const timeline = card.officialErrataTimeline || [];
  if (timeline.length) appendTextSection(panel, "Official errata timeline", timeline.map((x) => `${x.published || x.release || "Update"}: ${x.newText || x.text || x.entryId || "Errata"}`).join("\n\n"));
}

function renderRuleDetail(panel, payload) {
  clear(panel);
  const rule = payload.rule || {};
  appendTextSection(panel, `${payload.family === "tournament" ? "Tournament" : "Core"} Rule`, rule.ruleId);
  appendTextSection(panel, "Rule text", rule.text);
  appendTextSection(panel, "Example", rule.exampleText);
  addMetaGrid(panel, [["Source", rule.sourceId], ["Page", rule.pageStart === rule.pageEnd || !rule.pageEnd ? rule.pageStart : `${rule.pageStart}–${rule.pageEnd}`], ["Section", rule.majorSectionTitle]]);
  if (payload.citationId) {
    const row = node("div", { className: "citation-row" });
    row.append(citationButton(payload.citationId));
    panel.append(row);
  }
  const nav = rule.navigation || {};
  const related = [nav.parentRuleId, ...(nav.childRuleIds || []), ...(nav.resolvedCrossReferences || [])].filter(Boolean);
  if (related.length) appendTextSection(panel, "Related rules", Array.from(new Set(related)).join(", "));
}

function renderEvidenceDetail(panel, ev) {
  clear(panel);
  appendTextSection(panel, "Evidence", ev.evidenceId);
  appendTextSection(panel, "Type", ev.kind);
  appendTextSection(panel, "Question", ev.question);
  appendTextSection(panel, "Heading", ev.heading);
  appendTextSection(panel, "Text", ev.text || ev.effectiveText || ev.newText);
  appendTextSection(panel, "Source", ev.sourceId);
}

async function runSearch(resetOffset = true) {
  const query = $("#search-query").value.trim();
  const kind = $("#search-kind").value;
  if (!query) return;
  if (resetOffset) state.search.offset = 0;
  state.search.query = query;
  state.search.kind = kind;
  setPanelState("#search-state", "Searching the canonical index…");
  const params = new URLSearchParams({ q: query, limit: String(state.search.limit), offset: String(state.search.offset) });
  if (kind) params.set("kind", kind);
  try {
    const payload = await api(`/v1/search?${params.toString()}`);
    renderSearchResults(payload);
    setPanelState("#search-state", "");
    announce(`Search returned ${payload.returned || 0} results.`);
  } catch (err) {
    setPanelState("#search-state", err.message, true);
  }
}

function valueText(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(", ");
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${valueText(v)}`).join(" · ");
  return String(value);
}

function renderSources(payload) {
  state.sources = payload;
  const auth = $("#authority-details");
  const histories = $("#version-history");
  clear(auth); clear(histories);
  const authority = payload.authority || {};
  const summary = node("div", { className: "authority-summary" });
  [["Current gameplay authority", authority.currentRulesComplete ? "Complete" : "Incomplete"], ["Active overlays", valueText(authority.activeOverlays || [])], ["Missing", valueText(authority.missing || [])]].forEach(([label, value]) => {
    const row = node("div", { className: "authority-row" });
    row.append(node("strong", { text: label }), node("span", { text: value || "None" }));
    summary.append(row);
  });
  auth.append(summary);

  const versionData = payload.ruleVersionHistories || {};
  ["core", "tournament"].forEach((family) => {
    const info = versionData[family] || {};
    const group = node("div", { className: "history-group" });
    group.append(node("h3", { text: family === "core" ? "Core Rules" : "Tournament Rules" }));
    (info.versions || []).forEach((version) => {
      const row = node("div", { className: "history-row" });
      row.append(node("strong", { text: version.sourceId || "Unknown version" }));
      row.append(node("span", { text: `${version.status || "unknown"} · ${version.ruleCount || "?"} numbered entries${version.effectiveFrom ? ` · effective ${version.effectiveFrom}` : ""}` }));
      group.append(row);
    });
    histories.append(group);
  });
}

async function loadSources(force = false) {
  if (state.sources && !force) {
    renderSources(state.sources);
    return;
  }
  setPanelState("#sources-state", "Loading current authority and immutable source history…");
  try {
    const payload = await api("/v1/sources");
    renderSources(payload);
    setPanelState("#sources-state", "");
  } catch (err) {
    setPanelState("#sources-state", err.message, true);
  }
}

async function loadChanges() {
  const target = $("#changes-results");
  const family = $("#changes-family").value;
  clear(target);
  target.append(node("p", { className: "detail-text", text: "Loading version comparison…" }));
  try {
    const payload = await api(`/v1/changes?family=${encodeURIComponent(family)}`);
    clear(target);
    addMetaGrid(target, [["Current source", payload.sourceId], ["Previous source", payload.previousSourceId || "None archived"], ["Detailed diff", payload.detailedChangesAvailable ? "Available" : "Not archived for this version"]]);
    const counts = payload.changeCounts || {};
    const keys = Object.keys(counts);
    if (keys.length) {
      const rows = node("div", { className: "authority-summary" });
      keys.sort().forEach((key) => {
        const row = node("div", { className: "change-row", text: `${key}: ${counts[key]}` });
        rows.append(row);
      });
      target.append(rows);
    } else {
      target.append(node("p", { className: "detail-text", text: payload.hasPreviousVersion ? "This version ledger has no summarized change counts." : "No previous certified version is archived for comparison." }));
    }
    if (payload.note) target.append(node("p", { className: "result-snippet", text: payload.note }));
  } catch (err) {
    clear(target);
    target.append(node("p", { className: "detail-text", text: err.message }));
  }
}

async function loadStatus() {
  const pill = $("#authority-pill");
  try {
    const payload = await api("/v1/status");
    state.status = payload;
    const complete = Boolean(payload.authority && payload.authority.currentRulesComplete);
    pill.classList.toggle("is-good", complete);
    pill.classList.toggle("is-bad", !complete);
    $("#authority-label").textContent = complete ? "Current authority complete" : "Authority incomplete — Ask disabled";
    const release = payload.release || {};
    const releaseIdentity = release.productVersion ? `RiftKeep ${release.productVersion}` : (release.milestone || "RiftKeep Rules");
    $("#release-label").textContent = `${releaseIdentity} · ${release.releaseStatus || "development"}`;
    $("#ask-submit").disabled = !complete;
  } catch (err) {
    pill.classList.add("is-bad");
    $("#authority-label").textContent = "Rules service unavailable";
    $("#ask-submit").disabled = true;
  }
}

function bindEvents() {
  $$("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $("#ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const question = $("#ask-question").value.trim();
    if (question) submitAsk(question);
  });
  $("#ask-question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      $("#ask-form").requestSubmit();
    }
  });
  $("#search-form").addEventListener("submit", (event) => { event.preventDefault(); runSearch(true); });
  $("#search-prev").addEventListener("click", () => { state.search.offset = Math.max(0, state.search.offset - state.search.limit); runSearch(false); });
  $("#search-next").addEventListener("click", () => { state.search.offset += state.search.limit; runSearch(false); });
  $("#refresh-sources").addEventListener("click", () => loadSources(true));
  $("#load-changes").addEventListener("click", loadChanges);
  $("#evidence-close").addEventListener("click", () => $("#evidence-dialog").close());
  $("#evidence-dialog").addEventListener("click", (event) => {
    if (event.target === $("#evidence-dialog")) $("#evidence-dialog").close();
  });
}

function loadRecent() {
  try {
    const parsed = JSON.parse(localStorage.getItem("riftkeep.recentQuestions") || "[]");
    if (Array.isArray(parsed)) state.recentQuestions = parsed.filter((x) => typeof x === "string").slice(0, 5);
  } catch (_err) {
    state.recentQuestions = [];
  }
  renderRecent();
}

async function boot() {
  bindEvents();
  loadRecent();
  await loadStatus();
  announce("RiftKeep Rules interface ready.");
}

document.addEventListener("DOMContentLoaded", boot);
