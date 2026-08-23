# -*- coding: utf-8 -*-
"""
Хранение настроек приложения через ПРОФИЛИ.

Каждый профиль — самостоятельный JSON-файл со своим API-ключом и всеми
настройками (удобно для нескольких аккаунтов OpenRouter или разных
наборов участников под разные случаи). Профили лежат в:
  Windows: C:\\Users\\<имя>\\.ai_brainstorm\\profiles\\<имя>.json
  Linux/Mac: ~/.ai_brainstorm/profiles/<имя>.json

Отдельный маленький файл-указатель хранит только имя активного профиля:
  ~/.ai_brainstorm/active_profile.json  ->  {"active_profile": "default"}

Так при следующем запуске приложение знает, какой профиль подхватить
автоматически, без выбора вручную.
"""

import json
import os

from models_catalog import MODERATOR_DEFAULT_MODEL

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ai_brainstorm")
PROFILES_DIR = os.path.join(CONFIG_DIR, "profiles")
POINTER_PATH = os.path.join(CONFIG_DIR, "active_profile.json")

DEFAULT_PROFILE_NAME = "default"


def _empty_custom_slots():
    """Три независимых пустых словаря — важно, чтобы это не был один и
    тот же объект в памяти (иначе правки одного слота задели бы все)."""
    return [
        {"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "Выключено"}
        for _ in range(3)
    ]


DEFAULT_CONFIG = {
    "api_key": "",
    "selected_families": [],       # ключи семейств, отмеченных галочкой
    "family_model_choice": {},     # {family_key: конкретный выбранный model_id}
    "personas": {},                # {family_key: текст персонажа}
    "reasoning_levels": {},        # {family_key: "Выключено"|"Низкий"|"Средний"|"Высокий"}
    "custom_models": _empty_custom_slots(),
    "session_budget_usd": 0.5,     # лимит расходов на одну сессию, USD
    "max_replies": 12,             # лимит числа реплик участников на сессию
    "moderator_mode": "ai",        # "ai" или "human"
    "moderator_model": MODERATOR_DEFAULT_MODEL,
    "user_participation": False,   # разрешить ведущему звать пользователя высказаться
    "moderator_summary": False,    # отдельный вызов ведущего с тезисным итогом сессии
    "debug_tab_enabled": False,    # показывать вкладку "Лог" в интерфейсе
    "family_options_cache": {},    # {family_key: [id, id, ...]} — кэш списка моделей
    "all_model_ids_cache": [],     # полный неотфильтрованный список ID — для кастомных слотов
    "family_options_updated_at": "",  # когда кэш обновлялся последний раз
}


def _safe_filename(name):
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return safe or DEFAULT_PROFILE_NAME


def _profile_path(name):
    return os.path.join(PROFILES_DIR, _safe_filename(name) + ".json")


def list_profiles():
    """Возвращает отсортированный список имён существующих профилей.
    Если профилей ещё нет ни одного, возвращает [DEFAULT_PROFILE_NAME]
    (сам файл при этом появится только после первого save_profile)."""
    if not os.path.isdir(PROFILES_DIR):
        return [DEFAULT_PROFILE_NAME]
    names = [
        os.path.splitext(f)[0] for f in os.listdir(PROFILES_DIR)
        if f.endswith(".json")
    ]
    return sorted(names) or [DEFAULT_PROFILE_NAME]


def _read_pointer():
    if not os.path.exists(POINTER_PATH):
        return DEFAULT_PROFILE_NAME
    try:
        with open(POINTER_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("active_profile", DEFAULT_PROFILE_NAME)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PROFILE_NAME


def _write_pointer(name):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(POINTER_PATH, "w", encoding="utf-8") as f:
        json.dump({"active_profile": name}, f, ensure_ascii=False, indent=2)


_active_profile_name = DEFAULT_PROFILE_NAME  # обновляется load_config()/switch_active_profile()


def get_active_profile_name():
    return _active_profile_name


def switch_active_profile(name):
    """Помечает профиль активным (для последующих save_config без явного
    имени) и запоминает выбор на будущие запуски."""
    global _active_profile_name
    _active_profile_name = name
    _write_pointer(name)


def _normalize(data):
    """Дополняет загруженный словарь недостающими ключами по умолчанию и
    гарантирует ровно 3 кастомных слота (на случай файла от старой версии)."""
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update(data)

    slots = merged.get("custom_models") or []
    slots = list(slots)[:3]
    while len(slots) < 3:
        slots.append({"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "Выключено"})
    for slot in slots:
        slot.setdefault("reasoning_level", "Выключено")
    merged["custom_models"] = slots

    return merged


def load_config(profile_name=None):
    """Загружает профиль (по умолчанию — тот, что был активен в прошлый
    раз, согласно файлу-указателю). Если профиль ещё не существует на
    диске (самый первый запуск), создаёт его с настройками по умолчанию."""
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
    """Сохраняет словарь настроек в конкретный именованный профиль,
    не трогая указатель активного профиля."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(_profile_path(name), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def save_config(config, profile_name=None):
    """Сохраняет в АКТИВНЫЙ профиль (или в указанный явно) — основной
    метод сохранения, используемый большей частью приложения."""
    save_profile(profile_name or _active_profile_name, config)


def delete_profile(name):
    path = _profile_path(name)
    if os.path.exists(path):
        os.remove(path)
