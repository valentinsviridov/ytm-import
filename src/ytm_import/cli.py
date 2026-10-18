"""Command-line settings and the production YouTube Music client."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys

from ytmusicapi import YTMusic, setup as setup_browser_auth

from .client import MusicClient
from .config import ImportConfig
from .importer import import_playlists
from .storage import (
    default_auth_file,
    default_cache_file,
    resolve_playlist_files,
    sanitize_auth_file,
)


AUTH_INSTRUCTIONS = (
    "To authenticate with YouTube Music:\n"
    "  1. Open https://music.youtube.com in Firefox, Chrome, or Edge and sign in.\n"
    "  2. Open Developer Tools (F12 -> Network), filter by 'browse', and click Library or Home.\n"
    "  3. Click an authenticated POST /youtubei/v1/browse request (status 200).\n"
    "  4. Copy the Request Headers (including 'authorization', 'cookie', and 'x-goog-authuser')."
)


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], MusicClient] = YTMusic,
    auth_setup: Callable[[str], object] = setup_browser_auth,
    is_interactive: Callable[[], bool] | None = None,
    output: Callable[[str], None] = print,
) -> None:
    defaults = ImportConfig()
    parser = argparse.ArgumentParser(
        description="Bulk import text-file playlists into YouTube Music."
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, default=(),
        help="Optional .txt playlist files or directories (default: playlists/ or current directory)",
    )
    parser.add_argument(
        "--playlists-dir", type=Path, default=None,
        help="Directory containing .txt playlist files (default: playlists)",
    )
    parser.add_argument(
        "--auth-file", type=Path, default=None,
        help="Browser authentication file (default: ./browser.json or user config directory)",
    )
    parser.add_argument(
        "--report-file", type=Path, default=defaults.report_file,
        help="CSV report path (default: import_report.csv)",
    )
    parser.add_argument(
        "--cache-file", type=Path, default=None,
        help="Search cache path (default: ./search_cache.json or user cache directory)",
    )
    parser.add_argument(
        "--reauth", action="store_true",
        help="Prompt for new browser authentication headers before importing",
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
    auth_file = args.auth_file if args.auth_file is not None else default_auth_file()
    cache_file = args.cache_file if args.cache_file is not None else default_cache_file()
    playlists_dir = (
        args.playlists_dir if args.playlists_dir is not None else defaults.playlists_dir
    )
    try:
        config = ImportConfig(
            playlists_dir=playlists_dir,
            auth_file=auth_file,
            report_file=args.report_file,
            cache_file=cache_file,
            privacy=args.privacy,
            min_score=args.min_score,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        files = resolve_playlist_files(args.paths, args.playlists_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    interactive = sys.stdin.isatty() if is_interactive is None else is_interactive()
    if args.reauth or not config.auth_file.is_file():
        if not interactive:
            raise SystemExit(
                f"Authentication file does not exist: {config.auth_file}. "
                "Run 'ytm-import' in an interactive terminal (or 'uv run ytmusicapi browser') "
                "and paste the Request Headers from an authenticated "
                "POST /youtubei/v1/browse request on https://music.youtube.com "
                "(DevTools -> Network -> Headers -> Request Headers, including "
                "'authorization', 'cookie', and 'x-goog-authuser')."
            )
        output(f"Setting up authentication file: {config.auth_file}\n{AUTH_INSTRUCTIONS}\n")
        config.auth_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            auth_setup(str(config.auth_file))
        except Exception as exc:
            raise SystemExit(f"Authentication setup failed: {exc}") from exc

    sanitize_auth_file(config.auth_file)
    client = client_factory(str(config.auth_file))
    import_playlists(client, files, config, output=output)
