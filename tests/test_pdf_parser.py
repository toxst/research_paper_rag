########################################################
#             CODE TO TEST PDF PARSING                 #
########################################################

# Run this file with the command: uv run python -m tests.test_pdf_parser

import hashlib
import re
import uuid
from pathlib import Path

import pymupdf

from ingestion.models import UploadedPaper, ParsedPaper, ParsedPage
from ingestion.pdf_parser import parse_pdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PDF_PATH = (
    PROJECT_ROOT
    / "papers"
    / "Attention Is All You Need.pdf"
)

OUTPUT_DIR = PROJECT_ROOT / "output"

def test_pdf_parser():
    assert PDF_PATH.is_file(), (
        f"Sample PDF not found: {PDF_PATH}. Copy your research paper into papers/."
    )

    pdf_bytes = PDF_PATH.read_bytes()

    paper = UploadedPaper(
        filename=PDF_PATH.name,
        relative_path=PDF_PATH.name,
        content=pdf_bytes,
        content_hash=hashlib.sha256(
            pdf_bytes
        ).hexdigest(),
        paper_id=str(uuid.uuid4()),
    )

    use_fomula_ocr = True

    extracted_pages = parse_pdf(paper, recognise_formulas=use_fomula_ocr)

    assert isinstance(extracted_pages, ParsedPaper)
    assert extracted_pages.paper_id == paper.paper_id
    assert extracted_pages.filename == paper.filename
    assert all(isinstance(page, ParsedPage) for page in extracted_pages.pages)

    with pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    ) as doc:
        assert len(extracted_pages.pages) == doc.page_count

    assert [
        page.page_number
        for page in extracted_pages.pages
    ] == list(range(1, len(extracted_pages.pages) + 1))

    assert any(
        page.text.strip()
        for page in extracted_pages.pages
    ), "No Markdown content extracted."

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = OUTPUT_DIR / (
        f"{PDF_PATH.stem}_extracted.md"
    )

    report_parts = [
        f"# Extraction report: {extracted_pages.filename}",
        "",
        f"**PDF pages:** {len(extracted_pages.pages)}",
        f"**Detected title:** {extracted_pages.metadata.title or 'Not detected'}",
        f"**Authors:** {', '.join(extracted_pages.metadata.authors) or 'Not detected'}"
        "",
    ]

    for page in extracted_pages.pages:
        report_parts.extend([
            "---",
            "",
            f"**PDF Page {page.page_number}**",
            "",
            (page.markdown_with_formulas if use_fomula_ocr else page.text)
            or "*No extractable text on this page.*",
            "",
        ])
        if page.latex_formulas:
            report_parts.extend(["**Unverified formula OCR candidates:**", ""])
            for formula in page.latex_formulas:
                report_parts.extend(["```latex", formula["latex"], "```", ""])

    if extracted_pages.warnings:
        report_parts.extend(["---", "", "## Extraction warnings", ""])
        report_parts.extend(f"- {warning}" for warning in extracted_pages.warnings)
        report_parts.append("")


    report_path.write_text(
        "\n".join(report_parts),
        encoding="utf-8",
    )

    assert report_path.is_file()
    assert report_path.stat().st_size > 0

    heading_count = sum(
        len(re.findall(
            r"(?m)^#{1,6} +\S",
            page.markdown_with_formulas,
        ))
        for page in extracted_pages.pages
    )

    print(f"\nPDF: {PDF_PATH.name}")
    print(f"Pages extracted: {len(extracted_pages.pages)}")
    print(f"Formula candidates: {sum(len(p.latex_formulas) for p in extracted_pages.pages)}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    test_pdf_parser()