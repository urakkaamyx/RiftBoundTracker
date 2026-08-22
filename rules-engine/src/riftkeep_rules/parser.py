from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz

RULE_TOKEN_RE = re.compile(r"^(\d{3}(?:\.(?:\d+|[a-z]))*)\.$", re.I)
RULE_REF_RE = re.compile(r"\b(?:see\s+)?rules?\s+(\d{3}(?:\.(?:\d+|[a-z]))*)\b", re.I)
EXAMPLE_RE = re.compile(r"\bExamples?:\s*", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00ad", "").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_match(text: str) -> str:
    text = normalize_text(text).lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return text


def split_normative_examples(text: str) -> tuple[str, str | None]:
    text = normalize_text(text)
    m = EXAMPLE_RE.search(text)
    if not m:
        return text, None
    normative = text[: m.start()].strip()
    example = text[m.start() :].strip()
    return normative, example


@dataclass(frozen=True)
class VisualRow:
    page: int
    y: float
    words: tuple[tuple[float, float, float, float, str], ...]

    @property
    def text(self) -> str:
        return normalize_text(" ".join(w[4] for w in sorted(self.words, key=lambda x: x[0])))

    @property
    def x0(self) -> float:
        return min(w[0] for w in self.words)

    @property
    def first_token(self) -> str:
        return sorted(self.words, key=lambda x: x[0])[0][4]


def visual_rows(page: fitz.Page, page_no: int, y_tolerance: float = 0.8) -> list[VisualRow]:
    """Reconstruct visual rows from individual PDF words.

    PyMuPDF logical line blocks can split a numbered rule ID from the body or merge
    adjacent logical lines. Grouping by visual y coordinate is safer for this PDF.
    """
    words = [w[:5] for w in page.get_text("words") if str(w[4]).strip()]
    words.sort(key=lambda w: (w[1], w[0]))
    groups: list[list[tuple[float, float, float, float, str]]] = []
    ys: list[float] = []
    for raw in words:
        w = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]), str(raw[4]))
        placed = False
        for i in range(len(groups) - 1, max(-1, len(groups) - 4), -1):
            if abs(ys[i] - w[1]) <= y_tolerance:
                groups[i].append(w)
                # keep a stable representative y; do not drift too far
                ys[i] = sum(x[1] for x in groups[i]) / len(groups[i])
                placed = True
                break
        if not placed:
            groups.append([w])
            ys.append(w[1])
    rows = [VisualRow(page_no, ys[i], tuple(g)) for i, g in enumerate(groups)]
    rows.sort(key=lambda r: (r.y, r.x0))
    return rows


def _line_style_candidates(page: fitz.Page) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = normalize_text("".join(s.get("text", "") for s in spans))
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            all_bold = all("Bold" in str(s.get("font", "")) for s in spans)
            max_size = max(float(s.get("size", 0)) for s in spans)
            out.append(
                {
                    "text": text,
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "allBold": all_bold,
                    "maxSize": max_size,
                }
            )
    return out


def detect_visual_headings(doc: fitz.Document) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """Detect major and local visual headings conservatively.

    These headings improve retrieval but are metadata, not authoritative rule text.
    """
    major: list[dict[str, Any]] = []
    local_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for pi in range(len(doc)):
        page = doc[pi]
        page_no = pi + 1
        rows = visual_rows(page, page_no)
        rule_y: set[int] = set()
        for r in rows:
            toks = sorted(r.words, key=lambda x: x[0])
            if toks and toks[0][0] <= 80 and RULE_TOKEN_RE.match(toks[0][4]):
                rule_y.add(round(r.y))

        lines = _line_style_candidates(page)
        # major section title: 11pt bold title sharing y with a 3-digit root rule token.
        for line in lines:
            if line["maxSize"] >= 10.5 and line["allBold"] and 80 <= line["x0"] <= 220:
                if round(line["y0"]) in rule_y and len(line["text"]) <= 90:
                    # get root ID from corresponding visual row
                    candidates = [r for r in rows if abs(r.y - line["y0"]) <= 1.2]
                    for r in candidates:
                        toks = sorted(r.words, key=lambda x: x[0])
                        if toks and toks[0][0] <= 80:
                            m = RULE_TOKEN_RE.match(toks[0][4])
                            if m and "." not in m.group(1):
                                major.append(
                                    {
                                        "ruleId": m.group(1),
                                        "title": line["text"],
                                        "page": page_no,
                                        "y": line["y0"],
                                    }
                                )
                                break

        # local heading: standalone, all-bold, short, left-aligned in the content heading column,
        # no terminal punctuation, and not on a rule row.
        for line in lines:
            txt = line["text"]
            if (
                line["allBold"]
                and line["maxSize"] >= 7.8
                and 95 <= line["x0"] <= 200
                and round(line["y0"]) not in rule_y
                and 1 <= len(txt.split()) <= 10
                and len(txt) <= 80
                and not re.search(r"[.:;!?]$", txt)
                and not txt.lower().startswith(("example", "see rule", "last updated"))
            ):
                local_by_page[page_no].append(
                    {
                        "title": txt,
                        "page": page_no,
                        "y": line["y0"],
                        "confidence": "heuristic",
                    }
                )
    # de-dupe
    seen = set()
    major_out = []
    for x in sorted(major, key=lambda z: (z["page"], z["y"])):
        k = (x["ruleId"], x["title"])
        if k not in seen:
            seen.add(k)
            major_out.append(x)
    for page, items in list(local_by_page.items()):
        uniq = []
        s = set()
        for x in sorted(items, key=lambda z: z["y"]):
            k = x["title"]
            if k not in s:
                s.add(k)
                uniq.append(x)
        local_by_page[page] = uniq
    return major_out, dict(local_by_page)


