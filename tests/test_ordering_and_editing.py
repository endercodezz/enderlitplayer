"""Track ordering persistence and metadata editing / file renaming."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen import File as MutagenFile

from audio_fixtures import write_flac, write_mp3
from enderlitplayer.core.models import Album, CollectionKind, Track, make_id
from enderlitplayer.library import ordering
from enderlitplayer.library.editing import (
    EditError,
    TrackEdit,
    TrackEditError,
    apply_track_edit,
    parse_track_number,
)
from enderlitplayer.library.scanner import scan_library
from enderlitplayer.playlists.manager import PlaylistManager
from enderlitplayer.playlists.mix import RandomMix
from enderlitplayer.services.library_service import LibraryService
from enderlitplayer.storage.settings import SettingsStore


def make_album(paths: list[str]) -> Album:
    tracks = [Track(make_id(p), p, "A", "X", "A", "", i + 1, 0, 1.0, p) for i, p in enumerate(paths)]
    return Album("alb", "X", "A", "", tracks, 3.0)


def test_apply_saved_order() -> None:
    album = make_album(["a", "b", "c", "d"])
    assert ordering.apply_saved_order(album, ["c", "a", "missing"])
    assert [t.path for t in album.tracks] == ["c", "a", "b", "d"]
    assert [t.track_no for t in album.tracks] == [1, 2, 3, 4]
    assert not ordering.apply_saved_order(album, [])


def test_move_item_bounds() -> None:
    items = [1, 2, 3]
    assert ordering.move_item(items, 0, 1) == 1 and items == [2, 1, 3]
    assert ordering.move_item(items, 0, -1) is None
    assert ordering.move_item(items, 2, 1) is None
    assert items == [2, 1, 3]


def test_replace_path_in_orders() -> None:
    orders = {"x": ["a", "b"], "y": ["c"]}
    assert ordering.replace_path(orders, "b", "B")
    assert orders == {"x": ["a", "B"], "y": ["c"]}


def service(store: SettingsStore) -> LibraryService:
    return LibraryService(store, PlaylistManager(store), RandomMix(store))


def test_service_order_persists_across_scans(store: SettingsStore, sample_library: Path) -> None:
    lib = service(store)
    lib._on_finished(scan_library(str(sample_library)))
    album = next(a for a in lib.albums if a.title == "Northern Lights")
    assert lib.move_track(album, 0, 1) == 1
    expected = [t.title for t in album.tracks]
    assert expected == ["Polar Night", "Aurora", "Midnight Sun"]
    again = service(store)
    again._on_finished(scan_library(str(sample_library)))
    album = next(a for a in again.albums if a.title == "Northern Lights")
    assert [t.title for t in album.tracks] == expected
    assert [t.track_no for t in album.tracks] == [1, 2, 3]


def test_service_playlist_reorder(store: SettingsStore, sample_library: Path) -> None:
    lib = service(store)
    lib._on_finished(scan_library(str(sample_library)))
    paths = [t.path for t in lib.albums[0].tracks]
    playlist = lib.playlists.create("P")
    lib.playlists.add_tracks(playlist.id, paths)
    collection = lib.playlist_collection(playlist.id)
    assert collection.kind == CollectionKind.PLAYLIST
    lib.move_track(collection, 2, -2)
    assert PlaylistManager(store).get(playlist.id).track_paths == [paths[2], paths[0], paths[1]]


def test_edit_tags_and_rename(tmp_path: Path) -> None:
    path = write_mp3(tmp_path / "old.mp3", title="Old", artist="Someone", track="1")
    track = Track(make_id(str(path)), "Old", "Someone", "x", "Someone", "", 1, 0, 1.0, str(path))
    result = apply_track_edit(track, TrackEdit("New title", "New artist", "renamed", 5))
    assert result.renamed and result.number_changed
    assert track.path == str(tmp_path / "renamed.mp3")
    assert track.id == make_id(track.path)
    assert not path.exists()
    audio = MutagenFile(track.path, easy=True)
    assert audio["title"] == ["New title"]
    assert audio["artist"] == ["New artist"]
    assert audio["tracknumber"] == ["5"]


def test_edit_flac_without_rename(tmp_path: Path) -> None:
    path = write_flac(tmp_path / "x.flac", title="A", artist="B")
    track = Track("id", "A", "B", "x", "B", "", 0, 0, 1.0, str(path))
    result = apply_track_edit(track, TrackEdit("C", "D", "x.flac"))
    assert not result.renamed and not result.number_changed
    assert MutagenFile(str(path), easy=True)["title"] == ["C"]


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (TrackEdit("", "a", "f.mp3"), EditError.MISSING_FIELDS),
        (TrackEdit("t", "a", "f.flac"), EditError.INVALID_EXTENSION),
        (TrackEdit("t", "a", "bad:name"), EditError.INVALID_FILE_NAME),
        (TrackEdit("t", "a", "other.mp3"), EditError.FILE_EXISTS),
    ],
)
def test_edit_validation(tmp_path: Path, edit: TrackEdit, code: EditError) -> None:
    path = write_mp3(tmp_path / "f.mp3", title="t")
    write_mp3(tmp_path / "other.mp3", title="o")
    track = Track("id", "t", "a", "x", "a", "", 0, 0, 1.0, str(path))
    with pytest.raises(TrackEditError) as info:
        apply_track_edit(track, edit)
    assert info.value.code == code
    assert path.exists()


def test_edit_missing_and_unsupported_files(tmp_path: Path) -> None:
    gone = Track("id", "t", "a", "x", "a", "", 0, 0, 1.0, str(tmp_path / "gone.mp3"))
    with pytest.raises(TrackEditError) as info:
        apply_track_edit(gone, TrackEdit("t", "a", "gone.mp3"))
    assert info.value.code == EditError.FILE_MISSING
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"nope")
    track = Track("id", "t", "a", "x", "a", "", 0, 0, 1.0, str(junk))
    with pytest.raises(TrackEditError) as info:
        apply_track_edit(track, TrackEdit("t2", "a", "junk.mp3"))
    assert info.value.code == EditError.TAG_WRITE_FAILED


def test_parse_track_number() -> None:
    assert parse_track_number(" 7 ") == 7
    assert parse_track_number("") == 0
    with pytest.raises(TrackEditError):
        parse_track_number("seven")
    with pytest.raises(TrackEditError):
        parse_track_number("-1")


def test_rename_propagates_everywhere(store: SettingsStore, sample_library: Path) -> None:
    lib = service(store)
    lib._on_finished(scan_library(str(sample_library)))
    album = next(a for a in lib.albums if a.title == "Northern Lights")
    lib.move_track(album, 0, 1)
    target = album.tracks[0]
    old_path = target.path
    playlist = lib.playlists.create("P")
    lib.playlists.add_tracks(playlist.id, [old_path])
    lib.mix.regenerate([old_path])
    store.save_playback(old_path, 1000, False)

    lib.edit_track(target, TrackEdit(target.title, target.artist, "renamed.mp3"), album)
    new_path = str(Path(old_path).with_name("renamed.mp3"))
    assert target.path == new_path
    assert lib.track(new_path) is target and lib.track(old_path) is None
    assert store.load_track_orders()[album.id][0] == new_path
    assert PlaylistManager(store).get(playlist.id).track_paths == [new_path]
    assert RandomMix(store).paths == [new_path]
    assert store.load_playback()[0] == new_path


def test_number_edit_reorders_album(store: SettingsStore, sample_library: Path) -> None:
    lib = service(store)
    lib._on_finished(scan_library(str(sample_library)))
    album = next(a for a in lib.albums if a.title == "Northern Lights")
    first = album.tracks[0]
    lib.edit_track(first, TrackEdit(first.title, first.artist, Path(first.path).name, 9), album)
    assert album.tracks[-1] is first
    assert store.load_track_orders()[album.id][-1] == first.path
