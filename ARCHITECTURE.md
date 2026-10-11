# Architecture

Enderlit Player is a PySide6 (Qt Widgets) application packaged as `enderlitplayer` under `src/`.
Lower layers never import higher ones; Qt-free layers can be tested without a GUI.

```
src/enderlitplayer/
├── __init__.py          version and application identifiers (QSettings org/app names)
├── __main__.py          entry point for `python -m enderlitplayer` and the frozen build
├── app.py               bootstrap: QApplication, logging, object graph, --smoke-test
├── core/models.py       Track, Album (any playable collection), Playlist, CollectionKind, make_id
├── utils/formatting.py  time and text formatting
├── library/             Qt-free library logic
│   ├── metadata.py      tag reading/writing (mutagen), durations, cover discovery
│   ├── scanner.py       recursive scan, folder-based album grouping, sorting
│   ├── ordering.py      saved track orders, moving and renumbering
│   └── editing.py       validation and application of tag edits and file renames
├── playlists/
│   ├── manager.py       playlist CRUD, ordering, path updates, persistence format
│   └── mix.py           Random Mix generation and persistence
├── storage/settings.py  typed QSettings wrapper with 0.x-compatible keys
├── audio/
│   ├── backend.py       MediaBackend interface and the QMediaPlayer implementation
│   ├── queue.py         pure navigation rules (next, previous, random next album)
│   └── controller.py    PlaybackController: state, navigation, restore, persistence, errors
├── services/
│   ├── library_service.py  owns scanned albums; background scanning; edits and reordering
│   └── covers.py           asynchronous, cached cover decoding
├── i18n/                English/Russian strings, Translator with plural rules
└── ui/
    ├── main_window.py   composes widgets and wires them to services (no business logic)
    ├── styles/          design tokens, ThemeManager, generated stylesheet
    ├── assets/          vector icons and painted artwork (no image files needed)
    ├── widgets/         sidebar, player bar, album grid, track list, slider, controls, feedback
    ├── pages/           Songs, Albums, Playlists, collection detail, Settings
    └── dialogs/         confirmation, playlist, add-tracks and track-edit dialogs
```

## Layers and responsibilities

| Layer | Depends on | Notes |
| --- | --- | --- |
| `core`, `utils` | — | Plain dataclasses and helpers. |
| `library`, `playlists` | `core`, `storage` | No Qt widgets; fully unit-tested. |
| `storage` | QtCore | The only module that knows settings keys. |
| `audio` | `core`, `storage`, QtMultimedia | The controller only sees the `MediaBackend` interface. |
| `services` | everything above | Qt objects that own long-lived state. |
| `i18n` | `core` | Translator emits `languageChanged`. |
| `ui` | everything above | Pages emit intent signals; `MainWindow` routes them to services. |

`app.Application` creates every long-lived object once and passes dependencies explicitly — there are
no module-level singletons or global mutable state.

## Collections

`Album` represents anything playable: a folder album, a playlist, the Random Mix or the "all songs"
library view, distinguished by `CollectionKind`. Playback, the detail page and the track list treat them
uniformly; kind-specific behaviour (removal from playlists, reordering, "New mix") is switched on the kind.

## Data flow

1. `LibraryService.scan()` starts a `ScanWorker` in a `QThread`. The worker calls `scan_library`, reports
   progress through queued signals, and hands the albums back to the GUI thread. The thread and worker are
   deleted via `deleteLater` when finished; `shutdown()` cancels and joins a running scan on exit.
2. Saved album orders are applied, indexes by path and album id are rebuilt, and `scanFinished` fires.
3. `MainWindow` refreshes the pages. On the first scan it restores the last track (paused at the saved
   position); later scans rebind the playing track to the fresh objects without interrupting playback.
4. User actions on pages are emitted as signals with `Track`/`Album` objects; `MainWindow` calls
   `PlaybackController`, `LibraryService` or `PlaylistManager`, then refreshes the affected views.

Cover art is decoded on a `QThreadPool` by `CoverProvider`; grid cells request a size bucket and repaint
when `coverReady` fires. Large single covers (detail header, player bar) are decoded synchronously once
and cached.

## Persistence and compatibility

All state lives in `QSettings("EnderLit", "EnderLitPlayer")` with the 0.x keys: `language`, `theme`,
`cover_style`, `library_mode`, `library_path`, `playlists` (JSON list), `track_orders` (JSON object keyed
by album id = SHA-1 of the folder path), `volume`, `last_track_path`, `last_position`, `last_playing`,
`mix_tracks`, `mix_updated_at`. Version 2.0 adds only `window_geometry`. Values are parsed defensively
because registry, plist and INI backends return different types. Track and album identifiers are derived
exactly as before, so stored orders keep matching.

## Playback

`PlaybackController` keeps the current track and collection, applies the navigation rules from
`audio/queue.py`, persists position (debounced) and state, restores a saved position once media is loaded,
and skips missing or undecodable files without looping forever. Before a file is renamed or re-tagged the
controller releases it (`suspend`/`resume`), because Windows locks files that are open for playback.

## UI system

* **Tokens** (`ui/styles/tokens.py`): palettes for dark and light, spacing, radii, typography, component
  sizes. The stylesheet (`stylesheet.py`) is generated from them; painted widgets read colors from
  `ThemeManager`, which emits `themeChanged`/`coverStyleChanged`.
* **Item views**: the album grid (`QListView` in icon mode) and the track list (`QListView`) use custom
  delegates instead of item widgets, so large libraries stay fast. The track list header shares the
  column layout function with the row delegate.
* **Icons**: drawn with `QPainterPath` on a 24×24 grid and rendered at 1× and 2×.
* **Localization**: every visible string comes from `i18n/translations.py`; widgets implement
  `retranslate()` and respond to `languageChanged`.

## Testing

`tests/` uses pytest with Qt's `offscreen` platform. `audio_fixtures.py` generates silent WAV, MP3 and FLAC
files with tags and embedded pictures, so no copyrighted audio is stored. Playback tests use an in-memory
`MediaBackend`. UI smoke tests build the real `MainWindow`, scan a generated library in the worker thread
and exercise navigation, playback, playlists, reordering, search, theme/language switching, resizing and
the editing dialogs.

## Build and release

`scripts/build_windows.py` renders the `.ico`, writes Windows version metadata, runs PyInstaller
(`onedir`, windowed), verifies that the Qt multimedia and platform plugins were bundled, runs the frozen
executable with `--smoke-test`, then writes the portable ZIP and `SHA256SUMS.txt`. The release workflow runs
the same script on `windows-latest` for `v*` tags and publishes only after every step succeeds.
