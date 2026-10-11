"""Settings written by 0.x must be read unchanged by 2.0."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings

from enderlitplayer import APPLICATION_NAME, ORGANIZATION_NAME
from enderlitplayer.playlists.manager import PlaylistManager
from enderlitplayer.playlists.mix import RandomMix
from enderlitplayer.storage.settings import Keys, SettingsStore, parse_bool, parse_int, parse_json


def legacy_settings(path: Path) -> QSettings:
    """Exactly what 0.5.x stored (values are JSON strings, ints and bools)."""
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    settings.setValue("library_mode", "playlists")
    settings.setValue("theme", "light")
    settings.setValue("cover_style", "square")
    settings.setValue("library_path", "D:/Music")
    settings.setValue("volume", 35)
    settings.setValue("last_track_path", "D:/Music/A/01.mp3")
    settings.setValue("last_position", 61234)
    settings.setValue("last_playing", True)
    settings.setValue("track_orders", json.dumps({"abc123": ["D:/Music/A/02.mp3", "D:/Music/A/01.mp3"]}))
    settings.setValue(
        "playlists",
        json.dumps(
            [
                {"id": "playlist_1", "title": "Утро", "icon_path": "C:/i.png", "track_paths": ["a", "b", "a"]},
                {"title": "No id", "track_paths": []},
                {"title": "", "track_paths": ["x"]},
                "garbage",
            ],
            ensure_ascii=False,
        ),
    )
    settings.setValue("mix_tracks", json.dumps(["a", "b"]))
    settings.setValue("mix_updated_at", 1700000000.5)
    settings.sync()
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_identifiers_are_stable() -> None:
    assert (ORGANIZATION_NAME, APPLICATION_NAME) == ("EnderLit", "EnderLitPlayer")


def test_key_names_are_stable() -> None:
    assert Keys.PLAYLISTS == "playlists"
    assert Keys.TRACK_ORDERS == "track_orders"
    assert Keys.LAST_TRACK_PATH == "last_track_path"
    assert Keys.LAST_POSITION == "last_position"
    assert Keys.MIX_TRACKS == "mix_tracks"
    assert Keys.LIBRARY_PATH == "library_path"


def test_reads_legacy_values(tmp_path: Path, qapp: object) -> None:
    store = SettingsStore(legacy_settings(tmp_path / "legacy.ini"))
    assert store.language == "en"
    assert store.theme == "light"
    assert store.cover_style == "square"
    assert store.library_mode == "playlists"
    assert store.library_path == "D:/Music"
    assert store.volume == 35
    assert store.load_playback() == ("D:/Music/A/01.mp3", 61234, True)
    assert store.load_track_orders() == {"abc123": ["D:/Music/A/02.mp3", "D:/Music/A/01.mp3"]}
    assert store.load_mix() == (["a", "b"], 1700000000.5)


def test_legacy_playlists(tmp_path: Path, qapp: object) -> None:
    store = SettingsStore(legacy_settings(tmp_path / "legacy.ini"))
    manager = PlaylistManager(store)
    titles = [pl.title for pl in manager.playlists]
    assert titles == ["Утро", "No id"]
    first = manager.playlists[0]
    assert first.id == "playlist_1"
    assert first.icon_path == "C:/i.png"
    assert first.track_paths == ["a", "b"]
    assert manager.playlists[1].id  # generated


def test_round_trip_keeps_format(tmp_path: Path, qapp: object) -> None:
    path = tmp_path / "legacy.ini"
    store = SettingsStore(legacy_settings(path))
    manager = PlaylistManager(store)
    manager.add_tracks("playlist_1", ["c"])
    raw = QSettings(str(path), QSettings.Format.IniFormat).value("playlists")
    data = json.loads(raw)
    assert data[0] == {"id": "playlist_1", "title": "Утро", "icon_path": "C:/i.png", "track_paths": ["a", "b", "c"]}
    RandomMix(store).regenerate(["z"])
    assert json.loads(QSettings(str(path), QSettings.Format.IniFormat).value("mix_tracks")) == ["z"]


def test_defaults_and_invalid_values(store: SettingsStore) -> None:
    assert store.language == "ru"
    assert store.theme == "dark"
    assert store.cover_style == "rounded"
    assert store.library_mode == "albums"
    assert store.volume == 80
    store.set_value("theme", "neon")
    store.set_value("volume", "loud")
    store.set_value("track_orders", "{not json")
    store.set_value("playlists", "42")
    assert store.theme == "dark"
    assert store.volume == 80
    assert store.load_track_orders() == {}
    assert store.load_playlists_raw() == []
    store.volume = 250
    assert store.volume == 100


def test_parsers() -> None:
    assert parse_bool("true") and parse_bool(1) and not parse_bool("false") and not parse_bool(None)
    assert parse_int("12.7") == 12 and parse_int(None, 5) == 5
    assert parse_json(b'["a"]', list) == ["a"]
    assert parse_json({"a": 1}, dict) == {"a": 1}
    assert parse_json('{"a": 1}', list) == []
