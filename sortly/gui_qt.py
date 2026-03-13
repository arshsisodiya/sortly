#!/usr/bin/env python3
"""Sortly Qt GUI for the Windows File Organizer."""

import sys
import json
import os
from pathlib import Path
from typing import Optional

try:
    import winreg
except Exception:
    winreg = None

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QStyleFactory,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .core import CATEGORIES, FileOrganizer, OrganizationPlan, Settings, format_human_timestamp
from .movie_detector import MovieDetector
from .smart_presets import apply_preset, preset_names


def _candidate_base_dirs() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    bases = [module_dir, module_dir.parent]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.insert(0, Path(meipass))
    return bases


def _find_logo_path() -> Optional[Path]:
    names = [
        "sortly_logos/ICO/sortly.ico",
        "sortly_logos/PNG/transparent/sortly_transparent_512x512.png",
        "sortly_logos/PNG/transparent/sortly_transparent_256x256.png",
        "sortly_logos/PNG/dark/sortly_dark_256x256.png",
    ]
    for base in _candidate_base_dirs():
        for assets_name in ("assets", "Assets"):
            assets_dir = base / assets_name
            for name in names:
                candidate = assets_dir / Path(name)
                if candidate.exists():
                    return candidate
    return None


class MonitorBridge(QObject):
    file_organized = Signal(str, str, str)


class FileOrganizerQtApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self.organizer = FileOrganizer(settings=self.settings)
        self._movie_detector = MovieDetector()
        self._current_plan: Optional[OrganizationPlan] = None
        self._current_folder = ""
        self._notifications_unread = 0
        self._theme_mode = str(self.settings.get("ui_theme", "light")).lower()
        if self._theme_mode not in {"light", "dark"}:
            self._theme_mode = "light"

        self._monitor_bridge = MonitorBridge()
        self._monitor_bridge.file_organized.connect(self._on_monitor_file_organized)
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._run_scheduled_organize)

        self.setWindowTitle("Sortly: Windows File Organizer")
        self.resize(1180, 760)
        self.setMinimumSize(980, 620)

        logo_path = _find_logo_path()
        if logo_path:
            self.setWindowIcon(QIcon(str(logo_path)))

        self._apply_windows_base_style()
        self._build_ui()
        self._set_theme(self._theme_mode, persist=False)
        self._update_schedule_timer()
        self._refresh_history_label()
        self._sync_autostart_with_monitoring(notify=False)
        self._restore_monitoring_on_launch()

    def _autostart_value_name(self) -> str:
        return "SortlyFileOrganizer"

    def _autostart_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable)}"'

        script_path = Path(__file__).resolve().parents[1] / "sortly_gui_qt.py"
        python_exe = Path(sys.executable)
        pythonw_exe = python_exe.with_name("pythonw.exe")
        launcher = pythonw_exe if pythonw_exe.exists() else python_exe
        return f'"{launcher}" "{script_path}"'

    def _set_windows_autostart(self, enable: bool) -> tuple[bool, str]:
        if os.name != "nt" or winreg is None:
            return False, "Autostart management is only available on Windows."

        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        value_name = self._autostart_value_name()

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, self._autostart_command())
                    return True, "Autostart enabled for monitoring sessions."
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass
                return True, "Autostart disabled."
        except OSError as exc:
            return False, f"Failed to update autostart: {exc}"

    def _sync_autostart_with_monitoring(self, notify: bool = True):
        enabled = bool(self.settings.get("monitor_enabled", False))
        ok, message = self._set_windows_autostart(enabled)
        if notify:
            self._log(message, "info" if ok else "warning")

    def _restore_monitoring_on_launch(self):
        if not bool(self.settings.get("monitor_enabled", False)):
            return

        folders = [self.monitor_folders.item(i).text() for i in range(self.monitor_folders.count())]
        folders = [f for f in folders if os.path.isdir(f)]
        if not folders:
            self.settings.set("monitor_enabled", False)
            self._sync_autostart_with_monitoring(notify=False)
            self._log("Monitoring was enabled, but no valid monitored folders were found.", "warning")
            return

        self._start_monitoring(folders, startup_restore=True)

    def _apply_windows_base_style(self):
        app = QApplication.instance()
        if app is None:
            return

        available = [s.lower() for s in QStyleFactory.keys()]
        if "windowsvista" in available:
            app.setStyle("WindowsVista")
        elif "windows11" in available:
            app.setStyle("Windows11")
        elif "windows" in available:
            app.setStyle("Windows")

    def _stylesheet_for(self, theme: str) -> str:
        if theme == "dark":
            return (
                """
                QMainWindow { background: #111827; }
                QWidget { font-family: Segoe UI; font-size: 10pt; color: #e5e7eb; }

                QFrame#Sidebar {
                    background: #0f172a;
                    border-right: 1px solid #273246;
                }

                QLabel#Brand {
                    font-size: 16pt;
                    font-weight: 700;
                    color: #f9fafb;
                }

                QLabel#Muted {
                    color: #9ca3af;
                }

                QFrame#Divider {
                    background: #273246;
                    max-height: 1px;
                }

                QPushButton {
                    background: #1f2937;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #e5e7eb;
                }
                QPushButton:hover { background: #273449; }
                QPushButton:pressed { background: #334155; }
                QPushButton#Primary {
                    background: #2563eb;
                    border-color: #2563eb;
                    color: #ffffff;
                }
                QPushButton#Primary:hover { background: #1d4ed8; }

                QToolButton#InfoButton {
                    background: #1f2937;
                    border: 1px solid #334155;
                    border-radius: 9px;
                    color: #cbd5e1;
                    font-weight: 700;
                    min-width: 18px;
                    max-width: 18px;
                    min-height: 18px;
                    max-height: 18px;
                    padding: 0;
                }
                QToolButton#InfoButton:hover {
                    background: #273449;
                }

                QLineEdit, QComboBox, QTextEdit, QListWidget, QTableWidget {
                    background: #0b1220;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 6px;
                    color: #e5e7eb;
                }

                QTableWidget {
                    gridline-color: #273246;
                    alternate-background-color: #101827;
                }

                QTableWidget::item {
                    background: #0b1220;
                    color: #e5e7eb;
                }

                QTableWidget::item:selected {
                    background: #2563eb;
                    color: #ffffff;
                }

                QComboBox QAbstractItemView {
                    background: #0b1220;
                    color: #e5e7eb;
                    border: 1px solid #334155;
                    selection-background-color: #2563eb;
                    selection-color: #ffffff;
                    outline: none;
                }

                QComboBox::drop-down {
                    border: none;
                    width: 22px;
                }

                QHeaderView::section {
                    background: #1f2937;
                    border: none;
                    border-bottom: 1px solid #334155;
                    padding: 6px;
                    font-weight: 600;
                }

                QTabWidget::pane {
                    border: 1px solid #334155;
                    background: #111827;
                }

                QTabBar::tab {
                    background: #1f2937;
                    border: 1px solid #334155;
                    border-bottom: none;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    padding: 8px 12px;
                    margin-right: 4px;
                }
                QTabBar::tab:selected {
                    background: #0f172a;
                }

                QStatusBar {
                    background: #0f172a;
                    color: #cbd5e1;
                    border-top: 1px solid #273246;
                }

                QMessageBox {
                    background: #111827;
                }
                QMessageBox QLabel {
                    color: #e5e7eb;
                }
                QMessageBox QPushButton {
                    min-width: 80px;
                }

                QToolTip {
                    background: #0b1220;
                    color: #e5e7eb;
                    border: 1px solid #334155;
                    padding: 6px;
                }

                QScrollBar:vertical {
                    background: #0f172a;
                    width: 10px;
                    margin: 0;
                }
                QScrollBar::handle:vertical {
                    background: #334155;
                    min-height: 24px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #475569;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar:horizontal {
                    background: #0f172a;
                    height: 10px;
                    margin: 0;
                }
                QScrollBar::handle:horizontal {
                    background: #334155;
                    min-width: 24px;
                    border-radius: 4px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #475569;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                """
            )

        return (
            """
            QMainWindow { background: #f4f6f9; }
            QWidget { font-family: Segoe UI; font-size: 10pt; color: #1f2937; }

            QFrame#Sidebar {
                background: #ffffff;
                border-right: 1px solid #d9dee7;
            }

            QLabel#Brand {
                font-size: 16pt;
                font-weight: 700;
                color: #0f172a;
            }

            QLabel#Muted {
                color: #667085;
            }

            QFrame#Divider {
                background: #d9dee7;
                max-height: 1px;
            }

            QPushButton {
                background: #f8fafc;
                border: 1px solid #cfd7e3;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #eef3f9; }
            QPushButton:pressed { background: #e4ebf5; }
            QPushButton#Primary {
                background: #1668e3;
                border-color: #1668e3;
                color: #ffffff;
            }
            QPushButton#Primary:hover { background: #1156bf; }

            QToolButton#InfoButton {
                background: #ffffff;
                border: 1px solid #cfd7e3;
                border-radius: 9px;
                color: #344054;
                font-weight: 700;
                min-width: 18px;
                max-width: 18px;
                min-height: 18px;
                max-height: 18px;
                padding: 0;
            }
            QToolButton#InfoButton:hover {
                background: #eef3f9;
            }

            QLineEdit, QComboBox, QTextEdit, QListWidget, QTableWidget {
                background: #ffffff;
                border: 1px solid #d6dce6;
                border-radius: 8px;
                padding: 6px;
            }

            QTableWidget {
                gridline-color: #d6dce6;
                alternate-background-color: #f8fbff;
            }

            QTableWidget::item {
                background: #ffffff;
                color: #1f2937;
            }

            QTableWidget::item:selected {
                background: #1668e3;
                color: #ffffff;
            }

            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #1f2937;
                border: 1px solid #d6dce6;
                selection-background-color: #1668e3;
                selection-color: #ffffff;
                outline: none;
            }

            QComboBox::drop-down {
                border: none;
                width: 22px;
            }

            QHeaderView::section {
                background: #eef2f8;
                border: none;
                border-bottom: 1px solid #d6dce6;
                padding: 6px;
                font-weight: 600;
            }

            QTabWidget::pane {
                border: 1px solid #d6dce6;
                background: #ffffff;
            }

            QTabBar::tab {
                background: #edf2f8;
                border: 1px solid #d6dce6;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
            }

            QStatusBar {
                background: #ffffff;
                color: #475467;
                border-top: 1px solid #d9dee7;
            }

            QMessageBox {
                background: #ffffff;
            }
            QMessageBox QLabel {
                color: #1f2937;
            }
            QMessageBox QPushButton {
                min-width: 80px;
            }

            QToolTip {
                background: #ffffff;
                color: #1f2937;
                border: 1px solid #d6dce6;
                padding: 6px;
            }

            QScrollBar:vertical {
                background: #f4f6f9;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #c5cedb;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #aeb9c8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #f4f6f9;
                height: 10px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #c5cedb;
                min-width: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #aeb9c8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            """
        )

    def _set_theme(self, theme: str, persist: bool = True):
        theme = (theme or "light").lower()
        if theme not in {"light", "dark"}:
            theme = "light"

        self._theme_mode = theme
        self.setStyleSheet(self._stylesheet_for(theme))

        if hasattr(self, "theme_toggle"):
            self.theme_toggle.blockSignals(True)
            self.theme_toggle.setChecked(theme == "dark")
            self.theme_toggle.blockSignals(False)

        if persist:
            self.settings.set("ui_theme", theme)

    def _on_theme_toggled(self, _state):
        selected = "dark" if self.theme_toggle.isChecked() else "light"
        self._set_theme(selected, persist=True)
        self._log(f"Theme changed to: {selected}")

    def _on_schedule_settings_changed(self, _value=None):
        enabled = bool(self.schedule_checkbox.isChecked())
        interval = int(self.schedule_interval.currentText())
        self.settings.set("schedule_enabled", enabled)
        self.settings.set("schedule_interval_minutes", interval)
        self._update_schedule_timer()
        self._log(f"Scheduled auto-organize set to: {enabled} every {interval} minute(s)")

    def _apply_selected_preset(self):
        name = self.preset_selector.currentText().strip()
        if not name:
            return
        preset = apply_preset(name)
        for key, value in preset.items():
            self.settings.set(key, value)

        self._sync_ui_from_settings()
        self._log(f"Applied smart preset: {name}", "success")

    def _sync_ui_from_settings(self):
        self.organizer.settings = self.settings
        self.organizer.categorizer.custom_rules = self.settings.get("custom_rules", [])
        self.media_detection_checkbox.setChecked(bool(self.settings.get("enable_smart_media_detection", True)))
        self.duplicate_detection_checkbox.setChecked(bool(self.settings.get("enable_duplicate_detection", False)))
        self.protected_files_checkbox.setChecked(bool(self.settings.get("protect_recent_files", False)))
        self.schedule_checkbox.setChecked(bool(self.settings.get("schedule_enabled", False)))

        protected_value = str(self.settings.get("protect_recent_minutes", 30))
        protected_index = self.protected_minutes.findText(protected_value)
        if protected_index >= 0:
            self.protected_minutes.setCurrentIndex(protected_index)

        schedule_value = str(self.settings.get("schedule_interval_minutes", 15))
        schedule_index = self.schedule_interval.findText(schedule_value)
        if schedule_index >= 0:
            self.schedule_interval.setCurrentIndex(schedule_index)

        self._refresh_rules_list()
        self._refresh_category_mapping_list()
        self._refresh_conflict_policy_list()
        self._update_schedule_timer()

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Configuration", "sortly-config.json", "JSON Files (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.settings._data, handle, indent=2)
        self._log(f"Configuration exported: {path}", "success")

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Configuration", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            self._show_warning("Import failed", f"Could not read configuration.\n\n{exc}")
            return
        for key, value in data.items():
            self.settings.set(key, value)
        self._sync_ui_from_settings()
        self._log(f"Configuration imported: {path}", "success")

    def _update_schedule_timer(self):
        enabled = bool(self.settings.get("schedule_enabled", False))
        interval = int(self.settings.get("schedule_interval_minutes", 15))
        if enabled:
            self._schedule_timer.start(max(1, interval) * 60 * 1000)
        else:
            self._schedule_timer.stop()

    def _run_scheduled_organize(self):
        if not self._current_folder or not os.path.isdir(self._current_folder):
            self._log("Scheduled auto-organize skipped: no valid folder selected", "warning")
            return
        plan, _ = self.organizer.organize_folder(self._current_folder, auto=False)
        if plan.total_files == 0:
            self._log("Scheduled auto-organize: nothing to do")
            return
        records = self.organizer.execute_plan(plan, self._current_folder)
        self._current_plan = None
        self._refresh_history_label()
        self._log(f"Scheduled auto-organize moved {len(records)} file(s)", "success")
        self.statusBar().showMessage(f"Scheduled run completed: {len(records)} file(s) organized")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        shell.addWidget(splitter)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(10)

        brand = QLabel("Sortly")
        brand.setObjectName("Brand")
        sidebar_layout.addWidget(brand)

        subtitle = QLabel("Native Windows UI (Qt)")
        subtitle.setText("Organize your Windows files smartly")
        subtitle.setObjectName("Muted")
        sidebar_layout.addWidget(subtitle)

        self.folder_label = QLabel("No folder selected")
        self.folder_label.setWordWrap(True)
        sidebar_layout.addWidget(self.folder_label)

        actions_label = QLabel("Quick Actions")
        actions_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(actions_label)

        self.select_btn = QPushButton("Select Folder")
        self.select_btn.clicked.connect(self._pick_folder)
        sidebar_layout.addWidget(self.select_btn)

        self.organize_btn = QPushButton("Organize Now")
        self.organize_btn.setObjectName("Primary")
        self.organize_btn.clicked.connect(self._do_organize)
        sidebar_layout.addWidget(self.organize_btn)

        self.undo_btn = QPushButton("Undo Last Action")
        self.undo_btn.clicked.connect(self._do_undo)
        sidebar_layout.addWidget(self.undo_btn)

        line_quick = QFrame()
        line_quick.setObjectName("Divider")
        line_quick.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(line_quick)

        smart_label = QLabel("Smart Options")
        smart_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(smart_label)

        self.auto_checkbox = QCheckBox("Auto mode")
        self.auto_checkbox.setChecked(bool(self.settings.get("auto_mode", False)))
        self.auto_checkbox.stateChanged.connect(self._on_auto_mode_changed)
        sidebar_layout.addWidget(self.auto_checkbox)

        media_detection_row = QHBoxLayout()
        self.media_detection_checkbox = QCheckBox("Smart Media detection")
        default_enabled = bool(
            self.settings.get(
                "enable_smart_media_detection",
                self.settings.get("enable_movie_detection", True),
            )
        )
        self.media_detection_checkbox.setChecked(default_enabled)
        self.media_detection_checkbox.stateChanged.connect(self._on_smart_media_detection_changed)
        media_detection_row.addWidget(self.media_detection_checkbox)

        media_info_btn = QToolButton()
        media_info_btn.setObjectName("InfoButton")
        media_info_btn.setText("?")
        media_info_btn.setToolTip(
            "Smart Media detection:\n"
            "- Detects movie-like files using metadata heuristics\n"
            "- Detects web series when multiple episode files exist\n"
            "- Routes matched videos to Movies/WebSeries categories"
        )
        media_info_btn.clicked.connect(self._show_smart_media_info)
        media_info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        media_info_btn.setFixedSize(18, 18)
        media_detection_row.addWidget(media_info_btn)
        media_detection_row.addStretch(1)

        sidebar_layout.addLayout(media_detection_row)

        self.duplicate_detection_checkbox = QCheckBox("Duplicate finder before move")
        self.duplicate_detection_checkbox.setChecked(bool(self.settings.get("enable_duplicate_detection", False)))
        self.duplicate_detection_checkbox.stateChanged.connect(self._on_duplicate_detection_changed)
        sidebar_layout.addWidget(self.duplicate_detection_checkbox)

        self.protected_files_checkbox = QCheckBox("Protected recent files")
        self.protected_files_checkbox.setChecked(bool(self.settings.get("protect_recent_files", False)))
        self.protected_files_checkbox.stateChanged.connect(self._on_protected_files_changed)
        sidebar_layout.addWidget(self.protected_files_checkbox)

        protected_row = QHBoxLayout()
        sidebar_layout.addLayout(protected_row)
        protected_row.addWidget(QLabel("Ignore files newer than"))
        self.protected_minutes = QComboBox()
        self.protected_minutes.addItems(["5", "10", "30", "60", "180"])
        current_protected = str(self.settings.get("protect_recent_minutes", 30))
        protected_index = self.protected_minutes.findText(current_protected)
        if protected_index >= 0:
            self.protected_minutes.setCurrentIndex(protected_index)
        self.protected_minutes.currentTextChanged.connect(self._on_protected_files_changed)
        protected_row.addWidget(self.protected_minutes)
        protected_row.addWidget(QLabel("min"))

        line_smart = QFrame()
        line_smart.setObjectName("Divider")
        line_smart.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(line_smart)

        appearance_label = QLabel("Appearance & Settings")
        appearance_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(appearance_label)

        self.theme_toggle = QCheckBox("Dark theme")
        self.theme_toggle.setChecked(self._theme_mode == "dark")
        self.theme_toggle.stateChanged.connect(self._on_theme_toggled)
        sidebar_layout.addWidget(self.theme_toggle)

        config_row = QHBoxLayout()
        sidebar_layout.addLayout(config_row)
        export_btn = QPushButton("Export Config")
        export_btn.clicked.connect(self._export_config)
        config_row.addWidget(export_btn)
        import_btn = QPushButton("Import Config")
        import_btn.clicked.connect(self._import_config)
        config_row.addWidget(import_btn)

        preset_label = QLabel("Smart Presets")
        preset_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(preset_label)

        preset_row = QHBoxLayout()
        sidebar_layout.addLayout(preset_row)

        self.preset_selector = QComboBox()
        self.preset_selector.addItems(preset_names())
        preset_row.addWidget(self.preset_selector, 1)

        apply_preset_btn = QPushButton("Apply")
        apply_preset_btn.clicked.connect(self._apply_selected_preset)
        preset_row.addWidget(apply_preset_btn)

        line_settings = QFrame()
        line_settings.setObjectName("Divider")
        line_settings.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(line_settings)

        schedule_label = QLabel("Scheduled Auto-Organize")
        schedule_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(schedule_label)

        self.schedule_checkbox = QCheckBox("Enable schedule")
        self.schedule_checkbox.setChecked(bool(self.settings.get("schedule_enabled", False)))
        self.schedule_checkbox.stateChanged.connect(self._on_schedule_settings_changed)
        sidebar_layout.addWidget(self.schedule_checkbox)

        schedule_row = QHBoxLayout()
        sidebar_layout.addLayout(schedule_row)
        schedule_row.addWidget(QLabel("Every"))

        self.schedule_interval = QComboBox()
        self.schedule_interval.addItems(["5", "10", "15", "30", "60"])
        current_interval = str(self.settings.get("schedule_interval_minutes", 15))
        index = self.schedule_interval.findText(current_interval)
        if index >= 0:
            self.schedule_interval.setCurrentIndex(index)
        self.schedule_interval.currentTextChanged.connect(self._on_schedule_settings_changed)
        schedule_row.addWidget(self.schedule_interval)
        schedule_row.addWidget(QLabel("min"))

        line_history = QFrame()
        line_history.setObjectName("Divider")
        line_history.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(line_history)

        history_title = QLabel("History")
        history_title.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(history_title)

        self.history_label = QLabel("")
        self.history_label.setObjectName("Muted")
        self.history_label.setWordWrap(True)
        sidebar_layout.addWidget(self.history_label)

        line_monitor = QFrame()
        line_monitor.setObjectName("Divider")
        line_monitor.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(line_monitor)

        monitor_label = QLabel("Monitoring")
        monitor_label.setStyleSheet("font-weight: 600;")
        sidebar_layout.addWidget(monitor_label)

        self.monitor_folders = QListWidget()
        self.monitor_folders.setMinimumHeight(120)
        sidebar_layout.addWidget(self.monitor_folders)

        for folder in self.settings.get("monitored_folders", []):
            self.monitor_folders.addItem(folder)

        self.add_monitor_btn = QPushButton("Add Monitor Folder")
        self.add_monitor_btn.clicked.connect(self._add_monitor_folder)
        sidebar_layout.addWidget(self.add_monitor_btn)

        self.monitor_btn = QPushButton("Start Monitoring")
        self.monitor_btn.clicked.connect(self._toggle_monitor)
        sidebar_layout.addWidget(self.monitor_btn)

        sidebar_layout.addStretch(1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(10)

        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs, 1)

        self.preview_tab = self._build_preview_tab()
        self.rules_tab = self._build_rules_tab()
        self.history_tab = self._build_history_tab()
        self.notifications_tab = self._build_notifications_tab()
        self.log_tab = self._build_log_tab()

        self.tabs.addTab(self.preview_tab, "Preview")
        self.tabs.addTab(self.rules_tab, "Custom Rules")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.notifications_tab, "Notifications")
        self.tabs.addTab(self.log_tab, "Activity Log")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sidebar_scroll.setWidget(sidebar)

        splitter.addWidget(sidebar_scroll)
        splitter.addWidget(content)
        splitter.setSizes([320, 860])

        status = QStatusBar()
        self.setStatusBar(status)
        self.statusBar().showMessage("Ready")

        undo_action = QAction("Undo", self)
        undo_action.triggered.connect(self._do_undo)
        undo_action.setShortcut("Ctrl+Z")
        self.addAction(undo_action)

    def _build_preview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.summary_label = QLabel("Pick a folder and click Preview Organization.")
        self.summary_label.setObjectName("Muted")
        layout.addWidget(self.summary_label)

        self.moves_table = QTableWidget(0, 4)
        self.moves_table.setHorizontalHeaderLabels(["File", "Category", "Confidence", "Destination"])
        self.moves_table.horizontalHeader().setStretchLastSection(True)
        self.moves_table.verticalHeader().setVisible(False)
        self.moves_table.setAlternatingRowColors(True)
        self.moves_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.moves_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.moves_table.itemSelectionChanged.connect(self._show_selected_move_reason)
        layout.addWidget(self.moves_table)

        reason_title = QLabel("Why this classification")
        reason_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(reason_title)

        self.reason_panel = QTextEdit()
        self.reason_panel.setReadOnly(True)
        self.reason_panel.setMaximumHeight(130)
        layout.addWidget(self.reason_panel)
        return tab

    def _build_rules_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        layout.addLayout(top)

        self.rule_pattern = QLineEdit()
        self.rule_pattern.setPlaceholderText("Pattern (for example: invoice)")
        top.addWidget(self.rule_pattern, 2)

        self.rule_category = QComboBox()
        self.rule_category.addItems(list(CATEGORIES.keys()))
        self.rule_category.setCurrentText("Documents")
        top.addWidget(self.rule_category, 1)

        add_rule_btn = QPushButton("Add Rule")
        add_rule_btn.clicked.connect(self._add_rule)
        top.addWidget(add_rule_btn)

        self.rules_list = QListWidget()
        layout.addWidget(self.rules_list, 1)

        remove_rule_btn = QPushButton("Remove Selected Rule")
        remove_rule_btn.clicked.connect(self._remove_rule)
        layout.addWidget(remove_rule_btn)

        map_title = QLabel("Category to Folder Mapping")
        map_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(map_title)

        map_help = QLabel("Use this to route multiple categories into one folder (example: Audio -> Movies and Videos -> Movies).")
        map_help.setWordWrap(True)
        map_help.setObjectName("Muted")
        layout.addWidget(map_help)

        map_row = QHBoxLayout()
        layout.addLayout(map_row)

        self.map_category = QComboBox()
        self.map_category.addItems(list(CATEGORIES.keys()))
        self.map_category.setCurrentText("Audio")
        map_row.addWidget(self.map_category, 1)

        self.map_folder = QLineEdit()
        self.map_folder.setPlaceholderText("Target folder name (for example: Movies)")
        map_row.addWidget(self.map_folder, 2)

        save_map_btn = QPushButton("Save Mapping")
        save_map_btn.clicked.connect(self._save_category_mapping)
        map_row.addWidget(save_map_btn)

        self.map_list = QListWidget()
        self.map_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.map_list, 1)

        remove_map_btn = QPushButton("Remove Selected Mapping")
        remove_map_btn.clicked.connect(self._remove_category_mapping)
        layout.addWidget(remove_map_btn)

        conflict_title = QLabel("Per-Category Conflict Policy")
        conflict_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(conflict_title)

        conflict_help = QLabel("Choose what happens when a destination file already exists: rename, skip, or replace.")
        conflict_help.setWordWrap(True)
        conflict_help.setObjectName("Muted")
        layout.addWidget(conflict_help)

        conflict_row = QHBoxLayout()
        layout.addLayout(conflict_row)

        self.conflict_category = QComboBox()
        self.conflict_category.addItems(list(CATEGORIES.keys()))
        self.conflict_category.setCurrentText("Documents")
        conflict_row.addWidget(self.conflict_category, 1)

        self.conflict_policy = QComboBox()
        self.conflict_policy.addItems(["rename", "skip", "replace"])
        conflict_row.addWidget(self.conflict_policy, 1)

        save_conflict_btn = QPushButton("Save Policy")
        save_conflict_btn.clicked.connect(self._save_conflict_policy)
        conflict_row.addWidget(save_conflict_btn)

        self.conflict_list = QListWidget()
        self.conflict_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.conflict_list, 1)

        remove_conflict_btn = QPushButton("Remove Selected Policy")
        remove_conflict_btn.clicked.connect(self._remove_conflict_policy)
        layout.addWidget(remove_conflict_btn)

        tester_title = QLabel("Rule Tester")
        tester_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(tester_title)

        tester_help = QLabel("Enter a filename to see how it will be classified before organizing.")
        tester_help.setWordWrap(True)
        tester_help.setObjectName("Muted")
        layout.addWidget(tester_help)

        tester_row = QHBoxLayout()
        layout.addLayout(tester_row)

        self.rule_tester_input = QLineEdit()
        self.rule_tester_input.setPlaceholderText("Example: My.Show.S01E01.mkv")
        tester_row.addWidget(self.rule_tester_input, 1)

        test_rule_btn = QPushButton("Test")
        test_rule_btn.clicked.connect(self._test_rule)
        tester_row.addWidget(test_rule_btn)

        self.rule_tester_output = QTextEdit()
        self.rule_tester_output.setReadOnly(True)
        self.rule_tester_output.setMaximumHeight(120)
        layout.addWidget(self.rule_tester_output)

        self._refresh_rules_list()
        self._refresh_category_mapping_list()
        self._refresh_conflict_policy_list()
        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        layout.addLayout(top)

        history_help = QLabel("Recent organization sessions. Select one to inspect moved files.")
        history_help.setObjectName("Muted")
        top.addWidget(history_help, 1)

        preview_undo_btn = QPushButton("Preview Undo")
        preview_undo_btn.clicked.connect(self._preview_undo)
        top.addWidget(preview_undo_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_history_tab)
        top.addWidget(refresh_btn)

        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["Timestamp", "Folder", "Moves"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.itemSelectionChanged.connect(self._show_selected_history_moves)
        layout.addWidget(self.history_table, 1)

        self.history_moves = QListWidget()
        layout.addWidget(self.history_moves, 1)

        self._refresh_history_tab()
        return tab

    def _build_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)

        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.log_text.clear)
        layout.addWidget(clear_btn)
        return tab

    def _build_notifications_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        head = QHBoxLayout()
        layout.addLayout(head)

        self.notifications_status = QLabel("Notifications (0 unread)")
        self.notifications_status.setObjectName("Muted")
        head.addWidget(self.notifications_status, 1)

        mark_read_btn = QPushButton("Mark all as read")
        mark_read_btn.clicked.connect(self._mark_notifications_read)
        head.addWidget(mark_read_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_notifications)
        head.addWidget(clear_btn)

        self.notifications_list = QListWidget()
        layout.addWidget(self.notifications_list, 1)
        return tab

    def _on_tab_changed(self, index: int):
        if self.tabs.tabText(index) == "Notifications":
            self._mark_notifications_read()

    def _add_notification(self, message: str):
        self.notifications_list.insertItem(0, message)
        self._notifications_unread += 1
        self._update_notifications_badge()

    def _mark_notifications_read(self):
        self._notifications_unread = 0
        self._update_notifications_badge()

    def _clear_notifications(self):
        self.notifications_list.clear()
        self._notifications_unread = 0
        self._update_notifications_badge()

    def _update_notifications_badge(self):
        self.notifications_status.setText(f"Notifications ({self._notifications_unread} unread)")
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).startswith("Notifications"):
                if self._notifications_unread:
                    self.tabs.setTabText(i, f"Notifications ({self._notifications_unread})")
                else:
                    self.tabs.setTabText(i, "Notifications")
                break

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Organize")
        if not folder:
            return
        self._current_folder = folder
        self.folder_label.setText(folder)
        self.statusBar().showMessage(f"Selected: {folder}")
        self._log(f"Selected folder: {folder}")
        self._do_preview()

    def _show_smart_media_info(self):
        self._show_info(
            "Smart Media Detection",
            "Automatically improves video organization:\n"
            "- Promotes full-length videos to Movies using metadata heuristics\n"
            "- Detects series episodes (for example S01E01, 1x02) and groups them as WebSeries\n"
            "- Works during preview, organize, and monitor modes",
        )

    def _message_box(self, icon, title: str, text: str, buttons, default_button=None):
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default_button is not None:
            box.setDefaultButton(default_button)
        box.setStyleSheet(self.styleSheet())
        return box.exec()

    def _show_info(self, title: str, text: str):
        self._message_box(
            QMessageBox.Icon.Information,
            title,
            text,
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )

    def _show_warning(self, title: str, text: str):
        self._message_box(
            QMessageBox.Icon.Warning,
            title,
            text,
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )

    def _ask_confirmation(self, title: str, text: str) -> bool:
        result = self._message_box(
            QMessageBox.Icon.Question,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _do_preview(self):
        if not self._current_folder:
            self._show_warning("No folder selected", "Please select a folder first.")
            return

        self.statusBar().showMessage("Building preview...")
        plan, _ = self.organizer.organize_folder(self._current_folder, auto=False)
        self._current_plan = plan
        self._render_plan(plan)
        self._log(f"Preview generated for {self._current_folder}: {plan.total_files} file(s)")
        self.statusBar().showMessage("Preview ready")

    def _do_organize(self):
        if not self._current_folder:
            self._show_warning("No folder selected", "Please select a folder first.")
            return

        auto_mode = self.auto_checkbox.isChecked()
        if self._current_plan is None:
            self._do_preview()
            if self._current_plan is None:
                return

        plan = self._current_plan
        if plan.total_files == 0:
            self._show_info("Nothing to do", "No files need organizing.")
            return

        if not auto_mode:
            if not self._ask_confirmation("Confirm", f"Organize {plan.total_files} file(s)?"):
                return

        self.statusBar().showMessage("Organizing files...")
        records = self.organizer.execute_plan(plan, self._current_folder)
        self._log(f"Organized {len(records)} file(s)", "success")
        self._current_plan = None
        self._refresh_history_label()
        self._do_preview()
        self._show_info("Complete", f"Organized {len(records)} file(s).")

    def _render_plan(self, plan: OrganizationPlan):
        self.moves_table.setRowCount(0)
        for index, (src, dst, cat) in enumerate(plan.moves):
            detail = plan.move_details[index] if index < len(plan.move_details) else {}
            row = self.moves_table.rowCount()
            self.moves_table.insertRow(row)
            self.moves_table.setItem(row, 0, QTableWidgetItem(Path(src).name))
            self.moves_table.setItem(row, 1, QTableWidgetItem(cat))
            self.moves_table.setItem(row, 2, QTableWidgetItem(f"{detail.get('confidence', 0)}%"))
            self.moves_table.setItem(row, 3, QTableWidgetItem(dst))

        cats = plan.categories_summary
        if not cats:
            self.summary_label.setText("No files to organize. Folder already looks clean.")
            return

        summary = ", ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda i: -i[1]))
        self.summary_label.setText(f"{plan.total_files} file(s) planned. {summary}")
        if plan.move_details:
            self.moves_table.selectRow(0)
            self._show_selected_move_reason()
        else:
            self.reason_panel.setPlainText("No file selected.")

    def _show_selected_move_reason(self):
        if self._current_plan is None:
            self.reason_panel.setPlainText("Preview a folder to inspect classification reasons.")
            return

        row = self.moves_table.currentRow()
        if row < 0 or row >= len(self._current_plan.move_details):
            self.reason_panel.setPlainText("Select a file to inspect classification reasons.")
            return

        detail = self._current_plan.move_details[row]
        reasons = detail.get("reasons", []) or ["No additional reasoning available."]
        confidence = detail.get("confidence", 0)
        category = detail.get("category", "")
        destination = detail.get("destination", "")
        text = (
            f"Category: {category}\n"
            f"Confidence: {confidence}%\n"
            f"Destination: {destination}\n\n"
            + "\n".join(f"- {reason}" for reason in reasons)
        )
        self.reason_panel.setPlainText(text)

    def _do_undo(self):
        success, message = self.organizer.undo_last()
        if success:
            self._log(message, "success")
            self._show_info("Undo", message)
        else:
            self._log(message, "warning")
            self._show_warning("Undo", message)
        self._refresh_history_label()

    def _preview_undo(self):
        session = self.organizer.history.peek_last_session()
        if not session:
            self._show_info("Undo Preview", "No history available to undo.")
            return

        moves = session.get("moves", [])
        if not moves:
            self._show_info("Undo Preview", "The last session has no recorded moves.")
            return

        preview_lines = []
        for move in moves[:25]:
            src_name = Path(move.get("source", "")).name
            dst_name = Path(move.get("destination", "")).name
            preview_lines.append(f"{dst_name} -> {src_name}")
        if len(moves) > 25:
            preview_lines.append(f"... and {len(moves) - 25} more file(s)")

        text = (
            f"Undo will restore {len(moves)} file(s) from the last session.\n\n"
            + "\n".join(preview_lines)
        )
        self._show_info("Undo Preview", text)

    def _add_rule(self):
        pattern = self.rule_pattern.text().strip()
        category = self.rule_category.currentText().strip()
        if not pattern:
            self._show_warning("Invalid rule", "Pattern cannot be empty.")
            return

        rules = self.settings.get("custom_rules", [])
        rules.append({"pattern": pattern, "category": category})
        self.settings.set("custom_rules", rules)
        self.organizer.categorizer.custom_rules = rules

        self.rule_pattern.clear()
        self._refresh_rules_list()
        self._log(f"Rule added: '{pattern}' -> {category}", "success")

    def _remove_rule(self):
        row = self.rules_list.currentRow()
        if row < 0:
            return

        rules = self.settings.get("custom_rules", [])
        if row >= len(rules):
            return

        removed = rules.pop(row)
        self.settings.set("custom_rules", rules)
        self.organizer.categorizer.custom_rules = rules
        self._refresh_rules_list()
        self._log(f"Rule removed: '{removed.get('pattern', '')}'")

    def _refresh_rules_list(self):
        self.rules_list.clear()
        rules = self.settings.get("custom_rules", [])
        if not rules:
            self.rules_list.addItem("No custom rules configured.")
            self.rules_list.setEnabled(False)
            return

        self.rules_list.setEnabled(True)
        for idx, rule in enumerate(rules, start=1):
            self.rules_list.addItem(f"{idx}. {rule.get('pattern', '')} -> {rule.get('category', 'Others')}")

    def _refresh_category_mapping_list(self):
        self.map_list.clear()
        mapping = self.settings.get("category_folder_map", {}) or {}
        if not mapping:
            self.map_list.addItem("No custom destination mappings configured.")
            self.map_list.setEnabled(False)
            return

        self.map_list.setEnabled(True)
        for category, folder_name in sorted(mapping.items()):
            self.map_list.addItem(f"{category} -> {folder_name}")

    def _refresh_conflict_policy_list(self):
        self.conflict_list.clear()
        policies = self.settings.get("category_conflict_policy", {}) or {}
        if not policies:
            self.conflict_list.addItem("No custom conflict policies configured.")
            self.conflict_list.setEnabled(False)
            return

        self.conflict_list.setEnabled(True)
        for category, policy in sorted(policies.items()):
            self.conflict_list.addItem(f"{category} -> {policy}")

    def _save_category_mapping(self):
        category = self.map_category.currentText().strip()
        folder_name = self.map_folder.text().strip()
        if not category:
            return
        if not folder_name:
            self._show_warning("Invalid folder", "Target folder name cannot be empty.")
            return

        mapping = self.settings.get("category_folder_map", {}) or {}
        mapping[category] = folder_name
        self.settings.set("category_folder_map", mapping)

        self.map_folder.clear()
        self._refresh_category_mapping_list()
        self._log(f"Destination mapping saved: {category} -> {folder_name}", "success")

    def _remove_category_mapping(self):
        row = self.map_list.currentRow()
        if row < 0:
            return

        selected = self.map_list.currentItem()
        if selected is None:
            return

        text = selected.text()
        if " -> " not in text:
            return

        category = text.split(" -> ", 1)[0].strip()
        mapping = self.settings.get("category_folder_map", {}) or {}
        if category in mapping:
            del mapping[category]
            self.settings.set("category_folder_map", mapping)
            self._refresh_category_mapping_list()
            self._log(f"Destination mapping removed for: {category}")

    def _save_conflict_policy(self):
        category = self.conflict_category.currentText().strip()
        policy = self.conflict_policy.currentText().strip().lower()
        if not category or policy not in {"rename", "skip", "replace"}:
            return

        policies = self.settings.get("category_conflict_policy", {}) or {}
        policies[category] = policy
        self.settings.set("category_conflict_policy", policies)
        self._refresh_conflict_policy_list()
        self._log(f"Conflict policy saved: {category} -> {policy}", "success")

    def _remove_conflict_policy(self):
        row = self.conflict_list.currentRow()
        if row < 0:
            return

        item = self.conflict_list.currentItem()
        if item is None:
            return

        text = item.text()
        if " -> " not in text:
            return

        category = text.split(" -> ", 1)[0].strip()
        policies = self.settings.get("category_conflict_policy", {}) or {}
        if category in policies:
            del policies[category]
            self.settings.set("category_conflict_policy", policies)
            self._refresh_conflict_policy_list()
            self._log(f"Conflict policy removed for: {category}")

    def _test_rule(self):
        filename = self.rule_tester_input.text().strip()
        if not filename:
            self.rule_tester_output.setPlainText("Enter a filename to test.")
            return

        fake_path = str(Path(self._current_folder or os.getcwd()) / filename)
        decision = self.organizer.analyze_file(fake_path, sibling_video_paths=[fake_path])
        destination = self.organizer._destination_folder_name(decision.category)
        result = (
            f"Category: {decision.category}\n"
            f"Destination folder: {destination}\n"
            f"Confidence: {decision.confidence}%\n\n"
            + "\n".join(f"- {reason}" for reason in (decision.reasons or ["No rule matched."]))
        )
        self.rule_tester_output.setPlainText(result)

    def _refresh_history_tab(self):
        sessions = self.organizer.history.list_sessions(limit=50)
        self.history_table.setRowCount(0)

        for idx, session in enumerate(sessions):
            ts = format_human_timestamp(session.get("timestamp", ""))
            folder = str(session.get("folder", ""))
            moves = len(session.get("moves", []))

            self.history_table.insertRow(idx)
            self.history_table.setItem(idx, 0, QTableWidgetItem(ts))
            self.history_table.setItem(idx, 1, QTableWidgetItem(folder))
            self.history_table.setItem(idx, 2, QTableWidgetItem(str(moves)))

        if sessions:
            self.history_table.selectRow(0)
            self._show_selected_history_moves()
        else:
            self.history_moves.clear()
            self.history_moves.addItem("No history sessions yet.")

    def _show_selected_history_moves(self):
        self.history_moves.clear()
        row = self.history_table.currentRow()
        if row < 0:
            self.history_moves.addItem("Select a session to inspect its moves.")
            return

        sessions = self.organizer.history.list_sessions(limit=50)
        if row >= len(sessions):
            self.history_moves.addItem("No data available for selected session.")
            return

        session = sessions[row]
        moves = session.get("moves", [])
        if not moves:
            self.history_moves.addItem("No moves recorded in this session.")
            return

        for move in moves:
            src_name = Path(move.get("source", "")).name
            dst_name = Path(move.get("destination", "")).name
            self.history_moves.addItem(f"{src_name} -> {dst_name}")

    def _on_auto_mode_changed(self, _state):
        value = bool(self.auto_checkbox.isChecked())
        self.settings.set("auto_mode", value)
        self._log(f"Auto mode set to: {value}")

    def _on_smart_media_detection_changed(self, _state):
        enabled = bool(self.media_detection_checkbox.isChecked())
        self.settings.set("enable_smart_media_detection", enabled)
        # Keep legacy key in sync for backward compatibility.
        self.settings.set("enable_movie_detection", enabled)
        if enabled and not self._movie_detector.available:
            self._log("Smart media detection enabled (movie metadata unavailable; series detection still works)", "warning")
        else:
            self._log(f"Smart media detection set to: {enabled}")

    def _on_duplicate_detection_changed(self, _state):
        enabled = bool(self.duplicate_detection_checkbox.isChecked())
        self.settings.set("enable_duplicate_detection", enabled)
        self._log(f"Duplicate finder set to: {enabled}")

    def _on_protected_files_changed(self, _state=None):
        enabled = bool(self.protected_files_checkbox.isChecked())
        minutes = int(self.protected_minutes.currentText())
        self.settings.set("protect_recent_files", enabled)
        self.settings.set("protect_recent_minutes", minutes)
        self._log(f"Protected recent files set to: {enabled} ({minutes} minute(s))")

    def _add_monitor_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Monitor")
        if not folder:
            return

        existing = [self.monitor_folders.item(i).text() for i in range(self.monitor_folders.count())]
        if folder in existing:
            return

        self.monitor_folders.addItem(folder)
        self._save_monitor_folders()
        self._log(f"Monitor folder added: {folder}")

    def _toggle_monitor(self):
        if self.organizer.is_monitoring:
            self._stop_monitoring_by_user()
            return

        folders = [self.monitor_folders.item(i).text() for i in range(self.monitor_folders.count())]
        folders = [f for f in folders if os.path.isdir(f)]
        if not folders:
            self._show_warning("No folders", "Add at least one valid folder to monitor.")
            return

        self._start_monitoring(folders, startup_restore=False)

    def _start_monitoring(self, folders: list[str], startup_restore: bool = False):
        if not folders:
            return

        def callback(src: str, dst: str, category: str):
            self._monitor_bridge.file_organized.emit(src, dst, category)

        self.organizer.start_monitoring(folders, callback=callback)
        self.monitor_btn.setText("Stop Monitoring")
        self._save_monitor_folders()
        self.settings.set("monitor_enabled", True)
        self._sync_autostart_with_monitoring(notify=not startup_restore)
        if startup_restore:
            self._log(f"Monitoring restored on launch for {len(folders)} folder(s)", "success")
        else:
            self._log(f"Monitoring started for {len(folders)} folder(s)", "success")
        self.statusBar().showMessage("Monitoring active")

    def _stop_monitoring_by_user(self):
        self.organizer.stop_monitoring()
        self.monitor_btn.setText("Start Monitoring")
        self.settings.set("monitor_enabled", False)
        self._sync_autostart_with_monitoring(notify=True)
        self._log("Monitoring stopped")
        self.statusBar().showMessage("Monitoring stopped")

    def _on_monitor_file_organized(self, src: str, dst: str, category: str):
        name = Path(src).name
        self._log(f"[Monitor] {name} -> {category}")
        self._refresh_history_label()

    def _save_monitor_folders(self):
        folders = [self.monitor_folders.item(i).text() for i in range(self.monitor_folders.count())]
        self.settings.set("monitored_folders", folders)

    def _refresh_history_label(self):
        count = self.organizer.history.session_count
        last = self.organizer.history.peek_last_session()
        if not last:
            self.history_label.setText("History: no previous sessions")
            if hasattr(self, "history_table"):
                self._refresh_history_tab()
            return

        ts = format_human_timestamp(last.get("timestamp", ""))
        n = len(last.get("moves", []))
        self.history_label.setText(f"History: {count} session(s)\nLast: {ts} ({n} move(s))")
        if hasattr(self, "history_table"):
            self._refresh_history_tab()

    def _log(self, message: str, level: str = "info"):
        prefix = {
            "info": "[INFO]",
            "success": "[OK]",
            "warning": "[WARN]",
            "error": "[ERR]",
        }.get(level, "[INFO]")
        self.log_text.append(f"{prefix} {message}")
        self._add_notification(f"{prefix} {message}")

    def closeEvent(self, event: QCloseEvent):
        if self.organizer.is_monitoring:
            self.organizer.stop_monitoring()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sortly")
    app.setApplicationDisplayName("Sortly")
    app.setOrganizationName("Arsh Sisodiya")
    app.setApplicationVersion("1.0.0")
    logo_path = _find_logo_path()
    if logo_path:
        app.setWindowIcon(QIcon(str(logo_path)))
    window = FileOrganizerQtApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()