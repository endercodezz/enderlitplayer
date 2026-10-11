"""Plain data models shared by every layer. No Qt imports here."""

from enderlitplayer.core.models import (
    ALL_TRACKS_ID,
    MIX_ID,
    PLAYLIST_ID_PREFIX,
    UNKNOWN_ARTIST,
    VARIOUS_ARTISTS,
    Album,
    CollectionKind,
    Playlist,
    Track,
    make_id,
    summarize_artist,
)

__all__ = [
    "ALL_TRACKS_ID",
    "MIX_ID",
    "PLAYLIST_ID_PREFIX",
    "UNKNOWN_ARTIST",
    "VARIOUS_ARTISTS",
    "Album",
    "CollectionKind",
    "Playlist",
    "Track",
    "make_id",
    "summarize_artist",
]
