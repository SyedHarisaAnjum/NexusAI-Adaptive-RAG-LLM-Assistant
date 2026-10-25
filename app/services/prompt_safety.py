"""Defenses against prompt injection hidden in uploaded documents.

Document text is untrusted: anyone can upload a PDF containing
"Ignore previous instructions and ...". We defend in layers:

1. Delimiting   - excerpts are wrapped in <document_excerpt> tags and any tag-like
                  text inside them is neutralised, so a document can't "close" its
                  excerpt and start writing instructions.
2. Redaction    - well-known injection phrases are replaced with a marker and logged.
3. Instruction  - the system prompt tells Gemini that excerpts are data, never
   hierarchy      instructions (see rag_service.SYSTEM_INSTRUCTION).
4. Output       - answers must cite excerpts that exist (rag_service.validate), and
   checks         the frontend renders answers as plain text (no HTML/links/images),
                  so injected content can't run scripts or leak data through URLs.
"""

import re

INJECTION_PATTERNS = re.compile(
    r"(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?"
    r"(?:previous|prior|above|earlier|preceding|system)\s+(?:instructions?|prompts?|rules|messages?)"
    r"|you\s+are\s+now\s+(?:a|an|the|in)\b"
    r"|new\s+(?:system\s+)?instructions?\s*:"
    r"|(?:reveal|print|show|repeat)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)"
    r"|</?\s*(?:system|assistant|instructions?)\s*>",
    re.IGNORECASE,
)

REDACTION = "[removed: possible prompt injection]"
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EXCERPT_TAG = re.compile(r"<\s*/?\s*document_excerpt", re.IGNORECASE)


def sanitize_document_text(text: str) -> tuple[str, bool]:
    """Return (safe_text, injection_suspected)."""
    text = CONTROL_CHARS.sub("", text)
    text = EXCERPT_TAG.sub("&lt;document_excerpt", text)
    text, count = INJECTION_PATTERNS.subn(REDACTION, text)
    return text, count > 0


def sanitize_attribute(value: str, max_length: int = 120) -> str:
    """Make a value (e.g. a filename) safe to place inside a tag attribute or prompt line."""
    value = CONTROL_CHARS.sub("", value).replace("\n", " ")
    return re.sub(r'[<>"]', "", value)[:max_length]
