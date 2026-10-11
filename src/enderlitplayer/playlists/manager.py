"""Playlist management and persistence.

Playlists are stored as a JSON list under the ``playlists`` settings key with the
same shape as 0.x: ``{"id", "title", "icon_path", "track_paths"}``.

Unlike 0.x, tracks that are not present in the current scan are *kept* in the
playlist (they are only hidden), so scanning a different or temporarily
unavailable folder no longer erases playlist contents.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from enderlitplayer.core.models import (
    PLAYLIST_ID_PREFIX,
    VARIOUS_ARTISTS,
    Album,
    CollectionKind,
    Playlist,
    Track,
    make_id,
)
from enderlitplayer.storage.settings import SettingsStore

log = logging.getLogger(__name__)


def _dedupe(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def parse_playlists(data: list[Any]) -> list[Playlist]:
    """Build playlists from stored data, skipping invalid entries and fixing duplicate ids."""
    playlists: list[Playlist] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        playlist_id = str(item.get("id") or make_id(f"playlist:{title}:{index}"))
        if playlist_id in seen_ids:
            playlist_id = make_id(f"{playlist_id}:{index}:{time.time_ns()}")
        seen_ids.add(playlist_id)
        raw_paths = item.get("track_paths", [])
        paths = [str(path) for path in raw_paths if path] if isinstance(raw_paths, list) else []
        playlists.append(
            Playlist(
                id=playlist_id,
                title=title,
                icon_path=str(item.get("icon_path", "") or ""),
                track_paths=_dedupe(paths),
            )
        )
    return playlists


class PlaylistManager:
    def __init__(self, store: SettingsStore) -> None:
        self._store = store
        self.playlists: list[Playlist] = parse_playlists(store.load_playlists_raw())

    def save(self) -> None:
        try:
            self._store.save_playlists_raw([playlist.to_dict() for playlist in self.playlists])
        except Exception:
            log.exception("Could not save playlists")

    def get(self, playlist_id: str) -> Playlist | None:
        return next((pl for pl in self.playlists if pl.id == playlist_id), None)

    def create(self, title: str, icon_path: str = "") -> Playlist:
        title = title.strip()
        if not title:
            raise ValueError("Playlist title is required")
        playlist = Playlist(
            id=f"{PLAYLIST_ID_PREFIX}{make_id(f'{title}:{time.time_ns()}')}",
            title=title,
            icon_path=icon_path.strip(),
        )
        self.playlists.append(playlist)
        self.save()
        return playlist

    def delete(self, playlist_id: str) -> bool:
        before = len(self.playlists)
        self.playlists = [pl for pl in self.playlists if pl.id != playlist_id]
        if len(self.playlists) == before:
            return False
        self.save()
        return True

    def update(self, playlist_id: str, title: str | None = None, icon_path: str | None = None) -> bool:
        playlist = self.get(playlist_id)
        if playlist is None:
            return False
        if title is not None and title.strip():
            playlist.title = title.strip()
        if icon_path is not None:
            playlist.icon_path = icon_path.strip()
        self.save()
        return True

    def add_tracks(self, playlist_id: str, paths: Iterable[str]) -> int:
        playlist = self.get(playlist_id)
        if playlist is None:
            return 0
        existing = set(playlist.track_paths)
        added = [path for path in _dedupe(paths) if path not in existing]
        if added:
            playlist.track_paths.extend(added)
            self.save()
        return len(added)

    def remove_track(self, playlist_id: str, path: str) -> bool:
        playlist = self.get(playlist_id)
        if playlist is None or path not in playlist.track_paths:
            return False
        playlist.track_paths = [p for p in playlist.track_paths if p != path]
        self.save()
        return True

    def set_visible_order(self, playlist_id: str, visible_paths: list[str]) -> bool:
        """Persist a new order for the visible tracks; hidden (missing) tracks are kept at the end."""
        playlist = self.get(playlist_id)
        if playlist is None:
            return False
        visible = _dedupe(visible_paths)
        visible_set = set(visible)
        hidden = [path for path in playlist.track_paths if path not in visible_set]
        new_paths = visible + hidden
        if new_paths == playlist.track_paths:
            return False
        playlist.track_paths = new_paths
        self.save()
        return True

    def replace_path(self, old_path: str, new_path: str) -> bool:
        changed = False
        for playlist in self.playlists:
            if old_path in playlist.track_paths:
                playlist.track_paths = _dedupe(new_path if path == old_path else path for path in playlist.track_paths)
                changed = True
        if changed:
            self.save()
        return changed

    @staticmethod
    def resolve_tracks(playlist: Playlist, by_path: Mapping[str, Track]) -> list[Track]:
        return [by_path[path] for path in playlist.track_paths if path in by_path]

    def build_collection(self, playlist: Playlist, by_path: Mapping[str, Track]) -> Album:
        tracks = self.resolve_tracks(playlist, by_path)
        icon = playlist.icon_path if playlist.icon_path and Path(playlist.icon_path).is_file() else None
        return Album(
            id=playlist.id,
            title=playlist.title,
            artist=VARIOUS_ARTISTS,
            year="",
            tracks=tracks,
            duration=sum(track.duration for track in tracks),
            cover_path=icon,
            kind=CollectionKind.PLAYLIST,
        )
