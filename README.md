# Enderlit Player

## English
A modern, minimal desktop music player that scans local folders, groups albums, and plays tracks with cover art.

### Features
- Scans a folder for common audio formats (mp3, flac, m4a, aac, ogg, opus, wav)
- Groups albums by folder, not by artist
- Library tabs: `Albums` and `Playlists`
- Playlists: create, set custom icon, add tracks from any album
- Uses embedded cover art or `cover.jpg` / `folder.jpg`
- Track order editing in Edit mode (Up/Down) or by track number, with persistence
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
- Ready build is also available in `dist/EnderlitPlayer.exe` (you can run it right away)
- You can still build it yourself at any time; the result will be in `dist/EnderlitPlayer.exe`

### Controls
- Mouse side buttons: Back = Albums, Forward = Album
- Keyboard: `Space` Play/Pause, `Ctrl+Left/Right` Prev/Next, `Esc` Back

### Editing metadata
Open an album or playlist, select a track, edit Title / Artist / File name, then Save.

---

## Русский
Современный минималистичный плеер, который сканирует папки, группирует альбомы и играет треки с обложками.

### Возможности
- Сканирует папку с форматами mp3, flac, m4a, aac, ogg, opus, wav
- Группирует альбомы по папке, а не по исполнителю
- В медиатеке есть вкладки `Альбомы` и `Плейлисты`
- Плейлисты: создание, своя иконка, добавление треков из любых альбомов
- Берет обложки из тегов или из `cover.jpg` / `folder.jpg`
- Изменение порядка треков в режиме редактирования (Вверх/Вниз) или через номер трека (сохранится)
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
- Готовый билд также лежит в `dist/EnderlitPlayer.exe` (можно запускать сразу)
- При желании можно собрать самостоятельно; результат будет в `dist/EnderlitPlayer.exe`

### Управление
- Боковые кнопки мыши: Назад = Альбомы, Вперед = Альбом
- Клавиатура: `Space` Пауза/Плей, `Ctrl+Left/Right` Пред/След, `Esc` Назад

### Редактирование тегов
Откройте альбом или плейлист, выберите трек, измените Название / Автор / Имя файла, затем Сохранить.
