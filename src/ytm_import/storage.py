"""Local playlist and cache files; every path is supplied by the caller."""

from collections.abc import Sequence
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .client import SearchCache


APP_DIR_NAME = "ytm-import"


def default_auth_file() -> Path:
    """Prefer a local browser.json in the working directory; otherwise use user config."""
    local = Path("browser.json")
    if local.is_file():
        return local
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / APP_DIR_NAME / "browser.json"


def default_cache_file() -> Path:
    """Prefer a local search_cache.json in the working directory; otherwise use user cache."""
    local = Path("search_cache.json")
    if local.is_file():
        return local
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / APP_DIR_NAME / "search_cache.json"


def find_playlist_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Playlist directory does not exist: {directory}")
    files = sorted(path for path in directory.glob("*.txt") if path.is_file())
    if not files:
        raise ValueError(f"No .txt playlist files found in {directory}")
    return files


def resolve_playlist_files(
    paths: Sequence[Path] = (),
    playlists_dir: Path | None = None,
) -> list[Path]:
    """Resolve explicit .txt files/directories, --playlists-dir, ./playlists, or CWD .txt files."""
    if paths and playlists_dir is not None:
        raise ValueError("Specify either positional playlist paths or --playlists-dir, not both")

    if paths:
        resolved: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path.is_dir():
                candidates = find_playlist_files(path)
            elif path.is_file():
                if path.suffix.lower() != ".txt":
                    raise ValueError(f"Playlist file must end with .txt: {path}")
                candidates = [path]
            else:
                raise FileNotFoundError(f"Playlist path does not exist: {path}")
            for candidate in candidates:
                key = candidate.resolve()
                if key not in seen:
                    seen.add(key)
                    resolved.append(candidate)
        return resolved

    if playlists_dir is not None:
        return find_playlist_files(playlists_dir)

    default_dir = Path("playlists")
    if default_dir.is_dir():
        return find_playlist_files(default_dir)

    cwd_files = sorted(path for path in Path(".").glob("*.txt") if path.is_file())
    if cwd_files:
        return cwd_files

    raise FileNotFoundError(
        "Playlist directory does not exist: playlists (and no .txt playlist files found in the current directory)"
    )


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
    path.parent.mkdir(parents=True, exist_ok=True)
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
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass
