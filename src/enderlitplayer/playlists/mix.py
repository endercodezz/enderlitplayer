"""Random Mix: a persisted selection of random tracks, refreshed on request."""

from __future__ import annotations

import random
import time
from collections.abc import Mapping

from enderlitplayer.core.models import MIX_ID, VARIOUS_ARTISTS, Album, CollectionKind, Track
from enderlitplayer.storage.settings import SettingsStore

MIX_SIZE = 20


class RandomMix:
    def __init__(self, store: SettingsStore, rng: random.Random | None = None) -> None:
        self._store = store
        self._rng = rng or random.Random()
        self.paths, self.updated_at = store.load_mix()

    def regenerate(self, all_paths: list[str]) -> None:
        pool = list(dict.fromkeys(all_paths))
        self._rng.shuffle(pool)
        self.paths = pool[:MIX_SIZE]
        self.updated_at = time.time()
        self._store.save_mix(self.paths, self.updated_at)

    def resolve(self, by_path: Mapping[str, Track]) -> list[Track]:
        """Return the mix tracks, regenerating when empty or when any track disappeared."""
        if not by_path:
            return []
        tracks = [by_path[path] for path in self.paths if path in by_path]
        if not self.paths or len(tracks) != len(self.paths):
            self.regenerate(list(by_path))
            tracks = [by_path[path] for path in self.paths if path in by_path]
        return tracks

    def replace_path(self, old_path: str, new_path: str) -> bool:
        if old_path not in self.paths:
            return False
        self.paths = [new_path if path == old_path else path for path in self.paths]
        self._store.save_mix(self.paths, self.updated_at)
        return True

    def build_collection(self, by_path: Mapping[str, Track], title: str) -> Album | None:
        tracks = self.resolve(by_path)
        if not tracks:
            return None
        return Album(
            id=MIX_ID,
            title=title,
            artist=VARIOUS_ARTISTS,
            year="",
            tracks=tracks,
            duration=sum(track.duration for track in tracks),
            kind=CollectionKind.MIX,
        )
