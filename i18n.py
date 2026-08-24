# -*- coding: utf-8 -*-
"""
JSON-based UI translations (no gettext/.po — avoids needing msgfmt).

Languages are files in locales/ next to the profiles folder:
  ~/.ai_brainstorm/locales/Russian.json
  ~/.ai_brainstorm/locales/English.json
Format: {"code": "ru", "name": "Русский", "translations": {"key": "..."}}

The folder is rescanned on every call to list_available_languages(), so
dropping in a new file (e.g. French.json with "code": "fr") makes it
appear with no code changes. Built-in RU/EN dicts below are the source
for self-healing Russian.json/English.json if deleted or corrupted, and
the emergency fallback for t(). Manual edits to the files themselves are
always respected — read from disk, not from the embedded copy.
"""

import json
import logging
import os

logger = logging.getLogger("ai_brainstorm.i18n")

DEFAULT_LANGUAGE_CODE = "en"

_BUILTIN_FILENAMES = {"ru": "Russian.json", "en": "English.json"}
_BUILTIN_NAMES = {"ru": "Русский", "en": "English"}

_current_code = DEFAULT_LANGUAGE_CODE
_current_translations = {}
_available_cache = []


def _locales_dir():
    from config import LOCALES_DIR
    return LOCALES_DIR


def _write_locale_file(path, code, name, translations):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"code": code, "name": name, "translations": translations}, f, ensure_ascii=False, indent=2)


def _is_valid_locale_data(data):
    return isinstance(data, dict) and data.get("code") and isinstance(data.get("translations"), dict)


def _ensure_builtin_files():
    """Create Russian.json/English.json if missing or corrupted. Other
    (custom) language files are left alone — not our responsibility."""
    directory = _locales_dir()
    os.makedirs(directory, exist_ok=True)
    for code, filename in _BUILTIN_FILENAMES.items():
        path = os.path.join(directory, filename)
        needs_write = not os.path.exists(path)
        if not needs_write:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not _is_valid_locale_data(data):
                    raise ValueError("missing code/translations")
            except Exception as e:
                logger.warning("Locale file %s corrupted (%s), recreating", filename, e)
                needs_write = True
        if needs_write:
            _write_locale_file(path, code, _BUILTIN_NAMES[code], _BUILTIN_TRANSLATIONS[code])


