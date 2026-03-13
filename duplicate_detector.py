"""Duplicate file detection helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Iterable, Set


class DuplicateDetector:
    def __init__(self, chunk_size: int = 1024 * 1024):
        self.chunk_size = chunk_size

    def find_duplicates(self, file_paths: Iterable[str]) -> Set[str]:
        seen: Dict[str, str] = {}
        duplicates: Set[str] = set()
        for path in file_paths:
            file_hash = self._hash_file(path)
            if not file_hash:
                continue
            if file_hash in seen:
                duplicates.add(path)
            else:
                seen[file_hash] = path
        return duplicates

    def _hash_file(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return ""
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(self.chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except Exception:
            return ""
        return hasher.hexdigest()