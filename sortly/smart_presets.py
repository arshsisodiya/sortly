"""Common preset configurations for Sortly."""

from __future__ import annotations

from copy import deepcopy


SMART_PRESETS = {
    "Developer": {
        "custom_rules": [
            {"pattern": "setup", "category": "Executables"},
            {"pattern": "project", "category": "Code"},
        ],
        "category_folder_map": {"Code": "Projects"},
        "enable_duplicate_detection": True,
        "protect_recent_files": True,
        "protect_recent_minutes": 30,
    },
    "Student": {
        "custom_rules": [
            {"pattern": "assignment", "category": "Documents"},
            {"pattern": "lecture", "category": "Documents"},
        ],
        "category_folder_map": {"Documents": "Study"},
        "protect_recent_files": True,
        "protect_recent_minutes": 60,
    },
    "Content Creator": {
        "custom_rules": [
            {"pattern": "thumbnail", "category": "Images"},
            {"pattern": "recording", "category": "Videos"},
        ],
        "category_folder_map": {"Images": "Assets", "Videos": "Footage"},
        "enable_smart_media_detection": True,
        "enable_duplicate_detection": True,
    },
    "Office Work": {
        "custom_rules": [
            {"pattern": "invoice", "category": "Documents"},
            {"pattern": "report", "category": "Documents"},
        ],
        "category_folder_map": {"Documents": "Office"},
        "category_conflict_policy": {"Documents": "rename"},
    },
}


def preset_names() -> list[str]:
    return list(SMART_PRESETS.keys())


def apply_preset(name: str) -> dict:
    return deepcopy(SMART_PRESETS.get(name, {}))