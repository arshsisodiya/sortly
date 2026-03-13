# Sortly: Windows File Organizer

Smart file organization for Windows with a native Qt desktop app and a full CLI.

## What Changed

- Project is now modularized under the sortly package.
- Tkinter UI was removed.
- App branding updated to Sortly: Windows File Organizer.
- Logo/icon loading now uses assets/sortly_logos.

## Run From Source

Install dependencies:

```bash
pip install -r requirements.txt
```

Run Qt app:

```bash
python sortly_gui_qt.py
```

Run CLI:

```bash
python sortly_cli.py --help
python sortly_cli.py organize "C:\\Users\\You\\Downloads"
```

Legacy wrappers still exist:

```bash
python organizer_gui_qt.py
python organizer_cli.py --help
```

## Build Executables

```bash
python build_executables.py
```

Build outputs:

- dist/sortly-gui.exe
- dist/sortly-cli.exe

## Package Layout

```text
fileorganizer/
|- assets/
|  |- sortly_logos/
|- sortly/
|  |- __init__.py
|  |- core.py
|  |- gui_qt.py
|  |- cli.py
|  |- movie_detector.py
|  |- duplicate_detector.py
|  |- smart_presets.py
|- sortly_gui_qt.py
|- sortly_cli.py
|- organizer_gui_qt.py        # legacy wrapper
|- organizer_cli.py           # legacy wrapper
|- organizer_core.py          # legacy re-export
|- movie_detector.py          # legacy re-export
|- duplicate_detector.py      # legacy re-export
|- smart_presets.py           # legacy re-export
|- build_executables.py
|- requirements.txt
|- README.md
```

## Config and History Paths

Sortly stores data in:

- %USERPROFILE%\\.sortly\\settings.json
- %USERPROFILE%\\.sortly\\history.json
- %USERPROFILE%\\.sortly\\activity.log

## Notes

- Smart Media detection, presets, duplicate detection, scheduling, undo preview, and all recent features remain available in the Qt app.
- PyInstaller build uses assets/sortly_logos/ICO/sortly.ico for executable branding when present.
