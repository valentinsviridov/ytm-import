import csv
from dataclasses import replace
from unittest.mock import Mock, call

import pytest

from ytm_import.importer import import_playlists, match_tracks
from ytm_import.search import SearchResult
from ytm_import.storage import load_cache, save_cache


def read_report(config):
    with config.report_file.open(encoding="utf-8-sig", newline="") as report:
        return list(csv.DictReader(report))


def test_match_tracks_reports_decisions_and_original_line_numbers(track):
    search = Mock(side_effect=[
        SearchResult(track, 0.58, "SEARCH"),
        SearchResult(track, 0.99, "CACHE"),
        SearchResult({**track, "videoId": "weak"}, 0.57, "SEARCH"),
        SearchResult(None, 0, "NOT_FOUND"),
        SearchResult(None, 0, "ERROR: TimeoutError: slow"),
    ])
    rows = list(match_tracks(
        "Jazz", ["1. So What", "", "Same track", "Weak", "Missing", "Failed"], search
    ))
    assert [row.status for row in rows] == [
        "ADDED", "DUPLICATE_SKIPPED", "LOW_CONFIDENCE_SKIPPED",
        "NOT_FOUND", "ERROR: TimeoutError: slow",
    ]
    assert [row.line for row in rows] == [1, 3, 4, 5, 6]
    assert rows[0].source == "So What"
    assert rows[0].confidence == "0.580"
    assert rows[0].matched_artists == "Miles Davis"
    assert rows[0].playlist == "Jazz"
    assert search.call_args_list == [
        call("So What"), call("Same track"), call("Weak"), call("Missing"), call("Failed")
    ]


def test_low_confidence_match_does_not_block_a_later_good_match(track):
    search = Mock(side_effect=[
        SearchResult(track, 0.4, "SEARCH"), SearchResult(track, 0.9, "SEARCH")
    ])
    rows = list(match_tracks("Jazz", ["Vague query", "So What"], search))
    assert [row.status for row in rows] == ["LOW_CONFIDENCE_SKIPPED", "ADDED"]


def test_duplicates_are_scoped_to_each_playlist(track):
    search = Mock(return_value=SearchResult(track, 0.9, "CACHE"))
    for title in ["Jazz", "Favorites"]:
        assert list(match_tracks(title, ["So What"], search))[0].status == "ADDED"


def test_import_creates_unique_tracks_and_persists_report_and_cache(client, config, track):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("1. Miles Davis — So What\n\nSo What\nMissing\n", encoding="utf-8")
    config.report_file.write_text("old report", encoding="utf-8")
    client.search.side_effect = [[track], []]
    messages = []
    sleep = Mock()

    import_playlists(client, [source], config, sleep=sleep, output=messages.append)

    client.get_library_playlists.assert_called_once_with(limit=None)
    client.create_playlist.assert_called_once_with(
        title="Jazz", description="Imported from a text file.",
        privacy_status="PRIVATE", video_ids=["so-what"],
    )
    assert client.search.call_count == 2
    client.add_playlist_items.assert_not_called()
    rows = read_report(config)
    assert [row["status"] for row in rows] == ["ADDED", "DUPLICATE_SKIPPED", "NOT_FOUND"]
    assert [row["line"] for row in rows] == ["1", "3", "4"]
    assert list(rows[0]) == [
        "playlist", "line", "source", "matched_title", "matched_artists",
        "video_id", "confidence", "status",
    ]
    assert config.report_file.read_bytes().startswith(b"\xef\xbb\xbf")
    assert load_cache(config.cache_file)["missing"] == {"result": None, "score": 0.0}
    assert any("CREATED: Jazz" in message for message in messages)


