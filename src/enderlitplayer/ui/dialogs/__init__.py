"""Modal dialogs."""

from enderlitplayer.ui.dialogs.add_tracks_dialog import AddTracksDialog
from enderlitplayer.ui.dialogs.base import Dialog, confirm, inform
from enderlitplayer.ui.dialogs.playlist_dialog import PlaylistDialog, choose_image
from enderlitplayer.ui.dialogs.track_edit_dialog import TrackEditDialog

__all__ = ["AddTracksDialog", "Dialog", "PlaylistDialog", "TrackEditDialog", "choose_image", "confirm", "inform"]
