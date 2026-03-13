"""
FileOrganizer Core Engine
Shared logic for both CLI and GUI applications
"""

import os
import shutil
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from movie_detector import MovieDetector

# ─── Category Definitions ─────────────────────────────────────────────────────

CATEGORIES: Dict[str, Dict] = {
    "WebSeries": {
        "extensions": [],
        "icon": "📺",
        "color": "#00B894",
    },
    "Movies": {
        "extensions": [],
        "icon": "🎞️",
        "color": "#E17055",
    },
    "Images": {
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
                        ".ico", ".tiff", ".tif", ".heic", ".heif", ".raw", ".cr2",
                        ".nef", ".arw", ".dng", ".psd", ".ai", ".eps"],
        "icon": "🖼️",
        "color": "#FF6B9D",
    },
    "Videos": {
        "extensions": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
                        ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".vob",
                        ".f4v", ".rmvb", ".divx"],
        "icon": "🎬",
        "color": "#FF9F43",
    },
    "Audio": {
        "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a",
                        ".opus", ".aiff", ".mid", ".midi", ".amr", ".ape", ".alac"],
        "icon": "🎵",
        "color": "#A29BFE",
    },
    "Documents": {
        "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                        ".txt", ".rtf", ".odt", ".ods", ".odp", ".csv", ".md",
                        ".epub", ".pages", ".numbers", ".key", ".tex"],
        "icon": "📄",
        "color": "#74B9FF",
    },
    "Archives": {
        "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
                        ".iso", ".dmg", ".pkg", ".deb", ".rpm", ".cab", ".lz",
                        ".lzma", ".zst", ".tar.gz", ".tar.bz2", ".tar.xz"],
        "icon": "📦",
        "color": "#FFEAA7",
    },
    "Code": {
        "extensions": [".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm",
                        ".css", ".scss", ".sass", ".less", ".java", ".c", ".cpp",
                        ".h", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
                        ".sh", ".bat", ".ps1", ".sql", ".json", ".xml", ".yaml",
                        ".yml", ".toml", ".ini", ".cfg", ".env", ".vue", ".svelte",
                        ".r", ".m", ".lua", ".dart", ".ex", ".exs"],
        "icon": "💻",
        "color": "#55EFC4",
    },
    "Executables": {
        "extensions": [".exe", ".msi", ".apk", ".ipa", ".app", ".bin", ".run",
                        ".jar", ".appimage"],
        "icon": "⚙️",
        "color": "#FD79A8",
    },
    "Fonts": {
        "extensions": [".ttf", ".otf", ".woff", ".woff2", ".eot", ".fon"],
        "icon": "🔤",
        "color": "#B2BEC3",
    },
    "Others": {
        "extensions": [],  # Catch-all
        "icon": "📁",
        "color": "#636E72",
    },
}

# ─── File Move Record ──────────────────────────────────────────────────────────

class FileMoveRecord:
    def __init__(self, source: str, destination: str, timestamp: str = None):
        self.source = source
        self.destination = destination
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "destination": self.destination,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileMoveRecord":
        return cls(data["source"], data["destination"], data.get("timestamp"))


@dataclass
class ClassificationDecision:
    category: str
    confidence: int
    reasons: List[str] = field(default_factory=list)
    matched_rule: Optional[str] = None


# ─── Organization Plan ────────────────────────────────────────────────────────

class OrganizationPlan:
    """Represents a plan of file moves before they are executed."""

    def __init__(self):
        self.moves: List[Tuple[str, str, str]] = []  # (source, dest, category)
        self.move_details: List[Dict] = []
        self.skipped: List[Tuple[str, str]] = []     # (path, reason)
        self.new_dirs: List[str] = []

    def add_move(self, source: str, destination: str, category: str,
                 confidence: int = 0, reasons: Optional[List[str]] = None,
                 conflict_policy: str = "rename"):
        self.moves.append((source, destination, category))
        self.move_details.append({
            "source": source,
            "destination": destination,
            "category": category,
            "confidence": int(confidence),
            "reasons": list(reasons or []),
            "conflict_policy": conflict_policy,
        })

    def add_skip(self, path: str, reason: str):
        self.skipped.append((path, reason))

    def add_new_dir(self, path: str):
        if path not in self.new_dirs:
            self.new_dirs.append(path)

    @property
    def total_files(self) -> int:
        return len(self.moves)

    @property
    def categories_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for _, _, cat in self.moves:
            summary[cat] = summary.get(cat, 0) + 1
        return summary


