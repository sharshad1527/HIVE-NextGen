# core/preset_loader.py
"""
File-based preset auto-discovery system.
Drop a .json file into presets/{effects,transitions,captions}/ and it appears in the app.
"""

import os
import json
from pathlib import Path


# Resolve presets directory relative to the project root
_PROJECT_ROOT = Path(__file__).parent.parent
PRESETS_DIR = _PROJECT_ROOT / "presets"

_preset_cache = {}   # category -> list of preset dicts


def _discover_presets(category: str) -> list:
    """Scans the presets/<category>/ directory for JSON files and returns parsed preset data."""
    folder = PRESETS_DIR / category
    presets = []

    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return presets

    for file_path in sorted(folder.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Inject the source file path so we can trace it later
            data["_source_file"] = str(file_path)

            # Ensure mandatory fields
            if "name" not in data:
                data["name"] = file_path.stem.replace("_", " ").title()
            if "icon" not in data:
                data["icon"] = "mdi6.auto-fix"
            if "category" not in data:
                data["category"] = category
            if "properties" not in data:
                data["properties"] = {}

            presets.append(data)
        except Exception as e:
            print(f"[PresetLoader] Failed to load {file_path}: {e}")

    return presets


def get_presets(category: str, force_reload: bool = False) -> list:
    """
    Returns a list of preset dicts for the given category.
    Categories: 'effects', 'transitions', 'captions'
    Results are cached; pass force_reload=True to rescan disk.
    """
    if force_reload or category not in _preset_cache:
        _preset_cache[category] = _discover_presets(category)
    return _preset_cache[category]


def get_preset_by_name(category: str, name: str) -> dict | None:
    """Looks up a specific preset by name within a category."""
    for preset in get_presets(category):
        if preset["name"] == name:
            return preset
    return None


def get_default_properties(preset: dict) -> dict:
    """Extracts a flat dict of {property_name: default_value} from a preset definition."""
    props = {}
    for key, definition in preset.get("properties", {}).items():
        if isinstance(definition, dict):
            props[key] = definition.get("default", 0)
        else:
            props[key] = definition
    return props


def get_all_categories() -> list:
    """Returns all available preset categories by scanning subdirectories."""
    categories = []
    if PRESETS_DIR.exists():
        for item in sorted(PRESETS_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith("_"):
                categories.append(item.name)
    return categories


def reload_all():
    """Forces a rescan of all preset categories."""
    _preset_cache.clear()
    for cat in get_all_categories():
        get_presets(cat, force_reload=True)
