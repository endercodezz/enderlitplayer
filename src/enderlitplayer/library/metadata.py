"""Audio tag reading/writing and cover-art discovery (mutagen based, Qt free)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.aac import AAC
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from enderlitplayer.core.models import UNKNOWN_ARTIST

log = logging.getLogger(__name__)

AUDIO_EXTS = frozenset({".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"})
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
PREFERRED_COVER_NAMES = (
    "cover.jpg",
    "folder.jpg",
    "front.jpg",
    "album.jpg",
    "cover.png",
    "folder.png",
    "front.png",
    "album.png",
)

_SPECIFIC_TYPES: dict[str, Any] = {
    ".mp3": MP3,
    ".flac": FLAC,
    ".m4a": MP4,
    ".mp4": MP4,
    ".ogg": OggVorbis,
    ".opus": OggOpus,
    ".wav": WAVE,
    ".aac": AAC,
}


@dataclass
class TrackTags:
    title: str
    artist: str
    album: str
    album_artist: str
    year: str
    track_no: int
    disc_no: int
    duration: float


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def first_tag_value(tags: Any, keys: list[str]) -> str:
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(value, list):
            if value:
                return str(value[0]).strip()
            continue
        if value:
            return str(value).strip()
    return ""


def parse_number(value: str) -> int:
    """Parse ``"3"`` or ``"3/12"`` style tag values; anything else is 0."""
    if not value:
        return 0
    try:
        return max(0, int(str(value).split("/")[0].strip()))
    except ValueError:
        return 0


def _length(audio: Any) -> float:
    info = getattr(audio, "info", None)
    if info is None:
        return 0.0
    try:
        return float(getattr(info, "length", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def duration_from_specific(path: Path) -> float | None:
    cls = _SPECIFIC_TYPES.get(path.suffix.lower())
    if cls is None:
        return None
    try:
        return _length(cls(path))
    except Exception:
        return None


def probe_duration_ffprobe(path: Path) -> float | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        # Prevent a console window flashing for every file in the windowed build.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def read_tags(path: Path) -> TrackTags:
    """Read tags with sensible fallbacks. Raises ``MutagenError``/``OSError`` on unreadable files."""
    audio_easy = MutagenFile(path, easy=True)
    tags = audio_easy.tags if audio_easy is not None else None

    title = first_tag_value(tags, ["title"]) or path.stem
    artist = first_tag_value(tags, ["artist", "composer", "performer"]) or UNKNOWN_ARTIST
    album = first_tag_value(tags, ["album"]) or path.parent.name
    album_artist = first_tag_value(tags, ["albumartist", "album artist"]) or artist
    year = first_tag_value(tags, ["date", "year"])
    track_no = parse_number(first_tag_value(tags, ["tracknumber", "track"]))
    disc_no = parse_number(first_tag_value(tags, ["discnumber", "disc"]))

    duration = _length(audio_easy) if audio_easy is not None else 0.0
    if duration <= 0:
        duration = duration_from_specific(path) or 0.0
    if duration <= 0:
        duration = probe_duration_ffprobe(path) or 0.0

    return TrackTags(title, artist, album, album_artist, year, track_no, disc_no, duration)


def mime_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


def extract_embedded_cover(path: Path) -> tuple[str, bytes] | None:
    """Return ``(mime, data)`` for the first embedded picture, if any."""
    try:
        audio = MutagenFile(path)
    except (MutagenError, OSError):
        return None
    if audio is None:
        return None

    pictures = getattr(audio, "pictures", None)
    if pictures:
        picture = pictures[0]
        return picture.mime or mime_from_bytes(picture.data), bytes(picture.data)

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None

    if hasattr(tags, "getall"):
        apics = tags.getall("APIC")
        if apics:
            return apics[0].mime or mime_from_bytes(apics[0].data), bytes(apics[0].data)

    covr = tags.get("covr") if hasattr(tags, "get") else None
    if covr:
        data = bytes(covr[0])
        return mime_from_bytes(data), data
    return None


def find_cover_in_folder(folder: Path) -> Path | None:
    for name in PREFERRED_COVER_NAMES:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return None
    for candidate in entries:
        if candidate.suffix.lower() in IMAGE_EXTS and candidate.is_file():
            return candidate
    return None


class TagWriteError(Exception):
    pass


def write_tags(path: Path, title: str, artist: str, track_no: int) -> None:
    """Write title/artist (and track number when > 0) using mutagen's easy interface."""
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise TagWriteError(f"Unsupported file: {path}")
        if audio.tags is None and hasattr(audio, "add_tags"):
            audio.add_tags()
        audio["title"] = [title]
        audio["artist"] = [artist]
        if track_no > 0:
            audio["tracknumber"] = [str(track_no)]
        audio.save()
    except TagWriteError:
        raise
    except Exception as exc:
        log.warning("Tag update failed for %s: %s", path, exc)
        raise TagWriteError(str(exc)) from exc
