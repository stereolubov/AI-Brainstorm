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
from providers import DEFAULT_PROVIDER

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ai_brainstorm")
PROFILES_DIR = os.path.join(CONFIG_DIR, "profiles")
LOCALES_DIR = os.path.join(CONFIG_DIR, "locales")
POINTER_PATH = os.path.join(CONFIG_DIR, "active_profile.json")

DEFAULT_PROFILE_NAME = "default"
DEFAULT_LANGUAGE_CODE = "en"


MAX_CUSTOM_SLOTS_STORED = 8  # always allocate all 8 — family mode only shows/uses the
                              # first 3, but keeping the rest around means toggling
                              # "use_families" off and back on never loses data either way.


def _empty_custom_slots():
    # Independent dicts — must not be the same object, or editing one
    # slot would affect all others.
    return [
        {
            "id": "", "label": "", "persona": "", "enabled": False,
            "reasoning_level": "off",  # used by providers with a translatable format (tokens/effort)
            "reasoning_raw": "",       # used by the "custom" provider — exact JSON fragment, per slot,
                                       # since local servers vary the reasoning shape model to model
        }
        for _ in range(MAX_CUSTOM_SLOTS_STORED)
    ]


DEFAULT_CONFIG = {
    "api_key": "",
    "api_provider": DEFAULT_PROVIDER,
    "custom_base_url": "",          # only used when api_provider == "custom" — unknowable in advance
    "custom_base_url_history": [],  # every URL ever typed here, most recent first — lets the
                                     # person pick from a dropdown (e.g. switching between a
                                     # service's "main" and "RU" endpoint) instead of retyping
    "use_families": True,          # False = ignore families entirely, use all 8 custom_models slots
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
    "moderator_web_lookup": False,
    "moderator_free_only": False,
    "family_options_cache": {},    # {family_key: [id, ...]}
    "all_model_ids_cache": [],     # unfiltered, for custom-slot autocomplete
    "free_model_ids_cache": [],    # subset priced at $0 — for "free models only" in flat/custom slots
    "custom_models_free_only": False,  # only meaningful when use_families=False
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


def get_theme_code():
    return _read_pointer_data().get("theme", "light")


def set_theme_code(code):
    _update_pointer(theme=code)


_active_profile_name = DEFAULT_PROFILE_NAME  # kept in sync by load_config()/switch_active_profile()


def get_active_profile_name():
    return _active_profile_name


def switch_active_profile(name):
    global _active_profile_name
    _active_profile_name = name
    _update_pointer(active_profile=name)


def _normalize(data):
    # Fill in defaults for missing keys, guarantee exactly
    # MAX_CUSTOM_SLOTS_STORED custom slots (handles files from older
    # versions of the app, which only ever stored 3).
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update(data)

    slots = merged.get("custom_models") or []
    slots = list(slots)[:MAX_CUSTOM_SLOTS_STORED]
    while len(slots) < MAX_CUSTOM_SLOTS_STORED:
        slots.append({
            "id": "", "label": "", "persona": "", "enabled": False,
            "reasoning_level": "off", "reasoning_raw": "",
        })
    for slot in slots:
        slot.setdefault("reasoning_level", "off")
        slot.setdefault("reasoning_raw", "")
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
