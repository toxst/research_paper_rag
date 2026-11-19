import streamlit as st
from config import (
    MB,
    MAX_PDF_SIZE,
    MAX_PDF_COUNT,
    MAX_ZIP_SIZE,
    MAX_TOTAL_PDF_BYTES,
    MAX_COMPRESSION_RATIO,
)
from ingestion.upload_handler import process_uploads


UPLOAD_MODES = {
    "Multiple PDFs": "pdfs",
    "Folder": "folder",
    "ZIP archive": "zip",
}


def format_size(size_bytes):
    """Convert bytes to a readable MB value."""
    return f"{size_bytes / MB:g} MB"


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


def display_upload_results(result):
    """Display accepted PDFs and upload errors."""

    for error in result.errors:
        st.error(error)

    if result.skipped:
        with st.expander(
            f"Skipped files ({len(result.skipped)})"
        ):
            for message in result.skipped:
                st.warning(message)

    if not result.papers:
        st.warning("No PDFs were accepted.")
        return

    st.success(
        f"Successfully prepared "
        f"{len(result.papers)} research paper(s)."
    )

    st.subheader("Selected Research Papers")

    rows = []

    for paper in result.papers:
        rows.append(
            {
                "Filename": paper.filename,
                "Relative Path": paper.relative_path,
                "Size (MB)": round(
                    len(paper.content) / MB, 2
                ),
                "SHA-256": paper.content_hash[:12] + "...",
                "Paper ID": paper.paper_id,
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    total_size = sum(
        len(paper.content)
        for paper in result.papers
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Accepted PDFs",
            len(result.papers),
        )

    with col2:
        st.metric(
            "Total PDF Size",
            format_size(total_size),
        )



def main():
    st.set_page_config(
        page_title="Research Paper Assistant",
        page_icon="📚",
        layout="wide",
    )

    st.title("📚 Research Paper Assistant")

    st.write(
        "Upload academic research papers and "
        "explore their content using a "
        "RAG-powered assistant."
    )

    st.divider()

    st.subheader("Upload Research Papers")

    selected_mode = st.radio(
        "Choose an upload method",
        options=list(UPLOAD_MODES.keys()),
        horizontal=True,
    )

    mode = UPLOAD_MODES[selected_mode]

    # Show limits before file selection
    display_upload_limits(mode)

    st.markdown("#### Select Files")

    if mode == "pdfs":
        uploaded_files = st.file_uploader(
            "Choose one or more PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_uploader",
            max_upload_size=MAX_PDF_SIZE // MB,
            help=(
                f"Up to {MAX_PDF_COUNT} PDFs, "
                f"{format_size(MAX_PDF_SIZE)} each."
            ),
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
            help=(
                f"Maximum ZIP size: "
                f"{format_size(MAX_ZIP_SIZE)}."
            ),
        )

        uploaded_files = (
            [uploaded_zip] if uploaded_zip else []
        )

    if uploaded_files:
        st.caption(
            f"{len(uploaded_files)} upload item(s) selected."
        )

        if st.button(
            "Process Upload",
            type="primary",
        ):
            with st.spinner("Processing uploaded files..."):
                result = process_uploads(
                    uploaded_files,
                    mode,
                )

            display_upload_results(result)

    else:
        st.info(
            "Select PDFs, a folder, or a ZIP archive "
            "to get started."
        )


if __name__ == "__main__":
    main()
