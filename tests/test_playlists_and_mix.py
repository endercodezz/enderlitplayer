"""Playlist persistence and editing; Random Mix behaviour."""

from __future__ import annotations

import random

from enderlitplayer.core.models import MIX_ID, PLAYLIST_ID_PREFIX, CollectionKind, Track
from enderlitplayer.playlists.manager import PlaylistManager
from enderlitplayer.playlists.mix import MIX_SIZE, RandomMix
from enderlitplayer.storage.settings import SettingsStore


def track(path: str, duration: float = 10.0) -> Track:
    return Track(path, path, "A", "Al", "A", "", 0, 0, duration, path)


def test_create_persist_reload(store: SettingsStore) -> None:
    manager = PlaylistManager(store)
    playlist = manager.create("  Focus  ", "icon.png")
    assert playlist.id.startswith(PLAYLIST_ID_PREFIX)
    assert playlist.title == "Focus"
    assert manager.add_tracks(playlist.id, ["a", "b", "a"]) == 2
    assert manager.add_tracks(playlist.id, ["b"]) == 0
    reloaded = PlaylistManager(store)
    assert [(p.id, p.title, p.icon_path, p.track_paths) for p in reloaded.playlists] == [
        (playlist.id, "Focus", "icon.png", ["a", "b"])
    ]


def test_update_remove_delete(store: SettingsStore) -> None:
    manager = PlaylistManager(store)
    playlist = manager.create("One")
    manager.add_tracks(playlist.id, ["a", "b", "c"])
    assert manager.remove_track(playlist.id, "b")
    assert not manager.remove_track(playlist.id, "zz")
    assert manager.update(playlist.id, title="Two", icon_path="")
    assert PlaylistManager(store).get(playlist.id).track_paths == ["a", "c"]
    assert PlaylistManager(store).get(playlist.id).title == "Two"
    assert manager.delete(playlist.id)
    assert not manager.delete(playlist.id)
    assert PlaylistManager(store).playlists == []


def test_missing_tracks_are_kept(store: SettingsStore) -> None:
    """Scanning another folder must not erase playlist contents (0.x bug)."""
    manager = PlaylistManager(store)
    playlist = manager.create("Keep")
    manager.add_tracks(playlist.id, ["a", "gone", "b"])
    by_path = {"a": track("a"), "b": track("b")}
    collection = manager.build_collection(playlist, by_path)
    assert collection.kind == CollectionKind.PLAYLIST
    assert [t.path for t in collection.tracks] == ["a", "b"]
    assert collection.duration == 20.0
    manager.set_visible_order(playlist.id, ["b", "a"])
    assert PlaylistManager(store).get(playlist.id).track_paths == ["b", "a", "gone"]


def test_replace_path_after_rename(store: SettingsStore) -> None:
    manager = PlaylistManager(store)
    first = manager.create("1")
    second = manager.create("2")
    manager.add_tracks(first.id, ["old", "x"])
    manager.add_tracks(second.id, ["y"])
    assert manager.replace_path("old", "new")
    assert not manager.replace_path("missing", "zzz")
    assert PlaylistManager(store).get(first.id).track_paths == ["new", "x"]


def test_create_requires_title(store: SettingsStore) -> None:
    import pytest

    with pytest.raises(ValueError):
        PlaylistManager(store).create("   ")


def test_mix_generation_and_persistence(store: SettingsStore) -> None:
    by_path = {f"t{i}": track(f"t{i}") for i in range(50)}
    mix = RandomMix(store, random.Random(1))
    collection = mix.build_collection(by_path, "Mix")
    assert collection is not None and collection.id == MIX_ID and collection.kind == CollectionKind.MIX
    assert len(collection.tracks) == MIX_SIZE
    assert len({t.path for t in collection.tracks}) == MIX_SIZE
    saved = list(mix.paths)
    reloaded = RandomMix(store)
    assert reloaded.paths == saved
    assert [t.path for t in reloaded.resolve(by_path)] == saved


def test_mix_regenerates_when_tracks_disappear(store: SettingsStore) -> None:
    by_path = {f"t{i}": track(f"t{i}") for i in range(30)}
    mix = RandomMix(store, random.Random(2))
    mix.resolve(by_path)
    removed = mix.paths[0]
    del by_path[removed]
    tracks = mix.resolve(by_path)
    assert removed not in mix.paths
    assert len(tracks) == MIX_SIZE


def test_mix_small_and_empty_library(store: SettingsStore) -> None:
    mix = RandomMix(store, random.Random(3))
    assert mix.build_collection({}, "Mix") is None
    tracks = mix.resolve({"a": track("a"), "b": track("b")})
    assert sorted(t.path for t in tracks) == ["a", "b"]
    assert mix.replace_path("a", "c")
    assert "c" in RandomMix(store).paths
