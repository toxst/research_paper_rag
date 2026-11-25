from __future__ import annotations
import streamlit as st
import hashlib
from config import (
    MB,
    MAX_PDF_SIZE,
    MAX_PDF_COUNT,
    MAX_ZIP_SIZE,
    MAX_TOTAL_PDF_BYTES,
    MAX_COMPRESSION_RATIO,
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_ENDPOINT_URL,
)
from ingestion.upload_handler import process_uploads
from ingestion.pdf_parser import parse_pdf
from ingestion.r2_storage import R2Storage, R2StorageError


UPLOAD_MODES = {
    "Multiple PDFs": "pdfs",
    "Folder": "folder",
    "ZIP archive": "zip",
}

@st.cache_resource
def get_r2_storage() -> R2Storage:
    """Reuse the R2 client until the user explicitly refreshes the catalog."""

    settings = {
        "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
        "R2_BUCKET_NAME": R2_BUCKET_NAME,
        "R2_ENDPOINT_URL": R2_ENDPOINT_URL,
    }

    return R2Storage.from_settings(settings)

def refresh_r2_catalog() -> None:
    """Drop the R2 in-memory catalog, then reload the page with fresh data."""
    st.session_state.pop("r2_prepared_downloads", None)
    st.session_state['r2_catalog_revision'] = (
        st.session_state.get("r2_catalog_revision", 0) + 1
    )

    get_r2_storage.clear()
    st.rerun()


def format_size(size_bytes):
    """Convert bytes to a readable MB value."""
    return f"{size_bytes / MB:g} MB"

