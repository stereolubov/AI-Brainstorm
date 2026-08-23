# -*- coding: utf-8 -*-
"""
Обёртка над OpenRouter API. Используется только стандартная библиотека
Python (urllib, json, re) — чтобы не тащить сторонние зависимости в exe.
"""

import json
import logging
import re
import urllib.request
import urllib.error

from models_catalog import FAMILIES

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_INFO_URL = "https://openrouter.ai/api/v1/key"
MODELS_LIST_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT_SECONDS = 60
DEFAULT_MAX_TOKENS = 800  # с запасом, чтобы реплика не обрывалась на полуслове

logger = logging.getLogger("ai_brainstorm.api_client")


class OpenRouterError(Exception):
    """Базовое исключение для ошибок обращения к OpenRouter."""


def _headers(api_key=None):
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-ai-brainstorm-app",
        "X-Title": "AI Brainstorm Desktop",
    }
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    return headers


def _request(url, api_key=None, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
            error_json = json.loads(error_body)
            message = error_json.get("error", {}).get("message", error_body)
        except Exception:
            message = str(e)
        logger.error("HTTPError %s при обращении к %s: %s", e.code, url, message)
        raise OpenRouterError(f"Ошибка API ({e.code}): {message}") from e
    except urllib.error.URLError as e:
        logger.error("URLError при обращении к %s: %s", url, e.reason)
        raise OpenRouterError(f"Сетевая ошибка: {e.reason}") from e


def ask_model(api_key, model_id, system_prompt, user_prompt, max_tokens=DEFAULT_MAX_TOKENS, reasoning_max_tokens=None):
    """
    Отправляет один запрос к указанной модели через OpenRouter.

    reasoning_max_tokens — None/0 означает полностью выключенные
    рассуждения (payload["reasoning"] = {"enabled": False}); положительное
    число — бюджет токенов на скрытое размышление модели перед видимым
    ответом (payload["reasoning"] = {"max_tokens": N}). Не все модели
    поддерживают рассуждения — тогда параметр просто игнорируется
    провайдером, без ошибки.

    Возвращает кортеж (текст_ответа, usage), где usage — словарь вида
    {"prompt_tokens": int, "completion_tokens": int, "cost": float|None}.

    Бросает OpenRouterError при сетевой ошибке или ошибке API (в т.ч. 429).
    """
    if not api_key:
        raise OpenRouterError("Не указан API-ключ OpenRouter. Заполните его в настройках.")

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }
    if reasoning_max_tokens and reasoning_max_tokens > 0:
        payload["reasoning"] = {"max_tokens": reasoning_max_tokens}
    else:
        payload["reasoning"] = {"enabled": False}

    logger.debug("Запрос к модели %s (max_tokens=%s)", model_id, max_tokens)
    result = _request(CHAT_URL, api_key, method="POST", payload=payload)

    try:
        content = result["choices"][0]["message"]["content"].strip()
        finish_reason = result["choices"][0].get("finish_reason")
    except (KeyError, IndexError) as e:
        raise OpenRouterError(f"Не удалось разобрать ответ модели: {e}\nОтвет сервера: {result}") from e

    if finish_reason == "length":
        logger.warning("Модель %s: ответ обрезан по лимиту max_tokens=%s", model_id, max_tokens)
        content += "\n\n[…ответ обрезан по лимиту длины]"

    usage_raw = result.get("usage", {}) or {}
    usage = {
        "prompt_tokens": usage_raw.get("prompt_tokens"),
        "completion_tokens": usage_raw.get("completion_tokens"),
        "cost": usage_raw.get("cost"),
    }
    logger.debug("Ответ от %s: %s токенов, стоимость=%s", model_id, usage.get("completion_tokens"), usage.get("cost"))

    return content, usage


