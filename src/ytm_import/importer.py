"""Track selection and import orchestration, independent of authentication."""

import csv
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .client import MusicClient, Track
from .config import ImportConfig
from .matching import (
    artist_names,
    clean_line,
    normalize,
    result_score,
    track_variants,
)
from .search import SearchResult, SongSearcher
from .storage import load_cache, read_text_lines, save_cache


@dataclass(frozen=True)
class ReportRow:
    playlist: str
    line: int
    source: str
    matched_title: str = ""
    matched_artists: str = ""
    video_id: str = ""
    confidence: str = "0.000"
    status: str = "NOT_FOUND"


def _format_row(row: ReportRow) -> str:
    if row.matched_artists and row.matched_title:
        matched = f"{row.matched_artists} - {row.matched_title}"
    else:
        matched = row.matched_title or row.matched_artists
    if matched:
        return f"  {row.status:24} {row.source} -> {matched}"
    return f"  {row.status:24} {row.source}"


def _is_already_in_playlist(response: object) -> bool:
    """Detect YouTube Music's duplicate-track rejection when duplicates=False."""
    if not isinstance(response, dict) or response.get("status") != "STATUS_FAILED":
        return False
    actions = response.get("actions")
    return isinstance(actions, list) and "DEDUPE_OPTION_SKIP" in str(actions)


def _remember_track(known_tracks: dict[str, Track | None], track: Track) -> None:
    """Index exact metadata matches, leaving ambiguous names for the searcher."""
    if not track.get("videoId"):
        return
    for variant in track_variants(track):
        key = normalize(variant)
        if not key:
            continue
        if key not in known_tracks:
            known_tracks[key] = track
        elif (previous := known_tracks[key]) is not None:
            if previous["videoId"] != track["videoId"]:
                known_tracks[key] = None


def match_tracks(
    playlist_title: str,
    lines: Iterable[str],
    search: Callable[[str], SearchResult],
    *,
    min_score: float = 0.58,
    existing_tracks: Iterable[Track] = (),
) -> Iterator[ReportRow]:
    """Match missing tracks, avoiding searches for known playlist compositions."""
    existing_video_ids: set[str] = set()
    known_tracks: dict[str, Track | None] = {}
    query_matches: dict[str, SearchResult] = {}
    for track in existing_tracks:
        if track.get("videoId"):
            existing_video_ids.add(str(track["videoId"]))
            _remember_track(known_tracks, track)
    seen_video_ids = existing_video_ids.copy()
    for line_number, raw_line in enumerate(lines, start=1):
        query = clean_line(raw_line)
        if not query:
            continue

        key = normalize(query)
        known_track = known_tracks.get(key)
        if key in query_matches:
            match = query_matches[key]
        elif known_track is not None:
            match = SearchResult(
                known_track, result_score(query, known_track), "PLAYLIST",
            )
        else:
            match = search(query)
        if not match.source.startswith("ERROR"):
            query_matches[key] = match
        status = "NOT_FOUND"
        matched_title = ""
        matched_artists = ""
        video_id = ""

        if match.result is not None:
            matched_title = str(match.result.get("title", ""))
            matched_artists = artist_names(match.result)
            video_id = str(match.result.get("videoId") or "")

            if not video_id:
                status = "NOT_FOUND"
            elif match.score < min_score:
                status = "LOW_CONFIDENCE_SKIPPED"
            elif video_id in existing_video_ids:
                status = "ALREADY_PRESENT"
            elif video_id in seen_video_ids:
                status = "DUPLICATE_SKIPPED"
            else:
                status = "ADDED"
                seen_video_ids.add(video_id)
                _remember_track(known_tracks, match.result)

        if match.source.startswith("ERROR"):
            status = match.source

        yield ReportRow(
            playlist=playlist_title,
            line=line_number,
            source=query,
            matched_title=matched_title,
            matched_artists=matched_artists,
            video_id=video_id,
            confidence=f"{match.score:.3f}",
            status=status,
        )


