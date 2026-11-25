from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class UploadedPaper:
    filename: str
    relative_path: str
    content: bytes
    content_hash: str
    paper_id: str


@dataclass
class UploadResult:
    papers: list[UploadedPaper] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

@dataclass
class ParsedPage:
    page_number: int
    text: str
    latex_formulas: list[dict] = field(default_factory=list)
    markdown_with_formulas: str | None = None

@dataclass
class PaperMetadata:
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    sections: list[str] = field(default_factory=list)

@dataclass
class ParsedPaper:
    paper_id: str
    filename: str
    pages: list[ParsedPage]
    metadata: PaperMetadata
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class R2UploadReceipt:
    """Metadata for an object stored in R2."""
    key: str
    size_bytes: int
    sha256: str
    uploaded: bool  # False means an identical object was already stored.


@dataclass(frozen=True)
class PaperCatalogEntry:
    """Metadata for a paper stored in R2, enabling lookup without knowing the hash."""
    filename: str
    paper_id: str
    content_hash: str  # SHA-256, matches R2 object key
    key: str           # Full R2 object key (papers/xx/hash.pdf)
    size_bytes: int
    uploaded_at: str   # ISO 8601 UTC
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    year: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperCatalogEntry":
        # Handle legacy entries without optional fields
        return cls(
            filename=data["filename"],
            paper_id=data["paper_id"],
            content_hash=data["content_hash"],
            key=data["key"],
            size_bytes=data["size_bytes"],
            uploaded_at=data["uploaded_at"],
            title=data.get("title"),
            authors=data.get("authors"),
            year=data.get("year"),
        )
