"""Command-line settings and the production YouTube Music client."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from ytmusicapi import YTMusic

from .client import MusicClient
from .config import ImportConfig
from .importer import import_playlists
from .storage import find_playlist_files


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], MusicClient] = YTMusic,
) -> None:
    defaults = ImportConfig()
    parser = argparse.ArgumentParser(
        description="Bulk import text-file playlists into YouTube Music."
    )
    parser.add_argument(
        "--playlists-dir", type=Path, default=defaults.playlists_dir,
        help="Directory containing .txt playlist files (default: playlists)",
    )
    parser.add_argument(
        "--auth-file", type=Path, default=defaults.auth_file,
        help="Browser authentication file (default: browser.json)",
    )
    parser.add_argument(
        "--report-file", type=Path, default=defaults.report_file,
        help="CSV report path (default: import_report.csv)",
    )
    parser.add_argument(
        "--cache-file", type=Path, default=defaults.cache_file,
        help="Search cache path (default: search_cache.json)",
    )
    parser.add_argument(
        "--privacy", choices=["PRIVATE", "UNLISTED", "PUBLIC"],
        default=defaults.privacy, help="Playlist visibility (default: PRIVATE)",
    )
    parser.add_argument(
        "--min-score", type=float, default=defaults.min_score,
        help="Minimum match confidence from 0 to 1 (default: 0.58)",
    )
    args = parser.parse_args(argv)
    try:
        config = ImportConfig(**vars(args))
    except ValueError as exc:
        parser.error(str(exc))
    else:
        if not config.auth_file.is_file():
            raise SystemExit(
                f"Authentication file does not exist: {config.auth_file}. "
                "Run: uv run ytmusicapi browser"
            )
        try:
            files = find_playlist_files(config.playlists_dir)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc

        client = client_factory(str(config.auth_file))
        import_playlists(client, files, config)
