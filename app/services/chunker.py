import re
from dataclasses import dataclass

from app.schemas import PageText


@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping windows, breaking on whitespace where possible."""
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Back up to the last space so words are not cut in half,
            # but never shrink the chunk below half its target size.
            space = text.rfind(" ", start + chunk_size // 2, end)
            if space != -1:
                end = space
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break

        # Step back by `overlap` characters, then forward to a word boundary.
        next_start = max(end - overlap, start + 1)
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return [p for p in pieces if p]


def chunk_pages(pages: list[PageText], chunk_size: int, overlap: int) -> list[Chunk]:
    """Chunk each page separately so every chunk keeps an exact page number."""
    if overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[Chunk] = []
    for page in pages:
        text = re.sub(r"\s+", " ", page.text).strip()
        if not text:
            continue
        for piece in _split_text(text, chunk_size, overlap):
            chunks.append(Chunk(text=piece, page_number=page.page_number, chunk_index=len(chunks)))
    return chunks
