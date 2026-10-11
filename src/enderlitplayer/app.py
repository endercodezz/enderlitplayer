"""Application bootstrap: logging, QApplication, services and the main window."""

from __future__ import annotations

import logging
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from enderlitplayer import APP_NAME, APPLICATION_NAME, ORGANIZATION_NAME, __version__
from enderlitplayer.audio.backend import MediaBackend, QtMediaBackend
from enderlitplayer.audio.controller import PlaybackController
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.playlists.manager import PlaylistManager
from enderlitplayer.playlists.mix import RandomMix
from enderlitplayer.services.covers import CoverProvider
from enderlitplayer.services.library_service import LibraryService
from enderlitplayer.storage.settings import SettingsStore
from enderlitplayer.ui.assets.artwork import build_app_icon
from enderlitplayer.ui.main_window import MainWindow
from enderlitplayer.ui.styles.theme import ThemeManager

log = logging.getLogger("enderlitplayer")


def configure_logging() -> Path | None:
    """Log to stderr and to a rotating file in the per-user data directory."""
    root = logging.getLogger("enderlitplayer")
    if root.handlers:
        return None
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not location:
        return None
    log_dir = Path(location) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "enderlitplayer.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(formatter)
    root.addHandler(handler)
    return log_dir


class Application:
    """Owns every long-lived object so their lifetimes are explicit."""

    def __init__(
        self,
        qapp: QApplication,
        settings: QSettings | None = None,
        backend: MediaBackend | None = None,
    ) -> None:
        self.store = SettingsStore(settings)
        self.theme = ThemeManager(self.store.theme, self.store.cover_style)
        self.theme.apply(qapp)
        self.translator = Translator(self.store.language)
        self.playlists = PlaylistManager(self.store)
        self.mix = RandomMix(self.store)
        self.library = LibraryService(self.store, self.playlists, self.mix)
        self.covers = CoverProvider()
        self.backend = backend if backend is not None else QtMediaBackend()
        self.controller = PlaybackController(self.backend, self.store, self.library.random_album)
        self.window = MainWindow(self.store, self.library, self.controller, self.covers, self.theme, self.translator)


def create_qapplication(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    font = QFont("Segoe UI" if sys.platform == "win32" else app.font().family())
    font.setPixelSize(13)
    app.setFont(font)
    app.setWindowIcon(build_app_icon())
    return app


def run_smoke_test(app: QApplication) -> int:
    """Start the full stack with throwaway settings and quit (used to validate frozen builds)."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = QSettings(str(Path(tmp) / "smoke.ini"), QSettings.Format.IniFormat)
        application = Application(app, settings)
        application.window.resize(1024, 700)
        application.window.show()
        QTimer.singleShot(1500, app.quit)
        code = app.exec()
        application.window.close()
        app.processEvents()
    log.info("Smoke test finished with code %s", code)
    return code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = create_qapplication(args)
    log_dir = configure_logging()
    log.info("Starting %s %s (logs: %s)", APP_NAME, __version__, log_dir)
    if "--smoke-test" in args:
        return run_smoke_test(app)
    application = Application(app)
    application.window.show_initial()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
