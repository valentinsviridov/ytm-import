from unittest.mock import Mock, call

import pytest

from ytm_import.matching import normalize
from ytm_import.search import SearchResult, SongSearcher


def test_cache_hit_avoids_api_calls_and_delays(client, track):
    cache = {"miles davis so what": {"result": track, "score": 0.95}}
    sleep = Mock()
    searcher = SongSearcher(client, cache, sleep=sleep)
    assert searcher.search("MILES DAVIS — So What (Official Audio)") == (
        SearchResult(track, 0.95, "CACHE")
    )
    client.search.assert_not_called()
    sleep.assert_not_called()


def test_cached_miss_avoids_repeated_searches(client):
    cache = {"missing": {"result": None, "score": 0.0}}
    sleep = Mock()
    assert SongSearcher(client, cache, sleep=sleep).search("Missing") == (
        SearchResult(None, 0, "CACHE")
    )
    client.search.assert_not_called()
    sleep.assert_not_called()


def test_search_selects_best_available_candidate_and_caches_it(client, track):
    client.search.return_value = [
        {"title": "So What", "artists": track["artists"]},
        {**track, "videoId": "unavailable", "isAvailable": False},
        {"videoId": "other", "title": "Take Five", "artists": []},
        {**track, "irrelevant": "not needed in cache"},
    ]
    cache = {}
    sleep = Mock()
    result = SongSearcher(client, cache, search_delay=0.2, sleep=sleep).search(
        "Miles Davis — So What"
    )
    assert result.result["videoId"] == "so-what"
    assert result.score == pytest.approx(1)
    assert result.source == "SEARCH"
    assert "irrelevant" not in result.result
    assert cache["miles davis so what"] == {"result": result.result, "score": result.score}
    client.search.assert_called_once_with("Miles Davis — So What", filter="songs", limit=5)
    sleep.assert_called_once_with(0.2)


@pytest.mark.parametrize(
    "results", [[], [{"videoId": "unavailable", "isAvailable": False}], [{"title": "No ID"}]]
)
def test_no_usable_candidates_are_cached_as_a_miss(client, results):
    client.search.return_value = results
    cache = {}
    sleep = Mock()
    searcher = SongSearcher(client, cache, sleep=sleep)
    assert searcher.search("Missing") == SearchResult(None, 0, "NOT_FOUND")
    assert searcher.search("MISSING").source == "CACHE"
    client.search.assert_called_once()
    sleep.assert_not_called()


def test_transient_errors_retry_with_exponential_backoff(client, track):
    client.search.side_effect = [RuntimeError("busy"), TimeoutError("slow"), [track]]
    sleep = Mock()
    result = SongSearcher(client, {}, max_retries=3, sleep=sleep).search("So What")
    assert result.result["videoId"] == "so-what"
    assert client.search.call_count == 3
    assert sleep.call_args_list == [call(1), call(2), call(0.35)]


def test_exhausted_errors_are_reported_and_not_cached(client, track):
    client.search.side_effect = [TimeoutError("slow"), TimeoutError("slow"), [track]]
    cache = {}
    sleep = Mock()
    searcher = SongSearcher(client, cache, max_retries=2, sleep=sleep)
    assert searcher.search("So What") == SearchResult(None, 0, "ERROR: TimeoutError: slow")
    assert normalize("So What") not in cache
    sleep.assert_called_once_with(1)
    assert searcher.search("So What").source == "SEARCH"
    assert client.search.call_count == 3
