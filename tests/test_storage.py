from pathlib import Path

import pytest

from ytm_import.storage import (
    default_auth_file,
    default_cache_file,
    find_playlist_files,
    load_cache,
    read_text_lines,
    resolve_playlist_files,
    save_cache,
)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1251"])
def test_read_text_lines_supports_playlist_encodings(tmp_path, encoding):
    path = tmp_path / "playlist.txt"
    path.write_bytes("Кино — Группа крови\r\n\r\nMiles Davis — So What\r\n".encode(encoding))
    assert read_text_lines(path) == [
        "Кино — Группа крови", "", "Miles Davis — So What"
    ]


def test_find_playlist_files_sorts_files_and_excludes_documentation(tmp_path):
    for name in ["Jazz.txt", "Ambient.txt", "README.md"]:
        (tmp_path / name).touch()
    (tmp_path / "directory.txt").mkdir()
    assert find_playlist_files(tmp_path) == [
        tmp_path / "Ambient.txt", tmp_path / "Jazz.txt"
    ]


def test_find_playlist_files_rejects_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        find_playlist_files(tmp_path / "missing")


def test_find_playlist_files_rejects_empty_directory(tmp_path):
    with pytest.raises(ValueError, match="No .txt"):
        find_playlist_files(tmp_path)


def test_resolve_playlist_files_supports_files_dirs_and_cwd_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Rock.txt").touch()
    (tmp_path / "Jazz.txt").touch()
    assert resolve_playlist_files() == [Path("Jazz.txt"), Path("Rock.txt")]

    sub = tmp_path / "custom"
    sub.mkdir()
    (sub / "Ambient.txt").touch()
    assert resolve_playlist_files([Path("Rock.txt"), sub, Path("Rock.txt")]) == [
        Path("Rock.txt"), sub / "Ambient.txt"
    ]


def test_resolve_playlist_files_rejects_conflicting_or_non_txt_inputs(tmp_path):
    bad = tmp_path / "notes.md"
    bad.touch()
    with pytest.raises(ValueError, match=r"\.txt"):
        resolve_playlist_files([bad])
    with pytest.raises(ValueError, match="not both"):
        resolve_playlist_files([bad], playlists_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_playlist_files([tmp_path / "missing.txt"])


def test_default_auth_and_cache_files_prefer_cwd_then_user_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert default_auth_file() == tmp_path / ".xdg-config" / "ytm-import" / "browser.json"
    assert default_cache_file() == tmp_path / ".xdg-cache" / "ytm-import" / "search_cache.json"

    (tmp_path / "browser.json").write_text("{}", encoding="utf-8")
    (tmp_path / "search_cache.json").write_text("{}", encoding="utf-8")
    assert default_auth_file() == Path("browser.json")
    assert default_cache_file() == Path("search_cache.json")


def test_missing_cache_starts_empty(tmp_path):
    assert load_cache(tmp_path / "missing.json") == {}


@pytest.mark.parametrize("contents", ["not json", "{", "[]", "null"])
def test_unusable_cache_starts_empty(tmp_path, contents):
    path = tmp_path / "cache.json"
    path.write_text(contents, encoding="utf-8")
    assert load_cache(path) == {}


def test_cache_round_trip_keeps_existing_format_and_unicode(tmp_path, track):
    path = tmp_path / "nested" / "dir" / "cache.json"
    cache = {"кино": {"result": track, "score": 0.9}}
    save_cache(path, cache)
    assert load_cache(path) == cache
    assert "кино" in path.read_text(encoding="utf-8")


def test_interrupted_cache_replacement_preserves_previous_cache(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    original = {"old": {"result": None, "score": 0.0}}
    save_cache(path, original)

    def interrupt_replace(self, target):
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "replace", interrupt_replace)
    with pytest.raises(KeyboardInterrupt):
        save_cache(path, {"new": {"result": None, "score": 0.0}})
    assert load_cache(path) == original
    assert list(tmp_path.iterdir()) == [path]
