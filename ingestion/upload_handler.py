
import hashlib
import re
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import BinaryIO, Literal

from config import (
    MAX_ZIP_SIZE,
    MAX_TOTAL_PDF_BYTES,
    MAX_PDF_SIZE,
    MAX_PDF_COUNT,
    MAX_COMPRESSION_RATIO,
    MAX_ZIP_ENTRIES,
)
from ingestion.models import UploadedPaper, UploadResult


UploadMode = Literal["pdfs", "folder", "zip"]


def normalise_path(raw_path: str) -> str:
    """Validate and normalise an uploaded relative path."""
    path_string = raw_path.replace("\\", "/")
    path = PurePosixPath(path_string)

    if (
        not path_string
        or path_string.startswith("/")
        or re.match(r"^[A-Za-z]:", path_string)
        or "\x00" in path_string
        or any(part == ".." for part in path_string.split("/"))
        or not path.name
        or ":" in path_string
    ):
        raise ValueError("Unsafe or invalid relative path")

    # Remove redundant '.' and repeated '/' components.
    return path.as_posix()


def create_uploaded_paper(
    relative_path: str,
    pdf_bytes: bytes,
) -> UploadedPaper:
    """Construct an UploadedPaper from validated bytes."""
    safe_path = normalise_path(relative_path)

    return UploadedPaper(
        filename=PurePosixPath(safe_path).name,
        relative_path=safe_path,
        content=pdf_bytes,
        content_hash=hashlib.sha256(
            pdf_bytes
        ).hexdigest(),
        paper_id=str(uuid.uuid4()),
    )


def check_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
) -> None:
    """Perform basic checks before full PDF validation."""
    if not pdf_bytes:
        raise ValueError(f"{filename}: file is empty")

    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise ValueError(
            f"{filename}: exceeds the 25 MB PDF limit"
        )

    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError(
            f"{filename}: invalid PDF header"
        )


def add_paper(
    result: UploadResult,
    relative_path: str,
    pdf_bytes: bytes,
    seen_paths: set[str],
    seen_hashes: dict[str, str],
    total_bytes: int,
) -> int:
    """Validate and add one PDF to the upload result."""
    safe_path = normalise_path(relative_path)

    if safe_path in seen_paths:
        result.skipped.append(
            f"{safe_path}: duplicate relative path"
        )
        return total_bytes

    check_pdf_bytes(pdf_bytes, safe_path)

    content_hash = hashlib.sha256(
        pdf_bytes
    ).hexdigest()

    if content_hash in seen_hashes:
        original_paper = seen_hashes[content_hash]

        result.skipped.append(
            f"{safe_path}: skipped because its content "
            f"is identical to {original_paper} "
            f"(already accepted)."
        )
        return total_bytes

    if len(result.papers) >= MAX_PDF_COUNT:
        raise ValueError("Maximum of 50 PDFs reached")

    if total_bytes + len(pdf_bytes) > MAX_TOTAL_PDF_BYTES:
        raise ValueError(
            "Total PDF size exceeds 250 MB"
        )

    paper = create_uploaded_paper(
        safe_path, pdf_bytes
    )

    result.papers.append(paper)
    seen_paths.add(safe_path)
    seen_hashes[content_hash] = safe_path

    return total_bytes + len(pdf_bytes)


def process_pdf_files(
    uploaded_files: list[BinaryIO],
    preserve_paths: bool = False,
) -> UploadResult:
    """Process individual PDFs or folder uploads."""
    result = UploadResult()

    seen_paths = set()
    seen_hashes: dict[str, str] = {}
    total_bytes = 0

    if len(uploaded_files) > MAX_PDF_COUNT:
        result.errors.append(
            "Too many files selected. Maximum is 50."
        )
        return result

    for uploaded_file in uploaded_files:
        raw_name = uploaded_file.name

        try:
            # Single-file selections don't need a directory.
            relative_path = (
                raw_name
                if preserve_paths
                else PurePosixPath(
                    raw_name.replace("\\", "/")
                ).name
            )

            safe_path = normalise_path(relative_path)

            if not safe_path.lower().endswith(".pdf"):
                result.skipped.append(
                    f"{safe_path}: not a PDF"
                )
                continue

            # Check declared upload size before reading.
            file_size = getattr(
                uploaded_file, "size", None
            )

            if (
                file_size is not None
                and file_size > MAX_PDF_SIZE
            ):
                raise ValueError(
                    f"{safe_path}: exceeds 25 MB"
                )

            # Bound the bytes read from the file.
            uploaded_file.seek(0)
            pdf_bytes = uploaded_file.read(
                MAX_PDF_SIZE + 1
            )

            total_bytes = add_paper(
                result,
                safe_path,
                pdf_bytes,
                seen_paths,
                seen_hashes,
                total_bytes,
            )

        except (ValueError, OSError) as exc:
            result.errors.append(
                f"{raw_name}: {exc}"
            )

    return result


