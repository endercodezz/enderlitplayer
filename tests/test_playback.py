"""Playback navigation, restoration, volume and failure handling — without audio hardware."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from audio_fixtures import write_wav
from enderlitplayer.audio.backend import MediaBackend
from enderlitplayer.audio.controller import PlaybackController
from enderlitplayer.audio.queue import next_step, pick_random_album, previous_step
from enderlitplayer.core.models import Album, Track, make_id
from enderlitplayer.storage.settings import SettingsStore


class FakeBackend(MediaBackend):
    def __init__(self) -> None:
        super().__init__()
        self.source = ""
        self.playing = False
        self.pos = 0
        self.volume = 1.0
        self.calls: list[str] = []

    def set_source(self, path: str) -> None:
        self.source = path
        self.pos = 0
        self.calls.append(f"source:{Path(path).name}")

    def clear_source(self) -> None:
        self.source = ""
        self.playing = False
        self.calls.append("clear")

    def play(self) -> None:
        self.playing = True
        self.playingChanged.emit(True)

    def pause(self) -> None:
        self.playing = False
        self.playingChanged.emit(False)

    def stop(self) -> None:
        self.pause()

    def position(self) -> int:
        return self.pos

    def set_position(self, position_ms: int) -> None:
        self.pos = position_ms

    def duration(self) -> int:
        return 1000

    def is_playing(self) -> bool:
        return self.playing

    def set_volume(self, volume: float) -> None:
        self.volume = volume


def make_album(folder: Path, name: str, count: int) -> Album:
    tracks = []
    for i in range(count):
        path = write_wav(folder / name / f"{i}.wav", seconds=0.1)
        tracks.append(Track(make_id(str(path)), f"{name}{i}", "A", name, "A", "", i + 1, 0, 0.1, str(path)))
    return Album(make_id(name), name, "A", "", tracks, 0.3)


@pytest.fixture
def albums(tmp_path: Path) -> list[Album]:
    return [make_album(tmp_path, "one", 3), make_album(tmp_path, "two", 2)]


def controller(store: SettingsStore, albums: list[Album]) -> tuple[PlaybackController, FakeBackend]:
    backend = FakeBackend()
    ctl = PlaybackController(backend, store, lambda exclude: pick_random_album(albums, exclude, random.Random(0)))
    return ctl, backend


def test_queue_rules(albums: list[Album]) -> None:
    one = albums[0]
    assert next_step(one, one.tracks[0]).track is one.tracks[1]
    assert next_step(one, one.tracks[2]) is None
    assert previous_step(one, one.tracks[1], 1000).track is one.tracks[0]
    assert previous_step(one, one.tracks[0], 0).track is one.tracks[0]
    assert previous_step(one, one.tracks[1], 5000) is None
    assert pick_random_album(albums, one.id).id == albums[1].id
    assert pick_random_album([one], one.id) is None


def test_next_and_end_of_album(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    one, two = albums
    ctl.play_track(one.tracks[1], one)
    assert backend.playing and ctl.is_playing
    ctl.next()
    assert ctl.track is one.tracks[2]
    ctl.next()  # end of album -> a different random album from its first track
    assert ctl.collection is two and ctl.track is two.tracks[0]


def test_media_end_advances(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    ctl.play_collection(albums[0])
    backend.mediaEnded.emit()
    assert ctl.track is albums[0].tracks[1]


def test_previous_restarts_or_goes_back(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    one = albums[0]
    ctl.play_track(one.tracks[2], one)
    backend.pos = 4000
    ctl.previous()
    assert ctl.track is one.tracks[2] and backend.pos == 0
    ctl.previous()
    assert ctl.track is one.tracks[1]


def test_toggle_seek_volume(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    ctl.toggle()  # nothing loaded: no-op
    assert not backend.playing
    ctl.play_collection(albums[0])
    ctl.toggle()
    assert not ctl.is_playing
    ctl.seek(1500)
    assert backend.pos == 1500 and ctl.position == 1500
    ctl.set_volume(40)
    assert backend.volume == pytest.approx(0.4) and store.volume == 40
    ctl.set_muted(True)
    assert backend.volume == 0.0 and store.volume == 40
    ctl.set_muted(False)
    assert backend.volume == pytest.approx(0.4)


def test_state_saved_and_restored(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    one = albums[0]
    ctl.play_track(one.tracks[1], one)
    backend.positionChanged.emit(2500)
    ctl.save_state()
    assert store.load_playback() == (one.tracks[1].path, 2500, True)

    restored, backend2 = controller(store, albums)
    _path, position, _ = store.load_playback()
    restored.restore(one.tracks[1], one, position)
    assert backend2.source == one.tracks[1].path and not backend2.playing
    backend2.mediaLoaded.emit()
    assert backend2.pos == 2500 and not restored.is_playing


def test_missing_file_is_skipped(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    one = albums[0]
    Path(one.tracks[0].path).unlink()
    failures: list[str] = []
    ctl.playbackFailed.connect(failures.append)
    ctl.play_track(one.tracks[0], one)
    assert failures == [one.tracks[0].path]
    assert ctl.track is one.tracks[1] and backend.playing


def test_all_files_broken_does_not_loop(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    one = albums[0]
    for track in one.tracks:
        Path(track.path).unlink()
    ctl.play_track(one.tracks[0], one)
    assert not backend.playing


def test_backend_error_skips(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    ctl.play_collection(albums[0])
    backend.errorOccurred.emit("decoder failure")
    assert ctl.track is albums[0].tracks[1]


def test_suspend_resume_for_edits(store: SettingsStore, albums: list[Album]) -> None:
    ctl, backend = controller(store, albums)
    ctl.play_collection(albums[0])
    backend.pos = 700
    snapshot = ctl.suspend()
    assert backend.source == ""
    ctl.resume(snapshot)
    assert backend.source == albums[0].tracks[0].path and backend.playing
    backend.mediaLoaded.emit()
    assert backend.pos == 700


def test_update_collection_keeps_track(store: SettingsStore, albums: list[Album]) -> None:
    ctl, _ = controller(store, albums)
    one = albums[0]
    ctl.play_track(one.tracks[0], one)
    reordered = Album(one.id, one.title, one.artist, "", list(reversed(one.tracks)), one.duration)
    ctl.update_collection(reordered)
    assert ctl.collection is reordered
    assert ctl.track is one.tracks[0]
    ctl.next()  # track 0 is now last in the reordered album -> random other album
    assert ctl.collection is albums[1]
