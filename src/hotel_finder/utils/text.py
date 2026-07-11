"""Text normalization helpers."""

from __future__ import annotations

import html
import re
import unicodedata

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    """Turn an HTML snippet into readable plain text (drop tags, unescape entities, collapse
    whitespace). Provider descriptions (e.g. LiteAPI's ``hotelDescription``) arrive as HTML."""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return " ".join(text.split())


def normalize_text(value: str) -> str:
    """Lowercase, strip accents, drop punctuation, and collapse whitespace.

    Used for fuzzy matching of names and area labels (e.g. so "Barri Gòtic" and
    "barri gotic" compare equal).
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    kept = "".join(c if (c.isalnum() or c.isspace()) else " " for c in without_accents.lower())
    return " ".join(kept.split())
