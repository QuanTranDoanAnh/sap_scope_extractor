"""Render extracted ScopeItems to Markdown (v3.2 — adds optional Process Steps)."""
from __future__ import annotations

from typing import Iterable

from docx_parser import ScopeItem, Dependency, ProcessStep


PLACEHOLDER_NOT_FOUND = "_(Not specified in source document)_"
PLACEHOLDER_NO_DEPS = "_(None identified)_"
PLACEHOLDER_NO_STEPS = "_(No Overview Table found in source document)_"


# --- Cleanup helpers ------------------------------------------------------

def _normalize_body(text: str | None) -> str:
    if not text:
        return PLACEHOLDER_NOT_FOUND
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    cleaned: list[str] = []
    blank_run = 0
    for ln in lines:
        if not ln.strip():
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
        else:
            blank_run = 0
            cleaned.append(ln)
    return "\n".join(cleaned)


def _render_inline(text: str | None) -> str:
    body = _normalize_body(text)
    if body == PLACEHOLDER_NOT_FOUND:
        return body
    return body.replace("\n\n", "\n").replace("\n", " <br> ")


def _source_tag(item: ScopeItem) -> str:
    if item.process_description_source == "manual":
        return " *(source: manual override)*"
    if item.process_description_source == "testscript":
        return " *(source: Test Script)*"
    return ""


def _format_dep_line(d: Dependency) -> str:
    name_part = f" — {d.name}" if d.name else ""
    return f"`{d.scope_id}`{name_part} *({d.kind})*"


def _render_deps_inline(deps: list[Dependency]) -> str:
    if not deps:
        return PLACEHOLDER_NO_DEPS
    return " <br> ".join(f"• {_format_dep_line(d)}" for d in deps)


def _render_deps_block(deps: list[Dependency]) -> str:
    if not deps:
        return PLACEHOLDER_NO_DEPS
    return "\n".join(f"- {_format_dep_line(d)}" for d in deps)


# --- Process steps rendering ---------------------------------------------

def _md_escape_cell(text: str) -> str:
    """Make a cell value safe inside a GitHub-flavored Markdown table:
    - escape literal pipes
    - replace newlines with <br> so the row stays on one line
    - collapse multi-space runs
    """
    if not text:
        return ""
    text = text.replace("|", "\\|")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br>")
    # Collapse 2+ spaces to single space (cosmetic)
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _render_process_steps(steps: list[ProcessStep]) -> str:
    """Render the §3 Overview Table as Markdown.

    Group-heading rows render as bold sub-rows that span all columns
    visually (we put them in column 1 and use bold to set them apart).
    GFM doesn't support true rowspan, so we accept this slight degradation.
    """
    if not steps:
        return PLACEHOLDER_NO_STEPS

    out: list[str] = []
    out.append("| # | Process Step | Business Role | Transaction / App | Expected Results |")
    out.append("|---|---|---|---|---|")
    seq = 0
    for s in steps:
        if s.group_heading:
            # Group label spanning visually: leave # blank, bold the label
            out.append(
                f"|  | **{_md_escape_cell(s.process_step)}** |  |  |  |"
            )
        else:
            seq += 1
            out.append(
                f"| {seq} "
                f"| {_md_escape_cell(s.process_step)} "
                f"| {_md_escape_cell(s.business_role)} "
                f"| {_md_escape_cell(s.transaction_app)} "
                f"| {_md_escape_cell(s.expected_results)} |"
            )
    return "\n".join(out)


# --- Inline format (matches user template) --------------------------------

def render_inline_template(
    items: Iterable[ScopeItem],
    *,
    include_process_steps: bool = False,
) -> str:
    out = ["# LIST OF SCOPE ITEMS:", ""]
    for item in sorted(items, key=lambda x: x.scope_id):
        name = item.name or "(name not parsed)"
        out.append(f"## {item.scope_id} – {name}")
        out.append("")
        out.append(f"* **Scope Item ID:** {item.scope_id}")
        out.append(f"* **Scope Item Name:** {name}")
        out.append(
            f"* **Process Description:**{_source_tag(item)} "
            f"{_render_inline(item.process_description)}"
        )
        out.append(f"* **Dependencies:** {_render_deps_inline(item.dependencies)}")
        if item.warnings:
            out.append(f"* _Parser warnings:_ {'; '.join(item.warnings)}")

        if include_process_steps:
            out.append("")
            out.append("**Process Steps:**")
            out.append("")
            out.append(_render_process_steps(item.process_steps))

        out.append("")
    return "\n".join(out)


# --- Expanded format ------------------------------------------------------

def render_expanded(
    items: Iterable[ScopeItem],
    *,
    include_process_steps: bool = False,
) -> str:
    out = ["# LIST OF SCOPE ITEMS", ""]
    for item in sorted(items, key=lambda x: x.scope_id):
        name = item.name or "(name not parsed)"
        out.append(f"## {item.scope_id} – {name}")
        out.append("")
        out.append(f"**Scope Item ID:** `{item.scope_id}`  ")
        out.append(f"**Scope Item Name:** {name}")
        out.append("")
        out.append(f"### Process Description{_source_tag(item)}")
        out.append("")
        out.append(_normalize_body(item.process_description))
        out.append("")
        out.append("### Dependencies")
        out.append("")
        out.append(_render_deps_block(item.dependencies))

        if include_process_steps:
            out.append("")
            out.append("### Process Steps")
            out.append("")
            out.append(_render_process_steps(item.process_steps))

        if item.warnings:
            out.append("")
            out.append(f"> _Parser warnings: {'; '.join(item.warnings)}_")
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)
