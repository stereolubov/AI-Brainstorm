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

# Used when "use_families" is off — 8 flat slots need 8 distinct colors.
# Reuses the 5 family colors + the 3 custom-slot colors rather than
# inventing a new palette from scratch.
FLAT_MODE_COLORS = [fam["color"] for fam in FAMILIES] + CUSTOM_SLOT_COLORS
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

    Returns a list of {id, participant_id, label, color, persona,
    reasoning_max_tokens}. "id" is the REAL model ID (used for the
    actual API call); "participant_id" is the unique key everything
    else — the moderator prompt, speak counts, button dispatch, "who
    just spoke" tracking — uses to tell participants apart. They're the
    same string UNLESS the same model appears in more than one custom
    slot (allowed on purpose, so one model can be given several
    different personas) — then the 2nd/3rd/... occurrence gets a
    "#2"/"#3"/... suffix on participant_id only, invisible to the
    actual API call. Families can't collide with each other (checkbox
    per family), so their participant_id always just equals their id.

    "label" already includes the concrete model in parentheses, e.g.
    "Claude (claude-sonnet-5)" — for display in chat.
    """
    full = []

    use_families = config.get("use_families", True)
    custom_models = config.get("custom_models", []) or []

    if use_families:
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
                "participant_id": model_id,
                "label": f"{fam['label']} ({short_model_name(model_id)})",
                "color": fam["color"],
                "persona": persona,
                "reasoning_max_tokens": REASONING_LEVELS.get(level_code),
                "reasoning_raw": "",  # families never pair with a "raw"-format provider (use_families
                                      # is forced off for those), but the key is always present
            })
        # The 3 "own" slots live at storage indices 5-7 (not 0-2) — so
        # that switching to flat mode can put the 5 families at indices
        # 0-4 in their natural order without having to shuffle these
        # around; the visual list order stays stable either way.
        slots_to_use = custom_models[5:8]
        slot_colors = CUSTOM_SLOT_COLORS
    else:
        # Families switched off entirely — all 8 slots are flat, generic
        # custom entries, no family concept involved at all.
        slots_to_use = custom_models[:8]
        slot_colors = FLAT_MODE_COLORS

    seen_custom_model_ids = {}  # model_id -> how many times seen so far, for the #2/#3/... suffix
    for index, item in enumerate(slots_to_use):
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

        seen_custom_model_ids[model_id] = seen_custom_model_ids.get(model_id, 0) + 1
        occurrence = seen_custom_model_ids[model_id]
        participant_id = model_id if occurrence == 1 else f"{model_id}#{occurrence}"

        full.append({
            "id": model_id,
            "participant_id": participant_id,
            "label": label,
            "color": slot_colors[index % len(slot_colors)],
            "persona": persona,
            "reasoning_max_tokens": REASONING_LEVELS.get(level_code),
            "reasoning_raw": (item.get("reasoning_raw") or ""),  # only used when the active
                                                                  # provider's reasoning_format is "raw"
        })

    return full


def find_in_catalog(participant_id, full_catalog):
    for item in full_catalog:
        if item["participant_id"] == participant_id:
            return item
    return None
