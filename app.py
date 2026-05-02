"""Streamlit UI for SAP Scope Item Extractor (deployment build).

Differences from local build:
- Input is ZIP upload only (no local folder path — the cloud has no
  filesystem the user can browse).
- Password gate at app entry, reading APP_PASSWORD from st.secrets.
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from docx_parser import extract_scope_item, ScopeItem, Dependency
from markdown_writer import render_inline_template, render_expanded


st.set_page_config(
    page_title="SAP Scope Item Extractor",
    page_icon="📘",
    layout="wide",
)


# ------------------------------------------------------------------
# Password gate
# ------------------------------------------------------------------
def _check_password() -> bool:
    """Block app rendering until the correct password is entered.

    Reads the expected password from Streamlit secrets (st.secrets).
    Set this at https://share.streamlit.io → app settings → Secrets:

        APP_PASSWORD = "your-shared-password"

    If APP_PASSWORD is unset, the gate is skipped (useful for local dev).
    """
    expected = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
    if not expected:
        return True  # No password configured — open access (local dev mode)

    if st.session_state.get("authenticated"):
        return True

    st.title("📘 SAP Scope Item Extractor")
    st.caption("Internal tool for FPT Software EBS.ERP presales.")
    pw = st.text_input("Enter team password", type="password")
    if st.button("Sign in", type="primary"):
        if pw == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.caption(
        "If you don't have the password, contact the tool owner."
    )
    return False


if not _check_password():
    st.stop()


# ------------------------------------------------------------------
# Main app
# ------------------------------------------------------------------
st.title("📘 SAP S/4HANA Cloud Public Edition — Scope Item Extractor")
st.caption(
    "Reads SAP **Test Script (BPD) docx** files and produces a consolidated "
    "Markdown list with **ID**, **Name**, **Process Description**, "
    "**Dependencies**, and optionally **Process Steps** per scope item."
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _resolve_paths(uploaded_zip) -> tuple[list[Path], tempfile.TemporaryDirectory | None]:
    paths: list[Path] = []
    tmp_obj: tempfile.TemporaryDirectory | None = None
    if uploaded_zip is None:
        return paths, tmp_obj

    tmp_obj = tempfile.TemporaryDirectory()
    try:
        with zipfile.ZipFile(uploaded_zip) as zf:
            zf.extractall(tmp_obj.name)
    except zipfile.BadZipFile:
        st.error("That doesn't look like a valid ZIP file.")
        return [], None
    paths = sorted(Path(tmp_obj.name).rglob("*.docx"))
    if not paths:
        st.warning("No `.docx` files found inside the ZIP.")
    return paths, tmp_obj


def _apply_overrides(items: dict[str, ScopeItem], overrides: dict) -> None:
    pd_overrides = overrides.get("process_descriptions", {})
    for sid, txt in pd_overrides.items():
        if sid in items and txt.strip():
            items[sid].process_description = txt.strip()
            items[sid].process_description_source = "manual"

    dep_overrides = overrides.get("dependencies", {})
    for sid, dep_list in dep_overrides.items():
        if sid in items and isinstance(dep_list, list):
            items[sid].dependencies = [
                Dependency(
                    scope_id=d.get("scope_id", "").upper(),
                    name=d.get("name") or None,
                    kind=d.get("kind", "required"),
                    context=d.get("context", "manual override"),
                )
                for d in dep_list
                if d.get("scope_id", "").strip()
            ]


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    output_format = st.radio(
        "Output format",
        options=["Inline (per template)", "Expanded (sub-headings)"],
        index=1,
    )

    include_process_steps = st.checkbox(
        "Include Process Steps table per scope item",
        value=False,
        help=(
            "When enabled, the §3 Overview Table from each Test Script is "
            "rendered as a Markdown table in the output. Page references "
            "like '[page ] 58' are stripped automatically."
        ),
    )

    st.divider()
    st.markdown(
        "**Filename convention:**  \n"
        "`<ScopeID>_S4CLD<release>_BPD_EN_<region>.docx`  \n"
        "e.g. `1B6_S4CLD2602_BPD_EN_DE.docx`  \n"
        "or `1KA_S4CLD2602_BPD_EN_XX.docx`"
    )

    if st.button("Sign out"):
        st.session_state.pop("authenticated", None)
        st.rerun()


# ------------------------------------------------------------------
# Input
# ------------------------------------------------------------------
st.subheader("📝 Upload Test Script ZIP")
st.caption(
    "Upload a single ZIP containing the Test Script `.docx` files. "
    "Files in subfolders are picked up automatically."
)
uploaded = st.file_uploader(
    "ZIP file",
    type=["zip"],
    accept_multiple_files=False,
    label_visibility="collapsed",
)

paths, _tmp = _resolve_paths(uploaded)
if paths:
    st.success(f"{len(paths)} Test Script file(s) found")


# ------------------------------------------------------------------
# Run extraction
# ------------------------------------------------------------------
if paths and st.button("🚀 Extract scope items", type="primary"):
    items_by_id: dict[str, ScopeItem] = {}
    progress = st.progress(0.0, text="Starting…")

    for i, path in enumerate(paths, 1):
        progress.progress(i / len(paths), text=f"{i}/{len(paths)}: {path.name}")
        try:
            item = extract_scope_item(path)
        except Exception as e:
            item = ScopeItem(
                scope_id=path.name.split("_", 1)[0],
                source_filename=path.name,
                warnings=[f"Unhandled error: {e}"],
            )
        items_by_id[item.scope_id] = item

    progress.progress(1.0, text="Done.")
    st.session_state["items"] = items_by_id
    if "overrides" not in st.session_state:
        st.session_state["overrides"] = {
            "process_descriptions": {},
            "dependencies": {},
        }


# ------------------------------------------------------------------
# Display & overrides
# ------------------------------------------------------------------
if "items" in st.session_state:
    items_by_id: dict[str, ScopeItem] = st.session_state["items"]
    overrides = st.session_state.get("overrides", {
        "process_descriptions": {},
        "dependencies": {},
    })

    _apply_overrides(items_by_id, overrides)
    items_list = sorted(items_by_id.values(), key=lambda x: x.scope_id)

    st.divider()
    st.subheader("📊 Extraction summary")

    df = pd.DataFrame([
        {
            "ID": i.scope_id,
            "Name": i.name or "—",
            "ProcDesc": (
                "✏️ manual" if i.process_description_source == "manual"
                else "✓" if i.process_description else "—"
            ),
            "Deps": len(i.dependencies),
            "Dep IDs": ", ".join(d.scope_id for d in i.dependencies) or "—",
            "Steps": sum(1 for s in i.process_steps if not s.group_heading),
            "File": i.source_filename,
            "Warnings": "; ".join(i.warnings) if i.warnings else "",
        }
        for i in items_list
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scope items", len(items_list))
    c2.metric("Names parsed", sum(1 for i in items_list if i.name))
    c3.metric("With Process Description",
              sum(1 for i in items_list if i.process_description))
    c4.metric("Total dependency edges",
              sum(len(i.dependencies) for i in items_list))

    # Export summary as CSV (useful for spot-checking)
    st.download_button(
        "⬇️ Download summary CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="extraction_summary.csv",
        mime="text/csv",
    )

    # --- Manual override editor ---
    st.divider()
    with st.expander("✏️ Manual overrides (optional)", expanded=False):
        st.caption(
            "Use these when the auto-extracted values are missing or "
            "wrong. Overrides take precedence in the final Markdown output. "
            "Export as JSON to persist across runs."
        )

        uploaded_ov = st.file_uploader(
            "Import overrides JSON",
            type=["json"],
            key="ov_upload",
        )
        if uploaded_ov is not None:
            try:
                data = json.load(uploaded_ov)
                st.session_state["overrides"] = {
                    "process_descriptions": data.get("process_descriptions", {}),
                    "dependencies": data.get("dependencies", {}),
                }
                st.success("Imported. Click Save below to apply.")
            except Exception as e:
                st.error(f"Could not parse JSON: {e}")

        st.markdown("#### Process Description overrides")
        new_pd: dict[str, str] = {}
        for item in items_list:
            existing = overrides["process_descriptions"].get(
                item.scope_id, item.process_description or "")
            txt = st.text_area(
                f"**{item.scope_id} – {item.name or '?'}**",
                value=existing,
                height=100,
                key=f"pd_{item.scope_id}",
            )
            if txt.strip() and txt.strip() != (item.process_description or "").strip():
                new_pd[item.scope_id] = txt
            elif txt.strip() and item.process_description_source == "manual":
                new_pd[item.scope_id] = txt

        st.markdown("#### Dependency overrides")
        st.caption(
            "JSON format per scope item. Each dependency is "
            '`{"scope_id": "BD9", "name": "Sell from Stock", "kind": "required"}`. '
            "Leave blank to keep auto-extracted values."
        )
        new_deps: dict[str, list] = {}
        for item in items_list:
            current = overrides["dependencies"].get(
                item.scope_id,
                [
                    {"scope_id": d.scope_id, "name": d.name, "kind": d.kind}
                    for d in item.dependencies
                ],
            )
            txt = st.text_area(
                f"**{item.scope_id}** dependencies (JSON list)",
                value=json.dumps(current, indent=2, ensure_ascii=False)
                      if current else "[]",
                height=130,
                key=f"deps_{item.scope_id}",
            )
            try:
                parsed = json.loads(txt)
                if isinstance(parsed, list):
                    new_deps[item.scope_id] = parsed
            except json.JSONDecodeError:
                st.error(f"Invalid JSON for {item.scope_id}")

        cA, cB = st.columns([1, 4])
        with cA:
            if st.button("💾 Save overrides"):
                st.session_state["overrides"] = {
                    "process_descriptions": new_pd,
                    "dependencies": new_deps,
                }
                st.rerun()
        with cB:
            export_payload = {
                "process_descriptions": new_pd,
                "dependencies": new_deps,
            }
            st.download_button(
                "⬇️ Export overrides JSON",
                data=json.dumps(export_payload, indent=2,
                                ensure_ascii=False).encode("utf-8"),
                file_name="scope_overrides.json",
                mime="application/json",
            )

    # --- Render Markdown ---
    if output_format.startswith("Inline"):
        md = render_inline_template(items_list, include_process_steps=include_process_steps)
    else:
        md = render_expanded(items_list, include_process_steps=include_process_steps)

    st.divider()
    st.subheader("📥 Download")
    st.download_button(
        label="⬇️ Download consolidated Markdown",
        data=md.encode("utf-8"),
        file_name="scope_items.md",
        mime="text/markdown",
        type="primary",
    )

    with st.expander("Preview Markdown output", expanded=False):
        st.markdown(md)

    with st.expander("Inspect raw extraction per scope item", expanded=False):
        for item in items_list:
            st.markdown(f"##### {item.scope_id} — {item.name or '?'}")
            t1, t2, t3 = st.tabs(["Process Description", "Dependencies", "Process Steps"])
            with t1:
                st.text(item.process_description or "(not present)")
                st.caption(f"Source: {item.process_description_source}")
            with t2:
                if item.dependencies:
                    for d in item.dependencies:
                        st.markdown(
                            f"- **{d.scope_id}** "
                            f"{'— ' + d.name if d.name else ''} "
                            f"*({d.kind})*"
                        )
                        st.caption(f"Context: {d.context}")
                else:
                    st.text("(none identified)")
            with t3:
                if item.process_steps:
                    rows = [
                        {
                            "Process Step": (
                                f"📂 {s.process_step}" if s.group_heading
                                else s.process_step
                            ),
                            "Business Role": s.business_role,
                            "Transaction / App": s.transaction_app,
                            "Expected Results": s.expected_results,
                        }
                        for s in item.process_steps
                    ]
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.text("(no Overview Table found)")

elif not paths:
    st.info("👆 Upload a ZIP containing the Test Script `.docx` files to begin.")
