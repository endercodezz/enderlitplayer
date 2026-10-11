"""Generate tiny, valid, copyright-free audio files for tests.

* WAV: real PCM silence via the ``wave`` module.
* MP3: a run of silent MPEG-1 Layer III frames plus ID3 tags.
* FLAC: a STREAMINFO-only stream (no audio frames) with Vorbis comments.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK

# 128 kbps, 44.1 kHz, joint stereo; frame length = 144 * 128000 / 44100 = 417 bytes.
_MP3_HEADER = bytes([0xFF, 0xFB, 0x90, 0x64])
_MP3_FRAME = _MP3_HEADER + bytes(417 - 4)
_FRAMES_PER_SECOND = 44100 / 1152


def png_bytes(color: str = "#1db954", size: int = 64) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


def write_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def write_mp3(
    path: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    track: str | None = None,
    year: str | None = None,
    seconds: float = 2.0,
    cover: bytes | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MP3_FRAME * max(1, int(seconds * _FRAMES_PER_SECOND)))
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if track:
        tags.add(TRCK(encoding=3, text=track))
    if year:
        tags.add(TDRC(encoding=3, text=year))
    if cover:
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="cover", data=cover))
    tags.save(str(path))
    return path


def write_flac(
    path: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    track: str | None = None,
    disc: str | None = None,
    seconds: float = 3.0,
    rate: int = 44100,
    cover: bytes | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = int(seconds * rate)
    # STREAMINFO: block sizes, frame sizes, then 20-bit rate | 3-bit channels-1 | 5-bit bps-1 | 36-bit samples.
    packed = (rate << 44) | (1 << 41) | (15 << 36) | total
    info = struct.pack(">HH", 4096, 4096) + b"\x00" * 6 + packed.to_bytes(8, "big") + b"\x00" * 16
    header = bytes([0x80]) + len(info).to_bytes(3, "big")  # last-metadata-block flag + STREAMINFO type 0
    path.write_bytes(b"fLaC" + header + info)
    audio = FLAC(str(path))
    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if track:
        audio["tracknumber"] = track
    if disc:
        audio["discnumber"] = disc
    if cover:
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png"
        picture.data = cover
        audio.add_picture(picture)
    audio.save()
    return path


def build_sample_library(root: Path) -> Path:
    """A small library: two tagged albums, one untagged folder, nested folders, a broken file."""
    art = png_bytes("#2b6cb0")
    first = root / "Northern Lights"
    for number, name in enumerate(["Aurora", "Polar Night", "Midnight Sun"], start=1):
        write_mp3(
            first / f"{number:02d} {name}.mp3",
            title=name,
            artist="Lumen",
            album="Northern Lights",
            track=f"{number}/3",
            year="2021",
            cover=art if number == 1 else None,
        )
    second = root / "Second Album"
    write_flac(second / "b.flac", title="Second", artist="Duo", track="2")
    write_flac(second / "a.flac", title="First", artist="Duo", track="1")
    write_flac(second / "c.flac", title="Bonus", artist="Guest", track="1", disc="2")
    (second / "folder.jpg").write_bytes(png_bytes("#c05621"))
    untagged = root / "Field Recordings" / "2019"
    write_wav(untagged / "rain on the roof.wav", seconds=1.5)
    write_wav(untagged / "wind.wav", seconds=0.5)
    (untagged / "notes.txt").write_text("not audio", encoding="utf-8")
    (untagged / "broken.mp3").write_bytes(b"this is not an mp3 file at all")
    return root