@pytest.mark.parametrize("owned", [True, None])
def test_existing_owned_titles_are_resumed_ignoring_case(client, config, track, owned):
    existing = {"title": "jAzZ", "playlistId": "existing-jazz"}
    if owned is not None:
        existing["owned"] = owned
    client.get_library_playlists.return_value = [existing]
    client.get_playlist.return_value = {"tracks": [track]}
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("Miles Davis — So What", encoding="utf-8")
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.get_playlist.assert_called_once_with("existing-jazz", limit=None)
    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    client.add_playlist_items.assert_not_called()
    assert read_report(config)[0]["status"] == "ALREADY_PRESENT"


def test_unowned_playlist_does_not_prevent_creation(client, config, track):
    client.get_library_playlists.return_value = [{"title": "Jazz", "owned": False}]
    client.search.return_value = [track]
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    import_playlists(client, [source], replace(config, privacy="UNLISTED"), sleep=Mock(), output=Mock())
    assert client.create_playlist.call_args.kwargs["privacy_status"] == "UNLISTED"


def test_newly_created_title_is_resumed_on_later_files(client, config, track):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    second_source = config.playlists_dir / "JAZZ.txt"
    second_source.write_text("So What\nTake Five", encoding="utf-8")
    second_track = {**track, "videoId": "take-five", "title": "Take Five"}
    client.search.side_effect = [[track], [second_track]]
    import_playlists(
        client, [source, second_source], config,
        sleep=Mock(), output=Mock(),
    )
    client.create_playlist.assert_called_once()
    client.get_playlist.assert_not_called()
    client.add_playlist_items.assert_called_once_with(
        "created-playlist-id", ["take-five"], duplicates=False,
    )
    assert [row["status"] for row in read_report(config)] == [
        "ADDED", "ALREADY_PRESENT", "ADDED",
    ]


@pytest.mark.parametrize("results", [[], [{"videoId": "wrong", "title": "Nothing alike"}]])
def test_no_confident_matches_do_not_create_an_empty_playlist(client, config, results):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("Miles Davis — So What", encoding="utf-8")
    client.search.return_value = results
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.create_playlist.assert_not_called()
    assert read_report(config)[0]["status"] in {"NOT_FOUND", "LOW_CONFIDENCE_SKIPPED"}


def test_api_search_error_is_recorded_and_does_not_abort_import(client, config):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    client.search.side_effect = TimeoutError("offline")
    import_playlists(client, [source], replace(config, max_retries=1), sleep=Mock(), output=Mock())
    assert read_report(config)[0]["status"] == "ERROR: TimeoutError: offline"
    client.create_playlist.assert_not_called()
    assert load_cache(config.cache_file) == {}


def test_existing_cache_is_reused_across_imports(client, config, track):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    save_cache(config.cache_file, {"so what": {"result": track, "score": 1.0}})
    sleep = Mock()
    import_playlists(client, [source], config, sleep=sleep, output=Mock())
    client.search.assert_not_called()
    sleep.assert_not_called()
    assert read_report(config)[0]["status"] == "ADDED"


def test_playlist_creation_failure_propagates_and_closes_report(client, config, track):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    client.search.return_value = [track]
    client.create_playlist.return_value = {"error": "denied"}
    with pytest.raises(RuntimeError, match="Unable to create playlist 'Jazz'"):
        import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    assert read_report(config)[0]["status"].startswith("ERROR: RuntimeError:")
    assert "so what" in load_cache(config.cache_file)


def test_existing_metadata_and_repeated_queries_avoid_searches(track):
    search = Mock()
    rows = list(match_tracks(
        "Jazz", ["1. Miles Davis — So What", "SO WHAT", "So What — Miles Davis"],
        search, existing_tracks=[track],
    ))
    assert [row.status for row in rows] == ["ALREADY_PRESENT"] * 3
    search.assert_not_called()


