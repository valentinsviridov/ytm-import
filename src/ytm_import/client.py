"""The small portion of the YouTube Music API used by the importer."""

from typing import Any, Literal, Protocol, TypeAlias


Track: TypeAlias = dict[str, Any]
SearchCache: TypeAlias = dict[str, dict[str, Any]]


class MusicClient(Protocol):
    def search(
        self, query: str, *, filter: Literal["songs"], limit: int
    ) -> list[Track]: ...

    def get_library_playlists(
        self, *, limit: int | None
    ) -> list[dict[str, Any]]: ...

    def get_playlist(
        self, playlistId: str, *, limit: int | None
    ) -> dict[str, Any]: ...

    def create_playlist(
        self,
        *,
        title: str,
        description: str,
        privacy_status: str,
        video_ids: list[str],
    ) -> str | dict[str, Any]: ...

    def add_playlist_items(
        self, playlistId: str, videoIds: list[str], *, duplicates: bool
    ) -> str | dict[str, Any]: ...