def list_available_languages():
    """Rescans locales/ and returns [{"code","name","path"}, ...]."""
    _ensure_builtin_files()
    directory = _locales_dir()
    languages = []
    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(directory, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not _is_valid_locale_data(data):
                raise ValueError("missing code/translations")
            languages.append({"code": data["code"], "name": data.get("name") or data["code"], "path": path})
        except Exception as e:
            logger.warning("Skipping locale file %s: %s", filename, e)

    global _available_cache
    _available_cache = languages
    return languages


def get_available_languages():
    return _available_cache


def load_language(code):
    """Loads translations for `code`. Falls back to English if not found
    among available languages, and returns the code that actually got
    applied — caller should persist that if it differs from `code`."""
    global _current_code, _current_translations

    languages = list_available_languages()
    match = next((lang for lang in languages if lang["code"] == code), None)

    if match is None:
        if code != DEFAULT_LANGUAGE_CODE:
            logger.warning("Language %r not found, falling back to %r", code, DEFAULT_LANGUAGE_CODE)
        match = next((lang for lang in languages if lang["code"] == DEFAULT_LANGUAGE_CODE), None)
        code = DEFAULT_LANGUAGE_CODE

    if match is None:
        _current_code = DEFAULT_LANGUAGE_CODE
        _current_translations = dict(_BUILTIN_TRANSLATIONS.get(DEFAULT_LANGUAGE_CODE, {}))
        return _current_code

    try:
        with open(match["path"], "r", encoding="utf-8") as f:
            data = json.load(f)
        _current_translations = data.get("translations", {})
        _current_code = match["code"]
    except Exception as e:
        logger.warning("Could not read locale file %s: %s, using built-in", match["path"], e)
        _current_translations = dict(_BUILTIN_TRANSLATIONS.get(code, _BUILTIN_TRANSLATIONS[DEFAULT_LANGUAGE_CODE]))
        _current_code = code

    return _current_code


def get_current_language_code():
    return _current_code


def t(key, **kwargs):
    """Translate `key` for the active language. Fallback chain: active
    language -> built-in English -> built-in Russian -> the key itself."""
    text = _current_translations.get(key)
    if text is None:
        text = _BUILTIN_TRANSLATIONS.get(DEFAULT_LANGUAGE_CODE, {}).get(key)
    if text is None:
        text = _BUILTIN_TRANSLATIONS.get("ru", {}).get(key)
    if text is None:
        text = key

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# ---------- Built-in dictionaries: self-heal source + emergency fallback ----------

_BUILTIN_TRANSLATIONS = {
    "ru": {
        "app_title": "AI Brainstorm",

        "reasoning_off": "Выключено",
        "reasoning_low": "Низкий",
        "reasoning_medium": "Средний",
        "reasoning_high": "Высокий",
        "reasoning_label": "Рассуждения:",

        "cost_line": "(стоимость реплики: ${cost})",
        "cost_line_with_moderator": "(стоимость реплики: ${cost} + ведущий ${mod} = ${total})",
        "cost_line_summary": "(стоимость итога: ${cost})",

        "show_log_tab_checkbox": "Показывать вкладку «Лог» (техническая информация о работе программы)",
        "saved_confirmation": "Сохранено ✓",
        "tab_log": "Лог",

        "copy_all_button": "Копировать всё",
        "clear_button": "Очистить",

        "profile_block_title": "Профиль настроек",
        "active_profile_label": "Активный профиль:",
        "save_as_button": "Сохранить как…",
        "delete_button": "Удалить",
        "save_settings_button": "Сохранить настройки",
        "open_settings_folder_button": "Открыть папку настроек",
        "profile_block_hint": (
            "Каждый профиль хранит СВОЙ API-ключ и все настройки отдельно — "
            "удобно, если у вас несколько аккаунтов OpenRouter или разные "
            "наборы участников под разные случаи. Профиль применяется сразу "
            "при выборе из списка. Кнопка «Сохранить настройки» справа "
            "пишет все правки формы ниже в текущий активный профиль."
        ),
        "new_profile_name_prompt": "Название нового профиля:",
        "profile_exists_overwrite": "Профиль «{name}» уже существует. Перезаписать?",
        "profile_saved_and_active": "Сохранено как профиль «{name}» и сделано активным.",
        "cannot_delete_last_profile": "Нельзя удалить последний оставшийся профиль.",
        "confirm_delete_profile": "Удалить профиль «{name}» без возможности восстановления?",
        "open_folder_failed": "Не удалось открыть папку автоматически: {error}\n\nПуть: {path}",

        "log_profile_loaded": "Загружен профиль: {name}",
        "log_profile_saved_new": "Сохранён новый профиль: {name}",
        "log_profile_deleted": "Удалён профиль: {name}",
        "log_settings_folder_opened": "Открыта папка настроек: {path}",
        "log_settings_folder_error": "Не удалось открыть папку настроек: {error}",

        "api_key_block_title": "API-ключ OpenRouter",
        "show_checkbox": "показать",
        "check_balance_button": "Проверить баланс ключа",
        "refresh_models_button": "Обновить список моделей",
        "refresh_models_hint": (
            "Обновление списка моделей затрагивает сразу семейства "
            "стандартных моделей, модель ведущего и\nподсказки для "
            "дополнительных (кастомных) моделей ниже — один клик на всё."
        ),
        "enter_api_key_first": "Сначала введите API-ключ.",
        "checking_ellipsis": "Проверяю…",
        "error_prefix": "Ошибка: {error}",
        "not_available_abbr": "н/д",
        "cache_never_updated": "список ещё не обновлялся из сети — доступны только модели по умолчанию",
        "cache_updated_at": "обновлено: {timestamp}",

        "topic_label": "Тема обсуждения:",
        "max_replies_label": "Макс. реплик:",
        "start_brainstorm_button": "Начать брейншторм",
        "intervene_button": "Вмешаться",
        "export_button": "Экспорт…",

        "final_reply_choose_speaker": "Последняя реплика сессии — выберите, кто подведёт итог всего обсуждения:",
        "your_turn_choose_speaker": "Ваш ход как ведущего: кто говорит следующим?",
        "optional_comment_hint": "Необязательный комментарий выше добавится в чат от вашего имени перед выбранной репликой.",
        "speak_myself_button": "Я (высказаться)",
        "end_discussion_button": "Завершить обсуждение",
        "moderator_passed_you_the_floor": "Ведущий передал слово вам — введите реплику или пропустите:",
        "send_button": "Отправить",
        "skip_button": "Пропустить",
        "intervene_hint": "Вмешательство: можно добавить уточнение для участников или завершить сессию прямо сейчас.",
        "continue_with_note_button": "Продолжить с уточнением",
        "end_session_button": "Завершить сессию",

        "export_log_empty": "Лог обсуждения пуст — экспортировать нечего.",
        "markdown_filetype": "Markdown",
        "text_filetype": "Текстовый файл",
        "all_files_filetype": "Все файлы",
        "export_dialog_title": "Сохранить лог обсуждения",
        "save_file_failed": "Не удалось сохранить файл: {error}",
        "log_export_done": "Лог обсуждения экспортирован в {path}",
        "exported_to": "Экспортировано в {path}",
        "log_copied_to_clipboard": "Весь лог скопирован в буфер обмена.",
        "intervene_pending_status": "Запрошено вмешательство — сработает после текущей реплики…",
        "log_intervene_requested": "Пользователь запросил вмешательство",

        "set_api_key_first": "Сначала укажите API-ключ на вкладке «Настройки».",
        "select_min_models_in_settings": "На вкладке «Настройки» выберите минимум {min} моделей.",
        "enter_topic_warning": "Введите тему обсуждения.",
        "user_topic_label": "Пользователь (тема)",
        "spent_status": "Потрачено: {spent} из ${budget}",
        "discussion_in_progress": "Идёт обсуждение…",
        "log_session_started": (
            "Старт сессии: тема={topic!r}, участников={count}, ведущий={mode}, "
            "макс.реплик={max_replies}, бюджет=${budget}, итог={summary}"
        ),
        "error_speaker_suffix": "{label} (ошибка)",
        "system_label": "Система",
        "discussion_finished": "Обсуждение завершено.",

        "budget_limit_reached": "Достигнут лимит бюджета сессии (${budget}).",
        "reply_limit_reached": "Достигнут лимит числа реплик ({max_replies}).",
        "session_ended_by_user": "Сессия завершена пользователем.",
        "safety_loop_limit_reached": (
            "Сессия остановлена аварийным предохранителем (слишком много "
            "ходов без прогресса по лимиту реплик) — сообщите об этом, "
            "если увидите такое в обычной сессии."
        ),
        "user_clarification_transcript": "Пользователь (уточнение): {text}",
        "user_label": "Пользователь",
        "discussion_just_starting": "(обсуждение только начинается)",
        "final_reply_status_human": "Последняя реплика сессии — выберите, кто подведёт итог…",
        "your_turn_status_human": "Ваш ход как ведущего — выберите участника…",
        "user_comment_transcript": "Пользователь (комментарий): {comment}",
        "final_summary_task": "Подведи итог всего обсуждения одной обобщающей репликой.",
        "moderator_choosing_status": "Ведущий выбирает следующего участника…",
        "log_moderator_error": "Ошибка вызова ведущего: {error}",
        "log_moderator_fallback": "Ведущий не дал валидный ответ, выбран запасной вариант: {id}",
        "moderator_passed_floor_status": "Ведущий передал слово вам…",
        "user_reply_transcript": "Пользователь: {reply}",
        "log_unknown_model_chosen": "Ведущий выбрал неизвестную модель {id} — пропускаю ход",
        "model_preparing_status": "{label} готовит ответ…",
        "moderator_task_guidance": "\nЗадача от ведущего: {task}",
        "moderator_reaction_guidance": "\nОжидаемый тип реакции: {reaction_type}",
        "wrap_up_guidance": "\nОбсуждение близится к концу — дай более итоговую, подытоживающую реплику.",
        "participant_user_prompt": (
            "Тема обсуждения: {topic}\n\n"
            "История обсуждения:\n{transcript}\n"
            "{guidance}\n\n"
            "Дай свою реплику по теме — по существу, 3-5 предложений, "
            "обязательно заверши мысль в пределах этого объёма (лучше "
            "короче, но закончено, чем оборвано на полуслове)."
        ),
        "log_model_unavailable": "Модель {id} временно недоступна: {error}",
        "transcript_skipped_unavailable": "{label}: (пропущен — временно недоступен)",
        "transcript_reply_line": "{label}: {reply}",
        "log_summary_failed": "Не удалось получить итог от ведущего: {error}",
        "unknown_cost_note": (
            " (для {count} реплик провайдер не вернул точную стоимость — "
            "реальный расход мог быть чуть выше)"
        ),
        "log_session_finished": "Сессия завершена: {reason} Всего потрачено: ${total}",

        "tab_settings": "Настройки",
        "tab_chat": "Чат",
        "language_label": "Язык интерфейса:",
        "log_language_fallback": (
            "Сохранённый язык «{saved}» не найден среди доступных — "
            "переключено на «{applied}»"
        ),
        "log_language_switched": "Язык переключён на: {code}",

        "log_http_error": "HTTPError {code} при обращении к {url}: {message}",
        "api_error": "Ошибка API ({code}): {message}",
        "network_error": "Сетевая ошибка: {reason}",
        "log_url_error": "URLError при обращении к {url}: {reason}",
        "no_api_key_error": "Не указан API-ключ OpenRouter. Заполните его в настройках.",
        "no_api_key_short_error": "Не указан API-ключ OpenRouter.",
        "log_model_request": "Запрос к модели {model} (max_tokens={max_tokens})",
        "parse_error": "Не удалось разобрать ответ модели: {error}\nОтвет сервера: {result}",
        "log_model_truncated": "Модель {model}: ответ обрезан по лимиту max_tokens={max_tokens}",
        "truncated_note": "\n\n[…ответ обрезан по лимиту длины]",
        "log_model_response": "Ответ от {model}: {tokens} токенов, стоимость={cost}",

        "moderator_user_entry": (
            "\n- user: Пользователь — живой человек, тоже участвует в "
            "обсуждении; иногда стоит передавать ему слово, а не только "
            "ИИ-участникам."
        ),
        "moderator_final_reply_note": (
            "ВНИМАНИЕ: это ПОСЛЕДНЯЯ реплика сессии (лимит {max_replies} "
            "реплик будет достигнут сразу после неё, дальше уже никто не "
            "ответит). Обязательно выбери участника, который лучше всего "
            "подведёт общий итог всего обсуждения, поставь task на "
            "подведение итога и wrap_up=true."
        ),
        "moderator_progress_note": "Прогресс: {done} из {max_replies} реплик участников уже прозвучало.",
        "moderator_system_prompt_prefix": (
            "Ты — скрытый ведущий группового ИИ-брейншторма. Сам в "
            "обсуждении не участвуешь. После каждой реплики решаешь: КТО "
            "говорит следующим, ЧТО именно ему нужно сделать, ЗАЧЕМ "
            "(какую пользу это принесёт дискуссии прямо сейчас), КАКОЙ "
            "ТИП РЕАКЦИИ нужен (например: критика, поддержка идеи, новая "
            "идея, синтез, уточняющий вопрос, итог) — и не пора ли уже "
            "завершать обсуждение подведением итога. Не давай одному "
            "участнику говорить слишком много раз подряд без причины."
        ),
        # ВАЖНО: этот кусок добавляется в промпт ТОЛЬКО когда участие
        # пользователя реально разрешено (allow_user=True) — если просто
        # писать "если в списке есть user" безусловно, слабые модели
        # (например gpt-4o-mini) иногда всё равно выбирают user по
        # инерции, даже когда его физически нет в списке участников.
        "moderator_system_prompt_user_clause": (
            " Если в списке участников ниже есть \"user\", периодически "
            "передавай слово и ему тоже, а не только ИИ-моделям."
        ),
        "moderator_system_prompt_suffix": (
            " Используй ТОЛЬКО id из списка участников ниже, дословно. "
            "Отвечай СТРОГО в формате JSON без каких-либо пояснений вне "
            "него: {\"next\": \"<id участника или user>\", \"task\": "
            "\"<короткая инструкция участнику>\", \"reason\": \"<зачем "
            "именно сейчас>\", \"reaction_type\": \"<тип реакции>\", "
            "\"wrap_up\": true или false}"
        ),
        "moderator_user_prompt": (
            "Тема обсуждения: {topic}\n\n"
            "{progress_note}\n\n"
            "Участники:\n{participants_desc}\n\n"
            "История обсуждения:\n{transcript}\n\n"
            "Кто и зачем должен высказаться следующим?"
        ),
        "log_moderator_unrecognized": "Ведущий вернул нераспознаваемый ответ: {content!r} — включаю запасной выбор",
        "log_moderator_decision": "Ведущий выбрал {id}: task={task!r} reason={reason!r}",
        "key_limit_not_set": "лимит на ключ не задан (смотрите общий баланс на openrouter.ai)",
        "key_limit_set": "лимит ключа ${limit}, остаток ${remaining}",
        "key_balance_text": "Потрачено всего с ключа: {usage}  •  {limit_text}",

        "budget_block_title": "Бюджет",
        "session_budget_label": "Лимит расходов на одну сессию, $:",
        "session_budget_hint": (
            "— если суммарная стоимость реплик (включая вызовы ведущего) "
            "превысит лимит, обсуждение остановится автоматически."
        ),

        "moderator_block_title": "Ведущий и участие",
        "moderator_label": "Ведущий:",
        "moderator_mode_ai": "ИИ (автоматически)",
        "moderator_mode_human": "Человек (я сам выбираю каждый раз)",
        "moderator_model_label": "Модель ведущего (если ИИ):",
        "participation_checkbox": "Участвовать в беседе (ведущий сможет приглашать меня высказаться по своему усмотрению)",
        "moderator_summary_checkbox": "Ведущий подводит итоги (отдельным сообщением после завершения сессии)",
        "moderator_block_hint": (
            "ИИ-ведущий скрыт из диалога и после каждой реплики решает, кто "
            "говорит следующим — это отдельный вызов модели, поэтому по "
            "умолчанию стоит самая дешёвая. Человек-ведущий — управление "
            "полностью у вас, без лишних затрат на оркестрацию; там же на "
            "вкладке «Чат» при каждом выборе оратора можно оставить "
            "комментарий или сразу завершить сессию. При ИИ-ведущем для "
            "этого служит отдельная кнопка «Вмешаться». Итог сессии (если "
            "включён) считается моделью ведущего в любом режиме и тоже "
            "расходует бюджет."
        ),

        "standard_models_title": "Стандартные модели (до {max}, выбор конкретной модели внутри семейства)",
        "reasoning_intro_hint": (
            "Уровень рассуждений — необязательный бюджет токенов на скрытое "
            "размышление модели перед видимым ответом. По умолчанию "
            "выключено: для большинства тем брейншторма заметной пользы не "
            "даёт, а счёт может ощутимо вырасти. Не все модели поддерживают "
            "рассуждения — тогда настройка просто не даст эффекта. Подробнее:"
        ),
        "reasoning_budget_hint": (
            "Ориентир по бюджету токенов на рассуждение: Низкий — до 1024 "
            "(+20–40% к цене реплики), Средний — до 4096 (реплика может "
            "подорожать в 2–3 раза), Высокий — до 16000 (существенный "
            "расход, разумно включать точечно одному участнику, а не всем "
            "сразу)."
        ),

        "refreshing_models_ellipsis": "Обновляю список моделей…",
        "log_refresh_models_requested": "Запрошено обновление списка моделей по семействам",
        "log_refresh_models_failed": "Не удалось обновить список моделей: {error}",
        "refresh_error": "Ошибка обновления: {error}",
        "models_updated_status": "обновлено: {timestamp} ({counts}, всего моделей: {total})",
        "log_models_updated": "Список моделей обновлён: {counts} (всего {total})",

        "custom_models_title": "Дополнительные модели (до {max}, свои)",
        "custom_models_info": (
            "ℹ Сюда можно добавить любую другую модель с OpenRouter — "
            "например, DeepSeek или что угодно ещё из полного каталога. "
            "Укажите точный ID модели (формат «провайдер/название», "
            "например deepseek/deepseek-v4-flash-0731). Полный список "
            "моделей с ID:"
        ),
        "custom_slot_enable": "Слот {n}: включить",
        "model_id_label": "ID модели:",
        "name_label": "Название:",
        "persona_label": "Персонаж:",

        "custom_slot_missing_id": (
            "Слот дополнительной модели №{n} включён, но не указан ID "
            "модели. Укажите ID или снимите галочку «включить»."
        ),
        "custom_slot_duplicate_id": (
            "Модель с ID «{id}» уже выбрана (повтор в слоте №{n}). Уберите дубликат."
        ),
        "min_models_warning": "Выберите минимум {min} моделей для брейншторма.",
        "max_models_warning": "Максимум {max} моделей одновременно — иначе сессия станет слишком дорогой и долгой.",
        "invalid_budget_warning": "Лимит бюджета должен быть положительным числом, например 0.5",

        "status_moderator_summarizing": "Ведущий подводит итоги обсуждения…",
        "moderator_summary_label": "Итоги от ведущего ({model})",
        "moderator_summary_system_prompt": (
            "Ты — ведущий группового брейншторма. Обсуждение завершено. "
            "Составь краткий тезисный итог: ключевые идеи, точки согласия и "
            "разногласий, и если уместно — общий вывод. Формат — маркированный "
            "список, без вступлений и лишних слов."
        ),
        "moderator_summary_user_prompt": "Тема: {topic}\n\nПолная история обсуждения:\n{transcript}",
    },
    "en": {
        "app_title": "AI Brainstorm",

        "reasoning_off": "Off",
        "reasoning_low": "Low",
        "reasoning_medium": "Medium",
        "reasoning_high": "High",
        "reasoning_label": "Reasoning:",

        "cost_line": "(reply cost: ${cost})",
        "cost_line_with_moderator": "(reply cost: ${cost} + moderator ${mod} = ${total})",
        "cost_line_summary": "(summary cost: ${cost})",

        "show_log_tab_checkbox": "Show the \"Log\" tab (technical information about how the app is running)",
        "saved_confirmation": "Saved ✓",
        "tab_log": "Log",

        "copy_all_button": "Copy All",
        "clear_button": "Clear",

        "profile_block_title": "Settings Profile",
        "active_profile_label": "Active profile:",
        "save_as_button": "Save As…",
        "delete_button": "Delete",
        "save_settings_button": "Save Settings",
        "open_settings_folder_button": "Open Settings Folder",
        "profile_block_hint": (
            "Each profile stores its OWN API key and all settings "
            "separately — handy if you have several OpenRouter accounts "
            "or different participant sets for different occasions. A "
            "profile is applied as soon as you pick it from the list. "
            "The \"Save Settings\" button on the right writes all form "
            "edits below into the currently active profile."
        ),
        "new_profile_name_prompt": "New profile name:",
        "profile_exists_overwrite": "Profile \"{name}\" already exists. Overwrite?",
        "profile_saved_and_active": "Saved as profile \"{name}\" and made it active.",
        "cannot_delete_last_profile": "Can't delete the last remaining profile.",
        "confirm_delete_profile": "Permanently delete profile \"{name}\"?",
        "open_folder_failed": "Could not open the folder automatically: {error}\n\nPath: {path}",

        "log_profile_loaded": "Loaded profile: {name}",
        "log_profile_saved_new": "Saved new profile: {name}",
        "log_profile_deleted": "Deleted profile: {name}",
        "log_settings_folder_opened": "Opened settings folder: {path}",
        "log_settings_folder_error": "Could not open settings folder: {error}",

        "api_key_block_title": "OpenRouter API Key",
        "show_checkbox": "show",
        "check_balance_button": "Check Key Balance",
        "refresh_models_button": "Refresh Model List",
        "refresh_models_hint": (
            "Refreshing the model list updates the standard model "
            "families, the moderator model, and\nthe suggestions for "
            "additional (custom) models below — one click for everything."
        ),
        "enter_api_key_first": "Enter your API key first.",
        "checking_ellipsis": "Checking…",
        "error_prefix": "Error: {error}",
        "not_available_abbr": "n/a",
        "cache_never_updated": "list not refreshed yet — only default models available",
        "cache_updated_at": "updated: {timestamp}",

        "topic_label": "Discussion topic:",
        "max_replies_label": "Max replies:",
        "start_brainstorm_button": "Start Brainstorm",
        "intervene_button": "Intervene",
        "export_button": "Export…",

        "final_reply_choose_speaker": "Last reply of the session — pick who should sum up the whole discussion:",
        "your_turn_choose_speaker": "Your turn as moderator: who speaks next?",
        "optional_comment_hint": "The optional comment above will be added to the chat under your name, right before the chosen reply.",
        "speak_myself_button": "I'll speak",
        "end_discussion_button": "End Discussion",
        "moderator_passed_you_the_floor": "The moderator passed the floor to you — type a reply or skip:",
        "send_button": "Send",
        "skip_button": "Skip",
        "intervene_hint": "Intervention: add a note for the participants, or end the session right now.",
        "continue_with_note_button": "Continue with a Note",
        "end_session_button": "End Session",

        "export_log_empty": "The discussion log is empty — nothing to export.",
        "markdown_filetype": "Markdown",
        "text_filetype": "Text file",
        "all_files_filetype": "All files",
        "export_dialog_title": "Save Discussion Log",
        "save_file_failed": "Could not save the file: {error}",
        "log_export_done": "Discussion log exported to {path}",
        "exported_to": "Exported to {path}",
        "log_copied_to_clipboard": "Entire log copied to the clipboard.",
        "intervene_pending_status": "Intervention requested — will kick in after the current reply…",
        "log_intervene_requested": "User requested to intervene",

        "set_api_key_first": "Set your API key on the Settings tab first.",
        "select_min_models_in_settings": "On the Settings tab, select at least {min} models.",
        "enter_topic_warning": "Enter a discussion topic.",
        "user_topic_label": "User (topic)",
        "spent_status": "Spent: {spent} of ${budget}",
        "discussion_in_progress": "Discussion in progress…",
        "log_session_started": (
            "Session started: topic={topic!r}, participants={count}, moderator={mode}, "
            "max replies={max_replies}, budget=${budget}, summary={summary}"
        ),
        "error_speaker_suffix": "{label} (error)",
        "system_label": "System",
        "discussion_finished": "Discussion finished.",

        "budget_limit_reached": "Session budget limit reached (${budget}).",
        "reply_limit_reached": "Reply limit reached ({max_replies}).",
        "session_ended_by_user": "Session ended by the user.",
        "safety_loop_limit_reached": (
            "Session stopped by a safety limit (too many turns without "
            "reply-limit progress) — please report this if you see it "
            "during a normal session."
        ),
        "user_clarification_transcript": "User (clarification): {text}",
        "user_label": "User",
        "discussion_just_starting": "(the discussion is just getting started)",
        "final_reply_status_human": "Last reply of the session — pick who should sum things up…",
        "your_turn_status_human": "Your turn as moderator — pick a participant…",
        "user_comment_transcript": "User (comment): {comment}",
        "final_summary_task": "Sum up the whole discussion in one closing reply.",
        "moderator_choosing_status": "The moderator is picking the next participant…",
        "log_moderator_error": "Error calling the moderator: {error}",
        "log_moderator_fallback": "Moderator gave no valid answer, falling back to: {id}",
        "moderator_passed_floor_status": "The moderator passed the floor to you…",
        "user_reply_transcript": "User: {reply}",
        "log_unknown_model_chosen": "Moderator picked an unknown model {id} — skipping this turn",
        "model_preparing_status": "{label} is preparing a reply…",
        "moderator_task_guidance": "\nTask from the moderator: {task}",
        "moderator_reaction_guidance": "\nExpected type of reaction: {reaction_type}",
        "wrap_up_guidance": "\nThe discussion is wrapping up — give more of a summarizing, closing reply.",
        "participant_user_prompt": (
            "Discussion topic: {topic}\n\n"
            "Discussion history:\n{transcript}\n"
            "{guidance}\n\n"
            "Give your reply on the topic — to the point, 3-5 sentences, "
            "make sure to finish the thought within that length (better "
            "shorter but complete than cut off mid-sentence)."
        ),
        "log_model_unavailable": "Model {id} temporarily unavailable: {error}",
        "transcript_skipped_unavailable": "{label}: (skipped — temporarily unavailable)",
        "transcript_reply_line": "{label}: {reply}",
        "log_summary_failed": "Could not get the moderator's summary: {error}",
        "unknown_cost_note": (
            " (for {count} replies the provider didn't return an exact "
            "cost — actual spend may have been a bit higher)"
        ),
        "log_session_finished": "Session finished: {reason} Total spent: ${total}",

        "tab_settings": "Settings",
        "tab_chat": "Chat",
        "language_label": "Interface language:",
        "log_language_fallback": (
            "Saved language \"{saved}\" not found among available ones — "
            "switched to \"{applied}\""
        ),
        "log_language_switched": "Language switched to: {code}",

        "log_http_error": "HTTPError {code} calling {url}: {message}",
        "api_error": "API error ({code}): {message}",
        "network_error": "Network error: {reason}",
        "log_url_error": "URLError calling {url}: {reason}",
        "no_api_key_error": "No OpenRouter API key set. Add it in Settings.",
        "no_api_key_short_error": "No OpenRouter API key set.",
        "log_model_request": "Requesting model {model} (max_tokens={max_tokens})",
        "parse_error": "Could not parse the model's response: {error}\nServer response: {result}",
        "log_model_truncated": "Model {model}: reply cut off by max_tokens={max_tokens}",
        "truncated_note": "\n\n[…reply cut off by length limit]",
        "log_model_response": "Reply from {model}: {tokens} tokens, cost={cost}",

        "moderator_user_entry": (
            "\n- user: User — a real human, also part of the discussion; "
            "occasionally pass them the floor too, not only AI participants."
        ),
        "moderator_final_reply_note": (
            "NOTE: this is the LAST reply of the session (the {max_replies} "
            "reply limit will be reached right after it, no one will "
            "answer after that). Be sure to pick the participant best "
            "suited to sum up the whole discussion, set task to a "
            "wrap-up, and set wrap_up=true."
        ),
        "moderator_progress_note": "Progress: {done} of {max_replies} participant replies so far.",
        "moderator_system_prompt_prefix": (
            "You are the hidden moderator of a group AI brainstorm. You "
            "don't participate in the discussion yourself. After every "
            "reply, decide: WHO speaks next, WHAT exactly they should do, "
            "WHY (what value that adds to the discussion right now), what "
            "TYPE OF REACTION is needed (e.g.: critique, support an idea, "
            "new idea, synthesis, clarifying question, wrap-up) — and "
            "whether it's time to close the discussion with a summary. "
            "Don't let one participant speak too many times in a row without reason."
        ),
        # IMPORTANT: only appended when user participation is actually
        # allowed (allow_user=True) — an unconditional "if user is in the
        # list" phrasing can still make weaker models (e.g. gpt-4o-mini)
        # pick "user" out of habit even when it's not actually in the list.
        "moderator_system_prompt_user_clause": (
            " If \"user\" is in the participant list below, periodically "
            "pass the floor to them too, not just AI models."
        ),
        "moderator_system_prompt_suffix": (
            " Use ONLY ids from the participant list below, verbatim. "
            "Reply STRICTLY in JSON with no commentary outside it: "
            "{\"next\": \"<participant id or user>\", \"task\": \"<short "
            "instruction for the participant>\", \"reason\": \"<why right "
            "now>\", \"reaction_type\": \"<reaction type>\", \"wrap_up\": true or false}"
        ),
        "moderator_user_prompt": (
            "Discussion topic: {topic}\n\n"
            "{progress_note}\n\n"
            "Participants:\n{participants_desc}\n\n"
            "Discussion history:\n{transcript}\n\n"
            "Who should speak next, and why?"
        ),
        "log_moderator_unrecognized": "Moderator returned an unrecognizable reply: {content!r} — using a fallback pick",
        "log_moderator_decision": "Moderator picked {id}: task={task!r} reason={reason!r}",
        "key_limit_not_set": "no limit set on this key (see your overall balance at openrouter.ai)",
        "key_limit_set": "key limit ${limit}, remaining ${remaining}",
        "key_balance_text": "Total spent with this key: {usage}  •  {limit_text}",

        "budget_block_title": "Budget",
        "session_budget_label": "Spending limit per session, $:",
        "session_budget_hint": (
            "— if the total cost of replies (including moderator calls) "
            "exceeds the limit, the discussion stops automatically."
        ),

        "moderator_block_title": "Moderator & Participation",
        "moderator_label": "Moderator:",
        "moderator_mode_ai": "AI (automatic)",
        "moderator_mode_human": "Human (I pick every time)",
        "moderator_model_label": "Moderator model (if AI):",
        "participation_checkbox": "Participate in the discussion (the moderator can invite me to speak at its discretion)",
        "moderator_summary_checkbox": "Moderator writes a summary (a separate message after the session ends)",
        "moderator_block_hint": (
            "The AI moderator is hidden from the chat and decides who "
            "speaks next after every reply — that's an extra model call, "
            "so it defaults to the cheapest one. Human moderator — you're "
            "fully in control, no extra orchestration cost; on the Chat "
            "tab, each time you pick a speaker you can also leave a "
            "comment or end the session right there. With the AI "
            "moderator, a separate \"Intervene\" button does that. The "
            "session summary (if enabled) is generated by the moderator "
            "model in either mode and also draws on the budget."
        ),

        "standard_models_title": "Standard Models (up to {max}, pick a specific model within the family)",
        "reasoning_intro_hint": (
            "Reasoning level — an optional token budget for the model's "
            "hidden thinking before the visible reply. Off by default: "
            "rarely helps for a casual brainstorm and can noticeably "
            "inflate the bill. Not every model supports reasoning — the "
            "setting then simply has no effect. More:"
        ),
        "reasoning_budget_hint": (
            "Rough token budgets per level: Low — up to 1024 (+20–40% to "
            "reply cost), Medium — up to 4096 (reply may cost 2–3x more), "
            "High — up to 16000 (substantial cost, best used sparingly on "
            "one participant rather than everyone at once)."
        ),

        "refreshing_models_ellipsis": "Refreshing model list…",
        "log_refresh_models_requested": "Model list refresh requested",
        "log_refresh_models_failed": "Could not refresh model list: {error}",
        "refresh_error": "Refresh error: {error}",
        "models_updated_status": "updated: {timestamp} ({counts}, {total} models total)",
        "log_models_updated": "Model list updated: {counts} ({total} total)",

        "custom_models_title": "Additional Models (up to {max}, your own)",
        "custom_models_info": (
            "ℹ Add any other OpenRouter model here — DeepSeek, or "
            "anything else from the full catalog. Enter the exact model "
            "ID (format \"provider/name\", e.g. "
            "deepseek/deepseek-v4-flash-0731). Full model list with IDs:"
        ),
        "custom_slot_enable": "Slot {n}: enable",
        "model_id_label": "Model ID:",
        "name_label": "Name:",
        "persona_label": "Persona:",

        "custom_slot_missing_id": (
            "Custom model slot #{n} is enabled, but no model ID is set. "
            "Enter an ID or uncheck \"enable\"."
        ),
        "custom_slot_duplicate_id": (
            "Model \"{id}\" is already selected (duplicate in slot #{n}). Remove the duplicate."
        ),
        "min_models_warning": "Select at least {min} models for the brainstorm.",
        "max_models_warning": "Maximum {max} models at once — otherwise the session gets too expensive and slow.",
        "invalid_budget_warning": "The budget limit must be a positive number, e.g. 0.5",

        "status_moderator_summarizing": "The moderator is summarizing the discussion…",
        "moderator_summary_label": "Moderator's summary ({model})",
        "moderator_summary_system_prompt": (
            "You are the moderator of a group brainstorm. The discussion is "
            "over. Write a concise, bullet-point summary: key ideas, points "
            "of agreement and disagreement, and an overall takeaway if one "
            "makes sense. Bullet-list format, no preamble, no filler."
        ),
        "moderator_summary_user_prompt": "Topic: {topic}\n\nFull discussion history:\n{transcript}",
    },
}