def test_new_track_metadata_avoids_searches_for_later_duplicates(track):
    search = Mock(return_value=SearchResult(track, 1.0, "SEARCH"))
    rows = list(match_tracks(
        "Jazz", ["Miles Davis — So What", "So What", "MILES DAVIS: SO WHAT"], search,
    ))
    assert [row.status for row in rows] == ["ADDED", "DUPLICATE_SKIPPED", "DUPLICATE_SKIPPED"]
    search.assert_called_once_with("Miles Davis — So What")


def test_ambiguous_existing_titles_are_searched_instead_of_guessed(track):
    other = {**track, "videoId": "other-so-what", "artists": [{"name": "Other Artist"}]}
    search = Mock(return_value=SearchResult(track, 1.0, "SEARCH"))
    rows = list(match_tracks("Jazz", ["So What"], search, existing_tracks=[track, other]))
    assert rows[0].status == "ALREADY_PRESENT"
    search.assert_called_once_with("So What")


@pytest.mark.parametrize("keep_cache", [True, False])
def test_repeating_import_does_not_search_or_write_again(
    client, config, track, second_track, remote_library, keep_cache,
):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("Miles Davis — So What\nTake Five\nSo What", encoding="utf-8")
    client.search.side_effect = [[track], [second_track]]
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    assert [row["status"] for row in read_report(config)] == [
        "ADDED", "ADDED", "DUPLICATE_SKIPPED",
    ]

    if not keep_cache:
        config.cache_file.unlink()
    client.reset_mock()
    # Source line numbers and ordering are not used as progress checkpoints.
    source.write_text("1. Take Five\n2. So What — Miles Davis", encoding="utf-8")
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())

    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    client.add_playlist_items.assert_not_called()
    client.get_playlist.assert_called_once_with("playlist-1", limit=None)
    assert [row["status"] for row in read_report(config)] == ["ALREADY_PRESENT"] * 2
    assert [item["videoId"] for item in remote_library["playlist-1"]["tracks"]] == [
        "so-what", "take-five",
    ]


def test_interrupted_search_resumes_from_incrementally_added_tracks(
    client, config, track, second_track, remote_library,
):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What\nTake Five", encoding="utf-8")
    client.search.side_effect = [[track], [second_track]]
    # Interrupt after the second search result was cached, during its delay.
    with pytest.raises(KeyboardInterrupt):
        import_playlists(
            client, [source], config,
            sleep=Mock(side_effect=[None, KeyboardInterrupt]), output=Mock(),
        )
    assert [item["videoId"] for item in remote_library["playlist-1"]["tracks"]] == ["so-what"]
    assert [row["status"] for row in read_report(config)] == ["ADDED"]
    assert set(load_cache(config.cache_file)) == {"so what", "take five"}

    client.reset_mock()
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    client.add_playlist_items.assert_called_once_with("playlist-1", ["take-five"], duplicates=False)
    assert [row["status"] for row in read_report(config)] == ["ALREADY_PRESENT", "ADDED"]
    assert [item["videoId"] for item in remote_library["playlist-1"]["tracks"]] == ["so-what", "take-five"]


@pytest.mark.parametrize("operation", ["create_playlist", "add_playlist_items"])
def test_lost_write_response_is_reconciled_on_next_run(
    client, config, track, second_track, remote_library, operation,
):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What\nTake Five", encoding="utf-8")
    client.search.side_effect = [[track], [second_track]]
    write_method = getattr(client, operation)
    actual_write = write_method.side_effect

    def write_then_lose_response(*args, **kwargs):
        # The search mapping must be durable before an ambiguous remote write.
        expected_key = "so what" if operation == "create_playlist" else "take five"
        assert expected_key in load_cache(config.cache_file)
        actual_write(*args, **kwargs)
        raise TimeoutError("response lost")

    write_method.side_effect = write_then_lose_response
    with pytest.raises(TimeoutError, match="response lost"):
        import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    assert read_report(config)[-1]["status"] == "ERROR: TimeoutError: response lost"

    write_method.side_effect = actual_write
    client.reset_mock()
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.create_playlist.assert_not_called()
    if operation == "add_playlist_items":
        client.search.assert_not_called()
        client.add_playlist_items.assert_not_called()
        assert [row["status"] for row in read_report(config)] == ["ALREADY_PRESENT"] * 2
    else:
        client.search.assert_called_once_with("Take Five", filter="songs", limit=5)
        client.add_playlist_items.assert_called_once_with("playlist-1", ["take-five"], duplicates=False)
    assert len(remote_library) == 1
    assert [item["videoId"] for item in remote_library["playlist-1"]["tracks"]] == ["so-what", "take-five"]


