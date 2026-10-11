"""Library data models.

An :class:`Album` doubles as a generic playable *collection*: real folder albums,
playlists, the Random Mix and the "all songs" view are all represented by it and
distinguished by :attr:`Album.kind`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

UNKNOWN_ARTIST = "Unknown Artist"
VARIOUS_ARTISTS = "Various Artists"

MIX_ID = "mix_random"
ALL_TRACKS_ID = "library_all"
PLAYLIST_ID_PREFIX = "playlist_"


def make_id(value: str) -> str:
    """Stable short identifier. Album ids derived from it key persisted track orders."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


class CollectionKind(str, Enum):
    ALBUM = "album"
    PLAYLIST = "playlist"
    MIX = "mix"
    LIBRARY = "library"


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    album_artist: str
    year: str
    track_no: int
    disc_no: int
    duration: float
    path: str

    @property
    def file_name(self) -> str:
        return Path(self.path).name

    @property
    def folder(self) -> str:
        return str(Path(self.path).parent)


@dataclass(eq=False)
class Album:
    id: str
    title: str
    artist: str
    year: str
    tracks: list[Track]
    duration: float
    cover_path: str | None = None
    cover_bytes: bytes | None = None
    cover_mime: str | None = None
    kind: CollectionKind = CollectionKind.ALBUM

    def same_collection(self, other: Album | None) -> bool:
        return other is not None and other.id == self.id and other.kind == self.kind

    def index_of(self, track_id: str) -> int:
        for index, track in enumerate(self.tracks):
            if track.id == track_id:
                return index
        return -1

    def recompute(self) -> None:
        """Refresh derived fields after tracks were edited or reordered."""
        self.duration = sum(track.duration for track in self.tracks)
        if self.kind == CollectionKind.ALBUM:
            self.artist = summarize_artist(self.tracks)

    @property
    def is_editable_order(self) -> bool:
        return self.kind in (CollectionKind.ALBUM, CollectionKind.PLAYLIST)


@dataclass
class Playlist:
    id: str
    title: str
    icon_path: str = ""
    track_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "icon_path": self.icon_path,
            "track_paths": list(self.track_paths),
        }


def summarize_artist(tracks: list[Track]) -> str:
    artists = {track.artist for track in tracks if track.artist}
    if len(artists) == 1:
        return next(iter(artists))
    if not artists:
        return UNKNOWN_ARTIST
    return VARIOUS_ARTISTS
