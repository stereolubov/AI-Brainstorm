# -*- coding: utf-8 -*-
"""
Model "family" catalog for the brainstorm.

Each standard family is matched by a regex against the live OpenRouter
model list (see api_client.build_family_options), instead of a hardcoded
single model ID — so the catalog self-updates as providers ship new
models, no code changes needed.

default_persona is plain seed text for a brand-new profile (English,
since English is the default profile language) — NOT resolved through
i18n, because persona text is saved per-profile and freely editable;
its language has no effect on how the app functions.

reasoning level codes ARE translated live (see reasoning_level_label)
since that's an actual UI label the user sees in a dropdown, not saved
content.
"""

import i18n

FAMILIES = [
    {
        "key": "claude",
        "label": "Claude",
        "color": "#D97757",
        "pattern": r"^~?anthropic/claude-.*$",
        "default_model": "anthropic/claude-sonnet-5",
        "default_persona": (
            "You are a thoughtful tech-savvy philosopher. You reason deeply, "
            "connect disparate ideas into a coherent system, like to ask "
            "clarifying questions, but always bring the discussion back to "
            "the core of the topic."
        ),
    },
    {
        "key": "chatgpt",
        "label": "ChatGPT",
        "color": "#10A37F",
        "pattern": r"^~?openai/gpt-(?!oss-).*$",
        "default_model": "openai/gpt-5.6-terra",
        "default_persona": (
            "You are a pragmatic, skeptical engineer. You look for weak "
            "spots in other participants' ideas, but constructively — you "
            "immediately suggest how to fix them, and you stay concrete."
        ),
    },
    {
        "key": "grok",
        "label": "Grok",
        "color": "#1DA1F2",
        "pattern": r"^~?x-ai/grok-.*$",
        "default_model": "x-ai/grok-4.6",
        "default_persona": (
            "You are a bold generator of unconventional ideas. You're not "
            "afraid to propose provocative options, you enjoy humor, but "
            "you always bring the conversation back to something useful "
            "for the topic."
        ),
    },
    {
        "key": "gemini",
        "label": "Gemini",
        "color": "#4285F4",
        "pattern": r"^~?google/gemini-.*$",
        "default_model": "google/gemini-3.1-pro-preview",
        "default_persona": (
            "You are a systems thinker. You're good at structuring and "
            "summarizing other people's ideas, finding connections between "
            "different participants' replies, and tend to offer interim "
            "summaries."
        ),
    },
    {
        "key": "mistral",
        "label": "MistralAI",
        "color": "#FF7000",
        "pattern": r"^~?mistralai/.*$",
        "default_model": "mistralai/mistral-large-2512",
        "default_persona": (
            "You are a friendly conversationalist with an easygoing "
            "character. You bring simplicity and warmth to the discussion, "
            "and translate complex ideas into plain language."
        ),
    },
]

CUSTOM_SLOT_COLORS = ["#8E44AD", "#16A085", "#D4AC0D"]
CUSTOM_DEFAULT_PERSONA = (
    "You are a participant in a group brainstorm. Reply concisely and to "
    "the point, reacting to what other participants said."
)

MODERATOR_DEFAULT_MODEL = "openai/gpt-4o-mini"

# Reasoning token budget per level. Off by default: rarely helps for a
# casual brainstorm and can silently inflate cost. Stored/compared by
# neutral code ("off"/"low"/...), never by localized label — otherwise
# switching the UI language would break saved settings.
REASONING_LEVELS = {"off": None, "low": 1024, "medium": 4096, "high": 16000}
REASONING_LEVEL_CODES = list(REASONING_LEVELS.keys())
DEFAULT_REASONING_LEVEL = "off"

# Pre-i18n profiles stored the Russian word directly; migrate on read.
_LEGACY_REASONING_MAP = {
    "Выключено": "off", "Низкий": "low", "Средний": "medium", "Высокий": "high",
}


def normalize_reasoning_level(value):
    if value in REASONING_LEVELS:
        return value
    return _LEGACY_REASONING_MAP.get(value, DEFAULT_REASONING_LEVEL)


def reasoning_level_label(code):
    """Localized label for a reasoning level code, e.g. 'off' -> 'Off'."""
    return i18n.t(f"reasoning_{normalize_reasoning_level(code)}")


def find_family(key):
    for fam in FAMILIES:
        if fam["key"] == key:
            return dict(fam)
    return None


def short_model_name(model_id):
    """'anthropic/claude-sonnet-5' -> 'claude-sonnet-5' (drops the ~latest
    alias prefix too, if present)."""
    cleaned = model_id.lstrip("~")
    return cleaned.split("/", 1)[1] if "/" in cleaned else cleaned


def build_full_catalog(config):
    """
    Assembles the full participant list from current settings: checked
    families (with their chosen concrete model) + filled custom slots.

    Returns a list of {id, label, color, persona, reasoning_max_tokens}.
    "label" already includes the concrete model in parentheses, e.g.
    "Claude (claude-sonnet-5)" — for display in chat.
    """
    full = []

    selected_families = set(config.get("selected_families", []))
    family_choice = config.get("family_model_choice", {})
    personas = config.get("personas", {})
    reasoning_levels = config.get("reasoning_levels", {})

    for fam in FAMILIES:
        key = fam["key"]
        if key not in selected_families:
            continue
        model_id = family_choice.get(key) or fam["default_model"]
        persona = personas.get(key) or fam["default_persona"]
        level_code = normalize_reasoning_level(reasoning_levels.get(key))
        full.append({
            "id": model_id,
            "label": f"{fam['label']} ({short_model_name(model_id)})",
            "color": fam["color"],
            "persona": persona,
            "reasoning_max_tokens": REASONING_LEVELS.get(level_code),
        })

    for index, item in enumerate(config.get("custom_models", []) or []):
        if not item.get("enabled"):
            continue
        model_id = (item.get("id") or "").strip()
        if not model_id:
            continue
        raw_label = (item.get("label") or "").strip()
        short_name = short_model_name(model_id)
        label = f"{raw_label} ({short_name})" if raw_label else short_name
        persona = (item.get("persona") or "").strip() or CUSTOM_DEFAULT_PERSONA
        level_code = normalize_reasoning_level(item.get("reasoning_level"))
        full.append({
            "id": model_id,
            "label": label,
            "color": CUSTOM_SLOT_COLORS[index % len(CUSTOM_SLOT_COLORS)],
            "persona": persona,
            "reasoning_max_tokens": REASONING_LEVELS.get(level_code),
        })

    return full


def find_in_catalog(model_id, full_catalog):
    for item in full_catalog:
        if item["id"] == model_id:
            return item
    return None
