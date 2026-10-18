"""Offline fixtures; tests never use a real account or retry delays."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from ytm_import.client import MusicClient
from ytm_import.config import ImportConfig


@pytest.fixture(autouse=True)
def block_external_side_effects(monkeypatch, tmp_path):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("Unit tests must not make network requests")

    def unexpected_sleep(seconds):
        raise AssertionError("Inject a fake sleep function in unit tests")

    monkeypatch.setattr("requests.sessions.Session.request", unexpected_request)
    monkeypatch.setattr("time.sleep", unexpected_sleep)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".xdg-cache"))
    monkeypatch.setenv("APPDATA", str(tmp_path / ".appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / ".localappdata"))


@pytest.fixture
def client():
    mock = Mock(spec=MusicClient)
    mock.get_library_playlists.return_value = []
    mock.search.return_value = []
    mock.create_playlist.return_value = "created-playlist-id"
    mock.get_playlist.return_value = {"tracks": []}
    mock.add_playlist_items.return_value = {"status": "STATUS_SUCCEEDED"}
    return mock


@pytest.fixture
def track():
    return {
        "videoId": "so-what",
        "title": "So What",
        "artists": [{"name": "Miles Davis"}],
        "album": {"name": "Kind of Blue"},
    }


@pytest.fixture
def second_track():
    return {
        "videoId": "take-five", "title": "Take Five",
        "artists": [{"name": "The Dave Brubeck Quartet"}],
    }


@pytest.fixture
def remote_library(client, track, second_track):
    """A remote library that survives importer runs and rejects duplicate adds."""
    library = {}
    catalog = {item["videoId"]: item for item in [track, second_track]}

    def create_playlist(*, title, description, privacy_status, video_ids):
        playlist_id = f"playlist-{len(library) + 1}"
        library[playlist_id] = {
            "playlistId": playlist_id, "title": title, "owned": True,
            "tracks": [deepcopy(catalog[video_id]) for video_id in video_ids],
        }
        return playlist_id

    def add_playlist_items(playlist_id, video_ids, *, duplicates):
        assert duplicates is False
        tracks = library[playlist_id]["tracks"]
        if any(video_id in {item["videoId"] for item in tracks} for video_id in video_ids):
            return {"status": "STATUS_FAILED", "error": "duplicate"}
        tracks.extend(deepcopy(catalog[video_id]) for video_id in video_ids)
        return {"status": "STATUS_SUCCEEDED"}

    client.get_library_playlists.side_effect = lambda **kwargs: [
        {key: value for key, value in item.items() if key != "tracks"}
        for item in library.values()
    ]
    client.get_playlist.side_effect = lambda playlist_id, **kwargs: deepcopy(library[playlist_id])
    client.create_playlist.side_effect = create_playlist
    client.add_playlist_items.side_effect = add_playlist_items
    return library


@pytest.fixture
def config(tmp_path):
    playlists = tmp_path / "playlists"
    playlists.mkdir()
    return ImportConfig(
        playlists_dir=playlists,
        auth_file=tmp_path / "browser.json",
        report_file=tmp_path / "report.csv",
        cache_file=tmp_path / "cache.json",
    )
