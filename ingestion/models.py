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