# ─── Settings Manager ─────────────────────────────────────────────────────────

class Settings:
    DEFAULT_SETTINGS = {
        "auto_mode": False,
        "monitor_enabled": False,
        "enable_movie_detection": False,
        "enable_smart_media_detection": True,
        "monitored_folders": [],
        "custom_rules": [],          # [{pattern, category}]
        "category_folder_map": {},   # {"Audio": "Movies", "Videos": "Movies"}
        "category_conflict_policy": {},  # {"Documents": "skip"}
        "excluded_extensions": [],
        "excluded_folders": ["WebSeries", "Movies", "Images", "Videos", "Audio", "Documents",
                              "Archives", "Code", "Executables", "Fonts", "Others"],
        "log_file": "fileorganizer.log",
        "history_file": "fileorganizer_history.json",
    }

    def __init__(self, config_path: str = None):
        self.config_path = config_path or str(
            Path.home() / ".fileorganizer" / "settings.json"
        )
        self._data = dict(self.DEFAULT_SETTINGS)
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
        except Exception:
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self.set(key, value)


# ─── History Manager ──────────────────────────────────────────────────────────

class HistoryManager:
    def __init__(self, history_path: str = None):
        self.history_path = history_path or str(
            Path.home() / ".fileorganizer" / "history.json"
        )
        self._sessions: List[Dict] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r") as f:
                    self._sessions = json.load(f)
        except Exception:
            self._sessions = []

    def _save(self):
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self._sessions[-50:], f, indent=2)  # Keep last 50 sessions

    def push_session(self, records: List[FileMoveRecord], folder: str):
        session = {
            "folder": folder,
            "timestamp": datetime.now().isoformat(),
            "moves": [r.to_dict() for r in records],
        }
        self._sessions.append(session)
        self._save()

    def pop_last_session(self) -> Optional[Dict]:
        if not self._sessions:
            return None
        session = self._sessions.pop()
        self._save()
        return session

    def peek_last_session(self) -> Optional[Dict]:
        if not self._sessions:
            return None
        return self._sessions[-1]

    def list_sessions(self, limit: int = 50) -> List[Dict]:
        """Return recent sessions newest-first for UI inspection."""
        if limit <= 0:
            return []
        return list(reversed(self._sessions[-limit:]))

    @property
    def session_count(self) -> int:
        return len(self._sessions)


# ─── Logger Setup ─────────────────────────────────────────────────────────────

