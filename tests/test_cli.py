from pathlib import Path
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


def test_missing_authentication_fails_before_client_initialization_when_non_interactive(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Jazz.txt").write_text("So What", encoding="utf-8")
    factory = Mock()
    with pytest.raises(SystemExit, match="ytmusicapi browser") as exc:
        main([], client_factory=factory, is_interactive=lambda: False)
    assert "POST /youtubei/v1/browse" in str(exc.value)
    assert "Request Headers" in str(exc.value)
    factory.assert_not_called()


def test_interactive_setup_creates_and_sanitizes_user_auth_file_and_imports(
    client, track, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Jazz.txt").write_text("So What", encoding="utf-8")
    expected_auth = tmp_path / ".xdg-config" / "ytm-import" / "browser.json"
    expected_cache = tmp_path / ".xdg-cache" / "ytm-import" / "search_cache.json"
    save_cache(expected_cache, {"so what": {"result": track, "score": 0.9}})
    factory = Mock(return_value=client)
    messages = []

    def fake_setup(filepath: str) -> str:
        Path(filepath).write_text(
            '{"POST /youtubei/v1/browse?prettyPrint=false HTTP/2": "", "cookie": "ok"}',
            encoding="utf-8",
        )
        return "{}"

    auth_setup = Mock(side_effect=fake_setup)
    main(
        [],
        client_factory=factory,
        auth_setup=auth_setup,
        is_interactive=lambda: True,
        output=messages.append,
    )

    auth_setup.assert_called_once_with(str(expected_auth))
    factory.assert_called_once_with(str(expected_auth))
    assert "POST /youtubei/v1/browse" not in expected_auth.read_text(encoding="utf-8")
    assert expected_cache.is_file()
    assert (tmp_path / "import_report.csv").is_file()
    assert any("POST /youtubei/v1/browse" in msg for msg in messages)
    client.create_playlist.assert_called_once()


def test_reauth_prompts_even_when_auth_file_exists(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    auth_file = tmp_path / "browser.json"
    auth_file.write_text('{"cookie": "old"}', encoding="utf-8")
    (tmp_path / "Jazz.txt").write_text("", encoding="utf-8")
    auth_setup = Mock(
        side_effect=lambda path: Path(path).write_text('{"cookie": "new"}', encoding="utf-8")
    )
    factory = Mock(return_value=client)

    main(
        ["--reauth"],
        client_factory=factory,
        auth_setup=auth_setup,
        is_interactive=lambda: True,
        output=Mock(),
    )

    auth_setup.assert_called_once_with(str(Path("browser.json")))
    assert '"new"' in auth_file.read_text(encoding="utf-8")


def test_interactive_setup_failure_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Jazz.txt").write_text("So What", encoding="utf-8")
    factory = Mock()
    auth_setup = Mock(side_effect=RuntimeError("missing cookie header"))

    with pytest.raises(SystemExit, match="Authentication setup failed: missing cookie header"):
        main(
            [],
            client_factory=factory,
            auth_setup=auth_setup,
            is_interactive=lambda: True,
            output=Mock(),
        )
    factory.assert_not_called()


@pytest.mark.parametrize("has_directory", [True, False])
def test_missing_input_fails_before_auth_or_client_initialization(
    tmp_path, monkeypatch, has_directory
):
    monkeypatch.chdir(tmp_path)
    if has_directory:
        (tmp_path / "playlists").mkdir()
    factory = Mock()
    auth_setup = Mock()
    with pytest.raises(SystemExit, match="playlist|Playlist"):
        main([], client_factory=factory, auth_setup=auth_setup, is_interactive=lambda: True)
    auth_setup.assert_not_called()
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


def test_cli_accepts_positional_playlist_files(client, track, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "browser.json").write_text('{"cookie": "ok"}', encoding="utf-8")
    save_cache(tmp_path / "search_cache.json", {"so what": {"result": track, "score": 0.9}})
    custom_file = tmp_path / "custom" / "Grunge.txt"
    custom_file.parent.mkdir()
    custom_file.write_text("So What", encoding="utf-8")
    factory = Mock(return_value=client)

    main([str(custom_file)], client_factory=factory, output=Mock())

    client.create_playlist.assert_called_once()
    assert client.create_playlist.call_args.kwargs["title"] == "Grunge"
