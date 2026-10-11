"""Library state: background scanning, lookups, track ordering and edits.

This is the single owner of the scanned albums. UI code reads from it and asks
it to mutate state; it keeps persisted track orders, playlists and the Random
Mix consistent when files are renamed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from enderlitplayer.audio.queue import pick_random_album
from enderlitplayer.core.models import (
    ALL_TRACKS_ID,
    MIX_ID,
    VARIOUS_ARTISTS,
    Album,
    CollectionKind,
    Playlist,
    Track,
    make_id,
)
from enderlitplayer.library import ordering
from enderlitplayer.library.editing import EditResult, TrackEdit, TrackEditError, apply_track_edit
from enderlitplayer.library.scanner import ScanCancelled, scan_library
from enderlitplayer.playlists.manager import PlaylistManager
from enderlitplayer.playlists.mix import RandomMix
from enderlitplayer.services.covers import CoverSource
from enderlitplayer.storage.settings import SettingsStore

log = logging.getLogger(__name__)

PROGRESS_EVERY = 25


class ScanWorker(QObject):
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _report(self, count: int) -> None:
        if count % PROGRESS_EVERY == 0:
            self.progress.emit(count)

    @Slot()
    def run(self) -> None:
        try:
            albums = scan_library(self._path, progress=self._report, cancelled=lambda: self._cancelled)
        except FileNotFoundError:
            self.failed.emit("folder_not_found")
            return
        except ScanCancelled:
            self.failed.emit("cancelled")
            return
        except Exception:
            log.exception("Library scan failed")
            self.failed.emit("scan_failed")
            return
        self.finished.emit(albums)


class LibraryService(QObject):
    scanStarted = Signal(str)
    scanProgress = Signal(int)
    scanFinished = Signal()
    scanFailed = Signal(str)
    tracksChanged = Signal()

    def __init__(
        self,
        store: SettingsStore,
        playlists: PlaylistManager,
        mix: RandomMix,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self.playlists = playlists
        self.mix = mix
        self.albums: list[Album] = []
        self.has_scanned = False
        self._orders = store.load_track_orders()
        self._by_path: dict[str, Track] = {}
        self._albums_by_id: dict[str, Album] = {}
        self._thread: QThread | None = None
        self._scanning = False
        self._worker: ScanWorker | None = None

    # Scanning ------------------------------------------------------------------------
    @property
    def root_path(self) -> str:
        return self._store.library_path

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    def scan(self, path: str | None = None) -> bool:
        path = (path if path is not None else self.root_path).strip()
        if not path or self._scanning or self._thread is not None:
            return False
        self._store.library_path = path
        thread = QThread(self)
        worker = ScanWorker(path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.scanProgress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread, self._worker = thread, worker
        self._scanning = True
        self.scanStarted.emit(path)
        thread.start()
        return True

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)

    def _on_failed(self, reason: str) -> None:
        self._scanning = False
        if reason != "cancelled":
            self.scanFailed.emit(reason)

    def _on_finished(self, albums: list[Album]) -> None:
        self._scanning = False
        for album in albums:
            ordering.apply_saved_order(album, self._orders.get(album.id))
        self.set_albums(albums)
        self.has_scanned = True
        self.scanFinished.emit()

    def set_albums(self, albums: list[Album]) -> None:
        self.albums = albums
        self._reindex()

    def _reindex(self) -> None:
        self._albums_by_id = {album.id: album for album in self.albums}
        self._by_path = {track.path: track for album in self.albums for track in album.tracks}

    # Lookups -------------------------------------------------------------------------
    @property
    def tracks_by_path(self) -> dict[str, Track]:
        return self._by_path

    @property
    def track_count(self) -> int:
        return len(self._by_path)

    def album(self, album_id: str) -> Album | None:
        return self._albums_by_id.get(album_id)

    def track(self, path: str) -> Track | None:
        return self._by_path.get(path)

    def album_for_track(self, track: Track) -> Album | None:
        return self._albums_by_id.get(make_id(str(Path(track.path).parent)))

    def random_album(self, exclude_id: str | None) -> Album | None:
        return pick_random_album(self.albums, exclude_id)

    def library_collection(self, title: str) -> Album:
        tracks = [track for album in self.albums for track in album.tracks]
        return Album(
            id=ALL_TRACKS_ID,
            title=title,
            artist=VARIOUS_ARTISTS,
            year="",
            tracks=tracks,
            duration=sum(track.duration for track in tracks),
            kind=CollectionKind.LIBRARY,
        )

    def playlist_collection(self, playlist_id: str) -> Album | None:
        playlist = self.playlists.get(playlist_id)
        if playlist is None:
            return None
        return self.playlists.build_collection(playlist, self._by_path)

    def mix_collection(self, title: str, regenerate: bool = False) -> Album | None:
        if regenerate and self._by_path:
            self.mix.regenerate(list(self._by_path))
        return self.mix.build_collection(self._by_path, title)

    def resolve(self, kind: CollectionKind, collection_id: str, title: str = "") -> Album | None:
        """Fetch the current version of a collection (e.g. after a rescan)."""
        if kind == CollectionKind.ALBUM:
            return self.album(collection_id)
        if kind == CollectionKind.PLAYLIST:
            return self.playlist_collection(collection_id)
        if kind == CollectionKind.MIX and collection_id == MIX_ID:
            return self.mix_collection(title)
        if kind == CollectionKind.LIBRARY:
            return self.library_collection(title)
        return None

    # Artwork -------------------------------------------------------------------------
    @staticmethod
    def album_cover_source(album: Album) -> CoverSource | None:
        if not album.cover_bytes and not album.cover_path:
            return None
        return CoverSource(f"album:{album.id}", album.cover_bytes, album.cover_path)

    def playlist_cover_source(self, playlist: Playlist) -> CoverSource | None:
        if playlist.icon_path and Path(playlist.icon_path).is_file():
            return CoverSource(f"image:{playlist.icon_path}", path=playlist.icon_path)
        for path in playlist.track_paths:
            track = self._by_path.get(path)
            album = self.album_for_track(track) if track is not None else None
            source = self.album_cover_source(album) if album is not None else None
            if source is not None:
                return source
        return None

    def track_cover_source(self, track: Track) -> CoverSource | None:
        album = self.album_for_track(track)
        return self.album_cover_source(album) if album is not None else None

    def cover_source(self, collection: Album) -> CoverSource | None:
        if collection.kind == CollectionKind.ALBUM:
            return self.album_cover_source(collection)
        if collection.kind == CollectionKind.PLAYLIST:
            playlist = self.playlists.get(collection.id)
            return self.playlist_cover_source(playlist) if playlist is not None else None
        return None

    # Ordering ------------------------------------------------------------------------
    def _save_orders(self) -> None:
        try:
            self._store.save_track_orders(self._orders)
        except Exception:
            log.exception("Could not save track orders")

    def _persist_album_order(self, album: Album) -> None:
        self._orders[album.id] = ordering.order_paths(album)
        self._save_orders()

    def move_track(self, collection: Album, row: int, delta: int) -> int | None:
        """Move a track inside an album or playlist and persist the order."""
        if not collection.is_editable_order:
            return None
        target = ordering.move_item(collection.tracks, row, delta)
        if target is None:
            return None
        if collection.kind == CollectionKind.PLAYLIST:
            self.playlists.set_visible_order(collection.id, ordering.order_paths(collection))
        else:
            ordering.renumber(collection.tracks)
            self._persist_album_order(collection)
        return target

    # Editing -------------------------------------------------------------------------
    def edit_track(self, track: Track, edit: TrackEdit, collection: Album | None) -> EditResult:
        """Apply a metadata edit/rename and propagate path changes everywhere."""
        old_path = track.path
        try:
            result = apply_track_edit(track, edit)
        except TrackEditError:
            if track.title == edit.title.strip():
                # Tags were written but the rename failed: still refresh views.
                self.tracksChanged.emit()
            raise
        if result.renamed:
            self._on_renamed(old_path, result.new_path)
        album = self.album_for_track(track)
        if result.number_changed:
            self._apply_number_order(track, edit.track_no, collection, album)
        if album is not None:
            album.recompute()
        self.tracksChanged.emit()
        return result

    def _on_renamed(self, old_path: str, new_path: str) -> None:
        if ordering.replace_path(self._orders, old_path, new_path):
            self._save_orders()
        self.playlists.replace_path(old_path, new_path)
        self.mix.replace_path(old_path, new_path)
        stored_path, position, playing = self._store.load_playback()
        if stored_path == old_path:
            self._store.save_playback(new_path, position, playing)
        track = self._by_path.pop(old_path, None)
        if track is not None:
            self._by_path[new_path] = track

    def _apply_number_order(self, track: Track, number: int, collection: Album | None, album: Album | None) -> None:
        if collection is not None and collection.kind == CollectionKind.PLAYLIST:
            tracks = collection.tracks
            index = next((i for i, item in enumerate(tracks) if item.path == track.path), -1)
            if index >= 0:
                moved = tracks.pop(index)
                tracks.insert(max(0, min(len(tracks), number - 1)), moved)
                self.playlists.set_visible_order(collection.id, ordering.order_paths(collection))
            return
        if album is not None:
            album.tracks = ordering.sort_by_track_number(album.tracks)
            self._persist_album_order(album)
            if collection is not None and collection is not album and collection.kind == CollectionKind.ALBUM:
                collection.tracks = list(album.tracks)
