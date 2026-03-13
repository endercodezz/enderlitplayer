# Enderlit Player

## English
A modern, minimal desktop music player that scans local folders, groups albums, and plays tracks with cover art.

### Features
- Scans a folder for common audio formats (mp3, flac, m4a, aac, ogg, opus, wav)
- Groups albums by folder, not by artist
- Uses embedded cover art or `cover.jpg` / `folder.jpg`
- Drag-and-drop track reordering with persistence
- Click-to-seek progress bar
- Remembers your music folder and UI language
- English / Russian UI switch

### Quick Start
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Run the app:
   - `python desktop_app.py`

### Build .exe
- `build.bat` or `build.ps1` (generates `icon.ico` automatically)
- Result will be in `dist/EnderlitPlayer.exe`

### Controls
- Mouse side buttons: Back = Albums, Forward = Album
- Keyboard: `Space` Play/Pause, `Ctrl+Left/Right` Prev/Next, `Esc` Back

### Editing metadata
Open an album, select a track, edit Title / Artist / File name, then Save.

---

## Русский
Современный минималистичный плеер, который сканирует папки, группирует альбомы и играет треки с обложками.

### Возможности
- Сканирует папку с форматами mp3, flac, m4a, aac, ogg, opus, wav
- Группирует альбомы по папке, а не по исполнителю
- Берет обложки из тегов или из `cover.jpg` / `folder.jpg`
- Перетаскивание треков для изменения порядка (сохранится)
- Переход по клику на прогресс-баре
- Запоминает путь до музыки и язык интерфейса
- Переключение English / Russian

### Быстрый старт
1. Установить зависимости:
   - `python -m pip install -r requirements.txt`
2. Запустить приложение:
   - `python desktop_app.py`

### Сборка .exe
- `build.bat` или `build.ps1` (автоматически создаст `icon.ico`)
- Готовый файл будет в `dist/EnderlitPlayer.exe`

### Управление
- Боковые кнопки мыши: Назад = Альбомы, Вперед = Альбом
- Клавиатура: `Space` Пауза/Плей, `Ctrl+Left/Right` Пред/След, `Esc` Назад

### Редактирование тегов
Откройте альбом, выберите трек, измените Название / Автор / Имя файла, затем Сохранить.
