"""Playback coordination: current track/collection, navigation, persistence."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from enderlitplayer.audio.backend import MediaBackend
from enderlitplayer.audio.queue import next_step, previous_step
from enderlitplayer.core.models import Album, Track
from enderlitplayer.storage.settings import SettingsStore

log = logging.getLogger(__name__)

RandomAlbumProvider = Callable[[str | None], Album | None]
SAVE_DELAY_MS = 1200


@dataclass
class SuspendedPlayback:
    """Snapshot taken while the current file is released (e.g. for renaming)."""

    position_ms: int
    playing: bool


class PlaybackController(QObject):
    trackChanged = Signal(object, object)  # Track | None, Album | None
    playingChanged = Signal(bool)
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    volumeChanged = Signal(int)
    mutedChanged = Signal(bool)
    playbackFailed = Signal(str)  # path of the track that could not be played

    def __init__(
        self,
        backend: MediaBackend,
        store: SettingsStore,
        random_album: RandomAlbumProvider | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._store = store
        self._random_album = random_album
        self.track: Track | None = None
        self.collection: Album | None = None
        self._playing = False
        self._position = 0
        self._duration = 0
        self._pending_seek: int | None = None
        self._resume_after_load = False
        self._failures = 0
        self._volume = store.volume
        self._muted = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_state)

        backend.set_volume(self._volume / 100.0)
        backend.positionChanged.connect(self._on_position)
        backend.durationChanged.connect(self._on_duration)
        backend.playingChanged.connect(self._on_playing)
        backend.mediaLoaded.connect(self._on_loaded)
        backend.mediaEnded.connect(self.next)
        backend.errorOccurred.connect(self._on_error)

    # State ---------------------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def position(self) -> int:
        return self._position

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    def is_current(self, track: Track | None) -> bool:
        return track is not None and self.track is not None and track.path == self.track.path

    # Commands ------------------------------------------------------------------------
    def play_track(self, track: Track, collection: Album | None = None) -> None:
        self._failures = 0
        self._start(track, collection or self.collection, autoplay=True)

    def play_collection(self, collection: Album, start_index: int = 0) -> None:
        if not collection.tracks:
            return
        index = max(0, min(start_index, len(collection.tracks) - 1))
        self.play_track(collection.tracks[index], collection)

    def _start(self, track: Track, collection: Album | None, autoplay: bool, position_ms: int = 0) -> None:
        self.track = track
        self.collection = collection
        self._position = position_ms
        self._duration = int(track.duration * 1000)
        self._pending_seek = position_ms if position_ms > 0 else None
        self._resume_after_load = autoplay
        self.trackChanged.emit(track, collection)
        self.positionChanged.emit(self._position)
        self.durationChanged.emit(self._duration)
        if not os.path.isfile(track.path):
            log.warning("Track file is missing: %s", track.path)
            self._handle_failure()
            return
        self._backend.set_source(track.path)
        if autoplay:
            self._backend.play()
        else:
            self._backend.pause()
            self._set_playing(False)
        self.save_state()

    def restore(self, track: Track, collection: Album, position_ms: int) -> None:
        """Load the last played track paused at its saved position (0.x behaviour)."""
        self._start(track, collection, autoplay=False, position_ms=max(0, position_ms))

    def toggle(self) -> None:
        if self.track is None:
            return
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if self.track is None:
            return
        self._backend.play()
        self._set_playing(True)
        self.save_state()

    def pause(self) -> None:
        if self.track is None:
            return
        self._backend.pause()
        self._set_playing(False)
        self.save_state()

    def next(self) -> None:
        if self.track is None or self.collection is None:
            return
        step = next_step(self.collection, self.track)
        if step is not None:
            self._start(step.track, step.collection, autoplay=True)
            return
        if self.collection.index_of(self.track.id) < 0:
            return
        album = self._random_album(self.collection.id) if self._random_album else None
        if album is not None and album.tracks:
            self._start(album.tracks[0], album, autoplay=True)

    def previous(self) -> None:
        if self.track is None or self.collection is None:
            return
        step = previous_step(self.collection, self.track, self._backend.position())
        if step is None:
            self.seek(0)
            return
        self._start(step.track, step.collection, autoplay=True)

    def seek(self, position_ms: int) -> None:
        if self.track is None:
            return
        self._backend.set_position(max(0, int(position_ms)))
        self._position = max(0, int(position_ms))
        self.positionChanged.emit(self._position)
        self._schedule_save()

    def set_volume(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if value == self._volume and not self._muted:
            return
        self._volume = value
        self._muted = False
        self._backend.set_volume(value / 100.0)
        self._store.volume = value
        self.volumeChanged.emit(value)
        self.mutedChanged.emit(False)

    def set_muted(self, muted: bool) -> None:
        if muted == self._muted:
            return
        self._muted = muted
        self._backend.set_volume(0.0 if muted else self._volume / 100.0)
        self.mutedChanged.emit(muted)

    def update_collection(self, collection: Album) -> None:
        """Swap in an updated copy of the playing collection (reorder, playlist edits, rescan)."""
        if self.collection is not None and self.collection.same_collection(collection):
            self.collection = collection
            if self.track is not None:
                replacement = next((t for t in collection.tracks if t.path == self.track.path), None)
                if replacement is not None:
                    self.track = replacement

    def rebind(self, track: Track, collection: Album | None) -> None:
        """Point the controller at fresh objects for the *same* file (after a rescan)."""
        self.track = track
        if collection is not None:
            self.collection = collection
        self.trackChanged.emit(self.track, self.collection)

    def suspend(self) -> SuspendedPlayback | None:
        """Release the current file so it can be renamed/re-tagged."""
        if self.track is None:
            return None
        snapshot = SuspendedPlayback(self._backend.position(), self._playing)
        self._backend.clear_source()
        return snapshot

    def resume(self, snapshot: SuspendedPlayback | None) -> None:
        if snapshot is None or self.track is None:
            return
        self._pending_seek = snapshot.position_ms or None
        self._resume_after_load = snapshot.playing
        self._backend.set_source(self.track.path)
        if snapshot.playing:
            self._backend.play()
        else:
            self._backend.pause()
        self.trackChanged.emit(self.track, self.collection)
        self.save_state()

    def stop(self) -> None:
        self._backend.clear_source()
        self.track = None
        self.collection = None
        self._set_playing(False)
        self.trackChanged.emit(None, None)

    # Persistence ---------------------------------------------------------------------
    def _schedule_save(self) -> None:
        if not self._save_timer.isActive():
            self._save_timer.start()

    def save_state(self) -> None:
        self._save_timer.stop()
        if self.track is None:
            return
        try:
            self._store.save_playback(self.track.path, self._position, self._playing)
        except Exception:
            log.exception("Could not persist playback state")

    # Backend events ------------------------------------------------------------------
    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.playingChanged.emit(playing)

    def _on_playing(self, playing: bool) -> None:
        if playing:
            self._failures = 0
        self._set_playing(playing)

    def _on_position(self, position: int) -> None:
        if self._pending_seek is not None:
            return
        self._position = int(position)
        self.positionChanged.emit(self._position)
        if self.track is not None:
            self._schedule_save()

    def _on_duration(self, duration: int) -> None:
        if duration > 0:
            self._duration = int(duration)
            self.durationChanged.emit(self._duration)

    def _on_loaded(self) -> None:
        if self._pending_seek is None:
            return
        target = self._pending_seek
        self._pending_seek = None
        self._backend.set_position(target)
        self._position = target
        self.positionChanged.emit(target)
        if not self._resume_after_load:
            self._backend.pause()
            self._set_playing(False)

    def _on_error(self, message: str) -> None:
        log.warning("Cannot play %s: %s", self.track.path if self.track else "?", message)
        self._handle_failure()

    def _handle_failure(self) -> None:
        failed = self.track
        self._pending_seek = None
        self._set_playing(False)
        if failed is not None:
            self.playbackFailed.emit(failed.path)
        if not self._resume_after_load or failed is None or self.collection is None:
            return
        # Skip forward, but never loop forever over a collection of broken files.
        self._failures += 1
        if self._failures >= max(1, len(self.collection.tracks)):
            self._backend.clear_source()
            return
        step = next_step(self.collection, failed)
        if step is not None:
            self._start(step.track, step.collection, autoplay=True)