@pytest.mark.parametrize("failure", [{"status": "STATUS_FAILED"}, {"error": "denied"}, "STATUS_FAILED"])
def test_failed_add_is_not_reported_as_added_and_can_be_retried(
    client, config, track, second_track, remote_library, failure,
):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What\nTake Five", encoding="utf-8")
    client.search.side_effect = [[track], [second_track]]
    actual_add = client.add_playlist_items.side_effect
    client.add_playlist_items.side_effect = None
    client.add_playlist_items.return_value = failure
    with pytest.raises(RuntimeError, match="Unable to add track to playlist 'Jazz'"):
        import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    rows = read_report(config)
    assert rows[0]["status"] == "ADDED"
    assert rows[1]["status"].startswith("ERROR: RuntimeError:")
    assert len(remote_library["playlist-1"]["tracks"]) == 1

    client.add_playlist_items.side_effect = actual_add
    client.reset_mock()
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    assert [row["status"] for row in read_report(config)] == ["ALREADY_PRESENT", "ADDED"]
    assert len(remote_library["playlist-1"]["tracks"]) == 2


def test_existing_cached_video_id_is_skipped_without_matching_metadata(client, config, track):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("My alternate spelling", encoding="utf-8")
    client.get_library_playlists.return_value = [{"title": "Jazz", "playlistId": "jazz"}]
    client.get_playlist.return_value = {"tracks": [{"videoId": "so-what"}]}
    save_cache(config.cache_file, {"my alternate spelling": {"result": track, "score": 0.9}})
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.search.assert_not_called()
    client.add_playlist_items.assert_not_called()
    assert read_report(config)[0]["status"] == "ALREADY_PRESENT"


def test_missing_remote_track_is_restored_using_cache(client, config, track, remote_library):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    client.search.return_value = [track]
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    remote_library["playlist-1"]["tracks"].clear()
    client.reset_mock()
    import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    client.add_playlist_items.assert_called_once_with("playlist-1", ["so-what"], duplicates=False)
    assert read_report(config)[0]["status"] == "ADDED"


def test_same_composition_can_be_added_to_different_playlists(client, config, track, remote_library):
    sources = [config.playlists_dir / f"{name}.txt" for name in ["Jazz", "Favorites"]]
    for source in sources:
        source.write_text("So What", encoding="utf-8")
    client.search.return_value = [track]
    import_playlists(client, sources, config, sleep=Mock(), output=Mock())
    client.search.assert_called_once()
    assert client.create_playlist.call_count == 2
    assert [playlist["title"] for playlist in remote_library.values()] == ["Jazz", "Favorites"]
    assert all(len(playlist["tracks"]) == 1 for playlist in remote_library.values())


def test_unreadable_existing_playlist_fails_before_search_or_add(client, config):
    source = config.playlists_dir / "Jazz.txt"
    source.write_text("So What", encoding="utf-8")
    client.get_library_playlists.return_value = [{"title": "Jazz", "playlistId": "jazz"}]
    client.get_playlist.return_value = {"error": "denied"}
    with pytest.raises(RuntimeError, match="Unable to read playlist 'Jazz'"):
        import_playlists(client, [source], config, sleep=Mock(), output=Mock())
    client.search.assert_not_called()
    client.create_playlist.assert_not_called()
    client.add_playlist_items.assert_not_called()
