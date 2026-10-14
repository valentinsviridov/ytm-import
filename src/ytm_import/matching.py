"""Pure text normalization and candidate scoring functions."""

import re
import unicodedata
from difflib import SequenceMatcher

from .client import Track


def clean_line(line: str) -> str:
    line = line.lstrip("\ufeff").strip()
    # Remove numbering such as "1. ", "12) ", "#7: ", and "3 - ".
    line = re.sub(r"^\s*#?\d{1,4}\s*[.)\]:-]\s*", "", line)
    return line.strip()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(
        r"\b(official\s+(audio|video)|lyrics?|hd|4k|remaster(?:ed)?)\b",
        " ",
        text,
    )
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def similarity(query: str, candidate: str) -> float:
    q = normalize(query)
    c = normalize(candidate)
    if not q or not c:
        return 0.0

    sequence_score = SequenceMatcher(None, q, c).ratio()
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    token_score = len(q_tokens & c_tokens) / max(1, len(q_tokens))
    return 0.70 * sequence_score + 0.30 * token_score


def track_variants(result: Track) -> tuple[str, ...]:
    """Titles and artist/title combinations a source line can contain."""
    title = str(result.get("title", ""))
    artists = " ".join(
        str(artist.get("name", ""))
        for artist in result.get("artists", [])
        if isinstance(artist, dict)
    )
    album = result.get("album") or {}
    album_name = str(album.get("name", "")) if isinstance(album, dict) else ""

    return (
        title,
        f"{artists} {title}",
        f"{title} {artists}",
        f"{artists} {title} {album_name}",
    )


def result_score(query: str, result: Track) -> float:
    return max(similarity(query, variant) for variant in track_variants(result))


def artist_names(result: Track) -> str:
    return "; ".join(
        str(artist.get("name", ""))
        for artist in result.get("artists", [])
        if isinstance(artist, dict)
    )
