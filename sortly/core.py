"""Sortly core engine shared by the CLI and Qt GUI."""

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
from .movie_detector import MovieDetector
from .duplicate_detector import DuplicateDetector


def format_human_timestamp(value: str) -> str:
    """Format timestamp to DD:MM:YY HH:MM:SS when possible."""
    if not value:
        return "unknown time"
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%d:%m:%y %H:%M:%S")
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%d:%m:%y %H:%M:%S")
        except Exception:
            continue
    return text

# ─── Category Definitions ─────────────────────────────────────────────────────

CATEGORIES: Dict[str, Dict] = {
    "Duplicates": {
        "extensions": [],
        "icon": "🧬",
        "color": "#6C5CE7",
    },
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
        "schedule_enabled": False,
        "schedule_interval_minutes": 15,
        "enable_duplicate_detection": False,
        "protect_recent_files": False,
        "protect_recent_minutes": 30,
        "monitor_enabled": False,
        "enable_movie_detection": False,
        "enable_smart_media_detection": True,
        "monitored_folders": [],
        "custom_rules": [],          # [{pattern, category}]
        "category_folder_map": {},   # {"Audio": "Movies", "Videos": "Movies"}
        "category_conflict_policy": {},  # {"Documents": "skip"}
        "excluded_extensions": [],
        "excluded_folders": ["Duplicates", "WebSeries", "Movies", "Images", "Videos", "Audio", "Documents",
                              "Archives", "Code", "Executables", "Fonts", "Others"],
        "log_file": "sortly.log",
        "history_file": "sortly_history.json",
    }

    def __init__(self, config_path: str = None):
        self.config_path = config_path or str(
            Path.home() / ".sortly" / "settings.json"
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
            Path.home() / ".sortly" / "history.json"
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
    log_path = log_path or str(Path.home() / ".sortly" / "activity.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("Sortly")
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
        self.duplicate_detector = DuplicateDetector()
        self.progress_callback = progress_callback  # fn(current, total, message)
        self._monitor_observer: Optional[Observer] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_event: Optional[threading.Event] = None
        self._monitored_folders: List[str] = []

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

    def _is_protected_recent_file(self, file_path: str) -> bool:
        if not bool(self.settings.get("protect_recent_files", False)):
            return False
        minutes = int(self.settings.get("protect_recent_minutes", 30))
        try:
            modified_time = os.path.getmtime(file_path)
        except Exception:
            return False
        age_seconds = time.time() - modified_time
        return age_seconds < max(1, minutes) * 60

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
        duplicate_paths = set()
        if bool(self.settings.get("enable_duplicate_detection", False)):
            duplicate_paths = self.duplicate_detector.find_duplicates(sibling_paths)

        for entry in entries:
            ext = Path(entry.path).suffix.lower()
            if ext in excluded_exts:
                plan.add_skip(entry.path, f"Excluded extension: {ext}")
                continue

            if self._is_protected_recent_file(entry.path):
                plan.add_skip(entry.path, "Protected recent file")
                continue

            decision = self.analyze_file(entry.path, sibling_video_paths=sibling_paths)
            category = decision.category
            if entry.path in duplicate_paths:
                category = "Duplicates"
                decision.confidence = 98
                decision.reasons.append("Detected duplicate content by file hash")
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
        ts = format_human_timestamp(session.get("timestamp", ""))
        return True, f"Successfully undone {count} file move(s) from {ts}."

    # ── Real-time Monitoring ──────────────────────────────────────────────────

    def start_monitoring(self, folders: List[str], callback: Callable = None):
        """Start watching folders for new files."""
        if self._monitor_observer:
            self.stop_monitoring()

        valid_folders = [folder for folder in folders if os.path.isdir(folder)]
        self._monitored_folders = valid_folders

        self._monitor_observer = Observer()
        handler = FolderEventHandler(self, callback)

        for folder in valid_folders:
            self._monitor_observer.schedule(handler, folder, recursive=False)
            self.logger.info(f"Monitoring: {folder}")

        self._monitor_observer.start()

        self._monitor_stop_event = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._monitor_sweep_loop,
            args=(callback,),
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_sweep_loop(self, callback: Callable = None):
        """Periodic fallback sweep for reliability when OS events are dropped."""
        stop_event = self._monitor_stop_event
        if stop_event is None:
            return

        while not stop_event.wait(3.0):
            for folder in list(self._monitored_folders):
                if not os.path.isdir(folder):
                    continue
                try:
                    self._process_monitor_folder(folder, callback)
                except Exception as exc:
                    self.logger.error(f"Monitor sweep failed for {folder}: {exc}")

    def _process_monitor_folder(self, folder: str, callback: Callable = None):
        plan = self.build_plan(folder)
        if plan.total_files == 0:
            return

        records = self.execute_plan(plan, folder)
        if not records:
            return

        self.logger.info(f"[Monitor sweep] Organized {len(records)} file(s) for: {folder}")
        if callback:
            category_by_source = {src: cat for src, _, cat in plan.moves}
            for record in records:
                callback(record.source, record.destination, category_by_source.get(record.source, "Others"))

    def stop_monitoring(self):
        if self._monitor_stop_event is not None:
            self._monitor_stop_event.set()
            self._monitor_stop_event = None
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3)
            self._monitor_thread = None

        if self._monitor_observer:
            self._monitor_observer.stop()
            self._monitor_observer.join(timeout=3)
            self._monitor_observer = None
            self.logger.info("Monitoring stopped.")
        self._monitored_folders = []

    @property
    def is_monitoring(self) -> bool:
        return self._monitor_observer is not None and self._monitor_observer.is_alive()


# ─── File System Event Handler ────────────────────────────────────────────────

class FolderEventHandler(FileSystemEventHandler):
    def __init__(self, organizer: FileOrganizer, callback: Callable = None):
        super().__init__()
        self.organizer = organizer
        self.callback = callback
        self._pending: Dict[str, float] = {}
        self._pending_folders: Dict[str, float] = {}
        self._folder_workers: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._debounce_seconds = 2.0

    def on_created(self, event):
        if event.is_directory:
            self._enqueue_folder(event.src_path)
            return
        self._enqueue(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            self._enqueue_folder(event.dest_path)
            return
        self._enqueue(event.dest_path)

    def on_modified(self, event):
        if event.is_directory:
            self._enqueue_folder(event.src_path)
        else:
            self._enqueue(event.src_path)

    def _enqueue(self, path: str):
        folder = os.path.dirname(path)
        if not folder:
            return
        with self._lock:
            self._pending[path] = time.time()
            self._pending_folders[folder] = time.time()
            worker = self._folder_workers.get(folder)
            if worker is None or not worker.is_alive():
                worker = threading.Thread(target=self._folder_worker, args=(folder,), daemon=True)
                self._folder_workers[folder] = worker
                worker.start()

    def _enqueue_folder(self, folder: str):
        if not folder:
            return
        with self._lock:
            self._pending_folders[folder] = time.time()
            worker = self._folder_workers.get(folder)
            if worker is None or not worker.is_alive():
                worker = threading.Thread(target=self._folder_worker, args=(folder,), daemon=True)
                self._folder_workers[folder] = worker
                worker.start()

    def _folder_worker(self, folder: str):
        idle_ticks = 0
        while True:
            time.sleep(0.75)
            now = time.time()
            batch: List[str] = []
            should_process = False

            with self._lock:
                dirty_at = self._pending_folders.get(folder)
                has_pending_for_folder = dirty_at is not None
                if has_pending_for_folder and now - dirty_at >= self._debounce_seconds:
                    should_process = True
                    for path in list(self._pending.keys()):
                        if os.path.dirname(path) == folder:
                            batch.append(path)
                            self._pending.pop(path, None)
                    self._pending_folders.pop(folder, None)

            if should_process:
                idle_ticks = 0
                self._process_folder_batch(folder, batch)
                continue

            if has_pending_for_folder:
                idle_ticks = 0
                continue

            idle_ticks += 1
            if idle_ticks >= 3:
                with self._lock:
                    current = self._folder_workers.get(folder)
                    if current is threading.current_thread():
                        del self._folder_workers[folder]
                return

    def _wait_until_stable(self, path: str, timeout: float = 12.0) -> bool:
        deadline = time.time() + timeout
        last_size = -1
        last_mtime = -1.0
        stable_ticks = 0

        while time.time() < deadline:
            if not os.path.exists(path):
                return False
            try:
                stat = os.stat(path)
                current_size = stat.st_size
                current_mtime = stat.st_mtime
            except OSError:
                time.sleep(0.25)
                continue

            if current_size == last_size and current_mtime == last_mtime:
                stable_ticks += 1
                if stable_ticks >= 3:
                    return True
            else:
                stable_ticks = 0
                last_size = current_size
                last_mtime = current_mtime

            time.sleep(0.25)

        return os.path.exists(path)

    def _process_folder_batch(self, folder: str, candidates: List[str]):
        with self._process_lock:
            stable_paths: List[str] = []
            for path in candidates:
                if self._wait_until_stable(path):
                    stable_paths.append(path)

            stable_paths = [p for p in stable_paths if os.path.exists(p)]
            if not stable_paths:
                try:
                    stable_paths = [entry.path for entry in os.scandir(folder) if entry.is_file()]
                except Exception:
                    stable_paths = []
                if not stable_paths:
                    return

            excluded_folders = set(self.organizer.settings.get("excluded_folders", []))
            excluded_exts = set(e.lower() for e in self.organizer.settings.get("excluded_extensions", []))

            try:
                sibling_paths = [entry.path for entry in os.scandir(folder) if entry.is_file()]
            except Exception:
                sibling_paths = list(stable_paths)

            duplicate_paths = set()
            if bool(self.organizer.settings.get("enable_duplicate_detection", False)):
                duplicate_paths = self.organizer.duplicate_detector.find_duplicates(sibling_paths)

            plan = OrganizationPlan()

            for path in stable_paths:
                if not os.path.exists(path):
                    continue

                ext = Path(path).suffix.lower()
                if ext in excluded_exts:
                    plan.add_skip(path, f"Excluded extension: {ext}")
                    continue

                if self.organizer._is_protected_recent_file(path):
                    plan.add_skip(path, "Protected recent file")
                    continue

                parent_name = os.path.basename(os.path.dirname(path))
                if parent_name in excluded_folders:
                    plan.add_skip(path, "Already organized")
                    continue

                decision = self.organizer.analyze_file(path, sibling_video_paths=sibling_paths)
                category = decision.category
                if path in duplicate_paths:
                    category = "Duplicates"
                    decision.confidence = 98
                    decision.reasons.append("Detected duplicate content by file hash")

                target_folder = self.organizer._destination_folder_name(category)
                dest_dir = os.path.join(folder, target_folder)
                dest_path = os.path.join(dest_dir, os.path.basename(path))
                conflict_policy = self.organizer._conflict_policy(category)

                if os.path.exists(dest_path):
                    if conflict_policy == "skip":
                        plan.add_skip(path, f"Conflict policy skip: {os.path.basename(path)} already exists")
                        continue
                    if conflict_policy == "rename":
                        dest_path = self.organizer._resolve_conflict(dest_path)

                if not os.path.exists(dest_dir):
                    plan.add_new_dir(dest_dir)

                reasons = list(decision.reasons)
                if target_folder != category:
                    reasons.append(f"Destination folder mapped to: {target_folder}")
                reasons.append(f"Conflict policy: {conflict_policy}")

                plan.add_move(
                    path,
                    dest_path,
                    category,
                    confidence=decision.confidence,
                    reasons=reasons,
                    conflict_policy=conflict_policy,
                )

            if plan.total_files == 0:
                return

            records = self.organizer.execute_plan(plan, folder)
            self.organizer.logger.info(
                f"[Monitor] Organized {len(records)} file(s) in one session for: {folder}"
            )

            if self.callback:
                category_by_source = {src: cat for src, _, cat in plan.moves}
                for record in records:
                    category = category_by_source.get(record.source, "Others")
                    self.callback(record.source, record.destination, category)
