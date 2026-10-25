import logging
from pathlib import PurePath

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.auth.dependencies import CurrentUser, UploadUser
from app.config import get_settings
from app.schemas import DocumentMetadata, DocumentText
from app.services.document_store import document_store
from app.services.pdf_processor import PDFValidationError, extract_pages, validate_pdf_bytes
from app.services.rag_service import rag_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def _clean_filename(raw: str | None) -> str:
    # Keep only the base name for display; it is never used as a file path.
    name = PurePath((raw or "").replace("\\", "/")).name.strip()
    return name[:255] or "document.pdf"


@router.post("/upload", response_model=DocumentMetadata, status_code=201)
async def upload_document(user: UploadUser, file: UploadFile = File(...)) -> DocumentMetadata:
    settings = get_settings()
    filename = _clean_filename(file.filename)

    # 0. Per-user quota.
    if document_store.count(user.user_id) >= settings.max_documents_per_user:
        raise HTTPException(
            status_code=403,
            detail=f"Document limit reached ({settings.max_documents_per_user}). Delete a document first.",
        )

    # 1. Extension and declared type (cheap checks; the client controls both).
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are allowed.")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid content type: {file.content_type}")

    # 2. Size: read at most one byte past the limit so huge uploads are not loaded fully.
    #    (main.py also rejects oversized requests by Content-Length before they are read.)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit.")
    if not data:
        raise HTTPException(status_code=400, detail="File is empty.")

    # 3. Actual content: signature check + open with PyMuPDF (CPU-bound, so off the event loop).
    try:
        await run_in_threadpool(validate_pdf_bytes, data, settings.max_pdf_pages)
    except PDFValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pages = await run_in_threadpool(extract_pages, data)
    if not any(p.text for p in pages):
        raise HTTPException(
            status_code=400,
            detail="No extractable text found. Scanned/image-only PDFs are not supported.",
        )

    # 4. Index for RAG (chunk -> embed -> ChromaDB). If this fails nothing is saved,
    #    so there are never documents on disk that cannot be searched.
    document_id = document_store.new_document_id()
    try:
        chunk_count = await rag_service.index_document(document_id, user.user_id, filename, pages)
    except Exception as exc:
        await run_in_threadpool(vector_store.delete_document, document_id)
        logger.error("indexing_failed", exc_info=exc, extra={"document_id": document_id})
        raise HTTPException(status_code=502, detail="Indexing failed, please try again.")

    metadata = await run_in_threadpool(
        document_store.save, document_id, user.user_id, filename, data, pages, chunk_count
    )
    logger.info(
        "document_uploaded",
        extra={"document_id": document_id, "pages": len(pages), "chunks": chunk_count, "bytes": len(data)},
    )
    return metadata


@router.get("", response_model=list[DocumentMetadata])
async def list_documents(user: CurrentUser) -> list[DocumentMetadata]:
    return document_store.list_documents(user.user_id)


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(document_id: str, user: CurrentUser) -> DocumentMetadata:
    metadata = document_store.get(document_id, user.user_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return metadata


@router.get("/{document_id}/text", response_model=DocumentText)
async def get_document_text(document_id: str, user: CurrentUser) -> DocumentText:
    text = document_store.get_text(document_id, user.user_id)
    if text is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return text


@router.post("/{document_id}/reindex", response_model=DocumentMetadata)
async def reindex_document(document_id: str, user: UploadUser) -> DocumentMetadata:
    """Rebuild a document's vectors, e.g. after changing the chunking settings."""
    metadata = document_store.get(document_id, user.user_id)
    text = document_store.get_text(document_id, user.user_id)
    if metadata is None or text is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        chunk_count = await rag_service.index_document(
            document_id, user.user_id, metadata.filename, text.pages
        )
    except Exception as exc:
        logger.error("indexing_failed", exc_info=exc, extra={"document_id": document_id})
        raise HTTPException(status_code=502, detail="Indexing failed, please try again.")
    return document_store.set_chunk_count(document_id, user.user_id, chunk_count)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, user: CurrentUser) -> None:
    if not document_store.delete(document_id, user.user_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    await run_in_threadpool(vector_store.delete_document, document_id)
    logger.info("document_deleted", extra={"document_id": document_id})
