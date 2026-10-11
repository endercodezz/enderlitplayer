"""Pure track-navigation rules (no Qt), matching the 0.x behaviour.

* Next: the following track of the playing collection; after the last track a
  random *different* album starts from its first track.
* Previous: restarts the current track when more than 3 s have played, otherwise
  goes to the previous track (the first track restarts itself).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from enderlitplayer.core.models import Album, Track

PREV_RESTART_THRESHOLD_MS = 3000


@dataclass(frozen=True)
class Step:
    track: Track
    collection: Album


def next_step(collection: Album, current: Track) -> Step | None:
    """Next track inside the collection, or None at the end / when the track is not found."""
    index = collection.index_of(current.id)
    if index < 0 or index + 1 >= len(collection.tracks):
        return None
    return Step(collection.tracks[index + 1], collection)


def previous_step(collection: Album, current: Track, position_ms: int) -> Step | None:
    """Previous track, or None meaning "restart the current track"."""
    if position_ms > PREV_RESTART_THRESHOLD_MS:
        return None
    index = collection.index_of(current.id)
    if index < 0:
        return None
    return Step(collection.tracks[max(0, index - 1)], collection)


def pick_random_album(
    albums: Sequence[Album], exclude_id: str | None, rng: random.Random | None = None
) -> Album | None:
    candidates = [album for album in albums if album.tracks and album.id != exclude_id]
    if not candidates:
        return None
    return (rng or random).choice(candidates)
