"""Runtime language switching."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from enderlitplayer.core.models import UNKNOWN_ARTIST, VARIOUS_ARTISTS
from enderlitplayer.i18n.translations import TRANSLATIONS


def plural_form(language: str, n: int) -> str:
    n = abs(int(n))
    if language == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "many"


class Translator(QObject):
    languageChanged = Signal(str)

    def __init__(self, language: str = "en", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._language = language if language in TRANSLATIONS else "en"

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language in TRANSLATIONS and language != self._language:
            self._language = language
            self.languageChanged.emit(language)

    def t(self, key: str, **kwargs: object) -> str:
        text = TRANSLATIONS[self._language].get(key) or TRANSLATIONS["en"].get(key, key)
        return text.format(**kwargs) if kwargs else text

    def plural(self, base: str, n: int) -> str:
        return self.t(f"{base}_{plural_form(self._language, n)}", n=n)

    def artist(self, artist: str) -> str:
        """Localize the sentinel artist names produced by the scanner."""
        if artist == UNKNOWN_ARTIST:
            return self.t("unknown_artist")
        if artist == VARIOUS_ARTISTS:
            return self.t("various_artists")
        return artist
