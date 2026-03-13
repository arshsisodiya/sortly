"""Build script for Sortly executables on Windows."""

import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"


def clean():
    """Remove previous build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Cleaned: {d}")

    for spec in BASE_DIR.glob("*.spec"):
        spec.unlink()
        print(f"  Removed: {spec}")


def build_cli():
    """Build the CLI executable."""
    print("\n🔨  Building CLI executable…")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "sortly-cli",
        "--add-data", f"{BASE_DIR / 'assets'}{os.pathsep}assets",
        "--hidden-import", "watchdog.observers",
        "--hidden-import", "watchdog.observers.polling",
        "--hidden-import", "watchdog.events",
        str(BASE_DIR / "sortly_cli.py"),
    ]
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode == 0:
        print("  ✓  CLI executable built: dist/sortly-cli.exe")
    else:
        print("  ✗  CLI build failed.")
    return result.returncode == 0


def build_gui():
    """Build the GUI executable."""
    print("\n🔨  Building GUI executable…")

    # Check for icon
    icon_flag = []
    icon_path = BASE_DIR / "assets" / "sortly_logos" / "ICO" / "sortly.ico"
    if icon_path.exists():
        icon_flag = ["--icon", str(icon_path)]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",           # No console window for GUI
        "--name", "sortly-gui",
        "--add-data", f"{BASE_DIR / 'assets'}{os.pathsep}assets",
        "--hidden-import", "watchdog.observers",
        "--hidden-import", "watchdog.observers.polling",
        "--hidden-import", "watchdog.events",
        "--hidden-import", "PySide6",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        *icon_flag,
        str(BASE_DIR / "sortly_gui_qt.py"),
    ]
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode == 0:
        print("  ✓  GUI executable built: dist/sortly-gui.exe")
    else:
        print("  ✗  GUI build failed.")
    return result.returncode == 0


def main():
    print("=" * 60)
    print("  Sortly — Build System")
    print("=" * 60)

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"\n  PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("\n  ✗  PyInstaller not found. Install with:")
        print("     pip install pyinstaller")
        sys.exit(1)

    # Check watchdog
    try:
        import watchdog
        print(f"  watchdog {watchdog.__version__} found.")
    except ImportError:
        print("\n  ✗  watchdog not found. Install with:")
        print("     pip install watchdog")
        sys.exit(1)

    print()
    clean()

    ok_cli = build_cli()
    ok_gui = build_gui()

    print("\n" + "=" * 60)
    if ok_cli and ok_gui:
        print("  ✓  Build complete!")
        print(f"\n  Output files:")
        print(f"    dist/sortly-cli.exe  — Command-line tool")
        print(f"    dist/sortly-gui.exe  — Desktop application")
        print(f"\n  Usage:")
        print(f"    sortly-cli.exe organize C:\\Users\\You\\Downloads --auto")
        print(f"    sortly-cli.exe --help")
    else:
        print("  ⚠  Build completed with errors.")
    print("=" * 60)


if __name__ == "__main__":
    main()
