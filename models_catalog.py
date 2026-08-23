# -*- coding: utf-8 -*-
"""
Каталог "семейств" моделей для брейншторма.

Вместо жёсткой привязки к одному ID модели, каждое семейство описывается
регулярным выражением — под него на OpenRouter может подходить сразу
несколько конкретных моделей (разные версии/тиры одного вендора).
Список конкретных ID подтягивается динамически через
api_client.build_family_options() и кэшируется в config.json — так
каталог сам актуализируется, когда провайдер выпускает новую модель,
без правок кода.

default_model — то, что выбрано по умолчанию, пока пользователь не
выбрал другую модель внутри семейства (или пока список ещё не обновлён
из сети — тогда именно default_model остаётся единственным вариантом).
"""

FAMILIES = [
    {
        "key": "claude",
        "label": "Claude",
        "color": "#D97757",
        "pattern": r"^~?anthropic/claude-.*$",
        "default_model": "anthropic/claude-sonnet-5",
        "default_persona": (
            "Ты — вдумчивый философ-технарь. Рассуждаешь глубоко, "
            "связываешь разрозненные идеи в систему, любишь задавать "
            "уточняющие вопросы, но всегда возвращаешься к сути темы."
        ),
    },
    {
        "key": "chatgpt",
        "label": "ChatGPT",
        "color": "#10A37F",
        "pattern": r"^~?openai/gpt-(?!oss-).*$",
        "default_model": "openai/gpt-5.6-terra",
        "default_persona": (
            "Ты — прагматичный технарь-скептик. Ищешь слабые места в "
            "идеях других участников, но конструктивно — сразу "
            "предлагаешь, как их устранить, и держишься конкретики."
        ),
    },
    {
        "key": "grok",
        "label": "Grok",
        "color": "#1DA1F2",
        "pattern": r"^~?x-ai/grok-.*$",
        "default_model": "x-ai/grok-4.6",
        "default_persona": (
            "Ты — дерзкий генератор нестандартных идей. Не боишься "
            "предлагать провокационные варианты, любишь юмор, но "
            "всегда возвращаешь разговор к пользе для темы обсуждения."
        ),
    },
    {
        "key": "gemini",
        "label": "Gemini",
        "color": "#4285F4",
        "pattern": r"^~?google/gemini-.*$",
        "default_model": "google/gemini-3.1-pro-preview",
        "default_persona": (
            "Ты — системный мыслитель. Хорошо структурируешь и "
            "обобщаешь чужие идеи, находишь связи между репликами "
            "разных участников, склонен подводить промежуточные итоги."
        ),
    },
    {
        "key": "mistral",
        "label": "MistralAI",
        "color": "#FF7000",
        "pattern": r"^~?mistralai/.*$",
        "default_model": "mistralai/mistral-large-2512",
        "default_persona": (
            "Ты — дружелюбный собеседник с лёгким характером. "
            "Добавляешь в обсуждение простоту и человечность, "
            "переводишь сложные идеи на понятный язык."
        ),
    },
]

CUSTOM_SLOT_COLORS = ["#8E44AD", "#16A085", "#D4AC0D"]  # фиолетовый, бирюзовый, охра
CUSTOM_DEFAULT_PERSONA = (
    "Ты участник группового брейншторма. Отвечай по существу, кратко, "
    "реагируя на реплики остальных участников."
)

MODERATOR_DEFAULT_MODEL = "mistralai/mistral-large-2512"  # самый дешёвый вариант

# Уровни "рассуждений" (reasoning): вместо жёсткого вкл/выкл — управляемый
# бюджет токенов на скрытое размышление модели перед видимым ответом.
# По умолчанию выключено — для большинства тем брейншторма не даёт
# заметной пользы, а счёт может ощутимо вырасти. Явно измеряем в токенах
# (а не в "low/medium/high" эффорте самого провайдера), чтобы стоимость
# была предсказуемой, а не зависела от того, как конкретный провайдер
# интерпретирует расплывчатый "эффорт".
REASONING_LEVELS = {
    "Выключено": None,
    "Низкий": 1024,
    "Средний": 4096,
    "Высокий": 16000,
}
REASONING_LEVEL_NAMES = list(REASONING_LEVELS.keys())
DEFAULT_REASONING_LEVEL = "Выключено"


def find_family(key):
    for fam in FAMILIES:
        if fam["key"] == key:
            return dict(fam)
    return None


def short_model_name(model_id):
    """Убирает провайдерский префикс для компактного отображения в скобках:
    'anthropic/claude-sonnet-5' -> 'claude-sonnet-5'."""
    cleaned = model_id.lstrip("~")
    if "/" in cleaned:
        return cleaned.split("/", 1)[1]
    return cleaned


def build_full_catalog(config):
    """
    Собирает полный список участников брейншторма на основе текущих
    настроек: отмеченные семейства (с выбранной внутри них конкретной
    моделью) + заполненные кастомные слоты.

    Возвращает список словарей: {id, label, color, persona, reasoning_max_tokens}
    "label" уже содержит конкретную модель в скобках, например
    «Claude (claude-sonnet-5)» — для отображения в чате.
    "reasoning_max_tokens" — None (рассуждения выключены) либо число
    токенов-бюджета на скрытое размышление модели перед ответом.
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
        level_name = reasoning_levels.get(key) or DEFAULT_REASONING_LEVEL
        full.append({
            "id": model_id,
            "label": f"{fam['label']} ({short_model_name(model_id)})",
            "color": fam["color"],
            "persona": persona,
            "reasoning_max_tokens": REASONING_LEVELS.get(level_name),
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
        level_name = item.get("reasoning_level") or DEFAULT_REASONING_LEVEL
        full.append({
            "id": model_id,
            "label": label,
            "color": CUSTOM_SLOT_COLORS[index % len(CUSTOM_SLOT_COLORS)],
            "persona": persona,
            "reasoning_max_tokens": REASONING_LEVELS.get(level_name),
        })

    return full


def find_in_catalog(model_id, full_catalog):
    for item in full_catalog:
        if item["id"] == model_id:
            return item
    return None
