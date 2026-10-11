"""Media backend abstraction.

:class:`PlaybackController` talks to a :class:`MediaBackend`; the production
implementation wraps ``QMediaPlayer``. Tests substitute an in-memory backend so no
audio device is required.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

log = logging.getLogger(__name__)


class MediaBackend(QObject):
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playingChanged = Signal(bool)
    mediaLoaded = Signal()
    mediaEnded = Signal()
    errorOccurred = Signal(str)

    def set_source(self, path: str) -> None:
        raise NotImplementedError

    def clear_source(self) -> None:
        raise NotImplementedError

    def play(self) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def position(self) -> int:
        raise NotImplementedError

    def set_position(self, position_ms: int) -> None:
        raise NotImplementedError

    def duration(self) -> int:
        raise NotImplementedError

    def is_playing(self) -> bool:
        raise NotImplementedError

    def set_volume(self, volume: float) -> None:
        raise NotImplementedError


class QtMediaBackend(MediaBackend):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        # QMediaPlayer emits qint64; re-emit as Python ints.
        self._player.positionChanged.connect(lambda value: self.positionChanged.emit(int(value)))
        self._player.durationChanged.connect(lambda value: self.durationChanged.emit(int(value)))
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        self.playingChanged.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.mediaEnded.emit()
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.mediaLoaded.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.errorOccurred.emit(self._player.errorString() or "invalid media")

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            log.warning("Playback error: %s", message)
            self.errorOccurred.emit(message)

    def set_source(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path))

    def clear_source(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def position(self) -> int:
        return int(self._player.position())

    def set_position(self, position_ms: int) -> None:
        self._player.setPosition(int(position_ms))

    def duration(self) -> int:
        return int(self._player.duration())

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def set_volume(self, volume: float) -> None:
        self._output.setVolume(max(0.0, min(1.0, volume)))
