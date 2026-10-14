"""Import settings, independent of the CLI and process working directory."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportConfig:
    playlists_dir: Path = Path("playlists")
    auth_file: Path = Path("browser.json")
    report_file: Path = Path("import_report.csv")
    cache_file: Path = Path("search_cache.json")
    privacy: str = "PRIVATE"
    min_score: float = 0.58
    search_delay: float = 0.35
    max_retries: int = 5

    def __post_init__(self) -> None:
        if self.privacy not in {"PRIVATE", "UNLISTED", "PUBLIC"}:
            raise ValueError("privacy must be PRIVATE, UNLISTED, or PUBLIC")
        if not 0 <= self.min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")
        if not self.search_delay >= 0:
            raise ValueError("search_delay must be nonnegative")
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
