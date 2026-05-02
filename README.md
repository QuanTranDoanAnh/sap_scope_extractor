# SAP S/4HANA Cloud Public Edition — Scope Item Extractor (v3)

Streamlit tool that scans **SAP Test Script (BPD) docx files** and produces
a single consolidated Markdown listing every scope item with four fields:

| Field | Source |
| --- | --- |
| Scope Item ID | filename + cross-validated against cover table |
| Scope Item Name | first table on cover page (`<Name> (<ID>_<region>)`) |
| Process Description | §Purpose chapter, with boilerplate stripped |
| Dependencies | other scope item IDs referenced anywhere in the document |

This is the **simplified single-source build**. If you also need
implementation details (Prerequisites, Business Context, Communication
Scenarios) for AHP/integration estimation work, use the earlier dual-source
build that also reads Setup PDFs.

## How dependencies are identified

The parser scans every paragraph and table cell for three phrasing patterns
that SAP Test Scripts use to reference other scope items:

1. `scope item ... (<ID>)` — *"the scope item Sell from Stock (BD9)"*
2. `(<ID>) scope item` / `(<ID>) test script` — *"described in the test script of Handling Unit Management (4MM) scope item"*
3. bare `scope item <ID>` — *"It is mandatory that scope item 1NN is active"*

The "scope item" / "test script" keyword is required — this filters out
false positives that look like 3-character IDs but aren't (page numbers,
config parameters like `213` or `0S1`, currency codes like `USD`).

A scope-item ID is a 3-character alphanumeric token containing **at least
one digit AND at least one letter**, which excludes pure numbers (`100`,
`213`) and pure-letter abbreviations (`USA`, `EUR`, `XML`).

For each found dependency, the parser also extracts:

- **Name** — by walking backwards from `(<ID>)` and accepting capitalized
  words and small joiner words (`of`, `and`, `with`, `for`, `the`, `–`,
  etc.) until it hits a lowercase verb that breaks the pattern. Tested
  against six real cases: 100% match.
- **Kind** — `required` (default) vs `optional`, classified by the
  presence of phrases like *"only use if"*, *"(Optional)"*, *"if you have
  activated"*, *"in case"*, *"you can"* in the surrounding sentence.
- **Context** — the full sentence where the reference was found, for
  manual verification.

## Validated against

| File | Description (chars) | Dependencies found |
| --- | ---: | --- |
| `1B6_S4CLD2602_BPD_EN_DE.docx` | 976 | 1YT (opt), BD9 (opt), J58 (req), J59 (req) |
| `1MX_S4CLD2602_BPD_EN_DE.docx` | 474 | 4MM (req), BD9 (req) |

All identified dependencies were spot-checked against the source documents
— no false positives, no missed cases.

## Files

```
extractor/
├── app.py               Streamlit UI (Test Scripts only + override editor)
├── docx_parser.py       All extraction logic (single module)
├── markdown_writer.py   Inline + expanded Markdown rendering
├── requirements.txt     streamlit, python-docx, pandas
└── README.md
```

Smaller dependency footprint than v2 — no PyMuPDF needed.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

In the sidebar:
- **Local folder path** — paste the absolute path to your `TestScripts`
  folder (e.g. `D:\Works\S4HC_Public\S4C\Library\TestScripts`).
- **Upload ZIP** — works for any deployment.

Then choose output format (Inline matches the original spec; Expanded uses
sub-headings — recommended), click **Extract scope items**, review the
summary table, and download `scope_items.md`.

## Manual overrides

The override editor lets you fix two things per scope item:

1. **Process Description** — paste a richer text from SAP for Me /
   Process Navigator if the auto-extracted §Purpose is too thin.
2. **Dependencies** — edit the JSON list directly to add/remove/relabel
   dependencies. Each dependency is `{"scope_id": "BD9", "name": "Sell
   from Stock", "kind": "required"}`.

Overrides take precedence in the final Markdown output. Use the
**Export overrides JSON** button to persist them across runs and commit
alongside the project deliverable.

## Known limits

- Calibrated against SAP S/4HANA Cloud Public Edition release **S4CLD
  2602** (2025-12-02). Older or newer releases may need style-name or
  pattern recalibration.
- Dependency detection requires the literal phrase "scope item" or "test
  script" near the parenthesized ID. References that omit this keyword
  (e.g. just "the BD9 process") are missed by design — they're not
  reliably distinguishable from non-dependency 3-char tokens. Use the
  manual override to add such cases.
- The automatic kind classifier (required vs optional) is heuristic. Spot
  check the **Context** column in the per-item inspector to verify.
- Embedded tables in Process Description are flattened to text. Markdown
  table preservation is a small add-on if needed.

## Possible next extensions

- **Dependency graph view** — once you have ≥30 scope items, a simple
  Mermaid or D3 graph of `scope_id -> dependency_id` edges would
  surface dependency clusters and orphan scope items at a glance.
- **Reverse index** — *"who depends on BD9?"* — useful when reviewing
  whether a foundational scope item is in scope for the project.
- **Roles & Master Data extraction** — Test Script §2.2 (Roles) and §2.3
  (Master Data) are structured tables ready to lift into the same
  Markdown deliverable, useful for staffing and data migration scoping.

## Changelog

- **v3.1** — Cover-name regex now accepts both country-localized
  format (`<Name> (<ID>_<REGION>)`, e.g. `1B6_DE`) and cross-country
  generic format (`<Name> (<ID>)`, e.g. `1KA`). Fixes 21% Name
  extraction failure rate when scanning packages containing `_XX`
  files.

## v3.2 — Process Steps support

Added optional rendering of the §3 Overview Table from each Test Script
as a Markdown table per scope item. Toggled via a sidebar checkbox
("Include Process Steps table per scope item").

When enabled, each scope item gets a "Process Steps" section with a
table of: Process Step | Business Role | Transaction/App | Expected
Results. Page references like `[page ] 58` are stripped automatically.

**Group-heading rows** (rows where only column 0 has content, used in
1B6-style multi-variant scope items to separate sub-process groups
like "Sales Rebate Processing – One Customer") are rendered as bold
spanning rows inside the table — visually distinguishable from regular
numbered steps.

**Multi-line cells** (e.g. a Business Role cell containing three roles
on separate lines) are joined with `<br>` so the table row stays valid
GFM. Pipes `|` inside cells are escaped.

The "Steps" column in the summary table shows how many real (non-group)
steps were extracted per scope item, useful for spotting any cases where
extraction returned zero rows.

## v3.3 — Excel output

Added Excel (.xlsx) as a third output format alongside the two
Markdown variants. Selectable via the sidebar's "Output format" radio.

The Excel workbook contains exactly two sheets:

**Sheet 1 — Scope Items.** One row per scope item with these columns:
  - Scope Item ID
  - Scope Item Name
  - Process Description (wrap-text, full content)
  - Dependencies (one dep per line: `<ID> – <Name> (<kind>)`)

**Sheet 2 — Process Steps.** One row per actionable step (group-heading
rows from the source documents are excluded, since they have no
Business Role / Transaction / Expected Results to populate). Columns:
  - Scope Item ID
  - Scope Item Name
  - Process Step
  - Business Roles
  - Transaction/App
  - Expected Results

Both sheets ship with bold headers (Calibri, white-on-blue), frozen
top row, auto-filter on the header, sensible column widths, and
wrap-text on long-text columns. No formulas — pure data export.

The "Include Process Steps table" checkbox affects Markdown only; the
Excel format always includes the Process Steps sheet. The checkbox
greys out automatically when Excel is selected.
