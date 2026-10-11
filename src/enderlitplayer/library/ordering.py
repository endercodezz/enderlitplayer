"""Custom track ordering for albums.

Orders are persisted as ``{album_id: [track_path, ...]}`` — the same structure
0.x stored under the ``track_orders`` settings key.
"""

from __future__ import annotations

from enderlitplayer.core.models import Album, Track


def apply_saved_order(album: Album, order: list[str] | None) -> bool:
    """Reorder ``album.tracks`` by a saved path list and renumber them.

    Tracks missing from the saved list keep their scan order at the end.
    Returns True when an order was applied.
    """
    if not order:
        return False
    remaining = {track.path: track for track in album.tracks}
    ordered: list[Track] = []
    for path in order:
        track = remaining.pop(path, None)
        if track is not None:
            ordered.append(track)
    ordered.extend(remaining.values())
    album.tracks = ordered
    renumber(album.tracks)
    return True


def renumber(tracks: list[Track]) -> None:
    for index, track in enumerate(tracks, start=1):
        track.track_no = index


def move_item(items: list, row: int, delta: int) -> int | None:
    """Move ``items[row]`` by ``delta`` positions in place. Returns the new row or None."""
    target = row + delta
    if row < 0 or row >= len(items) or target < 0 or target >= len(items) or delta == 0:
        return None
    items.insert(target, items.pop(row))
    return target


def sort_by_track_number(tracks: list[Track]) -> list[Track]:
    """Order used after a track number is edited manually (unnumbered tracks last)."""
    return sorted(tracks, key=lambda t: (t.track_no or 9999, t.title.lower()))


def order_paths(album: Album) -> list[str]:
    return [track.path for track in album.tracks]


def replace_path(orders: dict[str, list[str]], old_path: str, new_path: str) -> bool:
    changed = False
    for album_id, paths in orders.items():
        if old_path in paths:
            orders[album_id] = [new_path if path == old_path else path for path in paths]
            changed = True
    return changed
