"""Local playlist and cache files; every path is supplied by the caller."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .client import SearchCache


def find_playlist_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Playlist directory does not exist: {directory}")
    files = sorted(path for path in directory.glob("*.txt") if path.is_file())
    if not files:
        raise ValueError(f"No .txt playlist files found in {directory}")
    return files


def read_text_lines(path: Path) -> list[str]:
    """Read UTF-8 (with or without a BOM), falling back to Windows-1251."""
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return path.read_text(encoding=encoding).splitlines()
        except UnicodeDecodeError:
            pass
    raise UnicodeError(f"Unable to determine file encoding: {path}")


def load_cache(path: Path) -> SearchCache:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, cache: SearchCache) -> None:
    """Replace the cache atomically so interruptions preserve the previous copy."""
    contents = json.dumps(cache, ensure_ascii=False, indent=2)
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def sanitize_auth_file(path: Path) -> None:
    """Remove HTTP request lines or blank keys left by ytmusicapi browser setup."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    cleaned = {
        key: value
        for key, value in data.items()
        if isinstance(key, str) and key and not any(ch.isspace() for ch in key)
    }
    if len(cleaned) != len(data):
        path.write_text(
            json.dumps(cleaned, ensure_ascii=True, indent=4, sort_keys=True),
            encoding="utf-8",
        )
