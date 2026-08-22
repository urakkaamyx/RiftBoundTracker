from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import tempfile
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import urlparse


WS_RE = re.compile(r"\s+")

def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


ALLOWED_OFFICIAL_HOSTS = {"playriftbound.com", "www.playriftbound.com", "riftbound.leagueoflegends.com", "www.riftbound.leagueoflegends.com"}
MAX_SOURCE_BYTES = 12 * 1024 * 1024


def validate_official_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError("Official source URLs must use HTTPS")
    if host not in ALLOWED_OFFICIAL_HOSTS:
        raise ValueError(f"Unapproved official source host: {host}")


def validate_snapshot_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on incomplete/incorrectly parsed source bodies.

    Generic type checks are supplemented by an optional manifest-driven validation
    profile. This lets a current authority overlay require known anchors before it
    is allowed to satisfy source-completeness.
    """
    stype = str(snapshot.get("sourceType") or "")
    blocks = list(snapshot.get("blocks") or [])
    sections = list(snapshot.get("sections") or [])
    texts = [_norm(str(b.get("text") or "")) for b in blocks]
    full_text = "\n".join(texts)
    errors: list[str] = []
    warnings: list[str] = []
    if not blocks:
        errors.append("no_semantic_blocks")
    if not sections:
        errors.append("no_searchable_sections")
    if stype == "official_faq":
        if not any(QUESTION_RE.match(t) for t in texts):
            errors.append("faq_contains_no_question_sections")
    elif stype == "patch_notes":
        title = str(snapshot.get("title") or "").lower()
        if "patch" not in title:
            warnings.append("patch_notes_title_does_not_contain_patch")
    elif stype == "card_errata":
        lows = {t.casefold() for t in texts}
        if not any("new text" in t for t in lows):
            errors.append("errata_contains_no_new_text_marker")
        if not any("old text" in t for t in lows):
            errors.append("errata_contains_no_old_text_marker")
    elif stype == "rules_hub":
        if not any(t.casefold() == "constructed format legality" for t in texts):
            errors.append("rules_hub_missing_constructed_legality_heading")

    profile = snapshot.get("validationProfile") or {}
    min_sections = int(profile.get("minSectionCount") or 0)
    if min_sections and len(sections) < min_sections:
        errors.append(f"section_count_below_profile_minimum:{len(sections)}<{min_sections}")
    low_full = full_text.casefold()
    for frag in profile.get("requiredTextFragments") or []:
        if _norm(str(frag)).casefold() not in low_full:
            errors.append(f"missing_required_text_fragment:{frag}")
    questions = "\n".join(_norm(str(sec.get("question") or "")) for sec in sections).casefold()
    for frag in profile.get("requiredQuestionFragments") or []:
        if _norm(str(frag)).casefold() not in questions:
            errors.append(f"missing_required_question_fragment:{frag}")
    return {"passed": not errors, "errors": errors, "warnings": warnings}

QUESTION_RE = re.compile(r"^(?:q(?:uestion)?\s*[:.-]?\s*)?(.+\?)$", re.I)
RULE_REF_RE = re.compile(r"\b(?:CR\s*)?(\d{3}(?:\.\d+)*(?:\.[a-z])?)\b", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm(text: str) -> str:
    return WS_RE.sub(" ", html_lib.unescape(text or "")).strip()


@dataclass
class TextBlock:
    kind: str
    text: str
    level: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "text": self.text}
        if self.level is not None:
            d["level"] = self.level
        return d


class _ArticleHTMLParser(HTMLParser):
    """Small, dependency-free semantic text extractor.

    This is intentionally conservative: it preserves headings, paragraphs, and list
    items and ignores scripts/styles. It does not attempt site-specific DOM scraping.
    """

    BLOCK_TAGS = {"p", "li", "blockquote"}
    HEADING_TAGS = {f"h{i}" for i in range(1, 7)}
    IGNORE_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[TextBlock] = []
        self._ignore_depth = 0
        self._active_tag: str | None = None
        self._active_level: int | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag in self.HEADING_TAGS or tag in self.BLOCK_TAGS:
            self._flush()
            self._active_tag = tag
            self._active_level = int(tag[1]) if tag in self.HEADING_TAGS else None
            self._parts = []
        elif tag == "br" and self._active_tag:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == self._active_tag:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._ignore_depth or not self._active_tag:
            return
        self._parts.append(data)

    def _flush(self) -> None:
        if not self._active_tag:
            return
        text = _norm("".join(self._parts))
        if text:
            if self._active_tag in self.HEADING_TAGS:
                self.blocks.append(TextBlock("heading", text, self._active_level))
            elif self._active_tag == "li":
                self.blocks.append(TextBlock("list_item", text))
            elif self._active_tag == "blockquote":
                self.blocks.append(TextBlock("blockquote", text))
            else:
                self.blocks.append(TextBlock("paragraph", text))
        self._active_tag = None
        self._active_level = None
        self._parts = []

    def close(self) -> None:
        self._flush()
        super().close()


def extract_blocks(raw: bytes, media_type: str, encoding: str = "utf-8") -> list[dict[str, Any]]:
    text = raw.decode(encoding, errors="replace")
    if media_type in {"text/html", "application/xhtml+xml"} or "<html" in text[:2000].lower():
        p = _ArticleHTMLParser()
        p.feed(text)
        p.close()
        return [x.to_dict() for x in p.blocks]

    # Plain text / markdown snapshots: retain heading-ish lines and paragraph chunks.
    lines = text.splitlines()
    blocks: list[TextBlock] = []
    buf: list[str] = []

    def flush_buf() -> None:
        nonlocal buf
        t = _norm(" ".join(buf))
        if t:
            blocks.append(TextBlock("paragraph", t))
        buf = []

    for line in lines:
        s = line.strip()
        if not s:
            flush_buf()
            continue
        if s.startswith("#"):
            flush_buf()
            m = re.match(r"^(#{1,6})\s*(.*)$", s)
            if m and m.group(2).strip():
                blocks.append(TextBlock("heading", _norm(m.group(2)), len(m.group(1))))
            continue
        if re.match(r"^[-*+]\s+", s):
            flush_buf()
            blocks.append(TextBlock("list_item", _norm(re.sub(r"^[-*+]\s+", "", s))))
            continue
        buf.append(s)
    flush_buf()
    return [x.to_dict() for x in blocks]


def _infer_title(blocks: list[dict[str, Any]], fallback: str) -> str:
    for b in blocks:
        if b.get("kind") == "heading" and b.get("text"):
            return str(b["text"])
    return fallback


def _sectionize(blocks: list[dict[str, Any]], source_id: str, source_type: str) -> list[dict[str, Any]]:
    """Turn source blocks into independently searchable evidence chunks.

    FAQ questions are treated as natural section boundaries. Other documents are split
    at headings. This preserves source wording without asserting semantic conclusions.
    """
    sections: list[dict[str, Any]] = []
    current_heading = ""
    current: list[dict[str, Any]] = []
    seq = 0

    def flush() -> None:
        nonlocal current, seq
        if not current:
            return
        body = "\n".join(str(x.get("text") or "") for x in current if x.get("text")).strip()
        if not body:
            current = []
            return
        seq += 1
        question = next((str(x["text"]) for x in current if QUESTION_RE.match(str(x.get("text") or ""))), None)
        refs = sorted({m.group(1) for m in RULE_REF_RE.finditer(body)})
        sections.append({
            "evidenceId": f"O:{source_id}:{seq:04d}",
            "sourceId": source_id,
            "sourceType": source_type,
            "sequence": seq,
            "heading": current_heading,
            "question": question,
            "text": body,
            "explicitRuleReferences": refs,
            "contentHash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
        current = []

    for b in blocks:
        text = str(b.get("text") or "").strip()
        if not text:
            continue
        if b.get("kind") == "heading":
            flush()
            current_heading = text
            continue
        # On FAQ-style material, a standalone question begins a new evidence section.
        if source_type == "official_faq" and QUESTION_RE.match(text) and current:
            flush()
        current.append(b)
    flush()
    return sections


def _manifest_source(root: Path, source_id: str) -> dict[str, Any] | None:
    p = root / "data/source/official_source_manifest.json"
    if not p.exists():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    return next((s for s in obj.get("sources", []) if s.get("id") == source_id), None)



def compare_source_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Conservative section-level diff for official web/text sources."""
    old_secs = list(old.get("sections") or [])
    new_secs = list(new.get("sections") or [])
    old_by_hash: dict[str, list[dict[str, Any]]] = {}
    new_by_hash: dict[str, list[dict[str, Any]]] = {}
    for sec in old_secs:
        old_by_hash.setdefault(str(sec.get("contentHash") or ""), []).append(sec)
    for sec in new_secs:
        new_by_hash.setdefault(str(sec.get("contentHash") or ""), []).append(sec)

    changes: list[dict[str, Any]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()

    # Exact content survives even if the section moved.
    for h, olds in old_by_hash.items():
        news = new_by_hash.get(h) or []
        if not h or len(olds) != 1 or len(news) != 1:
            continue
        o, n = olds[0], news[0]
        oi, ni = old_secs.index(o), new_secs.index(n)
        used_old.add(oi); used_new.add(ni)
        ctype = "UNCHANGED" if oi == ni else "MOVED"
        changes.append({
            "changeType": ctype, "oldSequence": o.get("sequence"), "newSequence": n.get("sequence"),
            "oldEvidenceId": o.get("evidenceId"), "newEvidenceId": n.get("evidenceId"),
            "heading": n.get("heading") or o.get("heading"), "question": n.get("question") or o.get("question"),
        })

    # Match remaining sections by stable question/heading anchor; changed wording remains reviewable.
    def anchor(sec: dict[str, Any]) -> str:
        return _norm(str(sec.get("question") or sec.get("heading") or "")).lower()

    unmatched_old = [i for i in range(len(old_secs)) if i not in used_old]
    unmatched_new = [i for i in range(len(new_secs)) if i not in used_new]
    new_anchor: dict[str, list[int]] = {}
    for i in unmatched_new:
        a = anchor(new_secs[i])
        if a:
            new_anchor.setdefault(a, []).append(i)
    for oi in list(unmatched_old):
        a = anchor(old_secs[oi])
        candidates = new_anchor.get(a) or []
        if len(candidates) != 1:
            continue
        ni = candidates[0]
        if ni in used_new:
            continue
        used_old.add(oi); used_new.add(ni)
        o, n = old_secs[oi], new_secs[ni]
        changes.append({
            "changeType": "TEXT_CHANGED", "oldSequence": o.get("sequence"), "newSequence": n.get("sequence"),
            "oldEvidenceId": o.get("evidenceId"), "newEvidenceId": n.get("evidenceId"),
            "heading": n.get("heading") or o.get("heading"), "question": n.get("question") or o.get("question"),
            "oldContentHash": o.get("contentHash"), "newContentHash": n.get("contentHash"),
        })

    for oi, o in enumerate(old_secs):
        if oi not in used_old:
            changes.append({"changeType": "REMOVED", "oldSequence": o.get("sequence"), "oldEvidenceId": o.get("evidenceId"), "heading": o.get("heading"), "question": o.get("question")})
    for ni, n in enumerate(new_secs):
        if ni not in used_new:
            changes.append({"changeType": "ADDED", "newSequence": n.get("sequence"), "newEvidenceId": n.get("evidenceId"), "heading": n.get("heading"), "question": n.get("question")})

    counts: dict[str, int] = {}
    for c in changes:
        counts[c["changeType"]] = counts.get(c["changeType"], 0) + 1
    return {
        "oldSha256": old.get("sha256"), "newSha256": new.get("sha256"),
        "changeCounts": counts, "changes": sorted(changes, key=lambda x: (x.get("newSequence") or 10**9, x.get("oldSequence") or 10**9)),
        "changed": old.get("sha256") != new.get("sha256"),
    }


def derive_rules_hub_metadata(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Extract current legality lists from a Rules Hub snapshot.

    The transform is intentionally narrow and fails closed if the expected official
    headings are absent. Raw source snapshots remain the audit record.
    """
    blocks = list(snapshot.get("blocks") or [])
    texts = [str(b.get("text") or "") for b in blocks]
    if not any(_norm(t).lower() == "constructed format legality" for t in texts):
        return None
    out: dict[str, Any] = {
        "schemaVersion": 1,
        "sourceId": snapshot.get("sourceId"),
        "sourceUrl": snapshot.get("sourceUrl"),
        "capturedAt": snapshot.get("capturedAt"),
        "snapshotSha256": snapshot.get("sha256"),
        "purpose": "Derived structured legality data from the archived official Rules Hub snapshot.",
        "constructed": {"lastUpdated": None, "banned": {"cards": [], "battlefields": []}},
        "twoVsTwoConstructed": {"lastUpdated": None, "banned": {"legends": [], "cards": [], "battlefields": []}},
    }
    mode: str | None = None
    category: str | None = None
    seen_legality_heading = False
    for b in blocks:
        text = _norm(str(b.get("text") or ""))
        low = text.lower()
        if low == "constructed format legality":
            mode = "constructed"; category = None; seen_legality_heading = True; continue
        if low in {"2v2 constructed legality", "2v2 constructed format legality"}:
            mode = "twoVsTwoConstructed"; category = None; seen_legality_heading = True; continue
        if seen_legality_heading and low in {"core rules", "tournament rules", "patch notes", "errata", "judges"}:
            mode = None; category = None
            if low == "core rules":
                # legality region has ended
                seen_legality_heading = False
            continue
        if mode is None:
            continue
        m = re.search(r"last updated\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%B %d, %Y")
                out[mode]["lastUpdated"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                out[mode]["lastUpdated"] = m.group(1)
            continue
        if low in {"legends", "cards", "battlefields"}:
            category = low
            out[mode]["banned"].setdefault(category, [])
            continue
        if b.get("kind") == "list_item" and category:
            out[mode]["banned"][category].append(text)
    # Fail closed if we did not recover the expected categories.
    if not out["constructed"]["banned"].get("cards") or not out["constructed"]["banned"].get("battlefields"):
        return None
    return out

def import_official_snapshot(
    root: Path,
    source_id: str,
    input_path: Path,
    *,
    media_type: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    published: str | None = None,
    effective_from: str | None = None,
) -> dict[str, Any]:
    """Archive and normalize one official source snapshot without overwriting history."""
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    meta = _manifest_source(root, source_id) or {}
    source_type = source_type or meta.get("type") or "official_article"
    source_url = source_url or meta.get("url")
    if source_url and source_type in {"rules_hub", "official_faq", "patch_notes", "card_errata", "official_article"}:
        validate_official_url(str(source_url))
    raw = input_path.read_bytes()
    sha = _sha256_bytes(raw)
    suffix = input_path.suffix.lower() or ".txt"
    if media_type is None:
        media_type = "text/html" if suffix in {".html", ".htm"} else "text/plain"

    snap_dir = root / "data/source/snapshots" / source_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    previous_snapshot = None
    previous_ptr = snap_dir / "latest.json"
    if previous_ptr.exists():
        try:
            ptr = json.loads(previous_ptr.read_text(encoding="utf-8"))
            rec = root / ptr.get("snapshotRecord", "")
            if rec.exists():
                previous_snapshot = json.loads(rec.read_text(encoding="utf-8"))
        except Exception:
            previous_snapshot = None
    archived = snap_dir / f"{sha[:16]}{suffix}"
    if not archived.exists():
        shutil.copyfile(input_path, archived)

    blocks = extract_blocks(raw, media_type)
    title = _infer_title(blocks, meta.get("title") or source_id)
    sections = _sectionize(blocks, source_id, source_type)
    snapshot = {
        "schemaVersion": 1,
        "sourceId": source_id,
        "sourceType": source_type,
        "sourceUrl": source_url,
        "title": title,
        "published": published or meta.get("published"),
        "effectiveFrom": effective_from or meta.get("effectiveFrom") or published or meta.get("published"),
        "capturedAt": _utc_now(),
        "mediaType": media_type,
        "sha256": sha,
        "byteLength": len(raw),
        "archivePath": str(archived.relative_to(root)),
        "blockCount": len(blocks),
        "sectionCount": len(sections),
        "blocks": blocks,
        "sections": sections,
        "authority": {
            "status": meta.get("status"),
            "scope": meta.get("authorityScope") or [],
            "precedence": meta.get("precedence"),
            "exhaustive": meta.get("exhaustive"),
        },
        "captureMode": meta.get("captureMode") or "source_file",
        "captureNote": meta.get("captureNote"),
        "validationProfile": meta.get("validationProfile") or {},
    }
    snapshot["validation"] = validate_snapshot_content(snapshot)
    if previous_snapshot is not None:
        snapshot["diffFromPrevious"] = compare_source_snapshots(previous_snapshot, snapshot)
        snapshot["previousSha256"] = previous_snapshot.get("sha256")
    else:
        snapshot["diffFromPrevious"] = {"changed": True, "changeCounts": {"INITIAL": len(sections)}, "changes": []}
        snapshot["previousSha256"] = None
    record = snap_dir / f"{sha[:16]}.snapshot.json"
    _atomic_json(record, snapshot)
    if snapshot.get("validation", {}).get("passed"):
        _atomic_json(snap_dir / "latest.json", {
            "sourceId": source_id,
            "sha256": sha,
            "snapshotRecord": str(record.relative_to(root)),
            "archivePath": str(archived.relative_to(root)),
            "capturedAt": snapshot["capturedAt"],
        })
    else:
        snapshot["quarantined"] = True
        snapshot["quarantineReason"] = "snapshot validation failed; latest pointer was not advanced"
        _atomic_json(record, snapshot)
    if source_type == "rules_hub" and snapshot.get("validation", {}).get("passed"):
        derived = derive_rules_hub_metadata(snapshot)
        if derived is not None:
            _atomic_json(root / "data/source/rules_hub_metadata.json", derived)
            snapshot["derivedStructuredSnapshot"] = "data/source/rules_hub_metadata.json"
            # Persist the pointer to the derived transform in the immutable snapshot record too.
            _atomic_json(record, snapshot)
    return snapshot


def fetch_official_snapshot(
    root: Path,
    source_id: str,
    *,
    url: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch an official page and ingest it. Intended for production/networked use."""
    meta = _manifest_source(root, source_id) or {}
    url = url or meta.get("url")
    if not url:
        raise ValueError(f"No URL configured for {source_id}")
    validate_official_url(str(url))
    req = Request(url, headers={"User-Agent": "RiftKeepRules/1.0 (+official-source-sync)"})
    with urlopen(req, timeout=timeout) as resp:
        announced = resp.headers.get("Content-Length")
        if announced and int(announced) > MAX_SOURCE_BYTES:
            raise ValueError(f"Official source exceeds maximum allowed size ({announced} bytes)")
        raw = resp.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f"Official source exceeds maximum allowed size ({MAX_SOURCE_BYTES} bytes)")
        ctype = resp.headers.get_content_type() or "text/html"
        if ctype not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise ValueError(f"Unsupported official source content type: {ctype}")
    tmp_dir = root / "data/source/.incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ext = ".html" if "html" in ctype else ".txt"
    tmp = tmp_dir / f"{source_id}{ext}"
    tmp.write_bytes(raw)
    try:
        return import_official_snapshot(root, source_id, tmp, media_type=ctype, source_url=url)
    finally:
        tmp.unlink(missing_ok=True)


def load_latest_snapshots(root: Path) -> list[dict[str, Any]]:
    base = root / "data/source/snapshots"
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for latest in sorted(base.glob("*/latest.json")):
        ptr = json.loads(latest.read_text(encoding="utf-8"))
        record = root / ptr["snapshotRecord"]
        if not record.exists():
            continue
        snap = json.loads(record.read_text(encoding="utf-8"))
        out.append(snap)
    return out


def compile_supplemental_sources(root: Path) -> dict[str, Any]:
    snapshots = load_latest_snapshots(root)
    documents: list[dict[str, Any]] = []
    catalog_path = root / "data/source/official_ruling_catalog.json"
    ruling_catalog: dict[str, Any] = {}
    if catalog_path.exists():
        try:
            ruling_catalog = (json.loads(catalog_path.read_text(encoding="utf-8")) or {}).get("sections") or {}
        except Exception:
            ruling_catalog = {}
    for snap in snapshots:
        for sec in snap.get("sections", []):
            doc = dict(sec)
            catalog_meta = ruling_catalog.get(str(sec.get("evidenceId") or "")) or {}
            if catalog_meta:
                doc["rulingRole"] = catalog_meta.get("role")
                doc["compilerFamily"] = catalog_meta.get("compilerFamily")
                doc["matchPhrases"] = catalog_meta.get("matchPhrases") or []
                doc["effectiveOverrides"] = catalog_meta.get("effectiveOverrides") or []
            doc.update({
                "title": snap.get("title"),
                "published": snap.get("published"),
                "effectiveFrom": snap.get("effectiveFrom"),
                "sourceUrl": snap.get("sourceUrl"),
                "authority": snap.get("authority"),
                "snapshotSha256": snap.get("sha256"),
                "partialSelection": False,
            })
            documents.append(doc)

    # Curated official rulings are deliberately allowed as a partial safety overlay.
    # They never satisfy source-completeness checks; they only make explicitly captured
    # current rulings available to deterministic adjudication while the full official
    # article snapshot is unavailable locally.
    curated_path = root / "data/source/curated_official_rulings.json"
    curated_count = 0
    full_snapshot_source_ids = {str(s.get("sourceId") or "") for s in snapshots}
    if curated_path.exists():
        curated = json.loads(curated_path.read_text(encoding="utf-8"))
        curated_source_id = str(curated.get("sourceId") or "")
        if curated_source_id in full_snapshot_source_ids:
            curated = {"documents": []}
        for raw in curated.get("documents", []):
            doc = dict(raw)
            doc.update({
                "sourceId": curated.get("sourceId"),
                "sourceType": curated.get("sourceType", "official_faq"),
                "title": "Vendetta Rules FAQ and Clarifications",
                "published": curated.get("published"),
                "effectiveFrom": curated.get("effectiveFrom"),
                "sourceUrl": curated.get("sourceUrl"),
                "authority": curated.get("authority") or {},
                "partialSelection": True,
                "curationNote": curated.get("note"),
            })
            documents.append(doc)
            curated_count += 1
    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "snapshotCount": len(snapshots),
        "curatedDocumentCount": curated_count,
        "documentCount": len(documents),
        "snapshots": [{
            "sourceId": s.get("sourceId"), "sourceType": s.get("sourceType"), "title": s.get("title"),
            "published": s.get("published"), "effectiveFrom": s.get("effectiveFrom"), "sha256": s.get("sha256"),
            "sectionCount": s.get("sectionCount"), "authority": s.get("authority"),
        } for s in snapshots],
        "documents": documents,
    }