def get_key_info(api_key):
    """Возвращает словарь: usage, limit, limit_remaining, label для ключа."""
    if not api_key:
        raise OpenRouterError("Не указан API-ключ OpenRouter.")
    result = _request(KEY_INFO_URL, api_key, method="GET")
    data = result.get("data", {})
    return {
        "usage": data.get("usage"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "label": data.get("label"),
    }


def fetch_all_model_ids(api_key=None):
    """Тянет полный список ID моделей с OpenRouter (эндпоинт публичный,
    ключ не обязателен, но передаём его если есть — не мешает)."""
    result = _request(MODELS_LIST_URL, api_key, method="GET")
    return [m.get("id", "") for m in result.get("data", []) if m.get("id")]


def build_family_options(api_key=None):
    """
    Группирует полный список моделей OpenRouter по семействам (см.
    models_catalog.FAMILIES) через regex-фильтры.

    Возвращает кортеж (options, all_ids):
      options — {family_key: [отсортированный список подходящих model_id]}
      all_ids — полный неотфильтрованный список всех ID (нужен, например,
                для автодополнения в слотах кастомных моделей — там может
                быть модель, не подходящая ни под одно семейство).
    """
    all_ids = fetch_all_model_ids(api_key)
    options = {}
    for fam in FAMILIES:
        pattern = re.compile(fam["pattern"])
        matched = sorted({model_id for model_id in all_ids if pattern.match(model_id)})
        options[fam["key"]] = matched
    return options, all_ids


# ---------- Ведущий ----------

_MODERATOR_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _resolve_participant(raw_value, participants, allow_user):
    """
    Мягко сопоставляет то, что вернул ведущий (в поле "next"), с реальным
    id участника. Модели-ведущие (особенно послабее) часто пишут не
    полный id ("anthropic/claude-sonnet-5"), а укороченное имя
    ("claude-sonnet-5"), название семейства ("Claude", "MistralAI") или
    алиас без провайдерского префикса ("grok-latest"). Раньше это
    приводило к тому, что ЛЮБОЙ ответ ведущего браковался как невалидный
    и включался запасной выбор — по факту ведущий не работал вообще.

    Возвращает id участника, "user" (если разрешено), либо None.
    """
    if not raw_value:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    if raw.lower() == "user":
        return "user" if allow_user else None

    # 1. точное совпадение по полному id
    for p in participants:
        if p["id"] == raw:
            return p["id"]

    def tail(model_id):
        return model_id.lstrip("~").split("/", 1)[-1].lower()

    raw_lower = raw.lstrip("~").lower()

    # 2. совпадение по "хвосту" id после провайдера (и без ~latest-префикса)
    for p in participants:
        if tail(p["id"]) == raw_lower:
            return p["id"]

    # 3. совпадение по названию семейства/лейблу, например "Gemini", "MistralAI"
    #    (лейбл вида "Claude (claude-sonnet-5)" -> базовая часть "claude")
    for p in participants:
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower == base_label:
            return p["id"]

    # 4. последняя попытка: подстрока в любую сторону
    for p in participants:
        id_lower = p["id"].lower()
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower in id_lower or id_lower in raw_lower or raw_lower in base_label or base_label in raw_lower:
            return p["id"]

    return None


def _parse_moderator_reply(raw_text, participants, allow_user):
    """
    Извлекает структурированное решение ведущего из текста ответа.
    Модели иногда оборачивают JSON в ```-блоки или добавляют текст вокруг —
    вырезаем первую { ... } подстроку.

    Возвращает словарь:
      {"next": id_или_"user"_или_None, "task": str, "reason": str,
       "reaction_type": str, "wrap_up": bool}
    """
    empty = {"next": None, "task": "", "reason": "", "reaction_type": "", "wrap_up": False}
    match = _MODERATOR_JSON_RE.search(raw_text or "")
    if not match:
        return empty
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return empty

    next_id = _resolve_participant(data.get("next"), participants, allow_user)
    return {
        "next": next_id,
        "task": str(data.get("task", "") or ""),
        "reason": str(data.get("reason", "") or ""),
        "reaction_type": str(data.get("reaction_type", "") or ""),
        "wrap_up": bool(data.get("wrap_up", False)),
    }


def ask_moderator(api_key, moderator_model_id, topic, transcript_text, participants,
                   allow_user, replies_done=0, max_replies=0, is_final_reply=False):
    """
    Просит модель-ведущего решить, кто должен высказаться следующим, что
    именно должен сделать, зачем, какой тип реакции нужен, и не пора ли
    уже подводить итог обсуждения (особенно полезно ближе к лимиту реплик).

    is_final_reply=True означает, что эта реплика — гарантированно
    последняя в сессии (лимит реплик будет достигнут сразу после неё).
    В этом случае wrap_up и task всё равно принудительно выставляются
    вызывающим кодом (main.py) даже если ведущий это проигнорирует —
    здесь это только усиливает промпт, чтобы ведущий выбрал участника,
    который лучше всего подведёт итог.

    participants — список словарей {id, label, persona} (из full_catalog,
    включает и стандартные, и кастомные модели пользователя); ДОЛЖЕН
    содержать только реально доступных сейчас участников (см. механизм
    "временно недоступен" в main.py) — так ведущий физически не сможет
    выбрать модель, которая прямо сейчас отдаёт ошибки.

    Возвращает кортеж (decision, usage), где decision — словарь из
    _parse_moderator_reply (может содержать next=None, если ведущий не
    дал распознаваемого ответа — тогда вызывающий код выбирает сам).
    """
    participants_desc = "\n".join(
        f"- {p['id']}: {p['label']} — {p['persona'][:100]}" for p in participants
    )
    user_note = (
        "Также можно выбрать значение \"user\" — тогда слово получит "
        "человек-пользователь, который тоже участвует в обсуждении."
        if allow_user else
        "Значение \"user\" сейчас недоступно — не выбирай его."
    )
    if is_final_reply:
        progress_note = (
            f"ВНИМАНИЕ: это ПОСЛЕДНЯЯ реплика сессии (лимит {max_replies} реплик "
            f"будет достигнут сразу после неё, дальше уже никто не ответит). "
            f"Обязательно выбери участника, который лучше всего подведёт общий "
            f"итог всего обсуждения, поставь task на подведение итога и "
            f"wrap_up=true."
        )
    else:
        progress_note = (
            f"Прогресс: {replies_done} из {max_replies} реплик участников уже прозвучало."
            if max_replies else ""
        )

    system_prompt = (
        "Ты — скрытый ведущий группового ИИ-брейншторма. Сам в обсуждении "
        "не участвуешь. После каждой реплики решаешь: КТО говорит следующим, "
        "ЧТО именно ему нужно сделать, ЗАЧЕМ (какую пользу это принесёт "
        "дискуссии прямо сейчас), КАКОЙ ТИП РЕАКЦИИ нужен (например: критика, "
        "поддержка идеи, новая идея, синтез, уточняющий вопрос, итог) — и не "
        "пора ли уже завершать обсуждение подведением итога. Не давай одному "
        "участнику говорить слишком много раз подряд без причины. Используй "
        "ТОЛЬКО id из списка участников ниже, дословно. "
        "Отвечай СТРОГО в формате JSON без каких-либо пояснений вне него: "
        '{"next": "<id участника или user>", "task": "<короткая инструкция '
        'участнику>", "reason": "<зачем именно сейчас>", "reaction_type": '
        '"<тип реакции>", "wrap_up": true или false}'
    )
    user_prompt = (
        f"Тема обсуждения: {topic}\n\n"
        f"{progress_note}\n\n"
        f"Участники:\n{participants_desc}\n\n"
        f"{user_note}\n\n"
        f"История обсуждения:\n{transcript_text or '(обсуждение только начинается)'}\n\n"
        f"Кто и зачем должен высказаться следующим?"
    )

    content, usage = ask_model(
        api_key, moderator_model_id, system_prompt, user_prompt,
        max_tokens=220, reasoning_max_tokens=None,
    )
    decision = _parse_moderator_reply(content, participants, allow_user)
    if decision["next"] is None:
        logger.warning("Ведущий вернул нераспознаваемый ответ: %r — включаю запасной выбор", content)
    else:
        logger.debug("Ведущий выбрал %s: task=%r reason=%r", decision["next"], decision["task"], decision["reason"])
    return decision, usage
