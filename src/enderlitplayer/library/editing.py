"""Validation and application of track metadata edits and file renames."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from enderlitplayer.core.models import Track, make_id
from enderlitplayer.library.metadata import TagWriteError, write_tags

log = logging.getLogger(__name__)


class EditError(str, Enum):
    MISSING_FIELDS = "missing_fields"
    INVALID_NUMBER = "invalid_number"
    INVALID_EXTENSION = "invalid_extension"
    INVALID_FILE_NAME = "invalid_file_name"
    FILE_EXISTS = "file_exists"
    FILE_MISSING = "file_missing"
    RENAME_FAILED = "rename_failed"
    TAG_WRITE_FAILED = "tag_update_failed"


class TrackEditError(Exception):
    def __init__(self, code: EditError) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class TrackEdit:
    title: str
    artist: str
    file_name: str
    track_no: int = 0


@dataclass(frozen=True)
class EditResult:
    old_path: str
    new_path: str
    number_changed: bool

    @property
    def renamed(self) -> bool:
        return self.old_path != self.new_path


_FORBIDDEN_CHARS = set('<>:"/\\|?*')


def parse_track_number(raw: str) -> int:
    raw = raw.strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError as exc:
        raise TrackEditError(EditError.INVALID_NUMBER) from exc
    if value < 0:
        raise TrackEditError(EditError.INVALID_NUMBER)
    return value


def resolve_target_path(track: Track, file_name: str) -> Path:
    """Validate a new file name and return the full target path."""
    original = Path(track.path)
    name = file_name.strip()
    if not name or any(char in _FORBIDDEN_CHARS for char in name) or name in {".", ".."}:
        raise TrackEditError(EditError.INVALID_FILE_NAME)
    candidate = Path(name)
    if candidate.suffix == "":
        candidate = candidate.with_name(candidate.name + original.suffix)
    if candidate.suffix.lower() != original.suffix.lower():
        raise TrackEditError(EditError.INVALID_EXTENSION)
    return original.with_name(candidate.name)


def validate_edit(track: Track, edit: TrackEdit) -> Path:
    if not edit.title.strip() or not edit.artist.strip() or not edit.file_name.strip():
        raise TrackEditError(EditError.MISSING_FIELDS)
    target = resolve_target_path(track, edit.file_name)
    original = Path(track.path)
    if target.name != original.name and target.exists() and target.name.lower() != original.name.lower():
        raise TrackEditError(EditError.FILE_EXISTS)
    return target


def apply_track_edit(track: Track, edit: TrackEdit) -> EditResult:
    """Write tags, then rename the file, then update ``track`` in place.

    The file must not be held open by the media player (Windows locks open files).
    """
    target = validate_edit(track, edit)
    original = Path(track.path)
    if not original.exists():
        raise TrackEditError(EditError.FILE_MISSING)

    title = edit.title.strip()
    artist = edit.artist.strip()
    try:
        write_tags(original, title, artist, edit.track_no)
    except TagWriteError as exc:
        raise TrackEditError(EditError.TAG_WRITE_FAILED) from exc

    track.title = title
    track.artist = artist
    number_changed = edit.track_no > 0 and edit.track_no != track.track_no
    if edit.track_no > 0:
        track.track_no = edit.track_no

    old_path = track.path
    if target.name != original.name:
        try:
            original.rename(target)
        except OSError as exc:
            log.warning("Rename failed %s -> %s: %s", original, target, exc)
            raise TrackEditError(EditError.RENAME_FAILED) from exc
        track.path = str(target)
        track.id = make_id(track.path)
    return EditResult(old_path=old_path, new_path=track.path, number_changed=number_changed)
