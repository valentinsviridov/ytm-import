from unittest.mock import Mock

import pytest

from ytm_import.cli import main
from ytm_import.storage import save_cache


def test_help_does_not_require_credentials_or_client(capsys):
    factory = Mock()
    with pytest.raises(SystemExit) as exc:
        main(["--help"], client_factory=factory)
    assert exc.value.code == 0
    assert "--playlists-dir" in capsys.readouterr().out
    factory.assert_not_called()


def test_missing_authentication_fails_before_client_initialization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    factory = Mock()
    with pytest.raises(SystemExit, match="uv run ytmusicapi browser") as exc:
        main([], client_factory=factory)
    assert "POST /youtubei/v1/browse" in str(exc.value)
    assert "Request Headers" in str(exc.value)
    factory.assert_not_called()


@pytest.mark.parametrize("has_directory", [True, False])
def test_missing_input_fails_before_client_initialization(tmp_path, monkeypatch, has_directory):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "browser.json").write_text("{}", encoding="utf-8")
    if has_directory:
        (tmp_path / "playlists").mkdir()
    factory = Mock()
    with pytest.raises(SystemExit, match="playlist|Playlist"):
        main([], client_factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan"])
def test_invalid_threshold_is_rejected_before_client_initialization(value, capsys):
    factory = Mock()
    with pytest.raises(SystemExit) as exc:
        main(["--min-score", value], client_factory=factory)
    assert exc.value.code == 2
    assert "min_score must be between 0 and 1" in capsys.readouterr().err
    factory.assert_not_called()


def test_cli_honors_custom_paths_and_visibility(client, config, track, tmp_path, monkeypatch):
    # All configured paths are absolute and work outside the project directory.
    monkeypatch.chdir(tmp_path)
    config.auth_file.write_text(
        '{"POST /youtubei/v1/browse?prettyPrint=false HTTP/2": "", "cookie": "ok"}',
        encoding="utf-8",
    )
    (config.playlists_dir / "Jazz.txt").write_text("So What", encoding="utf-8")
    save_cache(config.cache_file, {"so what": {"result": track, "score": 0.6}})
    factory = Mock(return_value=client)

    main([
        "--playlists-dir", str(config.playlists_dir),
        "--auth-file", str(config.auth_file),
        "--report-file", str(config.report_file),
        "--cache-file", str(config.cache_file),
        "--privacy", "PUBLIC", "--min-score", "0.6",
    ], client_factory=factory)

    factory.assert_called_once_with(str(config.auth_file))
    assert "POST /youtubei/v1/browse" not in config.auth_file.read_text(encoding="utf-8")
    client.search.assert_not_called()
    assert client.create_playlist.call_args.kwargs["privacy_status"] == "PUBLIC"
    assert config.report_file.is_file()