def parse_numbered_pdf(path: Path, source_id: str, stable_prefix: str, title: str) -> dict[str, Any]:
    doc = fitz.open(path)
    major_headings, local_headings = detect_visual_headings(doc)
    major_by_id = {x["ruleId"]: x["title"] for x in major_headings}
    major_order = [x["ruleId"] for x in major_headings]

    records: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    current_local_heading: str | None = None
    current_major_id: str | None = None
    current_major_title: str | None = None

    # allow local headings to change context before a subsequent rule on the same page
    heading_events: dict[int, list[dict[str, Any]]] = {
        p: sorted(items, key=lambda x: x["y"]) for p, items in local_headings.items()
    }

    def finish() -> None:
        nonlocal pending
        if pending is None:
            return
        full = normalize_text(" ".join(pending.pop("_parts")))
        normative, example = split_normative_examples(full)
        pending["text"] = full
        pending["normativeText"] = normative
        pending["exampleText"] = example
        pending["normalizedText"] = normalize_match(normative)
        pending["explicitCrossReferences"] = sorted(set(RULE_REF_RE.findall(full)))
        pending["textSha256"] = hashlib.sha256(full.encode("utf-8")).hexdigest()
        pending["normativeTextSha256"] = hashlib.sha256(normative.encode("utf-8")).hexdigest()
        records.append(pending)
        pending = None

    for pi in range(len(doc)):
        page = doc[pi]
        page_no = pi + 1
        rows = visual_rows(page, page_no)
        local_events = heading_events.get(page_no, [])
        event_i = 0
        for row in rows:
            while event_i < len(local_events) and local_events[event_i]["y"] < row.y - 0.6:
                current_local_heading = local_events[event_i]["title"]
                event_i += 1

            # Skip page headers/footers unless they are actual numbered rule rows.
            toks = sorted(row.words, key=lambda x: x[0])
            first = toks[0]
            m = RULE_TOKEN_RE.match(first[4]) if first[0] <= 80 else None
            if not m and (row.y < 70 or row.y > 750):
                continue
            text = row.text
            if not text:
                continue
            if not m and title.lower() in text.lower():
                continue
            if not m and text.lower().startswith("last updated"):
                continue

            # Skip standalone visual heading lines; they should not leak into previous rule body.
            if not m and any(abs(h["y"] - row.y) <= 0.8 and h["title"] == text for h in local_events):
                current_local_heading = text
                continue

            if m:
                finish()
                rid = m.group(1)
                if rid in major_by_id:
                    current_major_id = rid
                    current_major_title = major_by_id[rid]
                    current_local_heading = None
                # remove the first visual token (the identifier), preserve the rest of the row
                body = normalize_text(" ".join(w[4] for w in toks[1:]))
                pending = {
                    "ruleId": rid,
                    "sourceId": source_id,
                    "pageStart": page_no,
                    "pageEnd": page_no,
                    "majorSectionRuleId": current_major_id,
                    "majorSectionTitle": current_major_title,
                    "visualSubsection": current_local_heading,
                    "_parts": [body] if body else [],
                }
            elif pending is not None:
                pending["_parts"].append(text)
                pending["pageEnd"] = page_no
        # Process headings below the final row as context for next page only if needed.
        while event_i < len(local_events):
            current_local_heading = local_events[event_i]["title"]
            event_i += 1
    finish()
    doc.close()

    ids = {r["ruleId"] for r in records}
    by_parent: dict[str | None, list[str]] = defaultdict(list)
    for i, r in enumerate(records):
        rid = r["ruleId"]
        parts = rid.split(".")
        parent = None
        for cut in range(len(parts) - 1, 0, -1):
            c = ".".join(parts[:cut])
            if c in ids:
                parent = c
                break
        r["internalRuleId"] = f"{stable_prefix}-{i+1:06d}"
        r["sequence"] = i
        r["depth"] = len(parts)
        r["rootRuleId"] = parts[0]
        r["parentRuleId"] = parent
        r["previousRuleId"] = records[i - 1]["ruleId"] if i else None
        r["nextRuleId"] = records[i + 1]["ruleId"] if i + 1 < len(records) else None
        r["resolvedCrossReferences"] = [x for x in r["explicitCrossReferences"] if x in ids]
        r["unresolvedCrossReferences"] = [x for x in r["explicitCrossReferences"] if x not in ids]
        by_parent[parent].append(rid)
    for r in records:
        r["childRuleIds"] = by_parent.get(r["ruleId"], [])
        r["siblingRuleIds"] = [x for x in by_parent.get(r["parentRuleId"], []) if x != r["ruleId"]]

    return {
        "metadata": {
            "sourceId": source_id,
            "title": title,
            "sourceFile": path.name,
            "sourceSha256": sha256_file(path),
            "pageCount": len(fitz.open(path)),
            "ruleCount": len(records),
            "majorSections": major_headings,
            "majorSectionOrder": major_order,
            "parser": "visual-word-row-v2",
        },
        "rules": records,
    }


