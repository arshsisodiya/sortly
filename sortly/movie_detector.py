"""
Movie detection helper based on PyMediaInfo metadata.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Optional, Set

try:
    from pymediainfo import MediaInfo
except Exception:
    MediaInfo = None


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".vob",
    ".f4v", ".rmvb", ".divx",
}


class MovieDetector:
    def __init__(self, min_minutes: float = 40.0, min_size_mb: float = 300.0):
        self.min_minutes = float(min_minutes)
        self.min_size_bytes = int(min_size_mb * 1024 * 1024)

    @property
    def available(self) -> bool:
        return MediaInfo is not None

    def is_movie(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            return False
        if MediaInfo is None:
            return False

        try:
            media = MediaInfo.parse(file_path)
        except Exception:
            return False

        duration_min = self._duration_minutes(media)
        if duration_min is None:
            return False

        size_bytes = self._file_size(file_path)
        score = 0

        if duration_min >= 70:
            score += 3
        elif duration_min >= self.min_minutes:
            score += 2
        elif duration_min < 20:
            score -= 2

        if size_bytes >= 700 * 1024 * 1024:
            score += 2
        elif size_bytes >= self.min_size_bytes:
            score += 1
        elif size_bytes < 120 * 1024 * 1024:
            score -= 1

        filename = Path(file_path).name.lower()
        if any(k in filename for k in ["1080p", "2160p", "bluray", "webrip", "web-dl", "x264", "x265", "brrip"]):
            score += 1
        if any(k in filename for k in ["trailer", "teaser", "sample", "clip"]):
            score -= 2

        return score >= 3

    def detect_webseries_files(self, file_paths: list[str]) -> Set[str]:
        """Return video file paths that appear to be part of a series (>=2 episodes)."""
        groups: Dict[str, Set[str]] = {}
        for path in file_paths:
            ext = Path(path).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            key = self._series_key(path)
            if not key:
                continue
            groups.setdefault(key, set()).add(path)

        result: Set[str] = set()
        for items in groups.values():
            if len(items) >= 2:
                result.update(items)
        return result

    def _series_key(self, file_path: str) -> Optional[str]:
        name = Path(file_path).stem
        n = name.lower().replace("_", " ").replace(".", " ").strip()

        patterns = [
            r"\bs\d{1,2}\s*e\d{1,2}\b",
            r"\b\d{1,2}x\d{1,2}\b",
            r"\bseason\s*\d{1,2}\b",
            r"\bep(isode)?\s*\d{1,3}\b",
            r"\be\d{1,2}\b",
        ]

        matched = False
        for pat in patterns:
            if re.search(pat, n):
                n = re.sub(pat, " ", n)
                matched = True

        if not matched:
            return None

        n = re.sub(r"\b(1080p|2160p|720p|x264|x265|webrip|web\s*dl|bluray|hdr|h264|h265)\b", " ", n)
        n = re.sub(r"\s+", " ", n).strip(" -")

        if len(n) < 3:
            return None
        return n

    def _duration_minutes(self, media) -> Optional[float]:
        durations = []
        for track in media.tracks:
            if track.track_type in {"Video", "General"}:
                val = getattr(track, "duration", None)
                if val is None:
                    continue
                try:
                    durations.append(float(val) / 60000.0)
                except Exception:
                    continue
        if not durations:
            return None
        return max(durations)

    def _file_size(self, file_path: str) -> int:
        try:
            return os.path.getsize(file_path)
        except Exception:
            return 0
