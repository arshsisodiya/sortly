"""Build script for Sortly executables on Windows.

Usage:
    python build_executables.py               # build everything (PyInstaller + Inno Setup)
    python build_executables.py --skip-installer  # PyInstaller only (used by CI before ISCC step)
"""

import os
import sys
import subprocess
import shutil
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
UPX_DIR  = BASE_DIR / "tools" / "upx"

SKIP_INSTALLER = "--skip-installer" in sys.argv

# UPX release to download when not found in PATH or tools/upx/
_UPX_VERSION = "4.2.4"
_UPX_DOWNLOAD_URL = (
    f"https://github.com/upx/upx/releases/download/v{_UPX_VERSION}/"
    f"upx-{_UPX_VERSION}-win64.zip"
)

# Qt DLLs that have CFG (Control Flow Guard) and cannot be UPX-compressed.
# PyInstaller already skips them automatically, but listing them here lets us
# pass --upx-exclude so PyInstaller doesn't even try and waste time.
_UPX_EXCLUDE_DLLS = [
    "MSVCP140.dll",
    "MSVCP140_1.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
    "ucrtbase.dll",
    "python311.dll",
    "python3.dll",
    "MediaInfo.dll",
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Network.dll",
    "Qt6OpenGL.dll",
    "Qt6DBus.dll",
    "Qt6PrintSupport.dll",
    "Qt6Svg.dll",
    "shiboken6.abi3.dll",
    "PySide6.abi3.dll",
]


def _find_or_download_upx() -> Path | None:
    """Return the directory containing upx.exe, downloading it if needed."""
    # 1. Already extracted into tools/upx/
    local_exe = UPX_DIR / "upx.exe"
    if local_exe.exists():
        print(f"  UPX found: {local_exe}")
        return UPX_DIR

    # 2. UPX is on the system PATH
    path_upx = shutil.which("upx")
    if path_upx:
        print(f"  UPX found on PATH: {path_upx}")
        return Path(path_upx).parent

    # 3. Download from GitHub releases
    print(f"  UPX not found – downloading v{_UPX_VERSION} from GitHub...")
    zip_path = BASE_DIR / "tools" / f"upx-{_UPX_VERSION}-win64.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(_UPX_DOWNLOAD_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            # The zip contains a single folder upx-X.Y.Z-win64/
            for member in zf.namelist():
                if member.endswith("upx.exe"):
                    zf.extract(member, zip_path.parent)
                    extracted = zip_path.parent / member
                    UPX_DIR.mkdir(parents=True, exist_ok=True)
                    extracted.rename(UPX_DIR / "upx.exe")
                    break
        zip_path.unlink(missing_ok=True)
        print(f"  UPX downloaded: {UPX_DIR / 'upx.exe'}")
        return UPX_DIR
    except Exception as exc:
        print(f"  WARN Could not download UPX ({exc}) – building without compression.")
        return None


def _get_version() -> str:
    """Return the app version: APP_VERSION env var (set by CI) or package __version__."""
    v = os.environ.get("APP_VERSION", "").strip()
    if v:
        return v
    try:
        from sortly import __version__
        return __version__
    except Exception:
        return "1.0.0"


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
    print("\n[*] Building CLI executable...")

    upx_dir = _find_or_download_upx()
    upx_flags = ["--upx-dir", str(upx_dir)] if upx_dir else ["--noupx"]
    upx_exclude_flags = []
    for dll in _UPX_EXCLUDE_DLLS:
        upx_exclude_flags += ["--upx-exclude", dll]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "sortly-cli",
        "--add-data", f"{BASE_DIR / 'assets'}{os.pathsep}assets",
        "--hidden-import", "watchdog.observers",
        "--hidden-import", "watchdog.observers.polling",
        "--hidden-import", "watchdog.events",
        *upx_flags,
        *upx_exclude_flags,
        str(BASE_DIR / "sortly_cli.py"),
    ]
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode == 0:
        print("  OK  CLI executable built: dist/sortly-cli.exe")
    else:
        print("  ERR CLI build failed.")
    return result.returncode == 0


# Qt modules definitely not used by a PySide6 QtWidgets-only app.
# Excluding them shaves ~40-80 MB off the uncompressed output.
_QT_EXCLUDE_MODULES = [
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtLocation",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtHelp",
    "PySide6.QtDesigner",
    "PySide6.QtRemoteObjects",
    "PySide6.QtStateMachine",
    "PySide6.QtNfc",
    "PySide6.QtSpatialAudio",
    "PySide6.QtConcurrent",
]

