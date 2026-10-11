"""Folder scanning. Albums are grouped by containing folder, not by tags."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from mutagen import MutagenError

from enderlitplayer.core.models import Album, Track, make_id, summarize_artist
from enderlitplayer.library.metadata import (
    extract_embedded_cover,
    find_cover_in_folder,
    is_audio_file,
    read_tags,
)

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int], None]
CancelCheck = Callable[[], bool]


class ScanCancelled(Exception):
    pass


def default_scan_path() -> str | None:
    env_path = os.environ.get("MUSIC_DIR")
    if env_path:
        return os.path.expanduser(env_path)
    home = Path.home()
    for candidate in (home / "Music", home / "music"):
        if candidate.is_dir():
            return str(candidate)
    return None


def iter_audio_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda err: log.warning("%s", err)):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if is_audio_file(path):
                files.append(path)
    return files


def track_sort_key(track: Track) -> tuple[int, int, str]:
    return (track.disc_no or 0, track.track_no or 0, track.title or "")


def scan_library(
    root_path: str,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> list[Album]:
    """Scan ``root_path`` recursively and return albums sorted by artist and title.

    Unreadable files are skipped; a single bad file never aborts the scan.
    Raises ``FileNotFoundError`` when the root folder does not exist.
    """
    root = Path(root_path).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(root_path)

    albums: dict[str, Album] = {}
    for count, file_path in enumerate(iter_audio_files(root), start=1):
        if cancelled is not None and cancelled():
            raise ScanCancelled
        if progress is not None:
            progress(count)
        try:
            tags = read_tags(file_path)
        except (MutagenError, OSError, ValueError) as exc:
            log.info("Skipping unreadable file %s: %s", file_path, exc)
            continue
        except Exception:
            log.exception("Unexpected error while reading %s", file_path)
            continue

        folder = file_path.parent
        album_id = make_id(str(folder))
        album = albums.get(album_id)
        if album is None:
            album = Album(id=album_id, title=folder.name, artist="", year="", tracks=[], duration=0.0)
            albums[album_id] = album

        album.tracks.append(
            Track(
                id=make_id(str(file_path)),
                title=tags.title,
                artist=tags.artist,
                album=folder.name,
                album_artist=tags.album_artist,
                year=tags.year,
                track_no=tags.track_no,
                disc_no=tags.disc_no,
                duration=tags.duration,
                path=str(file_path),
            )
        )
        album.duration += tags.duration

        if album.cover_bytes is None:
            embedded = extract_embedded_cover(file_path)
            if embedded:
                album.cover_mime, album.cover_bytes = embedded

    for album in albums.values():
        album.tracks.sort(key=track_sort_key)
        album.artist = summarize_artist(album.tracks)
        years = [track.year for track in album.tracks if track.year]
        album.year = years[0] if years else ""
        if album.cover_bytes is None and album.tracks:
            image = find_cover_in_folder(Path(album.tracks[0].path).parent)
            if image is not None:
                album.cover_path = str(image)

    return sorted(albums.values(), key=lambda a: (a.artist.casefold(), a.title.casefold()))
