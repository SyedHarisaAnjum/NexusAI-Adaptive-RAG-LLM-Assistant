import pymupdf

from app.schemas import PageText


class PDFValidationError(ValueError):
    """Raised when uploaded bytes are not a usable PDF."""


PDF_MAGIC = b"%PDF-"


def validate_pdf_bytes(data: bytes, max_pages: int) -> int:
    """Check that the bytes are a real, readable PDF. Returns the page count."""
    # Check the file signature, not just the extension or Content-Type,
    # which the client controls.
    if not data.startswith(PDF_MAGIC):
        raise PDFValidationError("File content is not a PDF.")

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise PDFValidationError("Password-protected PDFs are not supported.")
            page_count = doc.page_count
    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError(f"PDF is corrupted or unreadable: {exc}")

    if page_count == 0:
        raise PDFValidationError("PDF has no pages.")
    if page_count > max_pages:
        raise PDFValidationError(f"PDF has {page_count} pages; the limit is {max_pages}.")
    return page_count


def extract_pages(data: bytes) -> list[PageText]:
    """Extract text page by page. Page numbers start at 1."""
    pages: list[PageText] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for index, page in enumerate(doc, start=1):
            pages.append(PageText(page_number=index, text=page.get_text("text").strip()))
    return pages
