import json
import threading
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.schemas import DocumentMetadata, DocumentText, PageText


class DocumentStore:
    """Saves uploaded PDFs, their extracted text and metadata under the data directory.

    Files on disk are always named by a server-generated UUID, never by the
    user's filename, so users cannot influence where files are written.

    Access control: every document has an owner_id, and every read/delete
    requires the caller's user id. A document owned by someone else behaves
    exactly like one that doesn't exist (404), so ids can't be probed.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._upload_dir = settings.upload_dir
        self._extracted_dir = settings.extracted_dir
        self._metadata_file = settings.metadata_file
        self._lock = threading.Lock()

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._extracted_dir.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> dict[str, dict]:
        if not self._metadata_file.exists():
            return {}
        return json.loads(self._metadata_file.read_text(encoding="utf-8"))

    def _write_all(self, records: dict[str, dict]) -> None:
        tmp = self._metadata_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
        tmp.replace(self._metadata_file)

    @staticmethod
    def new_document_id() -> str:
        return uuid.uuid4().hex

    def save(
        self,
        document_id: str,
        owner_id: str,
        filename: str,
        data: bytes,
        pages: list[PageText],
        chunk_count: int,
    ) -> DocumentMetadata:
        (self._upload_dir / f"{document_id}.pdf").write_bytes(data)
        text = DocumentText(document_id=document_id, pages=pages)
        (self._extracted_dir / f"{document_id}.json").write_text(
            text.model_dump_json(indent=2), encoding="utf-8"
        )

        metadata = DocumentMetadata(
            document_id=document_id,
            owner_id=owner_id,
            filename=filename,
            page_count=len(pages),
            size_bytes=len(data),
            char_count=sum(len(p.text) for p in pages),
            chunk_count=chunk_count,
            uploaded_at=datetime.now(timezone.utc),
        )
        with self._lock:
            records = self._read_all()
            records[document_id] = metadata.model_dump(mode="json")
            self._write_all(records)
        return metadata

    def set_chunk_count(self, document_id: str, owner_id: str, chunk_count: int) -> DocumentMetadata | None:
        with self._lock:
            records = self._read_all()
            record = records.get(document_id)
            if record is None or record.get("owner_id") != owner_id:
                return None
            record["chunk_count"] = chunk_count
            self._write_all(records)
            return DocumentMetadata(**record)

    def delete(self, document_id: str, owner_id: str) -> bool:
        with self._lock:
            records = self._read_all()
            record = records.get(document_id)
            if record is None or record.get("owner_id") != owner_id:
                return False
            del records[document_id]
            self._write_all(records)
        (self._upload_dir / f"{document_id}.pdf").unlink(missing_ok=True)
        (self._extracted_dir / f"{document_id}.json").unlink(missing_ok=True)
        return True

    def list_documents(self, owner_id: str) -> list[DocumentMetadata]:
        with self._lock:
            records = self._read_all()
        return [DocumentMetadata(**r) for r in records.values() if r.get("owner_id") == owner_id]

    def count(self, owner_id: str) -> int:
        return len(self.list_documents(owner_id))

    def get(self, document_id: str, owner_id: str) -> DocumentMetadata | None:
        with self._lock:
            record = self._read_all().get(document_id)
        if record is None or record.get("owner_id") != owner_id:
            return None
        return DocumentMetadata(**record)

    def get_text(self, document_id: str, owner_id: str) -> DocumentText | None:
        # Only look up IDs we issued to this owner, so the ID can never be used as a path.
        if self.get(document_id, owner_id) is None:
            return None
        path = self._extracted_dir / f"{document_id}.json"
        return DocumentText.model_validate_json(path.read_text(encoding="utf-8"))


document_store = DocumentStore()
