"""SAP Test Script (BPD) docx parser — simplified four-field model.

Extracts per scope item:
- Scope Item ID         (from filename + cross-validated with cover table)
- Scope Item Name       (from cover table)
- Process Description   (from §Purpose chapter)
- Dependencies          (other scope items referenced anywhere in the doc)

The Test Script docx is the sole source. No Setup PDFs needed.

Calibrated against SAP S/4HANA Cloud Public Edition release S4CLD 2602
(2025-12-02). Tested on 1B6 (Sales Rebate Processing) and 1MX (Intercompany
Sales Order Processing — International).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.document import Document as _Document


# --- Style markers (S4CLD2602 BPD template) -------------------------------
HEADING_STYLE = "Heading 1"
LABEL_STYLE = "SAP_KeyblockTitle"

# --- Boilerplate stripped from §Purpose -----------------------------------
BOILERPLATE_PATTERNS = [
    re.compile(
        r"^This document provides a detailed procedure for testing this scope item.*",
        re.IGNORECASE,
    ),
    re.compile(r"^Project-specific steps must be added\.?\s*$", re.IGNORECASE),
]


# --- Dependency extraction ------------------------------------------------
SCOPE_ID_CHARSET = r"[A-Z0-9]{3}"

# Three accepted phrasings for a scope-item reference:
DEP_PATTERNS = [
    # "scope item ... (<ID>)"   — works across line breaks
    re.compile(
        rf"scope\s+item[s]?[^.()]{{0,200}}?\(({SCOPE_ID_CHARSET})\)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "(<ID>) scope item"  or  "(<ID>) test script"
    re.compile(
        rf"\(({SCOPE_ID_CHARSET})\)\s+(?:scope\s+item|test\s+script)",
        re.IGNORECASE,
    ),
    # bare "scope item <ID>" (no parens)
    re.compile(
        rf"scope\s+item[s]?\s+({SCOPE_ID_CHARSET})\b",
        re.IGNORECASE,
    ),
]

# Tokens that may appear in a scope item name when walking backwards from
# "(<ID>)" to find the name. Anything else terminates the name.
NAME_JOINER_TOKENS = {
    "of", "and", "with", "for", "the", "in", "on", "from", "to",
    "a", "an", "or", "at", "by", "as", "–", "-", "&", "/",
}


@dataclass
class Dependency:
    scope_id: str
    name: str | None = None
    kind: str = "required"  # "required" | "optional"
    context: str = ""        # the sentence that mentioned this dep


@dataclass
class ProcessStep:
    """A single row from the §3 Overview Table.

    `group_heading` is set on rows that act as visual group headers
    inside the table (col 0 has content, cols 1+ are empty). For these,
    the other fields are empty.
    """
    process_step: str = ""
    business_role: str = ""
    transaction_app: str = ""
    expected_results: str = ""
    group_heading: bool = False


@dataclass
class ScopeItem:
    scope_id: str
    name: str | None = None
    process_description: str | None = None
    process_description_source: str = "none"  # "testscript" | "manual" | "none"
    dependencies: list[Dependency] = field(default_factory=list)
    process_steps: list[ProcessStep] = field(default_factory=list)
    source_filename: str = ""
    warnings: list[str] = field(default_factory=list)


# --- Helpers --------------------------------------------------------------

def _is_valid_scope_id(s: str) -> bool:
    """Real SAP scope IDs: 3 alphanumerics, mixed digit + letter.
    Excludes pure numbers (100, 213) and pure-letter abbreviations (USA, EUR)."""
    return (
        len(s) == 3
        and any(c.isdigit() for c in s)
        and any(c.isalpha() for c in s)
    )


def _is_name_token(tok: str) -> bool:
    if not tok:
        return False
    if tok.lower() in NAME_JOINER_TOKENS:
        return True
    if tok[0].isupper():
        return True
    return False


def _extract_name_before_parens(text: str, paren_pos: int) -> str | None:
    """Walk backwards from `(` position, collecting name-eligible tokens.

    Stops at the first lowercase verb / ineligible token. Trims leading/
    trailing joiners.
    """
    prefix = text[:paren_pos].rstrip()
    tokens = prefix.split()
    if not tokens:
        return None

    accepted: list[str] = []
    for tok in reversed(tokens):
        clean = tok.rstrip(".,;:!?)")
        if _is_name_token(clean):
            accepted.insert(0, clean)
        else:
            break

    while accepted and accepted[0].lower() in NAME_JOINER_TOKENS:
        accepted.pop(0)
    while accepted and accepted[-1].lower() in NAME_JOINER_TOKENS:
        accepted.pop()

    if not accepted or not (1 <= len(accepted) <= 12):
        return None
    return " ".join(accepted)


def _classify_kind(sentence: str) -> str:
    """Heuristic — required vs optional based on phrasing of the dependency."""
    s = sentence.lower()
    optional_signals = (
        "only use if", "(optional)", "if you have activated",
        "if you want to", "in case", "you can", "can be used",
        "for the case",
    )
    if any(sig in s for sig in optional_signals):
        return "optional"
    return "required"


# --- Section extraction ---------------------------------------------------

def _is_purpose_heading(p) -> bool:
    return (p.style.name == HEADING_STYLE
            and p.text.strip().lower() == "purpose")


def _is_other_h1(p) -> bool:
    return (p.style.name == HEADING_STYLE
            and p.text.strip()
            and p.text.strip().lower() != "purpose")


def _is_overview_label(p) -> bool:
    return (p.style.name == LABEL_STYLE
            and p.text.strip().lower() == "overview")


def _is_boilerplate(text: str) -> bool:
    return any(pat.match(text.strip()) for pat in BOILERPLATE_PATTERNS)


def _extract_purpose_body(doc: _Document) -> str | None:
    in_section = False
    parts: list[str] = []
    for p in doc.paragraphs:
        if not in_section:
            if _is_purpose_heading(p):
                in_section = True
            continue
        if _is_other_h1(p):
            break
        if _is_overview_label(p):
            continue
        text = p.text.strip()
        if not text or _is_boilerplate(text):
            continue
        parts.append(text)
    return "\n\n".join(parts) if parts else None


# --- Cover-page name extraction -------------------------------------------

# Cover format varies by file region:
#   Country-localized: "Sales Rebate Processing (1B6_DE)"
#   Cross-country/generic: "Information Lifecycle Management (1KA)"  ← no suffix
# The optional non-capturing group `(?:_[A-Z]{2})?` handles both.
COVER_NAME_RE = re.compile(
    rf"^(.+?)\s*\(({SCOPE_ID_CHARSET})(?:_[A-Z]{{2}})?\)\s*$"
)


def _extract_name(doc: _Document, scope_id: str) -> str | None:
    """Cover info lives in the first table of the doc, row 1."""
    if not doc.tables:
        return None
    first_table = doc.tables[0]
    for row in first_table.rows:
        for cell in row.cells:
            text = cell.text.strip()
            m = COVER_NAME_RE.match(text)
            if m and m.group(2).upper() == scope_id.upper():
                return m.group(1).strip()
    return None


# --- Dependency extraction ------------------------------------------------

def _all_text_chunks(doc: _Document) -> list[tuple[str, str]]:
    """All non-empty text from paragraphs and table cells, with locator."""
    chunks: list[tuple[str, str]] = []
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip():
            chunks.append((f"para[{i}]", p.text))
    for tn, table in enumerate(doc.tables):
        for r, row in enumerate(table.rows):
            for c, cell in enumerate(row.cells):
                if cell.text.strip():
                    chunks.append((f"table[{tn}].r{r}.c{c}", cell.text))
    return chunks


def _extract_dependencies(doc: _Document, own_id: str) -> list[Dependency]:
    """Find all scope-item references across the entire document."""
    found: dict[str, Dependency] = {}

    for loc, text in _all_text_chunks(doc):
        for pat in DEP_PATTERNS:
            for m in pat.finditer(text):
                sid = m.group(1).upper()
                if sid == own_id.upper() or not _is_valid_scope_id(sid):
                    continue

                # Sentence-level context for kind + name
                sentences = re.split(r"(?<=[.!?])\s+", text)
                ctx_sentence = next(
                    (s for s in sentences if sid in s),
                    text[:300],
                ).strip()[:300]

                # Try to recover the dep's name from "(SID)" position
                paren_idx = text.find(f"({m.group(1)})")
                name = (
                    _extract_name_before_parens(text, paren_idx)
                    if paren_idx >= 0 else None
                )

                if sid not in found:
                    found[sid] = Dependency(
                        scope_id=sid,
                        name=name,
                        kind=_classify_kind(ctx_sentence),
                        context=ctx_sentence,
                    )
                else:
                    # Upgrade name if better one becomes available later
                    if name and not found[sid].name:
                        found[sid].name = name

    return sorted(found.values(), key=lambda d: d.scope_id)


# --- Overview Table (§3) extraction ---------------------------------------

# Page references like "  [page ] 58" appended to Process Step text.
_PAGE_REF_RE = re.compile(r"\s*\[page\s*\]\s*\d+\s*$", re.IGNORECASE)


def _strip_page_ref(text: str) -> str:
    """Remove trailing '[page ] NN' from a cell value."""
    return _PAGE_REF_RE.sub("", text).strip()


def _find_overview_tables(doc: _Document) -> list:
    """Walk doc body XML and return the list of `docx.table.Table` objects
    that appear under the §Overview Table H1 heading.
    """
    from docx.oxml.ns import qn

    body = doc.element.body
    in_section = False
    matched_indices: list[int] = []
    seen = 0

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            pStyle = child.find(qn("w:pPr") + "/" + qn("w:pStyle"))
            style = pStyle.get(qn("w:val")) if pStyle is not None else None
            text = "".join(
                (t.text or "") for t in child.findall(".//" + qn("w:t"))
            ).strip()
            if style == "Heading1":
                if text.lower() == "overview table":
                    in_section = True
                elif in_section:
                    break
        elif tag == "tbl":
            if in_section:
                matched_indices.append(seen)
            seen += 1

    return [doc.tables[i] for i in matched_indices]


def _is_process_steps_table(table) -> bool:
    """The real Process Steps table has ≥3 columns and a header row whose
    first cell starts with 'Process Step'. We avoid the SAP info-banner
    table (1×1) and any other small auxiliary tables.
    """
    if len(table.columns) < 3 or len(table.rows) < 2:
        return False
    first_cell = table.rows[0].cells[0].text.strip().lower()
    return first_cell.startswith("process step")


def _extract_process_steps(doc: _Document) -> list[ProcessStep]:
    """Find the Process Steps table under §Overview Table and parse rows."""
    candidates = _find_overview_tables(doc)
    table = next((t for t in candidates if _is_process_steps_table(t)), None)
    if table is None:
        return []

    steps: list[ProcessStep] = []
    # Skip the header row
    for row in table.rows[1:]:
        cells = [c.text.strip() for c in row.cells]
        # Pad/trim to exactly 4 columns (some templates may have extra)
        while len(cells) < 4:
            cells.append("")
        c0, c1, c2, c3 = cells[0], cells[1], cells[2], cells[3]

        if not c0:
            # Empty row — skip
            continue

        # Always strip page refs from the Process Step column
        c0 = _strip_page_ref(c0)

        # Group-heading row: only column 0 has content
        if not (c1 or c2 or c3):
            steps.append(ProcessStep(
                process_step=c0,
                group_heading=True,
            ))
        else:
            steps.append(ProcessStep(
                process_step=c0,
                business_role=c1,
                transaction_app=c2,
                expected_results=c3,
                group_heading=False,
            ))

    return steps


# --- Public API -----------------------------------------------------------

def extract_scope_item(docx_path: str | Path) -> ScopeItem:
    """Open a Test Script docx and return a fully-populated ScopeItem."""
    docx_path = Path(docx_path)
    scope_id = docx_path.name.split("_", 1)[0]
    item = ScopeItem(scope_id=scope_id, source_filename=docx_path.name)

    try:
        doc = Document(docx_path)
    except Exception as e:
        item.warnings.append(f"Failed to open Test Script docx: {e}")
        return item

    item.name = _extract_name(doc, scope_id)
    if not item.name:
        item.warnings.append("Could not parse Scope Item Name from cover")

    item.process_description = _extract_purpose_body(doc)
    if item.process_description:
        item.process_description_source = "testscript"
    else:
        item.warnings.append("No Process Description found in §Purpose")

    item.dependencies = _extract_dependencies(doc, scope_id)

    item.process_steps = _extract_process_steps(doc)
    # No warning if absent — some scope items legitimately have no
    # Overview Table (rare, but possible).

    return item