def process_zip_file(
    uploaded_zip: BinaryIO,
) -> UploadResult:
    """Read PDFs from a ZIP with size and path checks."""
    result = UploadResult()

    seen_paths = set()
    seen_hashes = set()
    total_bytes = 0

    if uploaded_zip.size > MAX_ZIP_SIZE:
        result.errors.append(
            "ZIP archive exceeds 100 MB."
        )
        return result

    try:
        uploaded_zip.seek(0)

        with zipfile.ZipFile(uploaded_zip) as archive:
            members = archive.infolist()

            if len(members) > MAX_ZIP_ENTRIES:
                result.errors.append(
                    "ZIP archive contains too many entries."
                )
                return result

            pdf_members = []

            for member in members:
                if member.is_dir():
                    continue

                try:
                    path = normalise_path(
                        member.filename
                    )
                except ValueError:
                    result.errors.append(
                        "ZIP contains an unsafe path."
                    )
                    return result

                if (
                    "__MACOSX" in PurePosixPath(path).parts
                    or PurePosixPath(path).name.startswith(".")
                ):
                    continue

                if not path.lower().endswith(".pdf"):
                    continue

                # Reject symlinks encoded in ZIP metadata.
                file_type = (
                    member.external_attr >> 16
                ) & 0o170000

                if file_type == 0o120000:
                    result.errors.append(
                        f"{path}: symbolic links are unsupported"
                    )
                    return result

                if member.flag_bits & 0x1:
                    result.errors.append(
                        f"{path}: encrypted ZIP entries "
                        "are unsupported"
                    )
                    return result

                if member.file_size > MAX_PDF_SIZE:
                    result.errors.append(
                        f"{path}: PDF exceeds 25 MB"
                    )
                    return result

                ratio = (
                    member.file_size
                    / max(member.compress_size, 1)
                )

                if ratio > MAX_COMPRESSION_RATIO:
                    result.errors.append(
                        f"{path}: suspicious compression ratio"
                    )
                    return result

                pdf_members.append((member, path))

            if len(pdf_members) > MAX_PDF_COUNT:
                result.errors.append(
                    "ZIP contains more than 50 PDFs."
                )
                return result

            declared_total = sum(
                member.file_size
                for member, _ in pdf_members
            )

            if declared_total > MAX_TOTAL_PDF_BYTES:
                result.errors.append(
                    "Uncompressed PDFs exceed 250 MB."
                )
                return result

            for member, path in pdf_members:
                try:
                    # Read at most the per-PDF limit plus
                    # one byte, even if ZIP metadata is wrong.
                    with archive.open(member) as source:
                        pdf_bytes = source.read(
                            MAX_PDF_SIZE + 1
                        )

                    total_bytes = add_paper(
                        result,
                        path,
                        pdf_bytes,
                        seen_paths,
                        seen_hashes,
                        total_bytes,
                    )

                except (
                    ValueError,
                    RuntimeError,
                    OSError,
                    EOFError,
                    zipfile.BadZipFile,
                ) as exc:
                    result.errors.append(
                        f"{path}: {exc}"
                    )

    except (
        zipfile.BadZipFile,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        result.errors.append(
            f"Could not read ZIP archive: {exc}"
        )

    return result


def process_uploads(
    uploaded_files: list[BinaryIO],
    mode: UploadMode,
) -> UploadResult:
    """Single entry point for all supported upload modes."""
    if not uploaded_files:
        return UploadResult()

    if mode == "pdfs":
        return process_pdf_files(
            uploaded_files,
            preserve_paths=False,
        )

    if mode == "folder":
        return process_pdf_files(
            uploaded_files,
            preserve_paths=True,
        )

    if mode == "zip":
        if len(uploaded_files) != 1:
            return UploadResult(
                errors=["Select exactly one ZIP archive."]
            )

        return process_zip_file(uploaded_files[0])

    raise ValueError(f"Unsupported upload mode: {mode}")
