"""Asynchronous, cached cover-art decoding.

Decoding embedded artwork for hundreds of albums on the GUI thread makes
scrolling stutter, so images are decoded and scaled on a small thread pool and
cached as square pixmaps. Views repaint when :attr:`CoverProvider.coverReady`
fires for a key they display.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

log = logging.getLogger(__name__)

CACHE_LIMIT = 600
SIZE_STEP = 64


@dataclass(frozen=True)
class CoverSource:
    key: str
    data: bytes | None = None
    path: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.data and not self.path


def bucket_size(size: int) -> int:
    return max(SIZE_STEP, ((int(size) + SIZE_STEP - 1) // SIZE_STEP) * SIZE_STEP)


def load_square_image(source: CoverSource, size: int) -> QImage:
    """Decode and center-crop to a ``size``×``size`` image. Returns a null image on failure."""
    image = QImage()
    if source.data:
        image.loadFromData(source.data)
    if image.isNull() and source.path:
        image.load(source.path)
    if image.isNull():
        return QImage()
    scaled = image.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size) // 2)
    y = max(0, (scaled.height() - size) // 2)
    return scaled.copy(x, y, size, size)


class _Signals(QObject):
    loaded = Signal(str, int, QImage)


class _LoadTask(QRunnable):
    def __init__(self, source: CoverSource, size: int, signals: _Signals) -> None:
        super().__init__()
        self._source = source
        self._size = size
        self._signals = signals

    def run(self) -> None:
        try:
            image = load_square_image(self._source, self._size)
        except Exception:
            log.exception("Cover decoding failed for %s", self._source.key)
            image = QImage()
        self._signals.loaded.emit(self._source.key, self._size, image)


class CoverProvider(QObject):
    coverReady = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(3)
        self._signals = _Signals()
        self._signals.loaded.connect(self._on_loaded)
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._pending: set[tuple[str, int]] = set()
        self._missing: set[tuple[str, int]] = set()

    def pixmap(self, source: CoverSource | None, size: int) -> QPixmap | None:
        """Cached square pixmap for ``source`` at ≥ ``size`` device pixels, or None (loading/absent)."""
        if source is None or source.is_empty:
            return None
        cache_key = (source.key, bucket_size(size))
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached
        if cache_key in self._missing or cache_key in self._pending:
            return None
        self._pending.add(cache_key)
        self._pool.start(_LoadTask(source, cache_key[1], self._signals))
        return None

    def load_now(self, source: CoverSource | None, size: int) -> QPixmap | None:
        """Synchronous variant for single large covers (detail header, player bar)."""
        if source is None or source.is_empty:
            return None
        cache_key = (source.key, bucket_size(size))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        image = load_square_image(source, cache_key[1])
        if image.isNull():
            return None
        pixmap = QPixmap.fromImage(image)
        self._store(cache_key, pixmap)
        return pixmap

    def invalidate(self, key: str) -> None:
        for cache_key in [k for k in self._cache if k[0] == key]:
            del self._cache[cache_key]
        self._missing = {k for k in self._missing if k[0] != key}

    def clear(self) -> None:
        self._cache.clear()
        self._missing.clear()

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(3000)

    def _store(self, cache_key: tuple[str, int], pixmap: QPixmap) -> None:
        self._cache[cache_key] = pixmap
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)

    def _on_loaded(self, key: str, size: int, image: QImage) -> None:
        cache_key = (key, size)
        self._pending.discard(cache_key)
        if image.isNull():
            self._missing.add(cache_key)
            return
        self._store(cache_key, QPixmap.fromImage(image))
        self.coverReady.emit(key)
