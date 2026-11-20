import pymupdf
import pymupdf4llm
import re
from typing import Any

from ingestion.models import UploadedPaper, PaperMetadata, ParsedPage, ParsedPaper
from ingestion.validator import validate_pdf


def _recognise_formula(page: pymupdf.Page, bbox: Any, recogniser: Any) -> str | None:
    """Run pix2tex on a cropped formula bounding box (PyMuPDF points)."""

    from PIL import Image

    clip = pymupdf.Rect(bbox) & page.rect
    if clip.is_empty or clip.width <= 1 or clip.height <= 1:
        return None

    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(2, 2),
        clip=clip,
        colorspace=pymupdf.csRGB,
        alpha=False
    )

    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    latex = recogniser(image)
    return latex.strip() if isinstance(latex, str) and latex.strip() else None

def _extract_metadata(embedded: dict, pages: list[ParsedPage]) -> PaperMetadata:
    """Conservative, best-effort metadata extraction; no guessed publication year."""

    title = (embedded.get("title") or "").strip()
    if title.lower() in ("", "untitled", "unknown"):
        title = ""

    headings = []
    for page in pages:
        headings.extend(
            match.strip()
            for match in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", page.text)
        )

    if not title:
        title = next(
            (h for h in headings if h.lower() not in ("äbstract", "introduction")),
            ""
        )

    sections = []
    for h in headings:
        if h.lower() not in ("abstract", title.lower()) and h not in sections:
            sections.append(h)

    author_field = (embedded.get("author") or "").strip()

    authors = [a.strip() for a in re.split(r";|\band\b", author_field) if a.strip()]

    abstract = None
    for page in pages[:2]:
        match = re.search(
             r"(?ims)^#{1,6}\s+Abstract\s*\n(.*?)(?=^#{1,6}\s+|\Z)",
             page.text
        )

        if match:
            abstract = match.group(1).strip() or None
            break

    return PaperMetadata(
        title=title or None,
        authors=authors,
        year=None,
        abstract=abstract,
        sections=sections
    )


def parse_pdf(paper: UploadedPaper, recognise_formulas: bool=True) -> ParsedPaper:
    """Validate and extract page-aware Markdown from a PDF.
    """

    validate_pdf(paper.content)

    pages: list[ParsedPage] = []
    warnings: list[str] = []
    recogniser = None
    detected_formulas = 0

    with pymupdf.open(
        stream=paper.content,
        filetype='pdf'
    ) as doc:
        embedded = dict(doc.metadata or {})
        extracted_pages = pymupdf4llm.to_markdown(
            doc,
            page_chunks=True,
            use_ocr=False,
            write_images=False,
            embed_images=False,
            ignore_images=True,
            force_text=True
        )

        if len(extracted_pages) != doc.page_count:
            raise ValueError("Extracted page count does not match the original PDF.")

        for page_data in extracted_pages:
            page_number = int(page_data["metadata"]['page_number'])
            raw_md = page_data['text']
            formulas: list[dict] = []
            replacements: list[tuple[int, int, str]] = []

            if not raw_md.strip():
                warnings.append(f"PDF page {page_number} has no extracted text.")

            if recognise_formulas:
                formula_boxes = [
                    box for box in (page_data.get("page_boxes") or [])
                    if str(box.get("class", "")).lower() == "formula"
                ]
                detected_formulas += len(formula_boxes)

                if formula_boxes and recogniser is None:
                    try:
                        from pix2tex.cli import LatexOCR
                    except ImportError as exc:
                        raise RuntimeError("Formula OCR needs `uv add pix2tex pillow`.") from exc

                    recogniser = LatexOCR()

                for box in formula_boxes:
                    bbox = box.get('bbox')
                    if bbox is None:
                        warnings.append(f"Page {page_number}: formula has no bounding box.")
                        continue
                    try:
                        latex = _recognise_formula(doc[page_number - 1], bbox, recogniser)
                    except Exception as exc:
                        warnings.append(
                            f"Page {page_number}: formula recognition failed: {type(exc).__name__}."
                        )
                        continue

                    if not latex:
                        continue

                    formulas.append({
                        "latex": latex,
                        "page_number": page_number,
                        "bbox": list(bbox),
                        "verified": False
                    })

                    pos = box.get("pos")
                    if pos is not None and len(pos) == 2:
                        start, end = map(int, pos)
                        if 0 <= start <= end <= len(raw_md):
                            replacements.append((start, end, latex))

            preview_md = raw_md
            for start, end, latex in sorted(replacements, reverse=True):
                preview_md = (
                    preview_md[:start]
                    + f"\n\n$$\n{latex}\n$$\n\n"
                    + preview_md[end:]
                )

            pages.append(ParsedPage(
                page_number=page_number,
                text=raw_md.strip(),
                latex_formulas=formulas,
                markdown_with_formulas=preview_md.strip() if recognise_formulas else None
            ))

        if not any(page.text for page in pages):
            raise ValueError("No Markdown content was extracted.")

        if recognise_formulas and detected_formulas == 0:
            warnings.append("No formula regions detected; inline or unclassified equations may be missed.")

        return ParsedPaper(
            paper_id=paper.paper_id,
            filename=paper.filename,
            pages=pages,
            metadata=_extract_metadata(embedded, pages),
            warnings=warnings
        )