# Changelog

All notable changes to Enderlit Player are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-10-11

A complete redesign of the interface and a rewrite of the application internals.
Existing settings, playlists, track orders and playback state are kept.

### Interface
- New layout: sidebar navigation (Songs, Albums, Playlists, Random Mix, Settings), main content
  area and a persistent player bar. The sidebar collapses to icons in narrow windows.
- Responsive album grid with large artwork, truncated titles, hover play button and focus states.
- Redesigned album, playlist and mix pages: large artwork, clear title and details, a primary Play/Pause
  button, Reorder mode, in-list search and per-track hover actions.
- New Songs page listing the whole library with search.
- Redesigned player bar: artwork and track info, previous / play-pause / next, seek bar with timestamps,
  volume with mute. Version and project links moved to Settings → About.
- Music folder management moved to Settings → Library (change folder, rescan, library statistics).
- Metadata editing moved to a focused dialog (track number, title, artist, file name) with inline errors.
- Playlist dialog with cover preview; track picker with checkboxes and search.
- Empty states for first run, empty library, empty playlists and searches without results.
- Vector icon set, centralized design tokens, coherent dark and light themes, subtle transitions.
- Russian plural forms ("1 трек", "2 трека", "5 треков").

### Architecture
- The 3,400-line `desktop_app.py` was replaced by the `enderlitplayer` package (`src/` layout) with
  separate core models, library scanning/metadata/editing, playlists, storage, audio playback,
  services, localization and UI layers.
- Playback is coordinated by `PlaybackController` over a replaceable media backend.
- Library scanning runs in a worker thread with progress and cancellation; cover art is decoded on a
  thread pool and cached.
- Packaging via `pyproject.toml`; run with `python -m enderlitplayer` or the `enderlitplayer` command.
- Logging to a rotating file in the user data directory.

### Fixed
- Rescanning no longer resets the playing track (playback restore ran after every scan).
- Scanning a different or temporarily unavailable folder no longer erases tracks from playlists.
- `ffprobe` no longer flashes console windows on Windows.
- Renaming a file now also updates the Random Mix and the remembered last track.
- Editing the currently playing file no longer fails on Windows because the file was held open.
- Missing or unplayable files are skipped with a notice instead of stopping playback silently.
- The "Scanning" indicator and track counts update correctly after a scan.

### Build and tooling
- Automated tests (library scanning, grouping, metadata, playlists, ordering, settings compatibility,
  playback navigation, Random Mix, invalid files, UI smoke tests) that need no audio hardware.
- GitHub Actions CI on Windows and Linux; tag-triggered release workflow publishing a portable Windows ZIP
  and SHA256 checksums.
- PyInstaller `onedir` build with application icon, version metadata and a frozen smoke test.
- The prebuilt executable is no longer stored in the repository.

## [0.5.9] and earlier

Single-file prototype (`desktop_app.py`). See the Git history for details.

[2.0.0]: https://github.com/endercodezz/enderlitplayer/releases/tag/v2.0.0
