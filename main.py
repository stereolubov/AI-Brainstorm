# -*- coding: utf-8 -*-
"""
AI Brainstorm — десктопное приложение для группового брейншторма
с несколькими AI-моделями через OpenRouter.

Запуск:  python main.py
Сборка в exe:  pyinstaller --onefile --windowed --name AIBrainstorm main.py

Используется только стандартная библиотека Python — никаких pip install.
"""

import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog

from config import (
    load_config, save_config, save_profile, delete_profile,
    list_profiles, get_active_profile_name, switch_active_profile, PROFILES_DIR,
)
from models_catalog import (
    FAMILIES, MODERATOR_DEFAULT_MODEL, REASONING_LEVEL_NAMES, DEFAULT_REASONING_LEVEL,
    build_full_catalog, find_in_catalog, find_family, short_model_name,
)
from api_client import ask_model, ask_moderator, get_key_info, build_family_options, OpenRouterError

# Поставьте False перед сборкой в продакшен-exe — уберёт подробный лог
# в консоль (полезен только на этапе разработки). Это НЕЗАВИСИМО от
# вкладки "Лог" в самом приложении (см. QueueLogHandler ниже) — та
# включается/выключается пользователем в настройках, без правки кода.
DEBUG = True

logger = logging.getLogger("ai_brainstorm")
logger.setLevel(logging.DEBUG)  # логгер генерирует всё; что из этого реально
                                 # показывается — решает уровень КАЖДОГО обработчика
logger.propagate = False  # не дублировать через root-логгер

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG if DEBUG else logging.WARNING)
_console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_console_handler)


class QueueLogHandler(logging.Handler):
    """Прокидывает записи логов в очередь Tk-виджета вкладки "Лог" —
    тот же паттерн потокобезопасной передачи, что и для чата (worker
    может логировать из фонового потока, GUI обновляется через after()).
    Уровень всегда DEBUG независимо от консольного DEBUG-флага выше —
    вкладку явно включает пользователь в настройках, когда она нужна."""

    def __init__(self, ui_queue):
        super().__init__(level=logging.DEBUG)
        self.ui_queue = ui_queue
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    def emit(self, record):
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self.ui_queue.put(("log", message, record.levelname, None))


APP_TITLE = "AI Brainstorm"
MIN_MODELS = 2
MAX_STANDARD_MODELS = 5
MAX_CUSTOM_MODELS = 3
MAX_MODELS = MAX_STANDARD_MODELS + MAX_CUSTOM_MODELS  # = 8
OPENROUTER_MODELS_URL = "https://openrouter.ai/models"
OPENROUTER_REASONING_DOCS_URL = "https://openrouter.ai/docs/use-cases/reasoning-tokens"

