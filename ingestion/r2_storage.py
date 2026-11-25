from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ingestion.models import UploadedPaper, R2UploadReceipt, PaperCatalogEntry


class R2StorageError(RuntimeError):
    """R2 configuration, upload, or retrieval failed."""
    pass


CATALOG_KEY = "catalog/papers.json"


class R2Storage:
    """Store original PDFs privately using content-addressed R2 object keys.
    
    Maintains a persistent catalog (catalog/papers.json) mapping filenames,
    paper_ids, and hashes to R2 keys for cross-session retrieval.
    """

    def __init__(self, client: Any, bucket: str) -> None:
        if not bucket or not bucket.strip():
            raise R2StorageError("R2 bucket name is missing.")
        self._client = client
        self.bucket = bucket.strip()
        self._catalog: Optional[list[PaperCatalogEntry]] = None
        self._catalog_loaded = False

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> "R2Storage":
        """Create a client from st.secrets or a plain dictionary."""
        required = {
            "R2_ENDPOINT_URL",
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME"
        }

        try:
            values = {name: str(settings[name]).strip() for name in required}
        except KeyError as e:
            raise R2StorageError(f"Missing R2 setting: {e.args[0]}") from e

        for name, value in values.items():
            if not value:
                raise R2StorageError(f"Empty R2 setting: {name}")

        client = boto3.client(
            "s3",
            endpoint_url=values["R2_ENDPOINT_URL"],
            aws_access_key_id=values["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=values["R2_SECRET_ACCESS_KEY"],
            region_name='auto',
            config=Config(
                connect_timeout=10,
                read_timeout=60,
                retries={"mode": "standard", "max_attempts": 3},
                s3={"addressing_style": "path"},
            ),
        )

        return cls(client, values["R2_BUCKET_NAME"])

    @staticmethod
    def object_key(content_hash: str) -> str:
        """Use identical object keys for identical PDF bytes (deduplicates across batches)."""

        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise R2StorageError(f"Invalid SHA-256 content hash.")
        return f"papers/{content_hash[:2]}/{content_hash}.pdf"

    # ==================== Catalog Management ====================

    def _load_catalog(self) -> list[PaperCatalogEntry]:
        """Load catalog from R2, caching in memory."""
        if self._catalog_loaded:
            return self._catalog or []

        try:
            response = self._client.get_object(Bucket=self.bucket, Key=CATALOG_KEY)
            body = response["Body"]
            try:
                data = json.loads(body.read().decode("utf-8"))
            finally:
                body.close()
            self._catalog = [PaperCatalogEntry.from_dict(e) for e in data]
        except ClientError as e:
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            if error_code in ("404", "NoSuchKey", "NotFound"):
                self._catalog = []
            else:
                raise R2StorageError(f"Failed to load catalog from R2.") from e
        except (BotoCoreError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise R2StorageError(f"Failed to load or parse catalog.") from e

        self._catalog_loaded = True
        return self._catalog or []

    def _save_catalog(self, catalog: list[PaperCatalogEntry]) -> None:
        """Persist catalog to R2."""
        data = [e.to_dict() for e in catalog]
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=CATALOG_KEY,
                Body=json.dumps(data, indent=2).encode("utf-8"),
                ContentType="application/json",
            )
        except (BotoCoreError, ClientError) as e:
            raise R2StorageError(f"Failed to save catalog to R2.") from e
        self._catalog = catalog

    def _upsert_catalog_entry(self, entry: PaperCatalogEntry) -> None:
        """Add or update a single entry in the catalog."""
        catalog = self._load_catalog()
        # Replace existing entry with same content_hash (dedup by content)
        catalog = [e for e in catalog if e.content_hash != entry.content_hash]
        catalog.append(entry)
        # Sort by upload time descending (newest first)
        catalog.sort(key=lambda e: e.uploaded_at, reverse=True)
        self._save_catalog(catalog)

    # ==================== Public Catalog API ====================

    def list_papers(self) -> list[PaperCatalogEntry]:
        """Return all papers in the catalog, newest first."""
        return self._load_catalog()

    def get_by_filename(self, filename: str) -> Optional[PaperCatalogEntry]:
        """Find a paper by exact filename match."""
        catalog = self._load_catalog()
        for entry in catalog:
            if entry.filename == filename:
                return entry
        return None

    def get_by_paper_id(self, paper_id: str) -> Optional[PaperCatalogEntry]:
        """Find a paper by paper_id."""
        catalog = self._load_catalog()
        for entry in catalog:
            if entry.paper_id == paper_id:
                return entry
        return None

    def get_by_hash(self, content_hash: str) -> Optional[PaperCatalogEntry]:
        """Find a paper by SHA-256 content hash."""
        catalog = self._load_catalog()
        for entry in catalog:
            if entry.content_hash == content_hash:
                return entry
        return None

    def search(self, query: str) -> list[PaperCatalogEntry]:
        """Search papers by filename, title, or author (case-insensitive substring)."""
        query_lower = query.lower()
        catalog = self._load_catalog()
        results = [
            paper
            for paper in catalog
            if not query_lower
            or query_lower in paper.filename.lower()
            or (paper.title and query_lower in paper.title.lower())
            or (
                paper.authors
                and any(query_lower in author.lower() for author in paper.authors)
            )
        ]
        return results

    def download_pdf_by_filename(self, filename: str) -> bytes:
        """Download a PDF by filename (looks up key in catalog)."""
        entry = self.get_by_filename(filename)
        if not entry:
            raise R2StorageError(f"Paper not found in catalog: {filename}")
        return self.download_pdf(entry.key)

    def download_pdf_by_paper_id(self, paper_id: str) -> bytes:
        """Download a PDF by paper_id (looks up key in catalog)."""
        entry = self.get_by_paper_id(paper_id)
        if not entry:
            raise R2StorageError(f"Paper not found in catalog: {paper_id}")
        return self.download_pdf(entry.key)

    def download_pdf_by_hash(self, content_hash: str) -> bytes:
        """Download a PDF by content hash (looks up key in catalog)."""
        entry = self.get_by_hash(content_hash)
        if not entry:
            # Fall back to direct key construction (for papers uploaded before catalog)
            key = self.object_key(content_hash)
            return self.download_pdf(key)
        return self.download_pdf(entry.key)

    # ==================== Upload with Catalog ====================

    def upload_pdf(self, paper: UploadedPaper, metadata: Optional[dict] = None) -> R2UploadReceipt:
        """Upload a PDF from memory, or reuse an already-matching R2 object.
        
        Updates the persistent catalog with paper metadata for future lookup.
        """
        actual_hash = hashlib.sha256(paper.content).hexdigest()
        if actual_hash != paper.content_hash:
            raise R2StorageError(f"SHA-256 mismatch in uploaded paper: {paper.filename}")

        key = self.object_key(paper.content_hash)
        size = len(paper.content)

        # Check if the paper has been stored before
        try:
            existing = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            error_code = str(e.response.get("Error", {}).get("Code", ""))
            if error_code not in ("404", "NoSuchKey", "NotFound"):
                raise R2StorageError(f"Failed to check whether {paper.filename} is already in R2.") from e
        except BotoCoreError as e:
            raise R2StorageError("Unable to connect to R2.") from e
        else:
            if (
                existing.get("ContentLength") == size
                and existing.get("Metadata", {}).get("sha256") == actual_hash
            ):
                # Ensure catalog has an entry (may have been uploaded before catalog existed)
                self._ensure_catalog_entry(paper, actual_hash, key, size, metadata, uploaded=False)
                return R2UploadReceipt(key, size, actual_hash, uploaded=False)
            raise R2StorageError(
                f"An existing R2 object has mismatched metadata: {key}"
            )

        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=paper.content,
                ContentType="application/pdf",
                Metadata={"sha256": actual_hash}
            )
            stored = self._client.head_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as e:
            raise R2StorageError(f"Upload or verification failed for {paper.filename}.") from e

        if (
            stored.get("ContentLength") != size
            or stored.get("Metadata", {}).get("sha256") != actual_hash
        ):
            raise R2StorageError(
                f"R2 upload metadata verification failed for {paper.filename}."
            )

        # Update catalog with new entry
        self._ensure_catalog_entry(paper, actual_hash, key, size, metadata, uploaded=True)
        return R2UploadReceipt(key, size, actual_hash, uploaded=True)

    def _ensure_catalog_entry(
        self,
        paper: UploadedPaper,
        content_hash: str,
        key: str,
        size: int,
        metadata: Optional[dict],
        uploaded: bool
    ) -> None:
        """Create or update catalog entry for this paper."""
        # Extract optional metadata from paper or provided dict
        title = None
        authors = None
        year = None
        if metadata:
            title = metadata.get("title")
            authors = metadata.get("authors")
            year = metadata.get("year")

        entry = PaperCatalogEntry(
            filename=paper.filename,
            paper_id=paper.paper_id,
            content_hash=content_hash,
            key=key,
            size_bytes=size,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            title=title,
            authors=authors,
            year=year,
        )
        self._upsert_catalog_entry(entry)

    # ==================== Direct Download (unchanged) ====================

    def download_pdf(self, key: str) -> bytes:
        """Retrieve an original PDF and verify its SHA-256 against its object key."""

        match = re.fullmatch(r"papers/([0-9a-f]{2})/([0-9a-f]{64})\.pdf", key)
        if not match or match.group(1) != match.group(2)[:2]:
            raise R2StorageError("Invalid PDF object key.")

        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                content = body.read()
            finally:
                body.close()
        except (BotoCoreError, ClientError, OSError) as exc:
            raise R2StorageError(f"Unable to retrieve PDF from R2: {key}") from exc

        if hashlib.sha256(content).hexdigest() != match.group(2):
            raise R2StorageError(f"Downloaded PDF failed SHA-256 check: {key}")
        return content