# -*- coding: utf-8 -*-
"""
Profile-based settings storage.

Each profile is a standalone JSON file with its own API key and settings
(useful for multiple OpenRouter accounts or different participant sets):
  Windows: C:\\Users\\<name>\\.ai_brainstorm\\profiles\\<name>.json
  Linux/Mac: ~/.ai_brainstorm/profiles/<name>.json

A small pointer file holds app-wide state that isn't tied to any one
profile — active profile name, UI language, debug tab visibility:
  ~/.ai_brainstorm/active_profile.json ->
      {"active_profile": "default", "language": "en", "debug_tab_enabled": false}

Locale files live in the sibling locales/ folder — see i18n.py.
"""

import json
import os

from models_catalog import MODERATOR_DEFAULT_MODEL

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ai_brainstorm")
PROFILES_DIR = os.path.join(CONFIG_DIR, "profiles")
LOCALES_DIR = os.path.join(CONFIG_DIR, "locales")
POINTER_PATH = os.path.join(CONFIG_DIR, "active_profile.json")

DEFAULT_PROFILE_NAME = "default"
DEFAULT_LANGUAGE_CODE = "en"


def _empty_custom_slots():
    # Independent dicts — must not be the same object, or editing one
    # slot would affect all three.
    return [
        {"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "off"}
        for _ in range(3)
    ]


DEFAULT_CONFIG = {
    "api_key": "",
    "selected_families": [],
    "family_model_choice": {},     # {family_key: chosen model_id}
    "personas": {},                # {family_key: persona text}
    "reasoning_levels": {},        # {family_key: "off"|"low"|"medium"|"high"}
    "custom_models": _empty_custom_slots(),
    "session_budget_usd": 0.5,
    "max_replies": 12,
    "moderator_mode": "ai",        # "ai" or "human"
    "moderator_model": MODERATOR_DEFAULT_MODEL,
    "user_participation": False,
    "moderator_summary": False,
    "family_options_cache": {},    # {family_key: [id, ...]}
    "all_model_ids_cache": [],     # unfiltered, for custom-slot autocomplete
    "family_options_updated_at": "",
}


def _safe_filename(name):
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return safe or DEFAULT_PROFILE_NAME


def _profile_path(name):
    return os.path.join(PROFILES_DIR, _safe_filename(name) + ".json")


def list_profiles():
    if not os.path.isdir(PROFILES_DIR):
        return [DEFAULT_PROFILE_NAME]
    names = [os.path.splitext(f)[0] for f in os.listdir(PROFILES_DIR) if f.endswith(".json")]
    return sorted(names) or [DEFAULT_PROFILE_NAME]


def _read_pointer_data():
    if not os.path.exists(POINTER_PATH):
        return {}
    try:
        with open(POINTER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_pointer_data(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(POINTER_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _update_pointer(**changes):
    """Merge `changes` into the pointer file without clobbering other keys."""
    data = _read_pointer_data()
    data.update(changes)
    _write_pointer_data(data)


def _read_pointer():
    return _read_pointer_data().get("active_profile", DEFAULT_PROFILE_NAME)


def get_language_code():
    return _read_pointer_data().get("language", DEFAULT_LANGUAGE_CODE)


def set_language_code(code):
    _update_pointer(language=code)


def get_debug_tab_enabled():
    return bool(_read_pointer_data().get("debug_tab_enabled", False))


def set_debug_tab_enabled(enabled):
    _update_pointer(debug_tab_enabled=bool(enabled))


_active_profile_name = DEFAULT_PROFILE_NAME  # kept in sync by load_config()/switch_active_profile()


def get_active_profile_name():
    return _active_profile_name


def switch_active_profile(name):
    global _active_profile_name
    _active_profile_name = name
    _update_pointer(active_profile=name)


def _normalize(data):
    # Fill in defaults for missing keys, guarantee exactly 3 custom slots
    # (handles files from older versions of the app).
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update(data)

    slots = merged.get("custom_models") or []
    slots = list(slots)[:3]
    while len(slots) < 3:
        slots.append({"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "off"})
    for slot in slots:
        slot.setdefault("reasoning_level", "off")
    merged["custom_models"] = slots

    return merged


def load_config(profile_name=None):
    """Loads a profile (defaults to whichever was last active). Creates
    it with default settings if it doesn't exist yet (first run)."""
    name = profile_name or _read_pointer()
    path = _profile_path(name)

    if not os.path.exists(path):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        save_profile(name, cfg)
        switch_active_profile(name)
        return cfg

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}

    switch_active_profile(name)
    return _normalize(data)


def save_profile(name, config):
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(_profile_path(name), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def save_config(config, profile_name=None):
    """Saves to the active profile (or an explicit one) — the main save
    entry point used throughout the app."""
    save_profile(profile_name or _active_profile_name, config)


def delete_profile(name):
    path = _profile_path(name)
    if os.path.exists(path):
        os.remove(path)
