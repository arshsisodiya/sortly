# ⚡ FileOrganizer

**Smart Automatic File Organizer for Windows**  
A powerful desktop + CLI tool that automatically categorizes and organizes files into structured folders.

---

## Features

| Feature | GUI | CLI |
|---------|-----|-----|
| Automatic file categorization | ✅ | ✅ |
| Preview before organizing | ✅ | ✅ |
| Auto-organize mode | ✅ | ✅ |
| Full undo support | ✅ | ✅ |
| Real-time folder monitoring | ✅ | ✅ |
| Custom rules | ✅ | ✅ |
| Activity log | ✅ | ✅ |
| Dry-run mode | — | ✅ |

---

## File Categories

| Category | Extensions |
|----------|------------|
| 🖼️ Images | jpg, png, gif, bmp, svg, webp, heic, psd, ai… |
| 🎬 Videos | mp4, mkv, avi, mov, wmv, flv, webm… |
| 🎵 Audio | mp3, wav, flac, aac, ogg, m4a, opus… |
| 📄 Documents | pdf, doc, docx, xls, xlsx, ppt, txt, csv, md… |
| 📦 Archives | zip, rar, 7z, tar, gz, iso, dmg… |
| 💻 Code | py, js, ts, html, css, java, c, cpp, go, rs… |
| ⚙️ Executables | exe, msi, apk, jar, bin… |
| 🔤 Fonts | ttf, otf, woff, woff2… |
| 📁 Others | Everything else |

---

## Quick Start

### Prerequisites

```bash
pip install watchdog pyinstaller PySide6
```

### Build Executables (Windows)

```bash
python build_executables.py
```

This creates two files in the `dist/` folder:
- `fileorganizer-gui.exe` — Desktop application (double-click to run)
- `fileorganizer-cli.exe` — Command-line tool

---

## GUI Application

Double-click `fileorganizer-gui.exe` to launch the desktop app.

### Workflow:
1. **Select Folder** — Click "Select Folder" or the folder path display
2. **Preview** — Click "Preview & Organize" to scan and see what will be moved
3. **Execute** — Click "Execute Plan" to apply the organization
4. **Undo** — Click "Undo Last Action" if you need to revert

### Modes:
- **Preview/Confirm Mode** (default) — Shows preview, asks before moving files
- **Auto Mode** — Organizes immediately without confirmation (toggle in sidebar)

### Real-time Monitoring:
1. Click "Add Monitor Folder" to add folders to watch
2. Click "Start Monitoring" — new files added to watched folders are auto-organized

---

## CLI Application

### Commands

```bash
# Organize with preview + confirmation
fileorganizer-cli.exe organize "C:\Users\You\Downloads"

# Auto-organize without confirmation
fileorganizer-cli.exe organize "C:\Users\You\Downloads" --auto

# Dry run (preview only, no files moved)
fileorganizer-cli.exe organize "C:\Users\You\Downloads" --dry-run

# Organize without per-file preview (summary only)
fileorganizer-cli.exe organize "C:\Users\You\Downloads" --no-preview

# Monitor folders in real time (Ctrl+C to stop)
fileorganizer-cli.exe monitor "C:\Users\You\Downloads" "C:\Users\You\Desktop"

# Undo last organization
fileorganizer-cli.exe undo

# Undo without confirmation prompt
fileorganizer-cli.exe undo --yes

# Show status and configuration
fileorganizer-cli.exe status

# List all categories and their extensions
fileorganizer-cli.exe categories

# Manage custom rules
fileorganizer-cli.exe rules list
fileorganizer-cli.exe rules add "invoice" Documents
fileorganizer-cli.exe rules add "project_" Code
fileorganizer-cli.exe rules remove 1
```

### Custom Rules

Rules let you override automatic categorization based on filename patterns:

```bash
# Files with "invoice" in the name → Documents
fileorganizer-cli.exe rules add "invoice" Documents

# Files with "screenshot" in the name → Images
fileorganizer-cli.exe rules add "screenshot" Images

# Files with "setup" in the name → Executables
fileorganizer-cli.exe rules add "setup" Executables
```

### Route Multiple Categories To One Folder

You can map multiple categories to a single output folder using `category_folder_map` in settings.
Example: send both `Audio` and `Videos` to a `Movies` folder.

### Optional Smart Media Detection (PyMediaInfo)

The Qt UI includes a **Smart Media detection** toggle (enabled by default).
When enabled:
- Long-form video files that look like full movies are promoted from `Videos` to `Movies` using metadata heuristics.
- Episode-like files are grouped as `WebSeries` when multiple episodes from the same series are detected.

If `pymediainfo` is unavailable, movie metadata checks are skipped, while filename-based web series grouping can still work.

---

## Configuration

Settings are stored at `%USERPROFILE%\.fileorganizer\settings.json`
History is stored at `%USERPROFILE%\.fileorganizer\history.json`
Activity log at `%USERPROFILE%\.fileorganizer\activity.log`

### Settings file example:
```json
{
  "auto_mode": false,
  "monitor_enabled": false,
  "monitored_folders": [],
  "custom_rules": [
    {"pattern": "invoice", "category": "Documents"},
    {"pattern": "screenshot", "category": "Images"}
  ],
  "category_folder_map": {
    "Audio": "Movies",
    "Videos": "Movies"
  },
  "excluded_extensions": [".tmp", ".part"],
  "excluded_folders": ["Images", "Videos", "Audio", "Documents", "Archives", "Code", "Executables", "Fonts", "Others"]
}
```

---

## Safety & Undo

- **History is always saved** — every organization session is recorded
- **Undo** restores files to their original locations and removes empty category folders
- **50 sessions** are kept in history
- Files with conflicting names are renamed automatically: `file.jpg` → `file (1).jpg`

---

## Running from Source

```bash
# Install dependencies
pip install watchdog PySide6

# Run GUI (Qt / native Windows style)
python organizer_gui_qt.py

# Run legacy Tkinter GUI
python organizer_gui.py

# Run CLI
python organizer_cli.py organize "C:\Users\You\Downloads"
python organizer_cli.py --help
```

---

## Project Structure

```
fileorganizer/
├── organizer_core.py      # Shared engine (categorization, undo, monitoring)
├── organizer_gui.py       # Legacy tkinter GUI application
├── organizer_gui_qt.py    # PySide6 native-style GUI application
├── organizer_cli.py       # Command-line interface
├── build_executables.py   # Build script for .exe files
├── requirements.txt       # Dependencies
└── README.md
```

---

## License

MIT License — Free to use and modify.
