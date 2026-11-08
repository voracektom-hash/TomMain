"""Small text helpers: diacritics removal and keyword matching."""

from __future__ import annotations

import re
import unicodedata

VOWELS = "aeiouy"


def ascii_text(text: str) -> str:
    """'Žluťoučký kůň' -> 'Zlutoucky kun'. Anything non-ASCII left over becomes '?'."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    stripped = stripped.replace(" ", " ").replace("–", "-").replace("—", "-")
    return stripped.encode("ascii", "replace").decode("ascii")


def normalize(text: str) -> str:
    """Lowercase ASCII for comparisons."""
    return ascii_text(text).lower()


def keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Match a Czech word in any grammatical form.

    'dražba' -> stem 'drazb' matches 'dražba', 'dražbě' and, thanks to the optional
    inserted 'e' (dražba -> dražeb), also 'dražební';
    'nájemník' matches 'nájemníkem' but not 'nájemné'.
    The match must start at a word boundary, so 'podíl' does not hit 'spolupodílet'.
    """
    stem = normalize(keyword.strip())
    if len(stem) > 4 and stem[-1] in VOWELS:
        stem = stem[:-1]
    if len(stem) >= 4 and stem[-1] not in VOWELS and stem[-2] not in VOWELS:
        return re.compile(r"\b" + re.escape(stem[:-1]) + "e?" + re.escape(stem[-1]))
    return re.compile(r"\b" + re.escape(stem))


def find_keyword(text: str, keywords: list[str]) -> str | None:
    """Return the first keyword found in text, or None."""
    haystack = normalize(text)
    for keyword in keywords:
        if keyword.strip() and keyword_pattern(keyword).search(haystack):
            return keyword
    return None
