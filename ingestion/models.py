from dataclasses import dataclass, field

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