# Qt6 DLL name prefixes to delete from the onedir output after build.
# These correspond to the modules above and are safe to remove for a
# plain QtWidgets app.
_QT_DLL_PREFIXES_TO_REMOVE = (
    "Qt6WebEngine",
    "Qt6Multimedia",
    "Qt63D",
    "Qt6Quick",
    "Qt6Qml",
    "Qt6Charts",
    "Qt6DataVisualization",
    "Qt6Bluetooth",
    "Qt6Location",
    "Qt6Positioning",
    "Qt6Sensors",
    "Qt6SerialPort",
    "Qt6Sql",
    "Qt6Test",
    "Qt6Pdf",
    "Qt6Help",
    "Qt6Designer",
    "Qt6RemoteObjects",
    "Qt6StateMachine",
    "Qt6Nfc",
    "Qt6SpatialAudio",
    "Qt6Concurrent",
)


def _strip_unused_qt_dlls(gui_dist_dir: Path) -> None:
    """Delete Qt DLLs for modules the app does not use."""
    removed, saved = 0, 0
    for dll in list(gui_dist_dir.rglob("*.dll")):
        if dll.name.startswith(_QT_DLL_PREFIXES_TO_REMOVE):
            saved += dll.stat().st_size
            dll.unlink()
            removed += 1
    if removed:
        print(f"  Stripped {removed} unused Qt DLLs ({saved / 1_048_576:.1f} MB freed)")


def build_gui():
    """Build the GUI executable (onedir for fast startup and Inno Setup packaging)."""
    print("\n[*] Building GUI executable...")

    upx_dir = _find_or_download_upx()
    upx_flags = ["--upx-dir", str(upx_dir)] if upx_dir else ["--noupx"]
    upx_exclude_flags = []
    for dll in _UPX_EXCLUDE_DLLS:
        upx_exclude_flags += ["--upx-exclude", dll]

    # Check for icon
    icon_flag = []
    icon_path = BASE_DIR / "assets" / "sortly_logos" / "ICO" / "sortly.ico"
    if icon_path.exists():
        icon_flag = ["--icon", str(icon_path)]

    exclude_flags = []
    for mod in _QT_EXCLUDE_MODULES:
        exclude_flags += ["--exclude-module", mod]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
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
        "--collect-all", "pymediainfo",
        *exclude_flags,
        *upx_flags,
        *upx_exclude_flags,
        *icon_flag,
        str(BASE_DIR / "sortly_gui_qt.py"),
    ]
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode == 0:
        _strip_unused_qt_dlls(DIST_DIR / "sortly-gui")
        print("  OK  GUI built: dist/sortly-gui/sortly-gui.exe")
    else:
        print("  ERR GUI build failed.")
    return result.returncode == 0


def build_installer(version: str) -> bool:
    """Compile the Inno Setup installer. Requires Inno Setup 6 to be installed."""
    print(f"\n[*] Building installer (v{version})...")

    iscc_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)
    if iscc is None:
        print("  WARN Inno Setup 6 not found - skipping installer build.")
        print("     Install from: https://jrsoftware.org/isinfo.php")
        return False

    iss_path = BASE_DIR / "installer" / "sortly.iss"
    if not iss_path.exists():
        print(f"  ERR Inno Setup script not found: {iss_path}")
        return False

    result = subprocess.run(
        [str(iscc), f"/DMyAppVersion={version}", str(iss_path)],
        cwd=BASE_DIR,
    )
    if result.returncode == 0:
        print(f"  OK  Installer built: dist/SortlySetup-{version}.exe")
        return True
    else:
        print("  ERR Installer build failed.")
        return False


def main():
    print("=" * 60)
    print("  Sortly - Build System")
    print("=" * 60)

    version = _get_version()
    print(f"\n  Version: {version}")

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("\n  ERR PyInstaller not found. Install with:")
        print("     pip install pyinstaller")
        sys.exit(1)

    # Check watchdog
    try:
        import importlib.metadata
        import watchdog  # noqa: F401
        watchdog_ver = importlib.metadata.version("watchdog")
        print(f"  watchdog {watchdog_ver} found.")
    except ImportError:
        print("\n  ✗  watchdog not found. Install with:")
        print("     pip install watchdog")
        sys.exit(1)

    print()
    clean()

    ok_cli = build_cli()
    ok_gui = build_gui()
    ok_installer = True

    if ok_gui and not SKIP_INSTALLER:
        ok_installer = build_installer(version)

    print("\n" + "=" * 60)
    if ok_cli and ok_gui:
        print("  Build complete!")
        print(f"\n  Output files:")
        print(f"    dist/sortly-cli.exe             -- Portable CLI tool")
        print(f"    dist/sortly-gui/sortly-gui.exe  -- GUI application (onedir)")
        if ok_installer:
            print(f"    dist/SortlySetup-{version}.exe  -- Windows installer")
        print(f"\n  CLI usage:")
        print(f"    sortly-cli.exe organize C:\\Users\\You\\Downloads --auto")
        print(f"    sortly-cli.exe --help")
    else:
        print("  Build completed with errors.")
    print("=" * 60)


if __name__ == "__main__":
    main()