def setup_logger(log_path: str = None) -> logging.Logger:
    log_path = log_path or str(Path.home() / ".fileorganizer" / "activity.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("FileOrganizer")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger


# ─── Categorization Engine ────────────────────────────────────────────────────

class Categorizer:
    def __init__(self, custom_rules: List[Dict] = None):
        self.custom_rules = custom_rules or []
        # Build extension→category map
        self._ext_map: Dict[str, str] = {}
        for cat, info in CATEGORIES.items():
            if cat == "Others":
                continue
            for ext in info["extensions"]:
                self._ext_map[ext.lower()] = cat

    def categorize(self, file_path: str) -> str:
        name = os.path.basename(file_path).lower()
        ext = Path(file_path).suffix.lower()

        # Check custom rules first (pattern matching on filename)
        for rule in self.custom_rules:
            pattern = rule.get("pattern", "").lower()
            category = rule.get("category", "Others")
            if pattern and pattern in name:
                return category

        # Extension-based categorization
        if ext in self._ext_map:
            return self._ext_map[ext]

        # Handle compound extensions like .tar.gz
        name_lower = file_path.lower()
        for compound in [".tar.gz", ".tar.bz2", ".tar.xz"]:
            if name_lower.endswith(compound):
                return "Archives"

        return "Others"

    def matching_rule(self, file_path: str) -> Optional[Dict]:
        name = os.path.basename(file_path).lower()
        for rule in self.custom_rules:
            pattern = rule.get("pattern", "").lower()
            if pattern and pattern in name:
                return rule
        return None


# ─── Main Organizer ───────────────────────────────────────────────────────────

class FileOrganizer:
    def __init__(self, settings: Settings = None, progress_callback: Callable = None):
        self.settings = settings or Settings()
        self.logger = setup_logger()
        self.history = HistoryManager()
        self.categorizer = Categorizer(self.settings.get("custom_rules", []))
        self.movie_detector = MovieDetector()
        self.progress_callback = progress_callback  # fn(current, total, message)
        self._monitor_observer: Optional[Observer] = None
        self._monitor_thread: Optional[threading.Thread] = None

    def _emit_progress(self, current: int, total: int, message: str = ""):
        if self.progress_callback:
            self.progress_callback(current, total, message)

    def analyze_file(self, file_path: str, sibling_video_paths: Optional[List[str]] = None) -> ClassificationDecision:
        rule = self.categorizer.matching_rule(file_path)
        if rule:
            category = rule.get("category", "Others")
            return ClassificationDecision(
                category=category,
                confidence=100,
                reasons=[f"Matched custom rule: {rule.get('pattern', '')}"],
                matched_rule=rule.get("pattern", ""),
            )

        category = self.categorizer.categorize(file_path)
        reasons: List[str] = []
        confidence = 30

        ext = Path(file_path).suffix.lower()
        if category != "Others":
            confidence = 75
            reasons.append(f"Matched extension: {ext or '(none)'}")
        else:
            reasons.append("No matching rule or known extension")

        if category == "Videos" and self._is_smart_media_detection_enabled():
            series_files = set(self.movie_detector.detect_webseries_files(sibling_video_paths or [file_path]))
            if file_path in series_files:
                return ClassificationDecision(
                    category="WebSeries",
                    confidence=92,
                    reasons=reasons + ["Detected episode naming pattern across multiple files"],
                )
            if self.movie_detector.is_movie(file_path):
                return ClassificationDecision(
                    category="Movies",
                    confidence=86,
                    reasons=reasons + ["Detected long-form movie metadata"],
                )

        return ClassificationDecision(category=category, confidence=confidence, reasons=reasons)

    def _destination_folder_name(self, category: str) -> str:
        """Resolve final destination folder name for a category."""
        mapping = self.settings.get("category_folder_map", {}) or {}
        mapped = str(mapping.get(category, "")).strip()
        return mapped or category

    def _conflict_policy(self, category: str) -> str:
        policy_map = self.settings.get("category_conflict_policy", {}) or {}
        policy = str(policy_map.get(category, "rename")).strip().lower()
        if policy not in {"rename", "skip", "replace"}:
            return "rename"
        return policy

    def _is_smart_media_detection_enabled(self) -> bool:
        if self.settings.get("enable_smart_media_detection", None) is not None:
            return bool(self.settings.get("enable_smart_media_detection", True))
        return bool(self.settings.get("enable_movie_detection", False))

    def _maybe_promote_to_movie(self, file_path: str, category: str) -> str:
        if category != "Videos":
            return category
        if not self._is_smart_media_detection_enabled():
            return category
        if self.movie_detector.is_movie(file_path):
            return "Movies"
        return category

    def build_plan(self, folder: str) -> OrganizationPlan:
        """Scan a folder and build an OrganizationPlan without moving anything."""
        plan = OrganizationPlan()
        excluded_folders = set(self.settings.get("excluded_folders", []))
        excluded_exts = set(e.lower() for e in self.settings.get("excluded_extensions", []))

        try:
            entries = [e for e in os.scandir(folder) if e.is_file()]
        except PermissionError as e:
            self.logger.error(f"Permission denied: {folder} — {e}")
            return plan

        sibling_paths = [e.path for e in entries]

        for entry in entries:
            ext = Path(entry.path).suffix.lower()
            if ext in excluded_exts:
                plan.add_skip(entry.path, f"Excluded extension: {ext}")
                continue

            decision = self.analyze_file(entry.path, sibling_video_paths=sibling_paths)
            category = decision.category
            target_folder = self._destination_folder_name(category)
            dest_dir = os.path.join(folder, target_folder)
            dest_path = os.path.join(dest_dir, entry.name)
            conflict_policy = self._conflict_policy(category)

            # Avoid moving files already in a category subfolder
            parent_name = os.path.basename(os.path.dirname(entry.path))
            if parent_name in excluded_folders:
                plan.add_skip(entry.path, "Already organized")
                continue

            # Handle name conflicts using the configured per-category policy.
            if os.path.exists(dest_path):
                if conflict_policy == "skip":
                    plan.add_skip(entry.path, f"Conflict policy skip: {entry.name} already exists")
                    continue
                if conflict_policy == "rename":
                    dest_path = self._resolve_conflict(dest_path)

            if not os.path.exists(dest_dir):
                plan.add_new_dir(dest_dir)

            move_reasons = list(decision.reasons)
            if target_folder != category:
                move_reasons.append(f"Destination folder mapped to: {target_folder}")
            move_reasons.append(f"Conflict policy: {conflict_policy}")

            plan.add_move(
                entry.path,
                dest_path,
                category,
                confidence=decision.confidence,
                reasons=move_reasons,
                conflict_policy=conflict_policy,
            )

        return plan

    def _resolve_conflict(self, dest_path: str) -> str:
        """If destination exists, append (1), (2), ... to filename."""
        if not os.path.exists(dest_path):
            return dest_path
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while True:
            new_path = f"{base} ({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def execute_plan(self, plan: OrganizationPlan, folder: str) -> List[FileMoveRecord]:
        """Execute an OrganizationPlan and return list of move records."""
        records: List[FileMoveRecord] = []
        total = plan.total_files

        # Create directories
        for new_dir in plan.new_dirs:
            os.makedirs(new_dir, exist_ok=True)
            self.logger.info(f"Created directory: {new_dir}")

        for i, (source, destination, category) in enumerate(plan.moves):
            detail = plan.move_details[i] if i < len(plan.move_details) else {}
            conflict_policy = str(detail.get("conflict_policy", "rename")).lower()
            self._emit_progress(i + 1, total, f"Moving: {os.path.basename(source)}")
            try:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                if conflict_policy == "replace" and os.path.exists(destination):
                    os.remove(destination)
                shutil.move(source, destination)
                record = FileMoveRecord(source, destination)
                records.append(record)
                self.logger.info(f"[{category}] {os.path.basename(source)} → {destination}")
            except Exception as e:
                self.logger.error(f"Failed to move {source}: {e}")

        if records:
            self.history.push_session(records, folder)

        self._emit_progress(total, total, "Done!")
        return records

    def organize_folder(self, folder: str, auto: bool = None) -> Tuple[OrganizationPlan, List[FileMoveRecord]]:
        """
        Full organize flow.
        If auto=True, execute immediately.
        Returns (plan, records). If auto=False, records will be empty.
        """
        if auto is None:
            auto = self.settings.get("auto_mode", False)

        self.logger.info(f"Scanning: {folder}")
        plan = self.build_plan(folder)
        self.logger.info(f"Plan: {plan.total_files} files to organize")

        records = []
        if auto:
            records = self.execute_plan(plan, folder)

        return plan, records

    def undo_last(self) -> Tuple[bool, str]:
        """Undo the last organization session. Returns (success, message)."""
        session = self.history.pop_last_session()
        if not session:
            return False, "No history to undo."

        moves = session.get("moves", [])
        errors = []

        for move_data in reversed(moves):
            src = move_data["source"]
            dst = move_data["destination"]
            if os.path.exists(dst):
                try:
                    os.makedirs(os.path.dirname(src), exist_ok=True)
                    shutil.move(dst, src)
                    self.logger.info(f"Undone: {os.path.basename(dst)} → {src}")
                except Exception as e:
                    errors.append(str(e))
                    self.logger.error(f"Undo failed for {dst}: {e}")
            else:
                self.logger.warning(f"Undo skipped (not found): {dst}")

        # Clean up empty destination dirs used in this session
        folder = session.get("folder", "")
        if folder:
            seen_dirs = []
            for move_data in moves:
                dst_dir = os.path.dirname(move_data.get("destination", ""))
                if dst_dir and dst_dir not in seen_dirs:
                    seen_dirs.append(dst_dir)
            for dst_dir in seen_dirs:
                if os.path.isdir(dst_dir) and not os.listdir(dst_dir):
                    try:
                        os.rmdir(dst_dir)
                    except Exception:
                        pass

        if errors:
            return False, f"Undo completed with {len(errors)} error(s)."
        count = len(moves)
        return True, f"Successfully undone {count} file move(s) from {session.get('timestamp', 'unknown time')}."

    # ── Real-time Monitoring ──────────────────────────────────────────────────

    def start_monitoring(self, folders: List[str], callback: Callable = None):
        """Start watching folders for new files."""
        if self._monitor_observer:
            self.stop_monitoring()

        self._monitor_observer = Observer()
        handler = FolderEventHandler(self, callback)

        for folder in folders:
            if os.path.isdir(folder):
                self._monitor_observer.schedule(handler, folder, recursive=False)
                self.logger.info(f"Monitoring: {folder}")

        self._monitor_observer.start()

    def stop_monitoring(self):
        if self._monitor_observer:
            self._monitor_observer.stop()
            self._monitor_observer.join(timeout=3)
            self._monitor_observer = None
            self.logger.info("Monitoring stopped.")

    @property
    def is_monitoring(self) -> bool:
        return self._monitor_observer is not None and self._monitor_observer.is_alive()


# ─── File System Event Handler ────────────────────────────────────────────────

class FolderEventHandler(FileSystemEventHandler):
    def __init__(self, organizer: FileOrganizer, callback: Callable = None):
        super().__init__()
        self.organizer = organizer
        self.callback = callback
        self._pending: Dict[str, float] = {}  # debounce
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        with self._lock:
            self._pending[path] = time.time()
        threading.Thread(target=self._delayed_organize, args=(path,), daemon=True).start()

    def _delayed_organize(self, path: str):
        """Wait briefly to ensure file write is complete before organizing."""
        time.sleep(1.5)
        with self._lock:
            if path not in self._pending:
                return
            del self._pending[path]

        if not os.path.exists(path):
            return

        folder = os.path.dirname(path)
        category = self.organizer.categorizer.categorize(path)
        if self.organizer._is_smart_media_detection_enabled() and category == "Videos":
            try:
                sibling_files = [e.path for e in os.scandir(folder) if e.is_file()]
            except Exception:
                sibling_files = [path]
            series_files = self.organizer.movie_detector.detect_webseries_files(sibling_files)
            if path in series_files:
                category = "WebSeries"
            else:
                category = self.organizer._maybe_promote_to_movie(path, category)
        target_folder = self.organizer._destination_folder_name(category)
        dest_dir = os.path.join(folder, target_folder)
        dest_path = self.organizer._resolve_conflict(os.path.join(dest_dir, os.path.basename(path)))

        # Skip if already in a category folder
        parent = os.path.basename(folder)
        if parent in self.organizer.settings.get("excluded_folders", []):
            return

        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(path, dest_path)
            record = FileMoveRecord(path, dest_path)
            self.organizer.history.push_session([record], folder)
            self.organizer.logger.info(f"[Monitor→{category}] {os.path.basename(path)}")
            if self.callback:
                self.callback(path, dest_path, category)
        except Exception as e:
            self.organizer.logger.error(f"Monitor organize failed: {e}")
