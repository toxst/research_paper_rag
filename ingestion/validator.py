import pymupdf

class PDFValidationError(ValueError):
    pass

def validate_pdf(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PDFValidationError("Invalid PDF header.")

    try:
        with pymupdf.open(
            stream=pdf_bytes,
            filetype="pdf",
        ) as doc:

            if doc.needs_pass:
                raise PDFValidationError("Password-protected PDF.")

            if doc.page_count == 0:
                raise PDFValidationError("PDF has no pages.")

            total_chars = 0

            for page in doc:
                text = page.get_text("text")
                total_chars += len(text.strip())

            if total_chars < 100:
                raise PDFValidationError("Insufficient extractable text. The PDF may be scanned or image-only.")

    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError(
            f"Unable to read PDF: {exc}"
        ) from exc
