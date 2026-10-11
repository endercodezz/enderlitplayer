from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from audio_fixtures import build_sample_library
from enderlitplayer.storage.settings import SettingsStore


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def qsettings(tmp_path: Path, qapp: QApplication) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def store(qsettings: QSettings) -> SettingsStore:
    return SettingsStore(qsettings)


@pytest.fixture
def sample_library(tmp_path: Path, qapp: QApplication) -> Path:
    return build_sample_library(tmp_path / "music")
