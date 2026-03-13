from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.aac import AAC
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE


AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    album_artist: str
    year: str
    track_no: int
    disc_no: int
    duration: float
    path: str


@dataclass
class Album:
    id: str
    title: str
    artist: str
    year: str
    tracks: List[Track]
    duration: float
    cover_path: Optional[str]
    cover_bytes: Optional[bytes]
    cover_mime: Optional[str]


def default_scan_path() -> Optional[str]:
    env_path = os.environ.get("MUSIC_DIR")
    if env_path:
        return os.path.expanduser(env_path)

    home = Path.home()
    for candidate in [home / "Music", home / "music"]:
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
    return None


def make_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def first_tag_value(tags, keys: List[str]) -> str:
    for key in keys:
        if not tags:
            continue
        value = tags.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if value:
            return str(value)
    return ""


def parse_number(value: str) -> int:
    if not value:
        return 0
    try:
        return int(str(value).split("/")[0])
    except ValueError:
        return 0


def read_tags(path: Path) -> Tuple[str, str, str, str, str, int, int, float]:
    audio_easy = MutagenFile(path, easy=True)
    audio_full = MutagenFile(path)
    tags = audio_easy.tags if audio_easy else {}

    title = first_tag_value(tags, ["title"]) or path.stem
    artist = first_tag_value(tags, ["artist", "composer", "performer"]) or "Unknown Artist"
    album = first_tag_value(tags, ["album"]) or path.parent.name
    album_artist = first_tag_value(tags, ["albumartist", "album artist"]) or artist
    year = first_tag_value(tags, ["date", "year"])
    track_no = parse_number(first_tag_value(tags, ["tracknumber", "track"]))
    disc_no = parse_number(first_tag_value(tags, ["discnumber", "disc"]))
    duration = 0.0
    if audio_full and getattr(audio_full, "info", None):
        duration = float(getattr(audio_full.info, "length", 0.0) or 0.0)
    elif audio_easy and getattr(audio_easy, "info", None):
        duration = float(getattr(audio_easy.info, "length", 0.0) or 0.0)
    if duration <= 0:
        duration = duration_from_specific(path) or 0.0
    if duration <= 0:
        duration = probe_duration_ffprobe(path) or 0.0

    return title, artist, album, album_artist, year, track_no, disc_no, duration


def probe_duration_ffprobe(path: Path) -> Optional[float]:
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return float(value) if value else None
    except Exception:
        return None


def duration_from_specific(path: Path) -> Optional[float]:
    ext = path.suffix.lower()
    try:
        if ext == ".mp3":
            audio = MP3(path)
        elif ext == ".flac":
            audio = FLAC(path)
        elif ext in {".m4a", ".mp4"}:
            audio = MP4(path)
        elif ext == ".ogg":
            audio = OggVorbis(path)
        elif ext == ".opus":
            audio = OggOpus(path)
        elif ext == ".wav":
            audio = WAVE(path)
        elif ext == ".aac":
            audio = AAC(path)
        else:
            return None
        return float(getattr(audio.info, "length", 0.0) or 0.0)
    except Exception:
        return None


def _mime_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


def extract_embedded_cover(path: Path) -> Optional[Tuple[str, bytes]]:
    audio = MutagenFile(path)
    if not audio:
        return None

    pictures = getattr(audio, "pictures", None)
    if pictures:
        pic = pictures[0]
        return (pic.mime or "image/jpeg", pic.data)

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None

    if hasattr(tags, "getall"):
        apics = tags.getall("APIC")
        if apics:
            return (apics[0].mime or "image/jpeg", apics[0].data)

    covr = tags.get("covr") if hasattr(tags, "get") else None
    if covr:
        data = covr[0]
        mime = getattr(data, "mime", None) or _mime_from_bytes(bytes(data))
        return (mime, bytes(data))

    return None


def find_cover_in_folder(folder: Path) -> Optional[Path]:
    preferred = [
        "cover.jpg",
        "folder.jpg",
        "front.jpg",
        "album.jpg",
        "cover.png",
        "folder.png",
        "front.png",
        "album.png",
    ]
    for name in preferred:
        candidate = folder / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTS:
            return candidate
    return None


def scan_library(root_path: str) -> List[Album]:
    root = Path(root_path).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(root_path)

    albums: Dict[str, Album] = {}

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in AUDIO_EXTS:
            continue

        try:
            title, artist, album, album_artist, year, track_no, disc_no, duration = read_tags(
                file_path
            )
        except Exception:
            continue

        album_folder = file_path.parent
        album_id = make_id(str(album_folder))
        track_id = make_id(str(file_path))

        if album_id not in albums:
            albums[album_id] = Album(
                id=album_id,
                title=album_folder.name,
                artist="",
                year=year,
                tracks=[],
                duration=0.0,
                cover_path=None,
                cover_bytes=None,
                cover_mime=None,
            )

        album_obj = albums[album_id]
        track = Track(
            id=track_id,
            title=title,
            artist=artist,
            album=album_folder.name,
            album_artist=album_artist,
            year=year,
            track_no=track_no,
            disc_no=disc_no,
            duration=duration,
            path=str(file_path),
        )
        album_obj.tracks.append(track)
        album_obj.duration += duration

        if album_obj.cover_bytes is None and album_obj.cover_path is None:
            try:
                embedded = extract_embedded_cover(file_path)
            except Exception:
                embedded = None
            if embedded:
                album_obj.cover_mime, album_obj.cover_bytes = embedded

    for album_id, album_obj in albums.items():
        album_obj.tracks.sort(
            key=lambda t: (t.disc_no or 0, t.track_no or 0, t.title or "")
        )
        artists = {track.artist for track in album_obj.tracks if track.artist}
        if len(artists) == 1:
            album_obj.artist = next(iter(artists))
        elif len(artists) == 0:
            album_obj.artist = "Unknown Artist"
        else:
            album_obj.artist = "Various Artists"
        years = [track.year for track in album_obj.tracks if track.year]
        album_obj.year = years[0] if years else ""
        if album_obj.cover_bytes is None:
            if album_obj.tracks:
                folder = Path(album_obj.tracks[0].path).parent
                image_path = find_cover_in_folder(folder)
                if image_path:
                    album_obj.cover_path = str(image_path)

    return sorted(albums.values(), key=lambda a: (a.artist, a.title))
