"""Song search with an injectable API client, cache, and retry clock."""

import time
from collections.abc import Callable
from dataclasses import dataclass

from .client import MusicClient, SearchCache, Track
from .matching import normalize, result_score


@dataclass(frozen=True)
class SearchResult:
    result: Track | None
    score: float
    source: str


class SongSearcher:
    def __init__(
        self,
        client: MusicClient,
        cache: SearchCache,
        *,
        search_delay: float = 0.35,
        max_retries: int = 5,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.client = client
        self.cache = cache
        self.search_delay = search_delay
        self.max_retries = max_retries
        self.sleep = time.sleep if sleep is None else sleep

    def search(self, query: str) -> SearchResult:
        cache_key = normalize(query)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return SearchResult(
                cached.get("result"), float(cached.get("score", 0.0)), "CACHE"
            )

        last_error = ""
        for attempt in range(self.max_retries):
            try:
                results = self.client.search(query, filter="songs", limit=5)
                candidates = [
                    item
                    for item in results
                    if item.get("videoId") and item.get("isAvailable", True)
                ]

                if not candidates:
                    self.cache[cache_key] = {"result": None, "score": 0.0}
                    return SearchResult(None, 0.0, "NOT_FOUND")

                best = max(candidates, key=lambda item: result_score(query, item))
                score = result_score(query, best)
                compact = {
                    "videoId": best.get("videoId"),
                    "title": best.get("title", ""),
                    "artists": best.get("artists", []),
                    "album": best.get("album"),
                    "resultType": best.get("resultType", "song"),
                }
                self.cache[cache_key] = {"result": compact, "score": score}
                self.sleep(self.search_delay)
                return SearchResult(compact, score, "SEARCH")

            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < self.max_retries:
                    self.sleep(2**attempt)

        return SearchResult(None, 0.0, f"ERROR: {last_error}")
