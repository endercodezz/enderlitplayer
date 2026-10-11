"""UI smoke tests (offscreen): build the real window and exercise navigation and state changes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from enderlitplayer import __version__
from enderlitplayer.app import Application
from enderlitplayer.core.models import CollectionKind
from enderlitplayer.i18n.translations import EN, RU
from enderlitplayer.ui.assets.icons import ICON_NAMES, make_icon
from enderlitplayer.ui.styles.stylesheet import build_stylesheet
from enderlitplayer.ui.styles.tokens import DARK, LIGHT
from test_playback import FakeBackend


def wait_for(signal: object, timeout_ms: int = 15000) -> None:
    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


@pytest.fixture
def application(qapp: QApplication, tmp_path: Path, sample_library: Path) -> Application:
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    settings.setValue("library_path", str(sample_library))
    app = Application(qapp, settings, backend=FakeBackend())
    app.window.resize(1280, 800)
    app.window.show()
    assert app.library.scan()
    wait_for(app.library.scanFinished)
    qapp.processEvents()
    yield app
    app.window.close()
    app.window.deleteLater()
    qapp.processEvents()


def test_translations_complete() -> None:
    assert set(EN) == set(RU)
    assert all(value.strip() for value in RU.values())


def test_stylesheets_and_icons_build(qapp: QApplication) -> None:
    for palette in (DARK, LIGHT):
        sheet = build_stylesheet(palette)
        assert "rgba(" in sheet and "0." not in sheet.split("rgba(")[1].split(")")[0]
    for name in ICON_NAMES:
        assert not make_icon(name, qapp.palette().text().color(), 20).isNull()


def test_scan_populates_pages(application: Application) -> None:
    window = application.window
    assert len(application.library.albums) == 3
    assert window.albums_page.grid.grid_model.rowCount() == 3
    assert window.songs_page.panel.visible_count() == 8
    assert "3 albums" in window.settings_page.library_stats.text()
    assert window.scan_bar.isHidden()


def test_navigation_and_detail_pages(application: Application) -> None:
    window = application.window
    album = application.library.albums[0]
    window.open_album(album.id)
    assert window.current_page == "collection"
    assert window.collection_page.title_label.text() == album.title
    window.go_back()
    assert window.current_page == "albums"
    window.go_forward()
    assert window.current_page == "collection"
    window.navigate("mix")
    assert window.collection_page.kind == CollectionKind.MIX
    assert window.collection_page.panel.visible_count() == 8
    window.navigate("settings")
    assert window.current_page == "settings"
    assert __version__ in window.settings_page.version_label.text()


def test_playback_from_ui(application: Application) -> None:
    window = application.window
    album = application.library.albums[0]
    window.open_album(album.id)
    window.collection_page.playCollectionRequested.emit()
    assert application.controller.track is album.tracks[0]
    assert window.player_bar.title.full_text() == album.tracks[0].title
    assert window.collection_page.play_button.text() == "Pause"
    application.controller.next()
    assert window.collection_page.panel.view.playing_path == album.tracks[1].path


def test_playlist_lifecycle(application: Application) -> None:
    window = application.window
    lib = application.library
    playlist = lib.playlists.create("Smoke")
    lib.playlists.add_tracks(playlist.id, [t.path for t in lib.albums[0].tracks])
    window.refresh_playlists_view()
    assert window.playlists_page.grid.grid_model.rowCount() == 1
    window.open_playlist(playlist.id)
    page = window.collection_page
    assert page.kind == CollectionKind.PLAYLIST and page.add_button.isVisible()
    first = page.panel.track_at(0)
    window.move_track(page.collection, first, 1)
    assert lib.playlists.get(playlist.id).track_paths[1] == first.path
    window.remove_from_playlist(playlist.id, first)
    assert page.panel.visible_count() == len(lib.albums[0].tracks) - 1


def test_reorder_mode_and_search(application: Application) -> None:
    window = application.window
    album = next(a for a in application.library.albums if len(a.tracks) == 3)
    window.open_album(album.id)
    page = window.collection_page
    page.reorder_button.setChecked(True)
    assert page.panel.view.row_actions(0) == ["up", "down"]
    page.search.setText(album.tracks[0].title)
    assert not page.reorder_button.isChecked() and not page.reorder_button.isEnabled()
    assert page.panel.visible_count() == 1
    page.search.setText("no such track at all")
    assert page.panel.stack.currentWidget() is page.panel.empty


def test_theme_language_cover_switch(application: Application) -> None:
    window = application.window
    window.settings_page.themeRequested.emit("light")
    assert application.store.theme == "light" and application.theme.mode == "light"
    window.settings_page.languageRequested.emit("ru")
    assert window.albums_page.title.text() == "Альбомы"
    assert window.player_bar.title.full_text() == "Ничего не играет"
    window.settings_page.coverStyleRequested.emit("square")
    assert application.store.cover_style == "square"
    window.settings_page.languageRequested.emit("en")
    assert window.albums_page.title.text() == "Albums"


def test_resize_compacts_sidebar(application: Application, qapp: QApplication) -> None:
    window = application.window
    window.resize(920, 620)
    qapp.processEvents()
    assert window.sidebar.compact
    window.resize(1400, 860)
    qapp.processEvents()
    assert not window.sidebar.compact
    assert window.albums_page.grid.gridSize().width() >= 164


def test_restores_last_track(qapp: QApplication, tmp_path: Path, sample_library: Path) -> None:
    from enderlitplayer.library.scanner import scan_library

    target = next(t for a in scan_library(str(sample_library)) for t in a.tracks)
    settings = QSettings(str(tmp_path / "restore.ini"), QSettings.Format.IniFormat)
    settings.setValue("library_path", str(sample_library))
    settings.setValue("last_track_path", target.path)
    settings.setValue("last_position", 1234)
    app = Application(qapp, settings, backend=FakeBackend())
    app.library.scan()
    wait_for(app.library.scanFinished)
    assert app.controller.track is not None and app.controller.track.path == target.path
    assert not app.controller.is_playing
    app.window.close()


def test_track_edit_dialog(application: Application) -> None:
    from enderlitplayer.library.editing import EditError
    from enderlitplayer.ui.dialogs import TrackEditDialog

    track = application.library.albums[0].tracks[0]
    received = []

    def on_save(edit):
        received.append(edit)
        return EditError.FILE_EXISTS if len(received) == 1 else None

    dialog = TrackEditDialog(application.theme, application.translator, track, 3, on_save, application.window)
    assert dialog.number_edit.text() == "3"
    dialog.title_edit.setText("Renamed")
    dialog.submit()
    assert not dialog.error.isHidden() and "already exists" in dialog.error.text()
    dialog.submit()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert received[-1].title == "Renamed" and received[-1].track_no == 3


def test_playlist_dialog_requires_name(application: Application) -> None:
    from enderlitplayer.ui.dialogs import PlaylistDialog

    dialog = PlaylistDialog(application.theme, application.translator, title="New", accept_text="Create")
    dialog._on_accept()
    assert dialog.result() != dialog.DialogCode.Accepted and not dialog._error.isHidden()
    dialog.name_edit.setText("Mine")
    dialog._on_accept()
    assert dialog.result() == dialog.DialogCode.Accepted and dialog.name == "Mine"


def test_edit_through_window_updates_views(application: Application) -> None:
    from enderlitplayer.library.editing import TrackEdit

    window = application.window
    album = application.library.albums[0]
    track = album.tracks[0]
    application.controller.play_track(track, album)
    window.open_album(album.id)
    application.library.edit_track(track, TrackEdit("Edited Title", track.artist, Path(track.path).name), album)
    assert window.player_bar.title.full_text() == "Edited Title"
    assert window.collection_page.panel.track_at(0).title == "Edited Title"


def test_mouse_interactions(application: Application, qapp: QApplication) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from enderlitplayer.ui.widgets.album_grid import play_rect

    window = application.window
    window.navigate("albums")
    qapp.processEvents()
    grid = window.albums_page.grid
    first = grid.grid_model.item(0)
    rect = grid.visualRect(grid.grid_model.index(0))
    QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=play_rect(rect).center().toPoint())
    assert application.controller.collection is not None
    assert application.controller.collection.id == first.id
    assert window.current_page == "albums"  # the play button does not navigate

    QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=rect.center() - QPoint(0, rect.height() // 4))
    assert window.current_page == "collection"

    view = window.collection_page.panel.view
    row_rect = view.visualRect(view.track_model.index(1))
    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(row_rect.left() + 20, row_rect.center().y())
    )
    assert application.controller.track is view.track_model.row(1).track
