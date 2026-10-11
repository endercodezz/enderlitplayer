"""Typed access to the application's QSettings store.

The organization/application identifiers and every key name are identical to the
0.x releases, so upgrading keeps playlists, track orders, preferences and playback
state. Values are parsed defensively because QSettings backends (registry, plist,
INI) return different Python types for the same stored value.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from enderlitplayer import APPLICATION_NAME, ORGANIZATION_NAME

log = logging.getLogger(__name__)

LANGUAGES = ("en", "ru")
THEMES = ("dark", "light")
COVER_STYLES = ("rounded", "square")
PAGES = ("songs", "albums", "playlists", "mix")


class Keys:
    LANGUAGE = "language"
    THEME = "theme"
    COVER_STYLE = "cover_style"
    LIBRARY_MODE = "library_mode"
    LIBRARY_PATH = "library_path"
    PLAYLISTS = "playlists"
    TRACK_ORDERS = "track_orders"
    VOLUME = "volume"
    LAST_TRACK_PATH = "last_track_path"
    LAST_POSITION = "last_position"
    LAST_PLAYING = "last_playing"
    MIX_TRACKS = "mix_tracks"
    MIX_UPDATED_AT = "mix_updated_at"
    # Added in 2.0.0
    WINDOW_GEOMETRY = "window_geometry"


def _to_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, QByteArray):
        raw = raw.data()
    if isinstance(raw, (bytes, bytearray)):
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return ""
    return str(raw)


def parse_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default


def parse_int(raw: Any, default: int = 0) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def parse_float(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def parse_json(raw: Any, expected: type) -> Any:
    """Decode a JSON value stored as text; tolerate already-decoded containers."""
    if isinstance(raw, expected):
        return raw
    text = _to_text(raw)
    if not text:
        return expected()
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        log.warning("Ignoring malformed JSON setting")
        return expected()
    return data if isinstance(data, expected) else expected()


class SettingsStore:
    """Thin typed wrapper. Pass a custom ``QSettings`` (e.g. INI in a temp dir) in tests."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings(ORGANIZATION_NAME, APPLICATION_NAME)

    @property
    def qsettings(self) -> QSettings:
        return self._settings

    def value(self, key: str, default: Any = None) -> Any:
        return self._settings.value(key, default)

    def set_value(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)

    def sync(self) -> None:
        self._settings.sync()

    def _choice(self, key: str, choices: tuple[str, ...], default: str) -> str:
        value = _to_text(self._settings.value(key, default)).strip()
        return value if value in choices else default

    # Preferences -----------------------------------------------------------------
    @property
    def language(self) -> str:
        return self._choice(Keys.LANGUAGE, LANGUAGES, "ru")

    @language.setter
    def language(self, value: str) -> None:
        if value in LANGUAGES:
            self.set_value(Keys.LANGUAGE, value)

    @property
    def theme(self) -> str:
        return self._choice(Keys.THEME, THEMES, "dark")

    @theme.setter
    def theme(self, value: str) -> None:
        if value in THEMES:
            self.set_value(Keys.THEME, value)

    @property
    def cover_style(self) -> str:
        return self._choice(Keys.COVER_STYLE, COVER_STYLES, "rounded")

    @cover_style.setter
    def cover_style(self, value: str) -> None:
        if value in COVER_STYLES:
            self.set_value(Keys.COVER_STYLE, value)

    @property
    def library_mode(self) -> str:
        """Last visited library page. 0.x only knew ``albums``/``playlists``."""
        return self._choice(Keys.LIBRARY_MODE, PAGES, "albums")

    @library_mode.setter
    def library_mode(self, value: str) -> None:
        if value in PAGES:
            self.set_value(Keys.LIBRARY_MODE, value)

    @property
    def library_path(self) -> str:
        return _to_text(self._settings.value(Keys.LIBRARY_PATH, "")).strip()

    @library_path.setter
    def library_path(self, value: str) -> None:
        self.set_value(Keys.LIBRARY_PATH, value)

    @property
    def volume(self) -> int:
        return max(0, min(100, parse_int(self._settings.value(Keys.VOLUME, 80), 80)))

    @volume.setter
    def volume(self, value: int) -> None:
        self.set_value(Keys.VOLUME, max(0, min(100, int(value))))

    # Library state -----------------------------------------------------------------
    def load_track_orders(self) -> dict[str, list[str]]:
        data = parse_json(self._settings.value(Keys.TRACK_ORDERS), dict)
        orders: dict[str, list[str]] = {}
        for album_id, paths in data.items():
            if isinstance(paths, list):
                orders[str(album_id)] = [str(path) for path in paths if path]
        return orders

    def save_track_orders(self, orders: dict[str, list[str]]) -> None:
        self.set_value(Keys.TRACK_ORDERS, json.dumps(orders))
        self.sync()

    def load_playlists_raw(self) -> list[Any]:
        return parse_json(self._settings.value(Keys.PLAYLISTS), list)

    def save_playlists_raw(self, payload: list[dict[str, Any]]) -> None:
        self.set_value(Keys.PLAYLISTS, json.dumps(payload, ensure_ascii=False))
        self.sync()

    def load_mix(self) -> tuple[list[str], float]:
        raw = parse_json(self._settings.value(Keys.MIX_TRACKS), list)
        paths = [str(item) for item in raw if item]
        return paths, parse_float(self._settings.value(Keys.MIX_UPDATED_AT, 0), 0.0)

    def save_mix(self, paths: list[str], updated_at: float) -> None:
        self.set_value(Keys.MIX_TRACKS, json.dumps(paths))
        self.set_value(Keys.MIX_UPDATED_AT, float(updated_at))

    # Playback state ----------------------------------------------------------------
    def load_playback(self) -> tuple[str, int, bool]:
        path = _to_text(self._settings.value(Keys.LAST_TRACK_PATH, ""))
        position = max(0, parse_int(self._settings.value(Keys.LAST_POSITION, 0), 0))
        playing = parse_bool(self._settings.value(Keys.LAST_PLAYING, False))
        return path, position, playing

    def save_playback(self, path: str, position_ms: int, playing: bool) -> None:
        self.set_value(Keys.LAST_TRACK_PATH, path)
        self.set_value(Keys.LAST_POSITION, int(position_ms))
        self.set_value(Keys.LAST_PLAYING, bool(playing))

    # Window ------------------------------------------------------------------------
    def load_geometry(self) -> QByteArray | None:
        raw = self._settings.value(Keys.WINDOW_GEOMETRY)
        if isinstance(raw, QByteArray) and not raw.isEmpty():
            return raw
        if isinstance(raw, (bytes, bytearray)) and raw:
            return QByteArray(bytes(raw))
        return None

    def save_geometry(self, geometry: QByteArray) -> None:
        self.set_value(Keys.WINDOW_GEOMETRY, geometry)