def safe_download_filename(filename: str) -> str:
    """Use the basename for downloaded files, even for folder uploads."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1] or "paper.pdf"


def display_upload_limits(mode):
    """Show upload restrictions for the selected mode."""

    st.markdown("#### Upload Limits")

    if mode == "pdfs":
        st.info(
            f"📄 **Maximum PDFs:** {MAX_PDF_COUNT}\n\n"
            f"📦 **Maximum size per PDF:** "
            f"{format_size(MAX_PDF_SIZE)}\n\n"
            f"💾 **Maximum total PDF size:** "
            f"{format_size(MAX_TOTAL_PDF_BYTES)}"
        )

    elif mode == "folder":
        st.info(
            f"📁 **Maximum PDFs per folder upload:** "
            f"{MAX_PDF_COUNT}\n\n"
            f"📦 **Maximum size per PDF:** "
            f"{format_size(MAX_PDF_SIZE)}\n\n"
            f"💾 **Maximum total PDF size:** "
            f"{format_size(MAX_TOTAL_PDF_BYTES)}\n\n"
            "📂 **Nested subfolders:** Supported"
        )

    elif mode == "zip":
        st.info(
            f"🗜️ **Maximum ZIP size:** "
            f"{format_size(MAX_ZIP_SIZE)}\n\n"
            f"📄 **Maximum PDFs:** {MAX_PDF_COUNT}\n\n"
            f"📦 **Maximum size per PDF:** "
            f"{format_size(MAX_PDF_SIZE)}\n\n"
            f"💾 **Maximum total extracted PDF size:** "
            f"{format_size(MAX_TOTAL_PDF_BYTES)}\n\n"
            f"📊 **Maximum compression ratio:** "
            f"{MAX_COMPRESSION_RATIO}:1"
        )


def display_upload_results(report: dict) -> None:
    """Display the latest upload report across Streamlit reruns."""

    for error in report['errors']:
        st.error(error)

    if report["skipped"]:
        with st.expander(f"Skipped files ({len(report['skipped'])})"):
            for message in report["skipped"]:
                st.warning(message)

    if not report["accepted_rows"]:
        st.warning("No PDFs were accepted.")
        return

    st.success(f"Prepared {len(report['accepted_rows'])} research paper(s).")
    st.subheader("Selected Research Papers")
    st.dataframe(
        report["accepted_rows"],
        use_container_width=True,
        hide_index=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Accepted PDFs", len(report["accepted_rows"]))
    with col2:
        st.metric("Total PDF Size", format_size(report["accepted_size"]))

    for error in report["parse_errors"]:
        st.warning(error)
    for error in report["storage_errors"]:
        st.error(error)

    if report["receipts"]:
        st.subheader("R2 Storage")
        st.dataframe(
            report["receipts"], use_container_width=True, hide_index=True
        )
        deduplicated = sum(
            receipt["deduplicated"] for receipt in report["receipts"]
        )
        st.caption(
            f"New uploads: {len(report['receipts']) - deduplicated} | "
            f"Deduplicated: {deduplicated}"
        )

    if report["parsed_entries"]:
        st.divider()
        st.subheader("Parsed Paper Content")
        receipts_by_hash = {
            receipt["content_hash"]: receipt for receipt in report["receipts"]
        }
        for entry in report["parsed_entries"]:
            display_parsed_paper(
                entry["parsed"], receipts_by_hash.get(entry["content_hash"])
            )


def display_r2_catalog(r2: R2Storage):
    """Show the R2 catalog with search, row selection, and real downloads."""
    st.subheader("📚 Papers in R2 Storage")

    if st.button("🔄 Refresh", key="refresh_r2_catalog"):
        refresh_r2_catalog()
    
    try:
        all_papers = r2.list_papers()
    except R2StorageError as e:
        st.error(f"Failed to load the R2 catalog: {e}")
        return
    
    if not all_papers:
        st.info("No papers stored in R2 catalog. Upload some PDFs to get started. PDFs added directly to the bucket will need to be added to the catalog.")
        return
    
    # Summary metrics
    total_size = sum(p.size_bytes for p in all_papers)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Papers", len(all_papers))
    with col2:
        st.metric("Total Size", format_size(total_size))
    with col3:
        st.metric("Bucket", R2_BUCKET_NAME)
    
    # Search/filter
    query = st.text_input("🔍 Search papers", placeholder="Filter by filename, title, or author...", key="r2_catalog_search").strip()

    papers = r2.search(query)

    if not papers:
        st.info("No papers match your search.")
        st.session_state.pop("r2_prepared_downloads", None)
        return
    
    # Display table
    rows = []
    for p in papers:
        rows.append({
            "Filename": p.filename,
            "Title": p.title or "—",
            "Authors": ", ".join(p.authors) if p.authors else "—",
            "Year": p.year or "—",
            "Size (MB)": round(p.size_bytes / MB, 2),
            "Uploaded": p.uploaded_at[:10],  # Date only
            "Paper ID": p.paper_id[:8] + "...",
            "SHA-256": p.content_hash[:12] + "...",
        })

    query_id = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:12]
    revision = st.session_state.get("r2_catalog_revision", 0)
    
    selection = st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"r2_catalog_table_{revision}_{query_id}"
    )

    selected_indices = selection.selection.rows
    selected_papers = [
        papers[index]
        for index in selected_indices
        if 0 <= index < len(papers)
    ]
    selected_hashes = tuple(paper.content_hash for paper in selected_papers)

    prepared = st.session_state.get("r2_prepared_downloads")
    if prepared and prepared['hashes'] != selected_hashes:
        st.session_state.pop("r2_prepared_downloads", None)
        prepared = None

    st.markdown(f"**{len(selected_papers)} paper(s) selected**")

    if st.button("📥 Prepare Downloads", key="prepare_r2_downloads"):
        downloaded = {}
        with st.spinner("Downloading and verifying PDFs from R2..."):
            for paper in selected_papers:
                try:
                    # download_pdf() verifies content against the key's SHA-256.
                    downloaded[paper.content_hash] = r2.download_pdf(paper.key)
                except R2StorageError as exc:
                    st.error(f"Could not retrieve {paper.filename}: {exc}")

        prepared = {"hashes": selected_hashes, "files": downloaded}
        st.session_state["r2_prepared_downloads"] = prepared

    if prepared:
        for paper in selected_papers:
            content = prepared["files"].get(paper.content_hash)
            if content is not None:
                st.download_button(
                    label=f"Save {paper.filename}",
                    data=content,
                    file_name=safe_download_filename(paper.filename),
                    mime="application/pdf",
                    key=f"r2_save_{paper.content_hash}",
                    on_click="ignore",  # Do not rerun and hide download buttons.
                )

    with st.expander("View selected R2 object keys"):
        for paper in selected_papers:
            st.code(paper.key, language=None)


def process_and_store_uploads(uploaded_files, mode: str, recognise_formulas: bool, r2: R2Storage) -> None:
    """Validate, parse once, and store PDFs with extracted metadata in R2."""
    with st.spinner("Validating uploaded files..."):
        result = process_uploads(uploaded_files, mode)

    report = {
        "errors": list(result.errors),
        "skipped": list(result.skipped),
        "accepted_rows": [],
        "accepted_size": 0,
        "parse_errors": [],
        "storage_errors": [],
        "parsed_entries": [],
        "receipts": [],
    }

    for paper in result.papers:
        report["accepted_rows"].append(
            {
                "Filename": paper.filename,
                "Relative Path": paper.relative_path,
                "Size (MB)": round(len(paper.content) / MB, 2),
                "SHA-256": paper.content_hash[:12] + "...",
                "Paper ID": paper.paper_id,
            }
        )
        report["accepted_size"] += len(paper.content)

    if result.papers:
        progress = st.progress(0)
        status = st.empty()
        for index, paper in enumerate(result.papers, start=1):
            status.text(f"Processing {paper.filename} ({index}/{len(result.papers)})")

            metadata = None
            try:
                parsed = parse_pdf(
                    paper, recognise_formulas=recognise_formulas
                )
                report["parsed_entries"].append(
                    {"content_hash": paper.content_hash, "parsed": parsed}
                )
                metadata = {
                    "title": parsed.metadata.title,
                    "authors": parsed.metadata.authors,
                    "year": parsed.metadata.year,
                }
            except Exception as exc:
                # A parsing failure should not prevent preservation of the
                # original PDF, even when formula recognition is unavailable.
                report["parse_errors"].append(
                    f"Could not parse {paper.filename}: {exc}"
                )

            try:
                receipt = r2.upload_pdf(paper, metadata=metadata)
                report["receipts"].append(
                    {
                        "filename": paper.filename,
                        "content_hash": paper.content_hash,
                        "key": receipt.key,
                        "size_mb": round(receipt.size_bytes / MB, 2),
                        "sha256": receipt.sha256[:12] + "...",
                        "deduplicated": not receipt.uploaded,
                    }
                )
            except R2StorageError as exc:
                report["storage_errors"].append(
                    f"R2 upload failed for {paper.filename}: {exc}"
                )

            progress.progress(index / len(result.papers))

        progress.empty()
        status.empty()

    # Keep summaries and parsed data, not the raw UploadedPaper bytes.
    st.session_state["last_upload_report"] = report
    st.session_state["parsed_papers"] = [
        entry["parsed"] for entry in report["parsed_entries"]
    ]
    st.session_state["r2_receipts"] = report["receipts"]

    # The R2 catalog is drawn above the uploader. Reload so new papers appear
    # there immediately without needing a second manual refresh.
    if report["receipts"]:
        refresh_r2_catalog()


def display_parsed_paper(parsed, receipt: dict | None = None) -> None:
    """Show parsed metadata, text, formulas, and the optional R2 receipt."""
    with st.expander(f"📄 {parsed.filename}", expanded=False):
        meta = parsed.metadata
        col1, col2 = st.columns([3, 1])
        with col1:
            if meta.title:
                st.markdown(f"**Title:** {meta.title}")
            if meta.authors:
                st.markdown(f"**Authors:** {', '.join(meta.authors)}")
            if meta.year:
                st.markdown(f"**Year:** {meta.year}")
            if meta.sections:
                st.markdown(f"**Sections:** {', '.join(meta.sections)}")
        with col2:
            st.metric("Pages", len(parsed.pages))
            st.metric(
                "Formulas", sum(len(page.latex_formulas) for page in parsed.pages)
            )

        if meta.abstract:
            with st.expander("Abstract", expanded=False):
                st.markdown(meta.abstract)

        for warning in parsed.warnings:
            st.warning(warning)

        if receipt:
            with st.expander("📦 R2 Storage", expanded=False):
                st.code(receipt["key"], language=None)
                upload_status = (
                    "Deduplicated" if receipt["deduplicated"] else "New upload"
                )
                st.caption(
                    f"Size: {receipt['size_mb']} MB | "
                    f"SHA-256: {receipt['sha256']} | {upload_status}"
                )
                st.caption("Download the original PDF from the R2 library above.")

        if parsed.pages:
            tabs = st.tabs([f"Page {page.page_number}" for page in parsed.pages])
            for tab, page in zip(tabs, parsed.pages):
                with tab:
                    content = page.markdown_with_formulas or page.text
                    if content:
                        st.markdown(content)
                    else:
                        st.info("No extractable text found on this page.")

                    if page.latex_formulas:
                        st.markdown("**Detected Formulas:**")
                        for formula in page.latex_formulas:
                            formula_col, latex_col = st.columns([1, 4])
                            with formula_col:
                                st.caption(f"Page {formula['page_number']}")
                            with latex_col:
                                st.latex(formula["latex"])
                                if formula.get("bbox"):
                                    st.caption(f"BBox: {formula['bbox']}")


def main() -> None:
    st.set_page_config(
        page_title="Research Paper Assistant", page_icon="📚", layout="wide"
    )
    st.title("📚 Research Paper Assistant")
    st.write(
        "Upload academic research papers and explore their content "
        "using a RAG-powered assistant."
    )
    st.divider()

    try:
        r2 = get_r2_storage()
    except R2StorageError as exc:
        st.error(f"Could not connect to R2: {exc}")
        st.stop()

    display_r2_catalog(r2)
    st.divider()
    st.subheader("Upload Research Papers")

    selected_mode = st.radio(
        "Choose an upload method",
        options=list(UPLOAD_MODES.keys()),
        horizontal=True,
    )
    mode = UPLOAD_MODES[selected_mode]
    display_upload_limits(mode)
    st.markdown("#### Select Files")

    if mode == "pdfs":
        uploaded_files = st.file_uploader(
            "Choose one or more PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_uploader",
            max_upload_size=MAX_PDF_SIZE // MB,
            help=f"Up to {MAX_PDF_COUNT} PDFs, {format_size(MAX_PDF_SIZE)} each.",
        )
    elif mode == "folder":
        uploaded_files = st.file_uploader(
            "Choose a folder containing PDFs",
            type=["pdf"],
            accept_multiple_files="directory",
            key="folder_uploader",
            max_upload_size=MAX_PDF_SIZE // MB,
            help=(
                "Nested subfolders are supported. "
                f"Maximum {MAX_PDF_COUNT} PDFs."
            ),
        )
    else:
        uploaded_zip = st.file_uploader(
            "Choose a ZIP archive",
            type=["zip"],
            accept_multiple_files=False,
            key="zip_uploader",
            max_upload_size=MAX_ZIP_SIZE // MB,
            help=f"Maximum ZIP size: {format_size(MAX_ZIP_SIZE)}.",
        )
        uploaded_files = [uploaded_zip] if uploaded_zip else []

    if uploaded_files:
        st.caption(f"{len(uploaded_files)} upload item(s) selected.")
        recognise_formulas = st.checkbox(
            "Recognise formulas (requires pix2tex)",
            value=True,
            help=(
                "Extract LaTeX from formula regions using OCR. "
                "Slower but captures equations."
            ),
        )
        if st.button("Process Upload", type="primary"):
            process_and_store_uploads(uploaded_files, mode, recognise_formulas, r2)
    else:
        st.info("Select PDFs, a folder, or a ZIP archive to get started.")

    last_report = st.session_state.get("last_upload_report")
    if last_report is not None:
        st.divider()
        display_upload_results(last_report)


if __name__ == "__main__":
    main()