def extract_layout_rule_ids(path: Path) -> list[str]:
    """Independent validation path using pdftotext -layout."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        subprocess.run(["pdftotext", "-layout", str(path), str(out)], check=True, capture_output=True)
        ids: list[str] = []
        for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
            # Actual numbered entries are left-column anchored. Wrapped citations such as
            # "See CR 128" may begin a continuation line with the number far to the right.
            leading = len(line) - len(line.lstrip(" "))
            if leading > 8:
                continue
            m = re.match(r"^\s*(\d{3}(?:\.(?:\d+|[a-z]))*)\.\s", line, re.I)
            if m:
                ids.append(m.group(1))
        return ids
    finally:
        out.unlink(missing_ok=True)


def validate_pdf_parse(path: Path, parsed: dict[str, Any]) -> dict[str, Any]:
    parser_ids = [r["ruleId"] for r in parsed["rules"]]
    layout_ids = extract_layout_rule_ids(path)
    parser_set, layout_set = set(parser_ids), set(layout_ids)
    duplicates = sorted({x for x in parser_ids if parser_ids.count(x) > 1})
    # A numbered entry may intentionally consist only of Example:/Examples: text.
    # Treat it as non-empty when the full authoritative text is present.
    empty_text = [r["ruleId"] for r in parsed["rules"] if not r["text"]]
    return {
        "parserCount": len(parser_ids),
        "independentLayoutCount": len(layout_ids),
        "missingFromParser": sorted(layout_set - parser_set),
        "extraInParser": sorted(parser_set - layout_set),
        "duplicateParserIds": duplicates,
        "emptyText": empty_text,
        "passed": (
            len(parser_ids) == len(layout_ids)
            and parser_set == layout_set
            and not duplicates
            and not empty_text
        ),
    }


def load_cards(path: Path) -> dict[str, Any]:
    cards = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for c in cards:
        item = dict(c)
        text = normalize_text(c.get("textPlain") or "")
        errata = c.get("errata") or []
        current = text
        if errata and errata[-1].get("corrected"):
            current = normalize_text(errata[-1]["corrected"])
        item["databaseText"] = text
        item["effectiveText"] = current
        item["knownPrintedText"] = normalize_text(errata[0]["original"]) if errata and errata[0].get("original") else None
        item["textSource"] = "inline_errata.corrected" if errata and errata[-1].get("corrected") else "databaseText"
        out.append(item)
    return {
        "metadata": {
            "sourceFile": path.name,
            "sourceSha256": sha256_file(path),
            "recordCount": len(out),
        },
        "cards": out,
    }