def import_playlists(
    client: MusicClient,
    files: Iterable[Path],
    config: ImportConfig,
    *,
    sleep: Callable[[float], None] | None = None,
    output: Callable[[str], None] = print,
) -> None:
    """Resume named playlists, checking remote membership before adding tracks."""
    playlists: dict[str, str] = {}
    for item in client.get_library_playlists(limit=None):
        if item.get("owned", True):
            title = str(item.get("title", ""))
            playlist_id = item.get("playlistId") or item.get("id")
            if not playlist_id:
                raise RuntimeError(f"Missing ID for existing playlist {title!r}")
            playlists.setdefault(title.casefold(), str(playlist_id))
    playlist_tracks: dict[str, list[Track]] = {}
    cache = load_cache(config.cache_file)
    searcher = SongSearcher(
        client,
        cache,
        search_delay=config.search_delay,
        max_retries=config.max_retries,
        sleep=sleep,
    )

    try:
        with config.report_file.open("w", newline="", encoding="utf-8-sig") as report:
            writer = csv.DictWriter(
                report, fieldnames=[field.name for field in fields(ReportRow)]
            )
            writer.writeheader()
            report.flush()

            for txt_file in files:
                playlist_title = txt_file.stem
                playlist_id = playlists.get(playlist_title.casefold())
                existed = playlist_id is not None
                lines = read_text_lines(txt_file)
                if playlist_id is not None and playlist_id not in playlist_tracks:
                    playlist = client.get_playlist(playlist_id, limit=None)
                    if not isinstance(playlist.get("tracks"), list):
                        raise RuntimeError(
                            f"Unable to read playlist {playlist_title!r}: {playlist}"
                        )
                    playlist_tracks[playlist_id] = playlist["tracks"]

                added = 0
                output(f"\n[{playlist_title}]")
                for row in match_tracks(
                    playlist_title, lines, searcher.search,
                    min_score=config.min_score,
                    existing_tracks=playlist_tracks.get(playlist_id, []),
                ):
                    # Persist the query-to-ID mapping before a request that may
                    # succeed remotely even if its response never reaches us.
                    save_cache(config.cache_file, cache)
                    if row.status == "ADDED":
                        try:
                            if playlist_id is None:
                                response = client.create_playlist(
                                    title=playlist_title,
                                    description="Imported from a text file.",
                                    privacy_status=config.privacy,
                                    video_ids=[row.video_id],
                                )
                                if not isinstance(response, str) or not response:
                                    raise RuntimeError(
                                        f"Unable to create playlist {playlist_title!r}: {response}"
                                    )
                                playlist_id = response
                                playlists[playlist_title.casefold()] = playlist_id
                                playlist_tracks[playlist_id] = []
                                added += 1
                            else:
                                response = client.add_playlist_items(
                                    playlist_id, [row.video_id], duplicates=False,
                                )
                                status = (
                                    response.get("status")
                                    if isinstance(response, dict) else response
                                )
                                if _is_already_in_playlist(response):
                                    row = replace(row, status="ALREADY_PRESENT")
                                elif status != "STATUS_SUCCEEDED":
                                    raise RuntimeError(
                                        f"Unable to add track to playlist {playlist_title!r}: {response}"
                                    )
                                else:
                                    added += 1
                            playlist_tracks[playlist_id].append(
                                cache[normalize(row.source)]["result"]
                            )
                        except Exception as exc:
                            failed_row = replace(
                                row, status=f"ERROR: {type(exc).__name__}: {exc}",
                            )
                            writer.writerow(asdict(failed_row))
                            report.flush()
                            output(_format_row(failed_row))
                            raise
                    writer.writerow(asdict(row))
                    report.flush()
                    output(_format_row(row))

                if playlist_id is None:
                    output("  Playlist not created: no confident song matches.")
                else:
                    action = "UPDATED" if existed else "CREATED"
                    output(f"{action}: {playlist_title} — {added} songs added")
    finally:
        # Also retain results when interrupted during search or its retry delay.
        save_cache(config.cache_file, cache)
    output(f"\nDone. Report: {config.report_file}")
