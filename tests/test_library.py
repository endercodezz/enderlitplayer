"""Scanning, album grouping, metadata parsing, cover discovery and invalid files."""

from __future__ import annotations

from pathlib import Path

import pytest

from audio_fixtures import png_bytes, write_flac, write_mp3, write_wav
from enderlitplayer.core.models import UNKNOWN_ARTIST, VARIOUS_ARTISTS, make_id
from enderlitplayer.library.metadata import (
    AUDIO_EXTS,
    extract_embedded_cover,
    find_cover_in_folder,
    first_tag_value,
    mime_from_bytes,
    parse_number,
    read_tags,
)
from enderlitplayer.library.scanner import default_scan_path, scan_library


def albums_by_title(root: Path) -> dict:
    return {album.title: album for album in scan_library(str(root))}


def test_supported_formats_unchanged() -> None:
    assert {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"} == AUDIO_EXTS


def test_albums_grouped_by_folder(sample_library: Path) -> None:
    albums = albums_by_title(sample_library)
    assert set(albums) == {"Northern Lights", "Second Album", "2019"}
    folder = sample_library / "Northern Lights"
    assert albums["Northern Lights"].id == make_id(str(folder))
    assert all(track.album == "Northern Lights" for track in albums["Northern Lights"].tracks)


def test_tracks_sorted_by_disc_then_number(sample_library: Path) -> None:
    second = albums_by_title(sample_library)["Second Album"]
    assert [track.title for track in second.tracks] == ["First", "Second", "Bonus"]
    assert second.artist == VARIOUS_ARTISTS


def test_album_metadata(sample_library: Path) -> None:
    album = albums_by_title(sample_library)["Northern Lights"]
    assert album.artist == "Lumen"
    assert album.year == "2021"
    assert [t.track_no for t in album.tracks] == [1, 2, 3]
    assert album.duration == pytest.approx(sum(t.duration for t in album.tracks))
    assert album.tracks[0].duration > 1.5


def test_untagged_files_use_fallbacks(sample_library: Path) -> None:
    album = albums_by_title(sample_library)["2019"]
    titles = sorted(track.title for track in album.tracks)
    assert titles == ["rain on the roof", "wind"]
    assert album.artist == UNKNOWN_ARTIST
    assert album.tracks[0].duration > 0


def test_invalid_and_non_audio_files_do_not_break_scan(sample_library: Path) -> None:
    album = albums_by_title(sample_library)["2019"]
    paths = {Path(track.path).name for track in album.tracks}
    assert "notes.txt" not in paths
    assert "broken.mp3" not in paths


def test_embedded_and_folder_covers(sample_library: Path) -> None:
    albums = albums_by_title(sample_library)
    northern = albums["Northern Lights"]
    assert northern.cover_bytes and northern.cover_mime == "image/png"
    second = albums["Second Album"]
    assert second.cover_bytes is None
    assert second.cover_path and Path(second.cover_path).name == "folder.jpg"
    assert albums["2019"].cover_path is None


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan_library(str(tmp_path / "does-not-exist"))


def test_empty_folder(tmp_path: Path) -> None:
    assert scan_library(str(tmp_path)) == []


def test_progress_and_cancel(sample_library: Path) -> None:
    from enderlitplayer.library.scanner import ScanCancelled

    seen: list[int] = []
    scan_library(str(sample_library), progress=seen.append)
    assert seen and seen[-1] == 9  # 3 mp3 + 3 flac + 2 wav + broken.mp3 (counted, then skipped)
    with pytest.raises(ScanCancelled):
        scan_library(str(sample_library), cancelled=lambda: True)


def test_read_tags_mp3_and_flac(tmp_path: Path) -> None:
    mp3 = write_mp3(tmp_path / "a.mp3", title="T", artist="A", album="Al", track="4/9", year="1999")
    tags = read_tags(mp3)
    assert (tags.title, tags.artist, tags.album, tags.track_no, tags.year) == ("T", "A", "Al", 4, "1999")
    flac = write_flac(tmp_path / "b.flac", title="F", artist="B", track="2", disc="1", seconds=2)
    tags = read_tags(flac)
    assert (tags.title, tags.artist, tags.track_no, tags.disc_no) == ("F", "B", 2, 1)
    assert tags.duration == pytest.approx(2.0, abs=0.01)
    assert tags.album_artist == "B"


def test_read_tags_wav_fallback(tmp_path: Path) -> None:
    wav = write_wav(tmp_path / "Some Song.wav", seconds=1.0)
    tags = read_tags(wav)
    assert tags.title == "Some Song"
    assert tags.artist == UNKNOWN_ARTIST
    assert tags.album == tmp_path.name
    assert tags.duration == pytest.approx(1.0, abs=0.05)


def test_helpers() -> None:
    assert parse_number("3/12") == 3
    assert parse_number("") == 0
    assert parse_number("x") == 0
    assert first_tag_value({"title": ["a", "b"]}, ["title"]) == "a"
    assert first_tag_value({"artist": []}, ["artist", "composer"]) == ""
    assert first_tag_value(None, ["x"]) == ""
    assert mime_from_bytes(b"\x89PNG....") == "image/png"
    assert mime_from_bytes(b"\xff\xd8\xff") == "image/jpeg"
    assert mime_from_bytes(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"


def test_cover_helpers(tmp_path: Path) -> None:
    art = png_bytes()
    mp3 = write_mp3(tmp_path / "c.mp3", title="x", cover=art)
    assert extract_embedded_cover(mp3) == ("image/png", art)
    flac = write_flac(tmp_path / "c.flac", title="x", cover=art)
    assert extract_embedded_cover(flac) == ("image/png", art)
    assert extract_embedded_cover(tmp_path / "missing.mp3") is None
    (tmp_path / "zzz.png").write_bytes(art)
    assert find_cover_in_folder(tmp_path) == tmp_path / "zzz.png"
    (tmp_path / "cover.jpg").write_bytes(art)
    assert find_cover_in_folder(tmp_path) == tmp_path / "cover.jpg"
    assert find_cover_in_folder(tmp_path / "nope") is None


def test_default_scan_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    assert default_scan_path() == str(tmp_path)