CODE_FENCE_RE = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
MD_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|`([^`\n]+)`")



def _sorted_with_current(values, current):
    """Сортирует список значений по алфавиту, гарантируя, что текущее
    выбранное значение тоже присутствует в списке (даже если кэш ещё не
    содержит его — например, сразу после ручного ввода)."""
    pool = set(values or [])
    if current:
        pool.add(current)
    return sorted(pool)


def _make_link_label(parent, text, url):
    """Кликабельная 'ссылка' на базе tk.Label — открывает URL в браузере
    по умолчанию через модуль webbrowser."""
    link = tk.Label(
        parent, text=text, fg="#1565c0", cursor="hand2",
        font=("Segoe UI", 9, "underline"),
    )
    link.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return link


def _open_folder(path):
    """Открывает папку в системном файловом менеджере (Проводник на
    Windows, Finder на macOS, обычно Nautilus/Dolphin/... на Linux).
    Создаёт папку, если её ещё нет (например, до первого сохранения
    профиля вручную)."""
    os.makedirs(path, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: доступно только на Windows, платформа проверена выше
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _resource_path(relative_path):
    """Резолвит путь к файлу-ресурсу (иконка и т.п.) так, чтобы работало
    и при обычном запуске `python main.py`, и внутри exe, собранного
    через `pyinstaller --onefile` — там все файлы распаковываются во
    временную папку sys._MEIPASS, а не лежат рядом со скриптом."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class ScrollableFrame(ttk.Frame):
    """Прокручиваемый контейнер (вертикально и горизонтально) для вкладки
    настроек — контента там больше, чем помещается на экране FullHD без
    скролла, особенно после разворачивания блоков моделей."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        hscroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)

        self.inner = ttk.Frame(self.canvas, padding=12)
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _bind_mousewheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)

    def _unbind_mousewheel(self, _event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Shift-MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")


class LogTab(ttk.Frame):
    """Вкладка технического лога — то же самое, что раньше было видно
    только в консоли. Включается/выключается настройкой в SettingsTab,
    полезно для диагностики без необходимости запускать программу из
    терминала."""

    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.ui_queue = queue.Queue()

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text="Копировать всё", command=self._copy_all).pack(side="left")
        ttk.Button(btn_row, text="Очистить", command=self._clear).pack(side="left", padx=(6, 0))

        self.log_text = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("ERROR", foreground="#c62828")
        self.log_text.tag_config("WARNING", foreground="#e65100")
        self.log_text.bind("<Control-c>", self._copy_selection)
        self.log_text.bind("<Control-a>", self._select_all)

        self._poll_queue()

    def _copy_selection(self, _event=None):
        self.log_text.event_generate("<<Copy>>")
        return "break"

    def _select_all(self, _event=None):
        self.log_text.tag_add("sel", "1.0", "end")
        return "break"

    def _copy_all(self):
        content = self.log_text.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(content)

    def _clear(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _append(self, message, level):
        self.log_text.config(state="normal")
        tag = level if level in ("ERROR", "WARNING") else None
        if tag:
            self.log_text.insert("end", message + "\n", (tag,))
        else:
            self.log_text.insert("end", message + "\n")
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def _poll_queue(self):
        try:
            while True:
                kind, message, level, _unused = self.ui_queue.get_nowait()
                if kind == "log":
                    self._append(message, level)
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)


class SettingsTab(ttk.Frame):
    """Вкладка настроек: профиль, ключ, бюджет, ведущий, семейства моделей, кастомные модели."""

    def __init__(self, parent, config, on_saved, on_profile_switched):
        super().__init__(parent)
        self.config_data = config
        self.on_saved = on_saved
        self.on_profile_switched = on_profile_switched

        self.family_vars = {}          # key -> BooleanVar
        self.family_combo_vars = {}    # key -> StringVar (выбранная конкретная модель)
        self.family_combos = {}        # key -> ttk.Combobox (чтобы обновлять values)
        self.persona_texts = {}        # key -> Text widget
        self.reasoning_vars = {}       # key -> StringVar (уровень рассуждений семейства)
        self.custom_slots = []         # список словарей виджетов для 3 кастомных слотов

        scrollable = ScrollableFrame(self)
        scrollable.pack(fill="both", expand=True)
        self.content = scrollable.inner
        self.canvas = scrollable.canvas  # нужен, чтобы колесо мыши над Combobox/Spinbox
                                          # прокручивало окно, а не меняло значение виджета

        self._build_profile_block()
        self._build_api_key_block()
        self._build_budget_block()
        self._build_moderator_block()
        self._build_models_block()
        self._build_custom_models_block()

    def _protect_from_wheel(self, widget):
        """Не даёт колесу мыши менять значение Combobox/Spinbox, если
        курсор просто оказался над виджетом во время прокрутки окна —
        частый и неприятный способ незаметно для себя сменить модель
        или уровень рассуждений. Вместо изменения значения колесо
        прокручивает саму страницу настроек, как и ожидается."""

        def on_wheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def on_button4(_event):
            self.canvas.yview_scroll(-1, "units")
            return "break"

        def on_button5(_event):
            self.canvas.yview_scroll(1, "units")
            return "break"

        widget.bind("<MouseWheel>", on_wheel)   # Windows/macOS
        widget.bind("<Button-4>", on_button4)   # Linux, прокрутка вверх
        widget.bind("<Button-5>", on_button5)   # Linux, прокрутка вниз

    # ---------- Профили ----------

    def _build_profile_block(self):
        frame = ttk.LabelFrame(self.content, text="Профиль настроек", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        ttk.Label(row, text="Активный профиль:").pack(side="left")
        self.profile_var = tk.StringVar(value=get_active_profile_name())
        self.profile_combo = ttk.Combobox(
            row, textvariable=self.profile_var, values=sorted(list_profiles()),
            width=26, state="readonly",
        )
        self.profile_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(self.profile_combo)

        ttk.Button(row, text="Загрузить", command=self._load_selected_profile).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(row, text="Сохранить как…", command=self._save_as_new_profile).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(row, text="Удалить", command=self._delete_selected_profile).pack(
            side="left", padx=(6, 0)
        )
        ttk.Separator(row, orient="vertical").pack(side="left", fill="y", padx=(12, 12))
        ttk.Button(row, text="Сохранить настройки", command=self._save).pack(side="left")

        second_row = ttk.Frame(frame)
        second_row.pack(fill="x", pady=(6, 0))
        ttk.Button(
            second_row, text="Открыть папку с профилями", command=self._open_profiles_folder
        ).pack(side="left")
        ttk.Label(
            second_row, text=f"({PROFILES_DIR})", foreground="#888888",
            wraplength=800, justify="left",
        ).pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(frame, text="", foreground="#2e7d32")
        self.status_label.pack(anchor="w", pady=(4, 0))

        self.debug_tab_var = tk.BooleanVar(
            value=self.config_data.get("debug_tab_enabled", False)
        )
        ttk.Checkbutton(
            frame,
            text="Показывать вкладку «Лог» (техническая информация о работе "
                 "программы — то же самое, что раньше было видно только в консоли)",
            variable=self.debug_tab_var,
        ).pack(anchor="w", pady=(6, 0))

        ttk.Label(
            frame,
            text="Каждый профиль хранит СВОЙ API-ключ и все настройки отдельно — "
                 "удобно, если у вас несколько аккаунтов OpenRouter или разные наборы "
                 "участников под разные случаи. Кнопка «Сохранить настройки» справа "
                 "пишет все правки формы ниже в текущий активный профиль.",
            foreground="#555555", wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _load_selected_profile(self):
        name = self.profile_var.get()
        if name == get_active_profile_name():
            messagebox.showinfo(APP_TITLE, f"Профиль «{name}» уже активен.")
            return
        loaded = load_config(profile_name=name)
        switch_active_profile(name)
        self.config_data.clear()
        self.config_data.update(loaded)
        logger.info("Загружен профиль: %s", name)
        self.on_profile_switched()

    def _save_as_new_profile(self):
        data = self._collect_form()
        if data is None:
            return  # форма невалидна — сообщение уже показано внутри

        name = simpledialog.askstring(
            APP_TITLE, "Название нового профиля:", parent=self
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in list_profiles():
            if not messagebox.askyesno(
                APP_TITLE, f"Профиль «{name}» уже существует. Перезаписать?"
            ):
                return

        # ВАЖНО: старый активный профиль на диске не трогаем вообще —
        # значения формы применяются только к self.config_data в памяти
        # и уходят исключительно в НОВЫЙ файл профиля.
        self.config_data.update(data)
        save_profile(name, self.config_data)
        switch_active_profile(name)
        self.profile_combo["values"] = sorted(list_profiles())
        self.profile_var.set(name)
        logger.info("Сохранён новый профиль: %s", name)
        messagebox.showinfo(APP_TITLE, f"Сохранено как профиль «{name}» и сделано активным.")

    def _open_profiles_folder(self):
        try:
            _open_folder(PROFILES_DIR)
            logger.info("Открыта папка профилей: %s", PROFILES_DIR)
        except Exception as e:
            logger.error("Не удалось открыть папку профилей: %s", e)
            messagebox.showerror(
                APP_TITLE,
                f"Не удалось открыть папку автоматически: {e}\n\nПуть: {PROFILES_DIR}",
            )

    def _delete_selected_profile(self):
        name = self.profile_var.get()
        if len(list_profiles()) <= 1:
            messagebox.showwarning(APP_TITLE, "Нельзя удалить последний оставшийся профиль.")
            return
        if not messagebox.askyesno(
            APP_TITLE, f"Удалить профиль «{name}» без возможности восстановления?"
        ):
            return

        was_active = (name == get_active_profile_name())
        delete_profile(name)
        remaining = sorted(list_profiles())
        self.profile_combo["values"] = remaining
        logger.info("Удалён профиль: %s", name)

        if was_active:
            new_name = remaining[0]
            loaded = load_config(profile_name=new_name)
            switch_active_profile(new_name)
            self.config_data.clear()
            self.config_data.update(loaded)
            self.profile_var.set(new_name)
            self.on_profile_switched()
        else:
            self.profile_var.set(get_active_profile_name())

    # ---------- API-ключ ----------

    def _build_api_key_block(self):
        frame = ttk.LabelFrame(self.content, text="API-ключ OpenRouter", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        self.api_key_var = tk.StringVar(value=self.config_data.get("api_key", ""))
        self.show_key_var = tk.BooleanVar(value=False)

        entry = ttk.Entry(frame, textvariable=self.api_key_var, width=50, show="*")
        entry.pack(side="left", fill="x", expand=True)

        def toggle_show():
            entry.config(show="" if self.show_key_var.get() else "*")

        ttk.Checkbutton(
            frame, text="показать", variable=self.show_key_var, command=toggle_show
        ).pack(side="left", padx=(8, 0))

        buttons_row = ttk.Frame(frame)
        buttons_row.pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons_row, text="Проверить баланс ключа", command=self._check_key_balance
        ).pack(side="left")
        ttk.Button(
            buttons_row, text="Обновить список моделей", command=self._refresh_family_options
        ).pack(side="left", padx=(10, 0))

        self.balance_label = ttk.Label(
            frame, text="", foreground="#555555", wraplength=1000, justify="left"
        )
        self.balance_label.pack(anchor="w", pady=(6, 0))

        self.refresh_status_label = ttk.Label(
            frame, text=self._cache_status_text(), foreground="#555555",
            wraplength=1000, justify="left",
        )
        self.refresh_status_label.pack(anchor="w", pady=(2, 0))
        ttk.Label(
            frame,
            text="Обновление списка моделей затрагивает сразу семейства стандартных "
                 "моделей, модель ведущего и\nподсказки для дополнительных (кастомных) "
                 "моделей ниже — один клик на всё.",
            foreground="#555555", wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(4, 0))

    def _check_key_balance(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning(APP_TITLE, "Сначала введите API-ключ.")
            return
        self.balance_label.config(text="Проверяю…")

        def worker():
            try:
                info = get_key_info(api_key)
            except OpenRouterError as e:
                self.after(0, lambda: self.balance_label.config(
                    text=f"Ошибка: {e}", foreground="#c62828"
                ))
                return

            usage = info.get("usage")
            limit = info.get("limit")
            remaining = info.get("limit_remaining")

            usage_text = f"${usage:.4f}" if isinstance(usage, (int, float)) else "н/д"
            if limit is None:
                limit_text = "лимит на ключ не задан (смотрите общий баланс на openrouter.ai)"
            else:
                limit_text = f"лимит ключа ${limit:.2f}, остаток ${remaining:.4f}"

            text = f"Потрачено всего с ключа: {usage_text}  •  {limit_text}"
            self.after(0, lambda: self.balance_label.config(text=text, foreground="#555555"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Бюджет ----------

    def _build_budget_block(self):
        frame = ttk.LabelFrame(self.content, text="Бюджет", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        ttk.Label(frame, text="Лимит расходов на одну сессию, $:").pack(side="left")
        self.budget_var = tk.StringVar(
            value=str(self.config_data.get("session_budget_usd", 0.5))
        )
        ttk.Entry(frame, textvariable=self.budget_var, width=8).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(
            frame,
            text="— если суммарная стоимость реплик (включая вызовы ведущего) "
                 "превысит лимит, обсуждение остановится автоматически.",
            foreground="#555555",
            wraplength=420,
        ).pack(side="left", padx=(10, 0))

    # ---------- Ведущий и участие ----------

    def _build_moderator_block(self):
        frame = ttk.LabelFrame(self.content, text="Ведущий и участие", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        self.moderator_mode_var = tk.StringVar(
            value=self.config_data.get("moderator_mode", "ai")
        )
        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text="Ведущий:").pack(side="left")
        ttk.Radiobutton(
            mode_row, text="ИИ (автоматически)", variable=self.moderator_mode_var, value="ai"
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            mode_row, text="Человек (я сам выбираю каждый раз)",
            variable=self.moderator_mode_var, value="human",
        ).pack(side="left", padx=(8, 0))

        model_row = ttk.Frame(frame)
        model_row.pack(fill="x", pady=(8, 0))
        ttk.Label(model_row, text="Модель ведущего (если ИИ):").pack(side="left")
        self.moderator_model_var = tk.StringVar(
            value=self.config_data.get("moderator_model", MODERATOR_DEFAULT_MODEL)
        )
        moderator_options = self._all_known_model_ids()
        self.moderator_model_combo = ttk.Combobox(
            model_row, textvariable=self.moderator_model_var,
            values=moderator_options, width=40, state="readonly",
        )
        self.moderator_model_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(self.moderator_model_combo)

        self.participation_var = tk.BooleanVar(
            value=self.config_data.get("user_participation", False)
        )
        ttk.Checkbutton(
            frame,
            text="Участвовать в беседе (ведущий сможет приглашать меня высказаться "
                 "по своему усмотрению)",
            variable=self.participation_var,
        ).pack(anchor="w", pady=(8, 0))

        self.moderator_summary_var = tk.BooleanVar(
            value=self.config_data.get("moderator_summary", False)
        )
        ttk.Checkbutton(
            frame,
            text="Ведущий подводит итоги (отдельным сообщением после завершения сессии)",
            variable=self.moderator_summary_var,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(
            frame,
            text="ИИ-ведущий скрыт из диалога и после каждой реплики решает, кто "
                 "говорит следующим — это отдельный вызов модели, поэтому по умолчанию "
                 "стоит самая дешёвая. Человек-ведущий — управление полностью у вас, "
                 "без лишних затрат на оркестрацию; там же на вкладке «Чат» при каждом "
                 "выборе оратора можно оставить комментарий или сразу завершить сессию. "
                 "При ИИ-ведущем для этого служит отдельная кнопка «Вмешаться». Итог "
                 "сессии (если включён) считается моделью ведущего в любом режиме и "
                 "тоже расходует бюджет.",
            foreground="#555555", wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _all_known_model_ids(self):
        cache = self.config_data.get("family_options_cache", {}) or {}
        all_ids = {mid for ids in cache.values() for mid in ids}
        if not all_ids:
            all_ids = {MODERATOR_DEFAULT_MODEL}
        current = self.config_data.get("moderator_model", MODERATOR_DEFAULT_MODEL)
        return _sorted_with_current(all_ids, current)

    # ---------- Стандартные модели (семейства) ----------

    def _cache_status_text(self):
        ts = self.config_data.get("family_options_updated_at", "")
        return "список ещё не обновлялся из сети — доступны только модели по умолчанию" if not ts else f"обновлено: {ts}"

    def _build_models_block(self):
        frame = ttk.LabelFrame(
            self.content,
            text=f"Стандартные модели (до {MAX_STANDARD_MODELS}, выбор конкретной "
                 f"модели внутри семейства)",
            padding=10,
        )
        frame.pack(fill="both", expand=True, pady=(0, 10))

        ttk.Label(
            frame,
            text="Уровень рассуждений — необязательный бюджет токенов на скрытое "
                 "размышление модели перед видимым ответом. По умолчанию выключено: "
                 "для большинства тем брейншторма заметной пользы не даёт, а счёт "
                 "может ощутимо вырасти. Не все модели поддерживают рассуждения — "
                 "тогда настройка просто не даст эффекта. Подробнее:",
            foreground="#555555", wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(0, 2))
        _make_link_label(frame, OPENROUTER_REASONING_DOCS_URL, OPENROUTER_REASONING_DOCS_URL).pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text=(
                "Ориентир по бюджету токенов на рассуждение: Низкий — до 1024 "
                "(+20–40% к цене реплики), Средний — до 4096 (реплика может "
                "подорожать в 2–3 раза), Высокий — до 16000 (существенный расход, "
                "разумно включать точечно одному участнику, а не всем сразу)."
            ),
            foreground="#555555", wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        selected = set(self.config_data.get("selected_families", []))
        family_choice = self.config_data.get("family_model_choice", {})
        personas = self.config_data.get("personas", {})
        reasoning_levels = self.config_data.get("reasoning_levels", {})
        cache = self.config_data.get("family_options_cache", {})

        for fam in FAMILIES:
            key = fam["key"]
            block = ttk.Frame(frame, relief="groove", padding=8)
            block.pack(fill="x", pady=4)

            top_row = ttk.Frame(block)
            top_row.pack(fill="x")

            var = tk.BooleanVar(value=key in selected)
            self.family_vars[key] = var
            ttk.Checkbutton(top_row, text=fam["label"], variable=var, width=12).pack(
                side="left"
            )

            current = family_choice.get(key, fam["default_model"])
            options = _sorted_with_current(cache.get(key), current)
            combo_var = tk.StringVar(value=current)
            combo = ttk.Combobox(
                top_row, textvariable=combo_var, values=options, width=40, state="readonly"
            )
            combo.pack(side="left", padx=(10, 0))
            self._protect_from_wheel(combo)
            self.family_combo_vars[key] = combo_var
            self.family_combos[key] = combo

            bottom_row = ttk.Frame(block)
            bottom_row.pack(fill="x", pady=(6, 0))

            persona_value = personas.get(key, fam["default_persona"])
            text_widget = tk.Text(bottom_row, height=2, width=60, wrap="word")
            text_widget.insert("1.0", persona_value)
            text_widget.pack(side="left")
            self.persona_texts[key] = text_widget

            reasoning_frame = ttk.Frame(bottom_row)
            reasoning_frame.pack(side="left", padx=(12, 0), anchor="n")
            ttk.Label(reasoning_frame, text="Рассуждения:").pack(anchor="w")
            reasoning_var = tk.StringVar(
                value=reasoning_levels.get(key, DEFAULT_REASONING_LEVEL)
            )
            reasoning_combo = ttk.Combobox(
                reasoning_frame, textvariable=reasoning_var, values=REASONING_LEVEL_NAMES,
                width=12, state="readonly",
            )
            reasoning_combo.pack(anchor="w", pady=(2, 0))
            self._protect_from_wheel(reasoning_combo)
            self.reasoning_vars[key] = reasoning_var

    def _refresh_family_options(self):
        api_key = self.api_key_var.get().strip()
        self.refresh_status_label.config(text="Обновляю список моделей…")
        logger.info("Запрошено обновление списка моделей по семействам")

        def worker():
            try:
                options, all_ids = build_family_options(api_key or None)
            except OpenRouterError as e:
                logger.error("Не удалось обновить список моделей: %s", e)
                self.after(0, lambda: self.refresh_status_label.config(
                    text=f"Ошибка обновления: {e}", foreground="#c62828"
                ))
                return
            self.after(0, lambda: self._apply_family_options(options, all_ids))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_family_options(self, options, all_ids):
        self.config_data["family_options_cache"] = options
        self.config_data["all_model_ids_cache"] = all_ids
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.config_data["family_options_updated_at"] = timestamp
        save_config(self.config_data)

        for key, combo in self.family_combos.items():
            current = self.family_combo_vars[key].get()
            combo["values"] = _sorted_with_current(options.get(key), current)

        current_mod = self.moderator_model_var.get()
        self.moderator_model_combo["values"] = _sorted_with_current(all_ids, current_mod)

        sorted_all_ids = sorted(all_ids)
        for slot in self.custom_slots:
            current_id = slot["id_var"].get()
            slot["id_combo"]["values"] = _sorted_with_current(sorted_all_ids, current_id)

        counts = ", ".join(f"{find_family(k)['label']} {len(v)}" for k, v in options.items())
        self.refresh_status_label.config(
            text=f"обновлено: {timestamp} ({counts}, всего моделей: {len(all_ids)})",
            foreground="#2e7d32",
        )
        logger.info("Список моделей обновлён: %s (всего %d)", counts, len(all_ids))

    # ---------- Кастомные модели ----------

    def _build_custom_models_block(self):
        frame = ttk.LabelFrame(
            self.content, text=f"Дополнительные модели (до {MAX_CUSTOM_MODELS}, свои)", padding=10
        )
        frame.pack(fill="both", expand=True, pady=(0, 10))

        info = ttk.Label(
            frame,
            text=(
                "ℹ Сюда можно добавить любую другую модель с OpenRouter — например, "
                "DeepSeek или что угодно ещё из полного каталога. Укажите точный "
                "ID модели (формат «провайдер/название», например "
                "deepseek/deepseek-v4-flash-0731). Полный список моделей с ID:"
            ),
            foreground="#555555", wraplength=1000, justify="left",
        )
        info.pack(anchor="w", pady=(0, 2))
        _make_link_label(frame, OPENROUTER_MODELS_URL, OPENROUTER_MODELS_URL).pack(
            anchor="w", pady=(0, 10)
        )

        custom_config = self.config_data.get("custom_models", [])
        while len(custom_config) < MAX_CUSTOM_MODELS:
            custom_config.append({"id": "", "label": "", "persona": "", "enabled": False})

        all_ids_cache = self.config_data.get("all_model_ids_cache", [])

        for index in range(MAX_CUSTOM_MODELS):
            slot_data = custom_config[index]
            slot_frame = ttk.Frame(frame, relief="groove", padding=8)
            slot_frame.pack(fill="x", pady=4)

            enabled_var = tk.BooleanVar(value=slot_data.get("enabled", False))
            ttk.Checkbutton(
                slot_frame, text=f"Слот {index + 1}: включить", variable=enabled_var
            ).grid(row=0, column=0, columnspan=2, sticky="w")

            ttk.Label(slot_frame, text="ID модели:").grid(row=1, column=0, sticky="w", pady=(4, 0))
            id_var = tk.StringVar(value=slot_data.get("id", ""))
            id_values = _sorted_with_current(all_ids_cache, id_var.get())
            id_combo = ttk.Combobox(
                slot_frame, textvariable=id_var, values=id_values, width=36, state="normal"
            )
            id_combo.grid(row=1, column=1, sticky="w", padx=(6, 16), pady=(4, 0))
            self._protect_from_wheel(id_combo)

            ttk.Label(slot_frame, text="Название:").grid(row=1, column=2, sticky="w", pady=(4, 0))
            label_var = tk.StringVar(value=slot_data.get("label", ""))
            ttk.Entry(slot_frame, textvariable=label_var, width=20).grid(
                row=1, column=3, sticky="w", padx=(6, 0), pady=(4, 0)
            )

            ttk.Label(slot_frame, text="Персонаж:").grid(row=2, column=0, sticky="nw", pady=(4, 0))
            persona_text = tk.Text(slot_frame, height=2, width=46, wrap="word")
            persona_text.insert("1.0", slot_data.get("persona", ""))
            persona_text.grid(row=2, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))

            reasoning_frame = ttk.Frame(slot_frame)
            reasoning_frame.grid(row=2, column=3, sticky="nw", padx=(6, 0), pady=(4, 0))
            ttk.Label(reasoning_frame, text="Рассуждения:").pack(anchor="w")
            reasoning_var = tk.StringVar(
                value=slot_data.get("reasoning_level", DEFAULT_REASONING_LEVEL)
            )
            slot_reasoning_combo = ttk.Combobox(
                reasoning_frame, textvariable=reasoning_var, values=REASONING_LEVEL_NAMES,
                width=12, state="readonly",
            )
            slot_reasoning_combo.pack(anchor="w", pady=(2, 0))
            self._protect_from_wheel(slot_reasoning_combo)

            self.custom_slots.append({
                "enabled_var": enabled_var,
                "id_var": id_var,
                "id_combo": id_combo,
                "label_var": label_var,
                "persona_text": persona_text,
                "reasoning_var": reasoning_var,
            })

    # ---------- Сохранение ----------

    def _collect_form(self):
        """Собирает и валидирует значения формы. Возвращает словарь с
        данными при успехе, либо None (предупреждение уже показано
        внутри). НИЧЕГО не пишет на диск и не трогает self.config_data —
        это отдельная ответственность вызывающего кода (_save /
        _save_as_new_profile), чтобы «Сохранить как…» не задевала
        старый активный профиль."""
        selected_families = [key for key, var in self.family_vars.items() if var.get()]

        family_model_choice = {}
        personas = {}
        reasoning_levels = {}
        for key in self.family_vars:
            family_model_choice[key] = self.family_combo_vars[key].get()
            personas[key] = self.persona_texts[key].get("1.0", "end").strip()
            reasoning_levels[key] = self.reasoning_vars[key].get()

        seen_ids = {family_model_choice[k] for k in selected_families}
        custom_models = []
        custom_selected_ids = []

        for index, slot in enumerate(self.custom_slots):
            model_id = slot["id_var"].get().strip()
            label = slot["label_var"].get().strip()
            persona = slot["persona_text"].get("1.0", "end").strip()
            enabled = slot["enabled_var"].get()
            reasoning_level = slot["reasoning_var"].get()

            custom_models.append({
                "id": model_id, "label": label, "persona": persona,
                "enabled": enabled, "reasoning_level": reasoning_level,
            })

            if not enabled:
                continue
            if not model_id:
                messagebox.showwarning(
                    APP_TITLE,
                    f"Слот дополнительной модели №{index + 1} включён, но не указан "
                    f"ID модели. Укажите ID или снимите галочку «включить».",
                )
                return None
            if model_id in seen_ids:
                messagebox.showwarning(
                    APP_TITLE,
                    f"Модель с ID «{model_id}» уже выбрана (повтор в слоте №{index + 1}). "
                    f"Уберите дубликат.",
                )
                return None
            seen_ids.add(model_id)
            custom_selected_ids.append(model_id)

        total_count = len(selected_families) + len(custom_selected_ids)
        if total_count < MIN_MODELS:
            messagebox.showwarning(APP_TITLE, f"Выберите минимум {MIN_MODELS} моделей для брейншторма.")
            return None
        if total_count > MAX_MODELS:
            messagebox.showwarning(
                APP_TITLE,
                f"Максимум {MAX_MODELS} моделей одновременно — иначе сессия станет "
                f"слишком дорогой и долгой.",
            )
            return None

        try:
            budget = float(self.budget_var.get().strip().replace(",", "."))
            if budget <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Лимит бюджета должен быть положительным числом, например 0.5")
            return None

        return {
            "api_key": self.api_key_var.get().strip(),
            "selected_families": selected_families,
            "family_model_choice": family_model_choice,
            "personas": personas,
            "reasoning_levels": reasoning_levels,
            "custom_models": custom_models,
            "session_budget_usd": budget,
            "moderator_mode": self.moderator_mode_var.get(),
            "moderator_model": self.moderator_model_var.get(),
            "user_participation": self.participation_var.get(),
            "moderator_summary": self.moderator_summary_var.get(),
            "debug_tab_enabled": self.debug_tab_var.get(),
        }

    def _save(self):
        data = self._collect_form()
        if data is None:
            return
        self.config_data.update(data)
        save_config(self.config_data)
        logger.info(
            "Настройки сохранены (профиль «%s»): участников=%d, ведущий=%s",
            get_active_profile_name(),
            len(data["selected_families"]) + sum(1 for c in data["custom_models"] if c["enabled"]),
            data["moderator_mode"],
        )
        self.status_label.config(text="Сохранено ✓")
        self.after(2000, lambda: self.status_label.config(text=""))
        self.on_saved()


class ChatTab(ttk.Frame):
    """Вкладка брейншторма: тема, ведущий, лог обсуждения, вмешательство."""

    def __init__(self, parent, config):
        super().__init__(parent, padding=12)
        self.config_data = config
        self.ui_queue = queue.Queue()
        self.worker_thread = None
        self.export_log = []  # [(speaker_label, tag, raw_text), ...] — для честного экспорта в .md/.txt

        # Флаги/примитивы для связи с фоновым потоком
        self.intervene_requested = False
        self.abort_requested = False
        self._pending_event = None
        self._pending_response = None

        self._build_controls()
        self._build_input_panel()
        self._build_chat_log()
        self._poll_queue()

    # ---------- Верхняя панель управления ----------

    def _build_controls(self):
        topic_frame = ttk.Frame(self)
        topic_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(topic_frame, text="Тема обсуждения:").pack(anchor="w")
        self.topic_text = tk.Text(topic_frame, height=3, wrap="word")
        self.topic_text.pack(fill="x", pady=(2, 0))
        self.topic_text.bind("<Control-c>", lambda e: self._clipboard_op(self.topic_text, "<<Copy>>"))
        self.topic_text.bind("<Control-v>", lambda e: self._clipboard_op(self.topic_text, "<<Paste>>"))
        self.topic_text.bind("<Control-x>", lambda e: self._clipboard_op(self.topic_text, "<<Cut>>"))
        self.topic_text.bind("<Control-a>", self._select_all_topic)

        settings_row = ttk.Frame(self)
        settings_row.pack(fill="x", pady=(0, 6))

        ttk.Label(settings_row, text="Макс. реплик:").pack(side="left")
        self.max_replies_var = tk.IntVar(value=self.config_data.get("max_replies", 12))
        ttk.Spinbox(
            settings_row, from_=2, to=40, textvariable=self.max_replies_var, width=4
        ).pack(side="left", padx=(4, 16))

        self.start_button = ttk.Button(
            settings_row, text="Начать брейншторм", command=self._start_brainstorm
        )
        self.start_button.pack(side="left")

        self.intervene_button = ttk.Button(
            settings_row, text="Вмешаться", command=self._intervene_clicked, state="disabled"
        )
        self.intervene_button.pack(side="left", padx=(6, 0))

        ttk.Button(settings_row, text="Экспорт…", command=self._export_clicked).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(settings_row, text="Копировать всё", command=self._copy_all_clicked).pack(
            side="left", padx=(6, 0)
        )

        status_row = ttk.Frame(self)
        status_row.pack(fill="x")
        self.status_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self.status_var, foreground="#555555").pack(side="left")
        self.cost_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self.cost_var, foreground="#2e7d32").pack(side="right")

    # ---------- Панель для вмешательства/выбора говорящего ----------

    def _build_input_panel(self):
        self.input_panel = ttk.Frame(self, padding=8, relief="ridge")
        # Не паковится сразу — появляется только когда нужен ввод от пользователя.

    def _show_input_panel(self, mode, payload=None):
        for widget in self.input_panel.winfo_children():
            widget.destroy()

        if mode == "choose_speaker":
            label_text = (
                "Последняя реплика сессии — выберите, кто подведёт итог всего обсуждения:"
                if payload.get("is_final_reply")
                else "Ваш ход как ведущего: кто говорит следующим?"
            )
            ttk.Label(self.input_panel, text=label_text).pack(anchor="w")

            comment_entry = tk.Text(self.input_panel, height=2, wrap="word")
            comment_entry.pack(fill="x", pady=(4, 4))
            ttk.Label(
                self.input_panel,
                text="Необязательный комментарий выше добавится в чат от вашего имени "
                     "перед выбранной репликой.",
                foreground="#888888",
            ).pack(anchor="w")

            def choose(pid):
                comment = comment_entry.get("1.0", "end").strip()
                self._resolve_pending({"next": pid, "comment": comment})

            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x", pady=(6, 0))
            for participant in payload["participants"]:
                ttk.Button(
                    btn_row, text=participant["label"],
                    command=lambda pid=participant["id"]: choose(pid),
                ).pack(side="left", padx=4, pady=2)
            if payload.get("allow_user"):
                ttk.Button(
                    btn_row, text="Я (высказаться)", command=lambda: choose("user")
                ).pack(side="left", padx=4, pady=2)
            ttk.Button(
                btn_row, text="Завершить обсуждение",
                command=lambda: self._resolve_pending({"end": True}),
            ).pack(side="right", padx=4, pady=2)

        elif mode == "user_turn":
            ttk.Label(
                self.input_panel,
                text="Ведущий передал слово вам — введите реплику или пропустите:",
            ).pack(anchor="w")
            entry = tk.Text(self.input_panel, height=3, wrap="word")
            entry.pack(fill="x", pady=4)
            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x")
            ttk.Button(
                btn_row, text="Отправить",
                command=lambda: self._resolve_pending(entry.get("1.0", "end").strip() or None),
            ).pack(side="left", padx=4)
            ttk.Button(
                btn_row, text="Пропустить", command=lambda: self._resolve_pending(None)
            ).pack(side="left", padx=4)
            entry.focus_set()

        elif mode == "intervene":
            ttk.Label(
                self.input_panel,
                text="Вмешательство: можно добавить уточнение для участников или "
                     "завершить сессию прямо сейчас.",
            ).pack(anchor="w")
            entry = tk.Text(self.input_panel, height=3, wrap="word")
            entry.pack(fill="x", pady=4)
            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x")
            ttk.Button(
                btn_row, text="Продолжить с уточнением",
                command=lambda: self._resolve_pending(
                    {"action": "continue", "text": entry.get("1.0", "end").strip()}
                ),
            ).pack(side="left", padx=4)
            ttk.Button(
                btn_row, text="Завершить сессию",
                command=lambda: self._resolve_pending({"action": "end"}),
            ).pack(side="left", padx=4)
            entry.focus_set()

        self.input_panel.pack(fill="x", pady=(0, 8), before=self.chat_log)

    def _hide_input_panel(self):
        self.input_panel.pack_forget()

    def _resolve_pending(self, response):
        """Вызывается из главного потока (клик по кнопке) — передаёт ответ
        пользователя обратно в ждущий фоновый поток."""
        self._pending_response = response
        if self._pending_event:
            self._pending_event.set()
        self._hide_input_panel()

    def _sync_ui_request(self, mode, payload=None):
        """Вызывается ТОЛЬКО из фонового потока. Блокирует поток до тех
        пор, пока пользователь не ответит через панель ввода."""
        event = threading.Event()
        self._pending_event = event
        self._pending_response = None
        self.ui_queue.put(("ui_request", mode, payload, None))
        event.wait()
        return self._pending_response

    # ---------- Лог чата ----------

    def _build_chat_log(self):
        self.chat_log = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", font=("Segoe UI", 10)
        )
        self.chat_log.pack(fill="both", expand=True)

        self.chat_log.tag_config("system", foreground="#888888")
        self.chat_log.tag_config("error", foreground="#c62828")
        self.chat_log.tag_config("user_note", foreground="#1565c0", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("summary", foreground="#2e7d32", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("separator", foreground="#cccccc")
        self.chat_log.tag_config("code", font=("Consolas", 9), background="#f0f0f0")
        self.chat_log.tag_config("bold", font=("Segoe UI", 10, "bold"))

        self.chat_log.bind("<Control-c>", self._copy_selection)
        self.chat_log.bind("<Control-a>", self._select_all_log)

    def _copy_selection(self, _event=None):
        self.chat_log.event_generate("<<Copy>>")
        return "break"

    def _select_all_log(self, _event=None):
        self.chat_log.tag_add("sel", "1.0", "end")
        return "break"

    @staticmethod
    def _clipboard_op(widget, virtual_event):
        """Явно генерирует Copy/Cut/Paste — подстраховка на случай, если
        платформенная сборка Tk не обрабатывает Ctrl+C/V/X по умолчанию."""
        widget.event_generate(virtual_event)
        return "break"

    def _select_all_topic(self, _event=None):
        self.topic_text.tag_add("sel", "1.0", "end")
        return "break"

    def _ensure_model_tags(self, full_catalog):
        for model in full_catalog:
            self.chat_log.tag_config(
                model["id"], foreground=model["color"], font=("Segoe UI", 10, "bold")
            )

    def _insert_inline_formatted(self, text):
        """Обрабатывает **жирный текст**, `инлайн-код`, заголовки (# ...) и
        маркированные списки (- ...) внутри обычного (не блочного) текста."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                content = stripped.lstrip("#").strip()
                self.chat_log.insert("end", content, ("bold",))
            else:
                display_line = line
                if stripped.startswith(("- ", "* ")):
                    indent = line[:len(line) - len(stripped)]
                    display_line = indent + "• " + stripped[2:]
                last = 0
                for m in MD_INLINE_RE.finditer(display_line):
                    if m.start() > last:
                        self.chat_log.insert("end", display_line[last:m.start()])
                    if m.group(1) is not None:
                        self.chat_log.insert("end", m.group(1), ("bold",))
                    else:
                        self.chat_log.insert("end", m.group(2), ("code",))
                    last = m.end()
                if last < len(display_line):
                    self.chat_log.insert("end", display_line[last:])
            if i < len(lines) - 1:
                self.chat_log.insert("end", "\n")

    def _insert_body_with_code(self, text):
        """Вставляет текст реплики: ```блоки кода``` — моноширинным шрифтом
        с фоном, остальное — с базовым Markdown-форматированием (полезно,
        если тема касается кода или структурированных ответов)."""
        pos = 0
        for match in CODE_FENCE_RE.finditer(text):
            before = text[pos:match.start()]
            if before:
                self._insert_inline_formatted(before)
            code = match.group(1)
            self.chat_log.insert("end", code, ("code",))
            pos = match.end()
        rest = text[pos:]
        if rest:
            self._insert_inline_formatted(rest)

    def _append_log(self, speaker_label, tag, text):
        self.export_log.append((speaker_label, tag, text))

        self.chat_log.config(state="normal")
        self.chat_log.insert("end", f"{speaker_label}\n", (tag,))
        self._insert_body_with_code(text)
        self.chat_log.insert("end", "\n\n")
        self.chat_log.insert("end", "─" * 70 + "\n\n", ("separator",))
        self.chat_log.config(state="disabled")
        self.chat_log.see("end")

    # ---------- Экспорт / копирование ----------

    def _build_markdown_export(self):
        """Собирает .md из СЫРЫХ сообщений (self.export_log), а не из
        отрендеренного текста виджета — в виджете markdown-синтаксис уже
        заменён на визуальные теги (жирный/код), поэтому экспорт из
        него давал "голый" текст без разметки. Здесь же исходный текст
        реплик (со всеми **, ``` и т.д., как их написала модель) просто
        оборачивается в заголовки — так .md-файл открывается с
        форматированием в любом markdown-редакторе/просмотрщике."""
        parts = []
        for speaker_label, tag, text in self.export_log:
            if tag == "user_note":
                parts.append(f"> **{speaker_label}:** {text}")
            elif tag == "summary":
                parts.append(f"## {speaker_label}\n\n{text}")
            elif tag == "system":
                parts.append(f"*{speaker_label}: {text}*")
            elif tag == "error":
                parts.append(f"> ⚠ **{speaker_label}:** {text}")
            else:
                parts.append(f"### {speaker_label}\n\n{text}")
        return "\n\n---\n\n".join(parts) + "\n"

    def _build_plain_export(self):
        """Простой .txt: те же сырые сообщения, без markdown-синтаксиса
        (для людей, которым не нужен именно .md)."""
        parts = []
        for speaker_label, _tag, text in self.export_log:
            parts.append(f"{speaker_label}\n{text}")
        return ("\n\n" + "-" * 60 + "\n\n").join(parts) + "\n"

    def _export_clicked(self):
        if not self.export_log:
            messagebox.showinfo(APP_TITLE, "Лог обсуждения пуст — экспортировать нечего.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Текстовый файл", "*.txt"), ("Все файлы", "*.*")],
            title="Сохранить лог обсуждения",
        )
        if not path:
            return

        as_markdown = path.lower().endswith(".md")
        content = self._build_markdown_export() if as_markdown else self._build_plain_export()

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Не удалось сохранить файл: {e}")
            return
        logger.info("Лог обсуждения экспортирован в %s", path)
        self.status_var.set(f"Экспортировано в {path}")

    def _copy_all_clicked(self):
        content = self.chat_log.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_var.set("Весь лог скопирован в буфер обмена.")

    # ---------- Запуск/остановка сессии ----------

    def _intervene_clicked(self):
        self.intervene_requested = True
        self.status_var.set("Запрошено вмешательство — сработает после текущей реплики…")
        logger.info("Пользователь запросил вмешательство")

    def _start_brainstorm(self):
        api_key = self.config_data.get("api_key", "")
        full_catalog = build_full_catalog(self.config_data)
        topic = self.topic_text.get("1.0", "end").strip()

        if not api_key:
            messagebox.showwarning(APP_TITLE, "Сначала укажите API-ключ на вкладке «Настройки».")
            return
        if len(full_catalog) < MIN_MODELS:
            messagebox.showwarning(
                APP_TITLE, f"На вкладке «Настройки» выберите минимум {MIN_MODELS} моделей."
            )
            return
        if not topic:
            messagebox.showwarning(APP_TITLE, "Введите тему обсуждения.")
            return

        self.chat_log.config(state="normal")
        self.chat_log.delete("1.0", "end")
        self.chat_log.config(state="disabled")
        self.export_log.clear()
        self._hide_input_panel()
        self._append_log("Пользователь (тема)", "user_note", topic)

        budget = float(self.config_data.get("session_budget_usd", 0.5))
        max_replies = self.max_replies_var.get()
        moderator_mode = self.config_data.get("moderator_mode", "ai")
        moderator_model = self.config_data.get("moderator_model", MODERATOR_DEFAULT_MODEL)
        user_participation = self.config_data.get("user_participation", False)
        moderator_summary = self.config_data.get("moderator_summary", False)

        # Сохраняем текущее значение "макс. реплик" в конфиг, чтобы оно
        # подхватилось при следующем запуске (аналогично прочим настройкам).
        self.config_data["max_replies"] = max_replies
        save_config(self.config_data)

        self._ensure_model_tags(full_catalog)

        self.cost_var.set(f"Потрачено: $0.0000 из ${budget:.2f}")
        self.status_var.set("Идёт обсуждение…")
        self.start_button.config(state="disabled")
        if moderator_mode == "human":
            # В режиме человека-ведущего комментарий и завершение сессии уже
            # встроены прямо в панель выбора следующего оратора — отдельная
            # кнопка не нужна и только путала бы (два способа сделать одно).
            self.intervene_button.config(state="disabled")
        else:
            self.intervene_button.config(state="normal")
        self.abort_requested = False
        self.intervene_requested = False

        logger.info(
            "Старт сессии: тема=%r, участников=%d, ведущий=%s, макс.реплик=%d, бюджет=$%.2f, итог=%s",
            topic, len(full_catalog), moderator_mode, max_replies, budget, moderator_summary,
        )

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(api_key, full_catalog, topic, max_replies, budget,
                  moderator_mode, moderator_model, user_participation, moderator_summary),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_worker(self, api_key, full_catalog, topic, max_replies, budget,
                     moderator_mode, moderator_model, user_participation, moderator_summary):
        """Выполняется в фоновом потоке — не блокирует интерфейс."""
        transcript_lines = []
        total_cost = 0.0
        pending_moderator_cost = 0.0  # копится, показывается вместе со следующей видимой репликой
        replies_done = 0
        cost_unknown_calls = 0
        speak_counts = {p["id"]: 0 for p in full_catalog}
        unavailable_until = {}  # model_id -> time.time(), до которого считаем модель недоступной
        finish_reason = "Обсуждение завершено."

        def is_available(model_id):
            until = unavailable_until.get(model_id)
            return until is None or time.time() >= until

        def mark_unavailable(model_id, seconds=45):
            unavailable_until[model_id] = time.time() + seconds

        def pick_fallback_speaker(pool):
            pool = pool or full_catalog
            return min(pool, key=lambda p: speak_counts[p["id"]])["id"]

        while True:
            if total_cost >= budget:
                finish_reason = f"Достигнут лимит бюджета сессии (${budget:.2f})."
                break
            if replies_done >= max_replies:
                finish_reason = f"Достигнут лимит числа реплик ({max_replies})."
                break
            if self.abort_requested:
                finish_reason = "Сессия завершена пользователем."
                break

            if self.intervene_requested:
                self.intervene_requested = False
                resp = self._sync_ui_request("intervene")
                if not resp or resp.get("action") == "end":
                    self.abort_requested = True
                    continue
                clarification = (resp.get("text") or "").strip()
                if clarification:
                    transcript_lines.append(f"Пользователь (уточнение): {clarification}")
                    self.ui_queue.put(("message", "Пользователь", "user_note", clarification))
                continue

            transcript = "\n".join(transcript_lines) if transcript_lines else "(обсуждение только начинается)"
            available_participants = [p for p in full_catalog if is_available(p["id"])] or full_catalog
            is_final_reply = (replies_done == max_replies - 1)

            # --- выбор следующего говорящего ---
            task, reaction_type, wrap_up = "", "", False

            if moderator_mode == "human":
                status_text = (
                    "Последняя реплика сессии — выберите, кто подведёт итог…"
                    if is_final_reply else
                    "Ваш ход как ведущего — выберите участника…"
                )
                self.ui_queue.put(("status", status_text, None, None))
                resp = self._sync_ui_request(
                    "choose_speaker",
                    {
                        "participants": available_participants,
                        "allow_user": user_participation,
                        "is_final_reply": is_final_reply,
                    },
                )
                if not resp:
                    continue
                if resp.get("end"):
                    self.abort_requested = True
                    continue

                comment = (resp.get("comment") or "").strip()
                if comment:
                    transcript_lines.append(f"Пользователь (комментарий): {comment}")
                    self.ui_queue.put(("message", "Пользователь", "user_note", comment))

                next_id = resp.get("next")
                if next_id is None:
                    continue
                if is_final_reply:
                    task = "Подведи итог всего обсуждения одной обобщающей репликой."
                    wrap_up = True
            else:
                self.ui_queue.put(("status", "Ведущий выбирает следующего участника…", None, None))
                try:
                    decision, mod_usage = ask_moderator(
                        api_key, moderator_model, topic, transcript, available_participants,
                        user_participation, replies_done, max_replies, is_final_reply,
                    )
                except OpenRouterError as e:
                    logger.error("Ошибка вызова ведущего: %s", e)
                    decision, mod_usage = {"next": None, "task": "", "reason": "", "reaction_type": "", "wrap_up": False}, {}

                mod_cost = mod_usage.get("cost") if mod_usage else None
                if isinstance(mod_cost, (int, float)):
                    total_cost += mod_cost
                    pending_moderator_cost += mod_cost
                    self.ui_queue.put(("cost", f"${total_cost:.4f}", str(budget), None))

                next_id = decision["next"]
                task, reaction_type, wrap_up = decision["task"], decision["reaction_type"], decision["wrap_up"]

                if next_id is None:
                    next_id = pick_fallback_speaker(available_participants)
                    logger.info("Ведущий не дал валидный ответ, выбран запасной вариант: %s", next_id)

                # Гарантируем подведение итога на последней реплике даже
                # если ведущий проигнорировал wrap_up в своём ответе —
                # не полагаемся только на его послушность промпту.
                if is_final_reply:
                    wrap_up = True
                    if not task:
                        task = "Подведи итог всего обсуждения одной обобщающей репликой."

            if next_id == "user":
                self.ui_queue.put(("status", "Ведущий передал слово вам…", None, None))
                user_reply = self._sync_ui_request("user_turn")
                if user_reply:
                    transcript_lines.append(f"Пользователь: {user_reply}")
                    self.ui_queue.put(("message", "Пользователь", "user_note", user_reply))
                continue  # реплика пользователя не считается к лимиту реплик/бюджету

            model_info = find_in_catalog(next_id, full_catalog)
            if model_info is None:
                logger.warning("Ведущий выбрал неизвестную модель %s — пропускаю ход", next_id)
                continue

            label = model_info["label"]
            persona = model_info["persona"]
            reasoning_max_tokens = model_info.get("reasoning_max_tokens")

            self.ui_queue.put(("status", f"{label} готовит ответ…", None, None))

            guidance = ""
            if task:
                guidance += f"\nЗадача от ведущего: {task}"
            if reaction_type:
                guidance += f"\nОжидаемый тип реакции: {reaction_type}"
            if wrap_up:
                guidance += "\nОбсуждение близится к концу — дай более итоговую, подытоживающую реплику."

            user_prompt = (
                f"Тема обсуждения: {topic}\n\n"
                f"История обсуждения:\n{transcript}\n"
                f"{guidance}\n\n"
                f"Дай свою реплику по теме — по существу, 3-5 предложений, обязательно "
                f"заверши мысль в пределах этого объёма (лучше короче, но закончено, "
                f"чем оборвано на полуслове)."
            )

            try:
                reply, usage = ask_model(
                    api_key, next_id, persona, user_prompt,
                    reasoning_max_tokens=reasoning_max_tokens,
                )
            except OpenRouterError as e:
                # Не спамим в чат — всё равно ведущий тут же выберет другого
                # участника, а причина остаётся доступной во вкладке "Лог".
                logger.warning("Модель %s временно недоступна: %s", next_id, e)
                mark_unavailable(next_id)
                transcript_lines.append(f"{label}: (пропущен — временно недоступен)")
                continue

            cost = usage.get("cost")
            if isinstance(cost, (int, float)):
                total_cost += cost
                if pending_moderator_cost > 0:
                    display_cost = cost + pending_moderator_cost
                    cost_note = (
                        f"\n\n(стоимость реплики: ${cost:.4f} + ведущий "
                        f"${pending_moderator_cost:.4f} = ${display_cost:.4f})"
                    )
                else:
                    cost_note = f"\n\n(стоимость реплики: ${cost:.4f})"
                pending_moderator_cost = 0.0
                reply_shown = f"{reply}{cost_note}"
            else:
                cost_unknown_calls += 1
                reply_shown = reply

            speak_counts[next_id] = speak_counts.get(next_id, 0) + 1
            replies_done += 1

            self.ui_queue.put(("message", label, next_id, reply_shown))
            self.ui_queue.put(("cost", f"${total_cost:.4f}", str(budget), None))
            transcript_lines.append(f"{label}: {reply}")

        if moderator_summary and transcript_lines:
            self.ui_queue.put(("status", "Ведущий подводит итоги обсуждения…", None, None))
            transcript = "\n".join(transcript_lines)
            summary_system = (
                "Ты — ведущий группового брейншторма. Обсуждение завершено. "
                "Составь краткий тезисный итог: ключевые идеи, точки согласия и "
                "разногласий, и если уместно — общий вывод. Формат — маркированный "
                "список, без вступлений и лишних слов."
            )
            summary_user = f"Тема: {topic}\n\nПолная история обсуждения:\n{transcript}"
            try:
                summary_text, summary_usage = ask_model(
                    api_key, moderator_model, summary_system, summary_user,
                    max_tokens=500, reasoning_max_tokens=None,
                )
                summary_cost = summary_usage.get("cost")
                if isinstance(summary_cost, (int, float)):
                    total_cost += summary_cost
                    summary_text += f"\n\n(стоимость итога: ${summary_cost:.4f})"
                model_short = short_model_name(moderator_model)
                self.ui_queue.put((
                    "message", f"Итоги от ведущего ({model_short})", "summary", summary_text,
                ))
            except OpenRouterError as e:
                logger.warning("Не удалось получить итог от ведущего: %s", e)

        if cost_unknown_calls:
            finish_reason += (
                f" (для {cost_unknown_calls} реплик провайдер не вернул точную "
                f"стоимость — реальный расход мог быть чуть выше)"
            )
        logger.info("Сессия завершена: %s Всего потрачено: $%.4f", finish_reason, total_cost)
        self.ui_queue.put(("finished", finish_reason, None, None))

    def _poll_queue(self):
        """Периодически проверяет очередь сообщений из фонового потока."""
        try:
            while True:
                kind, label, tag, text = self.ui_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(label)
                elif kind == "message":
                    self._append_log(label, tag, text)
                elif kind == "error":
                    self._append_log(f"{label} (ошибка)", "error", text)
                elif kind == "cost":
                    spent, budget_str = label, tag
                    self.cost_var.set(f"Потрачено: {spent} из ${float(budget_str):.2f}")
                elif kind == "ui_request":
                    self._show_input_panel(mode=label, payload=tag)
                elif kind == "finished":
                    self._append_log("Система", "system", label)
                    self.status_var.set("Обсуждение завершено.")
                    self.start_button.config(state="normal")
                    self.intervene_button.config(state="disabled")
                    self._hide_input_panel()
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)

        icon_path = _resource_path("favicon.ico")
        if os.path.exists(icon_path):
            try:
                # default=... выставляет иконку не только для этого окна,
                # но и как иконку по умолчанию для всех последующих окон
                # приложения (диалоги simpledialog и т.п.) — на Windows
                # так же надёжнее ведёт себя таскбар, чем без default=.
                self.iconbitmap(default=icon_path)
            except tk.TclError as e:
                logger.warning("Не удалось установить иконку окна: %s", e)

        self.geometry("1060x780")
        self.minsize(900, 560)

        self.config_data = load_config()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Вкладка "Лог" создаётся один раз и живёт всю сессию приложения
        # (её просто показывают/прячут через notebook.add/forget) — так
        # накопленный лог не теряется при переключении видимости.
        self.log_tab = LogTab(self.notebook)
        self._log_handler = QueueLogHandler(self.log_tab.ui_queue)
        logger.addHandler(self._log_handler)

        self._build_tabs()

    def _build_tabs(self):
        self.chat_tab = ChatTab(self.notebook, self.config_data)
        self.settings_tab = SettingsTab(
            self.notebook, self.config_data,
            on_saved=self._on_settings_saved,
            on_profile_switched=self._on_profile_switched,
        )

        self.notebook.add(self.settings_tab, text="Настройки")
        self.notebook.add(self.chat_tab, text="Чат")

        self._apply_debug_visibility()

        if not self.config_data.get("api_key"):
            self.notebook.select(self.settings_tab)

    def _apply_debug_visibility(self):
        enabled = self.config_data.get("debug_tab_enabled", False)
        is_shown = str(self.log_tab) in self.notebook.tabs()
        if enabled and not is_shown:
            self.notebook.add(self.log_tab, text="Лог")
        elif not enabled and is_shown:
            self.notebook.forget(self.log_tab)

    def _on_settings_saved(self):
        # Настройки хранятся в общем словаре self.config_data, который уже
        # используется вкладкой чата — обновлять отдельно не нужно. Но
        # видимость вкладки "Лог" могла измениться — применяем.
        self._apply_debug_visibility()

    def _on_profile_switched(self):
        """Вызывается SettingsTab после загрузки/удаления профиля — сам
        словарь self.config_data уже заменён на данные нового профиля, но
        существующие виджеты были построены под старые значения и сами
        не обновятся. Проще и надёжнее — пересоздать вкладки заново."""
        self.notebook.forget(self.settings_tab)
        self.notebook.forget(self.chat_tab)
        if str(self.log_tab) in self.notebook.tabs():
            self.notebook.forget(self.log_tab)
        self.settings_tab.destroy()
        self.chat_tab.destroy()
        self._build_tabs()


if __name__ == "__main__":
    app = App()
    app.mainloop()
