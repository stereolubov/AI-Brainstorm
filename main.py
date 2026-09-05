# -*- coding: utf-8 -*-
"""
AI Brainstorm — a desktop app for group brainstorming with several AI
models via OpenRouter, Requesty, or any compatible provider (see providers.py).

Run:    python main.py
Build:  pyinstaller --onefile --windowed --icon=favicon.ico --add-data "favicon.ico;." --name AIBrainstorm main.py

Standard library only — no pip installs required.
"""

import base64
import logging
import mimetypes
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
    list_profiles, get_active_profile_name, switch_active_profile, CONFIG_DIR,
    get_language_code, set_language_code, get_debug_tab_enabled, set_debug_tab_enabled,
    get_theme_code, set_theme_code,
)
from models_catalog import (
    FAMILIES, MODERATOR_DEFAULT_MODEL, REASONING_LEVEL_CODES, DEFAULT_REASONING_LEVEL,
    reasoning_level_label, build_full_catalog, find_in_catalog, find_family, short_model_name,
)
from api_client import (
    ask_model, ask_moderator, ask_moderator_web_lookup, get_key_info,
    build_family_options, OpenRouterError,
)
import i18n
from i18n import t
import theme
from providers import PROVIDERS, DEFAULT_PROVIDER, get_provider, provider_ids_in_order, format_money, CURRENCY_SYMBOLS

logger = logging.getLogger("ai_brainstorm")
logger.setLevel(logging.DEBUG)
logger.propagate = False
# No console handler: all logging goes only to the optional "Log" tab
# (see QueueLogHandler below), toggled by the user in Settings.


class QueueLogHandler(logging.Handler):
    """Routes log records to the "Log" tab's Tk widget via a queue —
    same thread-safe handoff pattern used for chat messages (workers run
    in a background thread, GUI updates happen via after())."""

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
WINDOW_TITLE = "AI Brainstorm by stereolubov"
MIN_MODELS = 2
MAX_STANDARD_MODELS = 5
MAX_CUSTOM_MODELS = 3   # custom slots alongside families, when use_families=True
MAX_FLAT_SLOTS = 8      # all-custom slots, when use_families=False (families ignored)
MAX_MODELS = MAX_STANDARD_MODELS + MAX_CUSTOM_MODELS  # = 8, same total either way

CODE_FENCE_RE = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
MD_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|`([^`\n]+)`")
_COST_MARKER = "\u2063"  # invisible separator; splits reply body from the cost line for styling



def _sorted_with_current(values, current):
    """Alphabetical list, guaranteeing `current` is included even if not
    yet in the cache (e.g. right after manual entry)."""
    pool = set(values or [])
    if current:
        pool.add(current)
    return sorted(pool)


def _resolve_provider(config_data):
    """Provider dict with base_url resolved — for "custom", the registry
    has base_url=None (unknowable in advance), substituted here with
    whatever the person typed into the URL field. Module-level (not a
    method) since both SettingsTab and ChatTab need this."""
    provider = dict(get_provider(config_data.get("api_provider", DEFAULT_PROVIDER)))
    if provider.get("base_url") is None:
        provider["base_url"] = config_data.get("custom_base_url", "").strip()
    return provider


def _make_link_label(parent, text, url):
    """Clickable "link" built from tk.Label — opens `url` in the default browser."""
    link = tk.Label(
        parent, text=text, fg="#1565c0", cursor="hand2",
        font=("Segoe UI", 9, "underline"),
    )
    link.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return link


def _open_folder(path):
    """Opens `path` in the OS file manager, creating it first if needed."""
    os.makedirs(path, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _resource_path(relative_path):
    """Resolves a resource path (icon, etc.) so it works both when run
    as `python main.py` and inside a PyInstaller --onefile exe, where
    files are unpacked to sys._MEIPASS instead of living next to the script."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _set_windows_taskbar_icon(hwnd, icon_path):
    """
    Applies the window icon directly via WinAPI (WM_SETICON), working
    around tkinter.iconbitmap()'s tendency to use a single (small) frame
    from a multi-size .ico everywhere — including places that expect a
    large one (Alt+Tab, jump lists), producing a blurry stretched image.

    Loads two frames explicitly (16x16 for ICON_SMALL, 256x256 for
    ICON_BIG). Returns (hicon_small, hicon_big); keep a reference (see
    self._windows_icons in App.__init__) so the handles aren't GC'd.
    Windows-only — call only under sys.platform.startswith("win").
    """
    import ctypes

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1

    user32 = ctypes.windll.user32
    # Explicit argtypes/restype are required on 64-bit Windows — without
    # them ctypes assumes a 32-bit return and truncates pointers.
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
    ]

    hicon_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
    hicon_big = user32.LoadImageW(None, icon_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)

    if not hicon_small or not hicon_big:
        raise ctypes.WinError()

    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)

    return hicon_small, hicon_big


_WIN_VIRTUAL_KEYS = {"c": 0x43, "a": 0x41, "v": 0x56, "x": 0x58}


def _make_hotkey_handler(actions):
    """
    Builds a <Control-Key> event handler that recognizes Ctrl+<letter>
    regardless of the active keyboard layout.

    A plain "<Control-c>"-style binding matches by *keysym* — what the
    CURRENT layout produces for that physical key. On a non-Latin layout
    (e.g. Russian), the physical C key reports an entirely different
    keysym, so "<Control-c>" silently never fires — copy/paste/select-all
    just stop working, with no error, depending on what layout happens
    to be active. On Windows, the OS reports the same virtual-key code
    for a physical key no matter the layout (that's why system shortcuts
    work under any layout there) — Tkinter exposes this as
    `event.keycode`, so we match on that on Windows. Elsewhere we fall
    back to matching `event.keysym`, which covers the common case.

    `actions` maps single letters ("c", "a", "v", "x") to callables.
    """
    is_windows = sys.platform.startswith("win")

    def handler(event):
        if is_windows:
            for letter, vk in _WIN_VIRTUAL_KEYS.items():
                if letter in actions and event.keycode == vk:
                    return actions[letter](event)
        else:
            keysym = event.keysym.lower()
            if keysym in actions:
                return actions[keysym](event)
        return None

    return handler


def _hotkey_copy(event):
    event.widget.event_generate("<<Copy>>")
    return "break"


def _hotkey_paste(event):
    event.widget.event_generate("<<Paste>>")
    return "break"


def _hotkey_cut(event):
    event.widget.event_generate("<<Cut>>")
    return "break"


def _hotkey_select_all(event):
    widget = event.widget
    if isinstance(widget, tk.Text):
        widget.tag_add("sel", "1.0", "end")
    else:
        try:
            widget.selection_range(0, "end")
        except tk.TclError:
            pass
    return "break"


# Generic (not bound to any specific widget instance) — used for a
# single class-wide binding covering every Entry/Combobox/Spinbox/Text
# in Settings at once (see App.__init__), instead of wiring each of the
# many form fields individually. Safe even for the read-only chat/log
# Text widgets, which already have their own narrower instance-level
# "c"/"a"-only binding taking precedence — for "v"/"x" there, this
# generic one falls through to a harmless no-op (state="disabled"
# blocks the actual paste/cut from doing anything).
_GENERIC_EDITABLE_HOTKEYS = _make_hotkey_handler({
    "c": _hotkey_copy, "v": _hotkey_paste, "x": _hotkey_cut, "a": _hotkey_select_all,
})


class ScrollableFrame(ttk.Frame):
    """Vertically/horizontally scrollable container for the Settings tab —
    there's more content than fits on a FullHD screen once model blocks expand."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        theme.apply_canvas_theme(self.canvas, get_theme_code())
        self.vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hscroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)

        self.inner = ttk.Frame(self.canvas, padding=12)
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.vscroll.set, xscrollcommand=self.hscroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.hscroll.grid(row=1, column=0, sticky="ew")
        self._hscroll_visible = True
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_hscroll_visibility()

    def _on_canvas_configure(self, _event):
        self._update_hscroll_visibility()

    def _update_hscroll_visibility(self):
        """Hides the horizontal scrollbar entirely when the content
        actually fits the current window width — no point showing an
        always-on, always-empty scroll track when there's nothing to
        scroll sideways (which also happened to look visually "stuck"
        in the light theme's color regardless of the active theme)."""
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        content_width = bbox[2] - bbox[0]
        viewport_width = self.canvas.winfo_width()
        needed = content_width > viewport_width
        if needed and not self._hscroll_visible:
            self.hscroll.grid(row=1, column=0, sticky="ew")
            self._hscroll_visible = True
        elif not needed and self._hscroll_visible:
            self.hscroll.grid_remove()
            self._hscroll_visible = False

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
    """Technical log tab — enabled/disabled via a Settings checkbox."""

    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.ui_queue = queue.Queue()

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text=t("copy_all_button"), command=self._copy_all).pack(side="left")
        ttk.Button(btn_row, text=t("clear_button"), command=self._clear).pack(side="left", padx=(6, 0))

        self.log_text = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)
        theme.apply_text_widget_theme(self.log_text, get_theme_code())
        theme.replace_scrollbar_with_ttk(self.log_text)
        self.log_text.tag_config("ERROR", foreground="#c62828")
        self.log_text.tag_config("WARNING", foreground="#e65100")
        self.log_text.bind("<Control-Key>", _make_hotkey_handler({
            "c": lambda e: self._copy_selection(),
            "a": lambda e: self._select_all(),
        }))
        self.log_text.bind("<Button-1>", lambda e: self.log_text.focus_set())

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
    """Settings tab: profile, API key, budget, moderator, model families, custom models."""

    def __init__(self, parent, config, on_saved, on_profile_switched):
        super().__init__(parent)
        self.config_data = config
        self.on_saved = on_saved
        self.on_profile_switched = on_profile_switched

        self.family_vars = {}
        self.family_combo_vars = {}
        self.family_combos = {}
        self.persona_texts = {}
        self.reasoning_vars = {}       # key -> StringVar holding the LABEL (translated), not the code
        self.custom_slots = []

        self.use_families_var = tk.BooleanVar(value=self.config_data.get("use_families", True))
        if not self._current_provider().get("uses_families", True):
            # Custom (and any future provider without a stable vendor-
            # prefix naming convention) has no sensible "family" concept
            # at all — force flat mode, the checkbox itself is hidden.
            self.use_families_var.set(False)
        self.custom_slot_count = MAX_CUSTOM_MODELS if self.use_families_var.get() else MAX_FLAT_SLOTS
        # In family mode the 3 "own" slots are stored at indices 5-7 (not
        # 0-2) — so switching to flat mode can place the 5 families at
        # indices 0-4 in their natural order without reshuffling these,
        # keeping the visual list order stable across the toggle.
        self.custom_slot_offset = (MAX_FLAT_SLOTS - MAX_CUSTOM_MODELS) if self.use_families_var.get() else 0

        # Reasoning-level combos show a translated label but must save a
        # language-neutral code — build the label<->code mapping once.
        self._reasoning_labels = [reasoning_level_label(c) for c in REASONING_LEVEL_CODES]
        self._reasoning_label_to_code = {
            reasoning_level_label(c): c for c in REASONING_LEVEL_CODES
        }

        scrollable = ScrollableFrame(self)
        scrollable.pack(fill="both", expand=True)
        self.content = scrollable.inner
        self.canvas = scrollable.canvas  # needed so wheel-over-combobox scrolls the page, not the value

        self._build_profile_block()
        self._build_api_key_block()
        self._build_budget_block()
        self._build_moderator_block()
        self._build_models_block()
        self._build_custom_models_block()

    def _protect_from_wheel(self, widget):
        """Mouse wheel over a Combobox/Spinbox scrolls the page instead
        of silently changing its value — an easy way to accidentally
        swap a model or reasoning level while scrolling past it."""

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
        widget.bind("<Button-4>", on_button4)   # Linux, scroll up
        widget.bind("<Button-5>", on_button5)   # Linux, scroll down

    # ---------- Profile ----------

    def _build_profile_block(self):
        frame = ttk.LabelFrame(self.content, text=t("profile_block_title"), padding=10)
        frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        ttk.Label(row, text=t("active_profile_label")).pack(side="left")
        self.profile_var = tk.StringVar(value=get_active_profile_name())
        self.profile_combo = ttk.Combobox(
            row, textvariable=self.profile_var, values=sorted(list_profiles()),
            width=26, state="readonly",
        )
        self.profile_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(self.profile_combo)
        self.profile_combo.bind("<<ComboboxSelected>>", self._load_selected_profile)

        ttk.Button(row, text=t("save_as_button"), command=self._save_as_new_profile).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(row, text=t("delete_button"), command=self._delete_selected_profile).pack(
            side="left", padx=(6, 0)
        )
        ttk.Separator(row, orient="vertical").pack(side="left", fill="y", padx=(12, 12))
        ttk.Button(row, text=t("save_settings_button"), command=self._save).pack(side="left")

        second_row = ttk.Frame(frame)
        second_row.pack(fill="x", pady=(6, 0))
        ttk.Button(
            second_row, text=t("open_settings_folder_button"), command=self._open_settings_folder
        ).pack(side="left")
        ttk.Label(
            second_row, text=f"({CONFIG_DIR})", foreground=theme.get_palette(get_theme_code())["muted_fg"],
            wraplength=800, justify="left",
        ).pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(frame, text="", foreground="#2e7d32")
        self.status_label.pack(anchor="w", pady=(4, 0))

        lang_row = ttk.Frame(frame)
        lang_row.pack(fill="x", pady=(6, 0))
        ttk.Label(lang_row, text=t("language_label")).pack(side="left")

        self._languages = i18n.list_available_languages()
        self._lang_name_to_code = {lang["name"]: lang["code"] for lang in self._languages}
        current_code = i18n.get_current_language_code()
        current_name = next(
            (lang["name"] for lang in self._languages if lang["code"] == current_code),
            current_code,
        )
        self.language_var = tk.StringVar(value=current_name)
        language_combo = ttk.Combobox(
            lang_row, textvariable=self.language_var,
            values=[lang["name"] for lang in self._languages],
            width=20, state="readonly",
        )
        language_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(language_combo)
        language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

        ttk.Label(lang_row, text=t("theme_label")).pack(side="left", padx=(16, 0))
        self._theme_name_to_code = {
            t("theme_light"): "light",
            t("theme_dark"): "dark",
        }
        theme_names_by_code = {v: k for k, v in self._theme_name_to_code.items()}
        current_theme_code = get_theme_code()
        self.theme_var = tk.StringVar(
            value=theme_names_by_code.get(current_theme_code, t("theme_light"))
        )
        theme_combo = ttk.Combobox(
            lang_row, textvariable=self.theme_var,
            values=[t("theme_light"), t("theme_dark")],
            width=12, state="readonly",
        )
        theme_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(theme_combo)
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme_selected)

        self.debug_tab_var = tk.BooleanVar(value=get_debug_tab_enabled())
        ttk.Checkbutton(
            frame,
            text=t("show_log_tab_checkbox"),
            variable=self.debug_tab_var,
        ).pack(anchor="w", pady=(6, 0))

        ttk.Label(
            frame, text=t("profile_block_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _on_language_selected(self, _event=None):
        name = self.language_var.get()
        code = self._lang_name_to_code.get(name)
        if not code or code == i18n.get_current_language_code():
            return
        i18n.load_language(code)
        set_language_code(code)
        logger.info(t("log_language_switched", code=code))
        self.on_profile_switched()  # generic "rebuild everything" callback

    def _on_theme_selected(self, _event=None):
        name = self.theme_var.get()
        code = self._theme_name_to_code.get(name)
        if not code or code == get_theme_code():
            return
        theme.apply_theme(self, code)
        set_theme_code(code)
        logger.info(t("log_theme_switched", code=code))
        self.on_profile_switched()  # rebuilds tabs so plain tk.Text widgets re-theme too

    def _load_selected_profile(self, _event=None):
        name = self.profile_var.get()
        if name == get_active_profile_name():
            return
        loaded = load_config(profile_name=name)
        switch_active_profile(name)
        self.config_data.clear()
        self.config_data.update(loaded)
        logger.info(t("log_profile_loaded", name=name))
        self.on_profile_switched()

    def _save_as_new_profile(self):
        data = self._collect_form()
        if data is None:
            return  # invalid form — warning already shown inside

        name = simpledialog.askstring(APP_TITLE, t("new_profile_name_prompt"), parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in list_profiles():
            if not messagebox.askyesno(APP_TITLE, t("profile_exists_overwrite", name=name)):
                return

        # The OLD active profile on disk is left untouched — form values
        # only get applied to self.config_data in memory and are written
        # to the NEW profile file.
        self.config_data.update(data)
        save_profile(name, self.config_data)
        switch_active_profile(name)
        self.profile_combo["values"] = sorted(list_profiles())
        self.profile_var.set(name)
        logger.info(t("log_profile_saved_new", name=name))
        messagebox.showinfo(APP_TITLE, t("profile_saved_and_active", name=name))

    def _open_settings_folder(self):
        try:
            _open_folder(CONFIG_DIR)
            logger.info(t("log_settings_folder_opened", path=CONFIG_DIR))
        except Exception as e:
            logger.error(t("log_settings_folder_error", error=e))
            messagebox.showerror(APP_TITLE, t("open_folder_failed", error=e, path=CONFIG_DIR))

    def _delete_selected_profile(self):
        name = self.profile_var.get()
        if len(list_profiles()) <= 1:
            messagebox.showwarning(APP_TITLE, t("cannot_delete_last_profile"))
            return
        if not messagebox.askyesno(APP_TITLE, t("confirm_delete_profile", name=name)):
            return

        was_active = (name == get_active_profile_name())
        delete_profile(name)
        remaining = sorted(list_profiles())
        self.profile_combo["values"] = remaining
        logger.info(t("log_profile_deleted", name=name))

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

    # ---------- API key ----------

    def _build_api_key_block(self):
        frame = ttk.LabelFrame(self.content, text=t("api_key_block_title"), padding=10)
        frame.pack(fill="x", pady=(0, 10))

        provider_row = ttk.Frame(frame)
        provider_row.pack(fill="x", pady=(0, 8))
        ttk.Label(provider_row, text=t("api_provider_label")).pack(side="left")

        self._provider_name_to_id = {p["name"]: pid for pid, p in PROVIDERS.items()}
        provider_names = [PROVIDERS[pid]["name"] for pid in provider_ids_in_order()]
        current_provider_id = self.config_data.get("api_provider", DEFAULT_PROVIDER)
        current_provider_name = get_provider(current_provider_id)["name"]
        self.api_provider_var = tk.StringVar(value=current_provider_name)
        provider_combo = ttk.Combobox(
            provider_row, textvariable=self.api_provider_var, values=provider_names,
            width=20, state="readonly",
        )
        provider_combo.pack(side="left", padx=(8, 0))
        self._protect_from_wheel(provider_combo)
        provider_combo.bind("<<ComboboxSelected>>", self._on_api_provider_selected)

        self.custom_base_url_var = tk.StringVar(value=self.config_data.get("custom_base_url", ""))
        if current_provider_id == "custom":
            url_row = ttk.Frame(frame)
            url_row.pack(fill="x", pady=(0, 8))
            ttk.Label(url_row, text=t("custom_base_url_label")).pack(side="left")
            url_history = self.config_data.get("custom_base_url_history", []) or []
            url_combo = ttk.Combobox(
                url_row, textvariable=self.custom_base_url_var,
                values=_sorted_with_current(url_history, self.custom_base_url_var.get()),
                width=43, state="normal",
            )
            url_combo.pack(side="left", padx=(8, 0))
            self._protect_from_wheel(url_combo)
            ttk.Label(
                frame, text=t("custom_provider_warning"),
                foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
            ).pack(anchor="w", pady=(0, 8))

        self.api_key_var = tk.StringVar(value=self.config_data.get("api_key", ""))
        self.show_key_var = tk.BooleanVar(value=False)

        entry = ttk.Entry(frame, textvariable=self.api_key_var, width=61, show="*")
        entry.pack(side="left")

        def toggle_show():
            entry.config(show="" if self.show_key_var.get() else "*")

        ttk.Checkbutton(
            frame, text=t("show_checkbox"), variable=self.show_key_var, command=toggle_show
        ).pack(side="left", padx=(8, 0))

        buttons_row = ttk.Frame(frame)
        buttons_row.pack(fill="x", pady=(8, 0))
        # Not every provider has a balance-check endpoint (see providers.py) —
        # hidden entirely rather than shown-but-broken when unsupported.
        if get_provider(current_provider_id).get("has_key_info"):
            ttk.Button(
                buttons_row, text=t("check_balance_button"), command=self._check_key_balance
            ).pack(side="left")
        ttk.Button(
            buttons_row, text=t("refresh_models_button"), command=self._refresh_family_options
        ).pack(side="left", padx=(10, 0))

        self.balance_label = ttk.Label(
            frame, text="", foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left"
        )
        self.balance_label.pack(anchor="w", pady=(6, 0))

        self.refresh_status_label = ttk.Label(
            frame, text=self._cache_status_text(), foreground=theme.get_palette(get_theme_code())["muted_fg"],
            wraplength=1000, justify="left",
        )
        self.refresh_status_label.pack(anchor="w", pady=(2, 0))
        ttk.Label(
            frame, text=t("refresh_models_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(4, 0))

    def _current_provider(self):
        return _resolve_provider(self.config_data)

    def _on_api_provider_selected(self, _event=None):
        name = self.api_provider_var.get()
        provider_id = self._provider_name_to_id.get(name)
        old_provider_id = self.config_data.get("api_provider", DEFAULT_PROVIDER)
        if not provider_id or provider_id == old_provider_id:
            return
        old_currency = get_provider(old_provider_id).get("currency", "USD")
        new_currency = get_provider(provider_id).get("currency", "USD")
        self.config_data["api_provider"] = provider_id

        # Rescale the budget so a custom value survives a currency switch
        # roughly intact, instead of e.g. "$2" carrying over unchanged as
        # "2 ₽" and making the session hit its budget almost immediately.
        # A flat ×100 for USD<->RUB is a rough approximation, not a live
        # exchange rate — good enough for a spending ceiling, not meant
        # to be precise.
        if old_currency != new_currency:
            current_budget = self.config_data.get("session_budget_usd", 0.5)
            if old_currency == "USD" and new_currency == "RUB":
                self.config_data["session_budget_usd"] = round(current_budget * 100, 2)
            elif old_currency == "RUB" and new_currency == "USD":
                self.config_data["session_budget_usd"] = round(current_budget / 100, 4)

        # Cached model lists belong to the OLD provider's catalog — stale
        # and possibly nonsensical for the new one (different IDs
        # entirely), so clear them rather than risk showing garbage;
        # "Refresh Model List" repopulates them for the new provider.
        self.config_data["family_options_cache"] = {}
        self.config_data["all_model_ids_cache"] = []
        self.config_data["free_model_ids_cache"] = []
        self.config_data["family_options_updated_at"] = ""
        if not get_provider(provider_id).get("has_pricing_data"):
            # Otherwise the checkbox controlling this would be stuck ON
            # with nothing to show (empty free-models cache) and no
            # visible widget for this provider to turn it back off with.
            self.config_data["custom_models_free_only"] = False
            self.config_data["moderator_free_only"] = False
        save_config(self.config_data)
        logger.info(t("log_api_provider_switched", provider=provider_id))
        self.on_profile_switched()  # rebuild — gated UI (balance button, free-only, web lookup) may change

    def _check_key_balance(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning(APP_TITLE, t("enter_api_key_first"))
            return
        self.balance_label.config(text=t("checking_ellipsis"))
        provider = self._current_provider()
        base_url = provider["base_url"]
        key_info_path = provider.get("key_info_path", "/key")
        key_info_format = provider.get("key_info_format", "openrouter")
        currency = provider.get("currency", "USD")

        def worker():
            try:
                info = get_key_info(
                    api_key, base_url=base_url,
                    key_info_path=key_info_path, key_info_format=key_info_format,
                )
            except OpenRouterError as e:
                self.after(0, lambda: self.balance_label.config(
                    text=t("error_prefix", error=e), foreground="#c62828"
                ))
                return

            if key_info_format == "polza":
                # Prepaid-balance model — no "usage so far" or optional
                # cap concept like OpenRouter's, just "how much is left".
                balance = info.get("balance")
                if isinstance(balance, (int, float)):
                    text = t("key_balance_polza_text", balance=format_money(balance, currency, decimals=2))
                else:
                    text = t("not_available_abbr")
            else:
                usage = info.get("usage")
                limit = info.get("limit")
                remaining = info.get("limit_remaining")

                usage_text = format_money(usage, currency) if isinstance(usage, (int, float)) else t("not_available_abbr")
                if limit is None:
                    limit_text = t("key_limit_not_set")
                else:
                    limit_text = t(
                        "key_limit_set",
                        limit=format_money(limit, currency, decimals=2),
                        remaining=format_money(remaining, currency),
                    )

                text = t("key_balance_text", usage=usage_text, limit_text=limit_text)

            self.after(0, lambda: self.balance_label.config(text=text, foreground=theme.get_palette(get_theme_code())["muted_fg"]))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Budget ----------

    def _build_budget_block(self):
        self.budget_var = tk.StringVar(
            value=str(self.config_data.get("session_budget_usd", 0.5))
        )
        if not self._current_provider().get("has_cost_tracking", True):
            # No point showing a $ budget for a provider that never
            # reports a $ cost per request (typical for local/self-hosted
            # servers) — the field would just sit there doing nothing.
            return

        frame = ttk.LabelFrame(self.content, text=t("budget_block_title"), padding=10)
        frame.pack(fill="x", pady=(0, 10))

        currency_symbol = CURRENCY_SYMBOLS.get(self._current_provider().get("currency", "USD"), "$")
        ttk.Label(frame, text=t("session_budget_label", currency=currency_symbol)).pack(side="left")
        ttk.Entry(frame, textvariable=self.budget_var, width=8).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(
            frame, text=t("session_budget_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"],
            wraplength=420,
        ).pack(side="left", padx=(10, 0))

    # ---------- Moderator and participation ----------

    def _build_moderator_block(self):
        frame = ttk.LabelFrame(self.content, text=t("moderator_block_title"), padding=10)
        frame.pack(fill="x", pady=(0, 10))

        self.moderator_mode_var = tk.StringVar(
            value=self.config_data.get("moderator_mode", "ai")
        )
        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text=t("moderator_label")).pack(side="left")
        ttk.Radiobutton(
            mode_row, text=t("moderator_mode_ai"), variable=self.moderator_mode_var, value="ai",
            command=self._on_moderator_mode_changed,
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            mode_row, text=t("moderator_mode_human"),
            variable=self.moderator_mode_var, value="human",
            command=self._on_moderator_mode_changed,
        ).pack(side="left", padx=(8, 0))

        model_row = ttk.Frame(frame)
        model_row.pack(fill="x", pady=(8, 0))
        ttk.Label(model_row, text=t("moderator_model_label")).pack(side="left")
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

        self.moderator_free_only_var = tk.BooleanVar(
            value=self.config_data.get("moderator_free_only", False)
        )
        self.moderator_free_only_check = ttk.Checkbutton(
            frame, text=t("moderator_free_only_checkbox"), variable=self.moderator_free_only_var,
            command=self._on_moderator_free_only_toggled,
        )
        if self._current_provider().get("has_pricing_data"):
            self.moderator_free_only_check.pack(anchor="w", pady=(6, 0))

        self.participation_var = tk.BooleanVar(
            value=self.config_data.get("user_participation", False)
        )
        self.participation_check = ttk.Checkbutton(
            frame, text=t("participation_checkbox"), variable=self.participation_var,
        )
        self.participation_check.pack(anchor="w", pady=(8, 0))

        self.moderator_summary_var = tk.BooleanVar(
            value=self.config_data.get("moderator_summary", False)
        )
        self.moderator_summary_check = ttk.Checkbutton(
            frame, text=t("moderator_summary_checkbox"), variable=self.moderator_summary_var,
        )
        self.moderator_summary_check.pack(anchor="w", pady=(4, 0))

        self.web_lookup_var = tk.BooleanVar(
            value=self.config_data.get("moderator_web_lookup", False)
        )
        self.web_lookup_check = ttk.Checkbutton(
            frame, text=t("web_lookup_checkbox"), variable=self.web_lookup_var,
        )
        if self._current_provider().get("has_web_plugin"):
            self.web_lookup_check.pack(anchor="w", pady=(4, 0))

        ttk.Label(
            frame, text=t("moderator_block_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        # Applies both the mode-dependent (AI/Human) and free-only-dependent
        # widget states right away, matching whatever was loaded from config.
        self._refresh_moderator_widget_states()

    def _refresh_moderator_widget_states(self):
        """Single source of truth for which moderator-block widgets are
        interactive right now — depends on BOTH the AI/Human mode and the
        free-only checkbox, so the two conditions combine correctly
        instead of one silently overriding the other."""
        is_ai = self.moderator_mode_var.get() == "ai"
        free_only = self.moderator_free_only_var.get()

        self.moderator_model_combo.config(state=("readonly" if is_ai else "disabled"))
        self.moderator_free_only_check.config(state=("normal" if is_ai else "disabled"))
        self.participation_check.config(state=("normal" if is_ai else "disabled"))
        self.moderator_summary_check.config(state=("normal" if is_ai else "disabled"))
        # Web lookup needs BOTH conditions satisfied — AI mode AND not
        # restricted to free models (the search plugin costs money
        # regardless of whether the underlying model itself is free).
        self.web_lookup_check.config(state=("normal" if (is_ai and not free_only) else "disabled"))

    def _on_moderator_mode_changed(self):
        """"Модель ведущего" and the other AI-only fields only matter in
        AI mode — greyed out (not just visually, actually unclickable) in
        Human mode, matching the model field's own "(если ИИ)" framing."""
        self._refresh_moderator_widget_states()

    def _on_moderator_free_only_toggled(self, persist=True):
        """Switches the moderator model dropdown to the free-models pool
        (or back to the full list), and — since OpenRouter's web search
        plugin costs money regardless of whether the underlying model
        itself is free — force-disables the web lookup checkbox while
        this is on, so a "free" moderator setup can't quietly still cost
        something via the search plugin."""
        checked = self.moderator_free_only_var.get()
        pool = self.config_data.get("free_model_ids_cache", []) if checked else self._all_known_model_ids()
        current = self.moderator_model_var.get()
        self.moderator_model_combo["values"] = _sorted_with_current(pool, current)

        if checked:
            self.web_lookup_var.set(False)

        self._refresh_moderator_widget_states()

        if persist:
            self.config_data["moderator_free_only"] = checked
            save_config(self.config_data)
            logger.info(t("log_moderator_free_only_toggled", value=checked))

    def _all_known_model_ids(self):
        cache = self.config_data.get("family_options_cache", {}) or {}
        all_ids = {mid for ids in cache.values() for mid in ids}
        if not all_ids:
            all_ids = {MODERATOR_DEFAULT_MODEL}
        current = self.config_data.get("moderator_model", MODERATOR_DEFAULT_MODEL)
        return _sorted_with_current(all_ids, current)

    # ---------- Standard models (families) ----------

    def _cache_status_text(self):
        ts = self.config_data.get("family_options_updated_at", "")
        return t("cache_never_updated") if not ts else t("cache_updated_at", timestamp=ts)

    def _build_models_block(self):
        frame = ttk.LabelFrame(
            self.content,
            text=t("standard_models_title", max=MAX_STANDARD_MODELS),
            padding=10,
        )
        frame.pack(fill="both", expand=True, pady=(0, 10))

        if self._current_provider().get("uses_families", True):
            ttk.Checkbutton(
                frame, text=t("use_families_checkbox"), variable=self.use_families_var,
                command=self._on_use_families_toggled,
            ).pack(anchor="w", pady=(0, 8))

        if not self.use_families_var.get():
            note_key = (
                "families_disabled_note" if self._current_provider().get("uses_families", True)
                else "families_unavailable_note"
            )
            ttk.Label(
                frame, text=t(note_key),
                foreground=theme.get_palette(get_theme_code())["muted_fg"],
                wraplength=1000, justify="left",
            ).pack(anchor="w")
            return

        ttk.Label(
            frame, text=t("reasoning_intro_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(0, 2))
        reasoning_docs_url = self._current_provider().get("reasoning_docs_url")
        if reasoning_docs_url:
            _make_link_label(frame, reasoning_docs_url, reasoning_docs_url).pack(
                anchor="w", pady=(0, 8)
            )
        ttk.Label(
            frame, text=t("reasoning_budget_hint"),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
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
            theme.apply_text_widget_theme(text_widget, get_theme_code())
            self.persona_texts[key] = text_widget

            reasoning_frame = ttk.Frame(bottom_row)
            reasoning_frame.pack(side="left", padx=(12, 0), anchor="n")
            ttk.Label(reasoning_frame, text=t("reasoning_label")).pack(anchor="w")
            current_code = reasoning_levels.get(key, DEFAULT_REASONING_LEVEL)
            reasoning_var = tk.StringVar(value=reasoning_level_label(current_code))
            reasoning_combo = ttk.Combobox(
                reasoning_frame, textvariable=reasoning_var, values=self._reasoning_labels,
                width=12, state="readonly",
            )
            reasoning_combo.pack(anchor="w", pady=(2, 0))
            self._protect_from_wheel(reasoning_combo)
            self.reasoning_vars[key] = reasoning_var

    def _on_use_families_toggled(self):
        """Applies immediately (like the language/theme switches) rather
        than waiting for "Save Settings" — flipping this fundamentally
        changes which widgets exist at all, so there's no sensible way
        to preview the change without rebuilding right away."""
        new_value = self.use_families_var.get()
        if not new_value:
            self._migrate_families_to_flat_slots()
        self.config_data["use_families"] = new_value
        save_config(self.config_data)
        logger.info(t("log_use_families_toggled", value=new_value))
        self.on_profile_switched()  # generic "rebuild everything" callback

    def _migrate_families_to_flat_slots(self):
        """Called right before switching families off. The 5 families
        always land at FIXED positions 0-4 (matching FAMILIES' order:
        Claude, ChatGPT, Grok, Gemini, Mistral) regardless of which ones
        were checked — so the visual list order stays predictable and
        doesn't reshuffle based on what happened to be selected. Indices
        5-7 (the original "own" slots) are never touched here — they
        already live there even in family mode, no data movement needed.

        Only writes indices 0-4 if they're ALL still empty, so
        re-toggling later never clobbers data someone has since typed
        directly into those slots while in flat mode."""
        custom_models = list(self.config_data.get("custom_models", []))
        while len(custom_models) < MAX_FLAT_SLOTS:
            custom_models.append({"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "off"})

        family_area = custom_models[:MAX_FLAT_SLOTS - MAX_CUSTOM_MODELS]  # indices 0-4
        if any((slot.get("id") or "").strip() for slot in family_area):
            self.config_data["custom_models"] = custom_models
            return  # already has data there — don't overwrite

        for i, fam in enumerate(FAMILIES):
            key = fam["key"]
            model_id = self.family_combo_vars[key].get()
            persona = self.persona_texts[key].get("1.0", "end").strip()
            level_code = self._reasoning_label_to_code.get(
                self.reasoning_vars[key].get(), DEFAULT_REASONING_LEVEL
            )
            custom_models[i] = {
                "id": model_id, "label": fam["label"], "persona": persona,
                "enabled": self.family_vars[key].get(), "reasoning_level": level_code,
            }
        self.config_data["custom_models"] = custom_models

    def _current_slot_model_pool(self):
        """Which cached ID list feeds the custom/flat slots' autocomplete
        right now — free-only or the full list — based on the checkbox
        (available in both family and flat mode)."""
        if self.free_only_var.get():
            return self.config_data.get("free_model_ids_cache", [])
        return self.config_data.get("all_model_ids_cache", [])

    def _on_free_only_toggled(self):
        """Instant — both lists are already cached from the last
        refresh, so no network call is needed to switch between them."""
        self.config_data["custom_models_free_only"] = self.free_only_var.get()
        save_config(self.config_data)
        pool = self._current_slot_model_pool()
        for slot in self.custom_slots:
            current_id = slot["id_var"].get()
            slot["id_combo"]["values"] = _sorted_with_current(pool, current_id)
        logger.info(t("log_free_only_toggled", value=self.free_only_var.get()))

    def _live_base_url(self):
        """Like _current_provider()["base_url"], but for "custom" reads
        the URL field's CURRENT value (possibly not yet saved) instead
        of the last-saved one — so "Refresh Model List" works with
        whatever's typed right now, same as the API key field already does."""
        provider = get_provider(self.config_data.get("api_provider", DEFAULT_PROVIDER))
        if provider.get("base_url") is None:
            return self.custom_base_url_var.get().strip()
        return provider["base_url"]

    def _refresh_family_options(self):
        api_key = self.api_key_var.get().strip()
        base_url = self._live_base_url()
        if not base_url:
            messagebox.showwarning(APP_TITLE, t("enter_custom_url_first"))
            return
        self.refresh_status_label.config(text=t("refreshing_models_ellipsis"))
        logger.info(t("log_refresh_models_requested"))

        def worker():
            try:
                options, all_ids, free_ids = build_family_options(api_key or None, base_url=base_url)
            except OpenRouterError as e:
                logger.error(t("log_refresh_models_failed", error=e))
                self.after(0, lambda: self.refresh_status_label.config(
                    text=t("refresh_error", error=e), foreground="#c62828"
                ))
                return
            self.after(0, lambda: self._apply_family_options(options, all_ids, free_ids))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_family_options(self, options, all_ids, free_ids):
        self.config_data["family_options_cache"] = options
        self.config_data["all_model_ids_cache"] = all_ids
        self.config_data["free_model_ids_cache"] = free_ids
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.config_data["family_options_updated_at"] = timestamp
        save_config(self.config_data)

        for key, combo in self.family_combos.items():
            current = self.family_combo_vars[key].get()
            combo["values"] = _sorted_with_current(options.get(key), current)

        current_mod = self.moderator_model_var.get()
        self.moderator_model_combo["values"] = _sorted_with_current(all_ids, current_mod)

        # Flat/custom slots use whichever list matches the current
        # "free models only" state — free_ids if checked, all_ids otherwise.
        slot_pool = self._current_slot_model_pool()
        for slot in self.custom_slots:
            current_id = slot["id_var"].get()
            slot["id_combo"]["values"] = _sorted_with_current(slot_pool, current_id)

        has_pricing_data = self._current_provider().get("has_pricing_data")
        status_key = "models_updated_status" if has_pricing_data else "models_updated_status_no_pricing"
        self.refresh_status_label.config(
            text=t(status_key, timestamp=timestamp, total=len(all_ids), free=len(free_ids)),
            foreground="#2e7d32",
        )
        log_key = "log_models_updated" if has_pricing_data else "log_models_updated_no_pricing"
        logger.info(t(log_key, total=len(all_ids), free=len(free_ids)))

    # ---------- Custom models ----------

    def _build_custom_models_block(self):
        title_key = "custom_models_title" if self.use_families_var.get() else "flat_models_title"
        frame = ttk.LabelFrame(
            self.content, text=t(title_key, max=self.custom_slot_count), padding=10
        )
        frame.pack(fill="both", expand=True, pady=(0, 10))

        provider = self._current_provider()
        info = ttk.Label(
            frame, text=t("custom_models_info", provider=provider["name"]),
            foreground=theme.get_palette(get_theme_code())["muted_fg"], wraplength=1000, justify="left",
        )
        info.pack(anchor="w", pady=(0, 2))
        models_docs_url = provider.get("models_docs_url")
        if models_docs_url:
            _make_link_label(frame, models_docs_url, models_docs_url).pack(
                anchor="w", pady=(0, 10)
            )

        self.free_only_var = tk.BooleanVar(value=self.config_data.get("custom_models_free_only", False))
        if self._current_provider().get("has_pricing_data"):
            ttk.Checkbutton(
                frame, text=t("free_only_checkbox"), variable=self.free_only_var,
                command=self._on_free_only_toggled,
            ).pack(anchor="w", pady=(0, 10))

        custom_config = self.config_data.get("custom_models", [])
        while len(custom_config) < self.custom_slot_offset + self.custom_slot_count:
            custom_config.append({"id": "", "label": "", "persona": "", "enabled": False})

        all_ids_cache = self._current_slot_model_pool()

        for index in range(self.custom_slot_count):
            slot_data = custom_config[self.custom_slot_offset + index]
            slot_frame = ttk.Frame(frame, relief="groove", padding=8)
            slot_frame.pack(fill="x", pady=4)

            enabled_var = tk.BooleanVar(value=slot_data.get("enabled", False))
            ttk.Checkbutton(
                slot_frame, text=t("custom_slot_enable", n=index + 1), variable=enabled_var
            ).grid(row=0, column=0, columnspan=2, sticky="w")

            ttk.Label(slot_frame, text=t("model_id_label")).grid(row=1, column=0, sticky="w", pady=(4, 0))
            id_var = tk.StringVar(value=slot_data.get("id", ""))
            id_values = _sorted_with_current(all_ids_cache, id_var.get())
            id_combo = ttk.Combobox(
                slot_frame, textvariable=id_var, values=id_values, width=36, state="normal"
            )
            id_combo.grid(row=1, column=1, sticky="w", padx=(6, 16), pady=(4, 0))
            self._protect_from_wheel(id_combo)

            ttk.Label(slot_frame, text=t("name_label")).grid(row=1, column=2, sticky="w", pady=(4, 0))
            label_var = tk.StringVar(value=slot_data.get("label", ""))
            ttk.Entry(slot_frame, textvariable=label_var, width=20).grid(
                row=1, column=3, sticky="w", padx=(6, 0), pady=(4, 0)
            )

            ttk.Label(slot_frame, text=t("persona_label")).grid(row=2, column=0, sticky="nw", pady=(4, 0))
            persona_text = tk.Text(slot_frame, height=2, width=46, wrap="word")
            persona_text.insert("1.0", slot_data.get("persona", ""))
            persona_text.grid(row=2, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))
            theme.apply_text_widget_theme(persona_text, get_theme_code())

            reasoning_frame = ttk.Frame(slot_frame)
            reasoning_frame.grid(row=2, column=3, sticky="nw", padx=(6, 0), pady=(4, 0))

            if provider.get("reasoning_format") == "raw":
                # No guessable shape for an arbitrary server (confirmed
                # OpenRouter/Requesty/LM Studio already differ from each
                # other) — the person writes the exact JSON fragment
                # themselves, per model (local servers vary this model
                # to model). Empty = send nothing reasoning-related.
                ttk.Label(reasoning_frame, text=t("reasoning_raw_label")).pack(anchor="w")
                reasoning_raw_var = tk.StringVar(value=slot_data.get("reasoning_raw", ""))
                reasoning_raw_entry = ttk.Entry(
                    reasoning_frame, textvariable=reasoning_raw_var, width=24
                )
                reasoning_raw_entry.pack(anchor="w", pady=(2, 0))
                reasoning_var = None
            else:
                ttk.Label(reasoning_frame, text=t("reasoning_label")).pack(anchor="w")
                slot_current_code = slot_data.get("reasoning_level", DEFAULT_REASONING_LEVEL)
                reasoning_var = tk.StringVar(value=reasoning_level_label(slot_current_code))
                slot_reasoning_combo = ttk.Combobox(
                    reasoning_frame, textvariable=reasoning_var, values=self._reasoning_labels,
                    width=12, state="readonly",
                )
                slot_reasoning_combo.pack(anchor="w", pady=(2, 0))
                self._protect_from_wheel(slot_reasoning_combo)
                reasoning_raw_var = None

            self.custom_slots.append({
                "enabled_var": enabled_var,
                "id_var": id_var,
                "id_combo": id_combo,
                "label_var": label_var,
                "persona_text": persona_text,
                "reasoning_var": reasoning_var,          # None when reasoning_format == "raw"
                "reasoning_raw_var": reasoning_raw_var,  # None otherwise
            })

    # ---------- Save ----------

    def _collect_form(self):
        """Collects and validates form values. Returns a dict on success,
        or None (a warning was already shown) — writes nothing to disk and
        doesn't touch self.config_data itself (that's up to the caller:
        _save / _save_as_new_profile, so "Save As" never touches the old
        active profile)."""
        use_families = self.use_families_var.get()

        if use_families:
            selected_families = [key for key, var in self.family_vars.items() if var.get()]
            family_model_choice = {}
            personas = {}
            reasoning_levels = {}
            for key in self.family_vars:
                family_model_choice[key] = self.family_combo_vars[key].get()
                personas[key] = self.persona_texts[key].get("1.0", "end").strip()
                reasoning_levels[key] = self._reasoning_label_to_code.get(
                    self.reasoning_vars[key].get(), DEFAULT_REASONING_LEVEL
                )
        else:
            # No family widgets exist in this mode — keep whatever was
            # already saved untouched rather than overwriting with blanks,
            # so switching back to family mode later restores it as-is.
            selected_families = list(self.config_data.get("selected_families", []))
            family_model_choice = dict(self.config_data.get("family_model_choice", {}))
            personas = dict(self.config_data.get("personas", {}))
            reasoning_levels = dict(self.config_data.get("reasoning_levels", {}))

        # Only tracks FAMILY selections — custom slots are allowed to
        # duplicate each other on purpose (same model, different
        # personas — each gets a unique participant_id under the hood,
        # see models_catalog.build_full_catalog), but still can't reuse
        # a model already claimed by a family: families have their own,
        # separate uniqueness guarantee (one checkbox per family) that
        # a custom slot shouldn't be able to silently collide with.
        family_ids_in_use = {family_model_choice[k] for k in selected_families if k in family_model_choice} if use_families else set()

        # custom_models is always stored as MAX_FLAT_SLOTS entries — only
        # the slots actually visible right now (self.custom_slots) get
        # overwritten; anything beyond that (the "other" mode's data)
        # carries forward untouched, same reasoning as families above.
        custom_models = list(self.config_data.get("custom_models", []))
        while len(custom_models) < MAX_FLAT_SLOTS:
            custom_models.append({"id": "", "label": "", "persona": "", "enabled": False, "reasoning_level": "off"})

        custom_selected_ids = []
        for index, slot in enumerate(self.custom_slots):
            model_id = slot["id_var"].get().strip()
            label = slot["label_var"].get().strip()
            persona = slot["persona_text"].get("1.0", "end").strip()
            enabled = slot["enabled_var"].get()

            storage_index = self.custom_slot_offset + index
            existing_slot = custom_models[storage_index] if storage_index < len(custom_models) else {}

            if slot["reasoning_var"] is not None:
                reasoning_level = self._reasoning_label_to_code.get(
                    slot["reasoning_var"].get(), DEFAULT_REASONING_LEVEL
                )
                # No raw-JSON widget exists for this slot right now (the
                # active provider isn't "raw") — keep whatever was saved
                # for it untouched, don't lose it just because it's hidden.
                reasoning_raw = existing_slot.get("reasoning_raw", "")
            else:
                reasoning_raw = slot["reasoning_raw_var"].get().strip()
                reasoning_level = existing_slot.get("reasoning_level", "off")

            custom_models[storage_index] = {
                "id": model_id, "label": label, "persona": persona,
                "enabled": enabled, "reasoning_level": reasoning_level,
                "reasoning_raw": reasoning_raw,
            }

            if not enabled:
                continue
            if not model_id:
                messagebox.showwarning(APP_TITLE, t("custom_slot_missing_id", n=index + 1))
                return None
            if model_id in family_ids_in_use:
                messagebox.showwarning(APP_TITLE, t("custom_slot_duplicates_family", id=model_id, n=index + 1))
                return None
            custom_selected_ids.append(model_id)

        total_count = (len(selected_families) if use_families else 0) + len(custom_selected_ids)
        if total_count < MIN_MODELS:
            messagebox.showwarning(APP_TITLE, t("min_models_warning", min=MIN_MODELS))
            return None
        if total_count > MAX_MODELS:
            messagebox.showwarning(APP_TITLE, t("max_models_warning", max=MAX_MODELS))
            return None

        try:
            budget = float(self.budget_var.get().strip().replace(",", "."))
            if budget <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, t("invalid_budget_warning"))
            return None

        new_base_url = self.custom_base_url_var.get().strip()
        url_history = [u for u in self.config_data.get("custom_base_url_history", []) if u != new_base_url]
        if new_base_url:
            url_history.insert(0, new_base_url)
        url_history = url_history[:8]  # a handful of recent URLs is plenty — this isn't meant to be a full log

        return {
            "api_key": self.api_key_var.get().strip(),
            "custom_base_url": new_base_url,
            "custom_base_url_history": url_history,
            "use_families": use_families,
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
            "moderator_web_lookup": self.web_lookup_var.get(),
        }

    def _save(self):
        """Returns True on success, False if the form didn't validate
        (a warning was already shown by _collect_form()) — used both by
        the "Save Settings" button and by ChatTab's auto-save-before-start."""
        data = self._collect_form()
        if data is None:
            return False
        self.config_data.update(data)
        save_config(self.config_data)
        set_debug_tab_enabled(self.debug_tab_var.get())  # app-wide, not profile data
        logger.info(
            "Settings saved (profile %r): %d participants, moderator=%s",
            get_active_profile_name(),
            len(data["selected_families"]) + sum(1 for c in data["custom_models"] if c["enabled"]),
            data["moderator_mode"],
        )
        self.status_label.config(text=t("saved_confirmation"))
        self.after(2000, lambda: self.status_label.config(text=""))
        self.on_saved()
        return True


class ChatTab(ttk.Frame):
    """Brainstorm tab: topic, moderator, discussion log, intervention."""

    def __init__(self, parent, config, save_settings_callback=None):
        super().__init__(parent, padding=12)
        self.config_data = config
        self.save_settings_callback = save_settings_callback
        self.ui_queue = queue.Queue()
        self.worker_thread = None
        self.export_log = []  # [(speaker_label, tag, raw_text), ...] — for honest .md/.txt export

        # Flags/primitives for talking to the background worker thread
        self.intervene_requested = False
        self.abort_requested = False
        self._pending_event = None
        self._pending_response = None

        # Optional image attached to the topic — sent to every PARTICIPANT
        # reply (not moderator calls, which only need the text transcript
        # to pick who speaks next). Built once at attach time and reused
        # for the whole session rather than re-reading the file per call.
        self.attached_image_path = None
        self.attached_image_data_url = None

        self._build_controls()
        self._build_input_panel()
        self._build_chat_log()
        self._poll_queue()

    # ---------- Top control bar ----------

    def _build_controls(self):
        topic_frame = ttk.Frame(self)
        topic_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(topic_frame, text=t("topic_label")).pack(anchor="w")
        self.topic_text = tk.Text(topic_frame, height=3, wrap="word")
        self.topic_text.pack(fill="x", pady=(2, 0))
        theme.apply_text_widget_theme(self.topic_text, get_theme_code())
        self.topic_text.bind("<Control-Key>", _make_hotkey_handler({
            "c": lambda e: self._clipboard_op(self.topic_text, "<<Copy>>"),
            "v": lambda e: self._clipboard_op(self.topic_text, "<<Paste>>"),
            "x": lambda e: self._clipboard_op(self.topic_text, "<<Cut>>"),
            "a": lambda e: self._select_all_topic(),
        }))
        self.topic_text.bind("<Button-1>", lambda e: self.topic_text.focus_set())

        image_row = ttk.Frame(topic_frame)
        image_row.pack(fill="x", pady=(4, 0))
        ttk.Button(
            image_row, text=t("attach_image_button"), command=self._attach_image_clicked
        ).pack(side="left")
        self.attached_image_label = ttk.Label(
            image_row, text="", foreground=theme.get_palette(get_theme_code())["muted_fg"]
        )
        self.attached_image_label.pack(side="left", padx=(8, 0))
        self.remove_image_button = ttk.Button(
            image_row, text=t("remove_image_button"), command=self._remove_image_clicked, width=3,
        )
        # Not packed until something is actually attached — see
        # _update_image_attachment_display().

        settings_row = ttk.Frame(self)
        settings_row.pack(fill="x", pady=(0, 6))

        ttk.Label(settings_row, text=t("max_replies_label")).pack(side="left")
        self.max_replies_var = tk.IntVar(value=self.config_data.get("max_replies", 12))
        ttk.Spinbox(
            settings_row, from_=2, to=40, textvariable=self.max_replies_var, width=4
        ).pack(side="left", padx=(4, 16))

        self.start_button = ttk.Button(
            settings_row, text=t("start_brainstorm_button"), command=self._start_brainstorm
        )
        self.start_button.pack(side="left")

        self.intervene_button = ttk.Button(
            settings_row, text=t("intervene_button"), command=self._intervene_clicked, state="disabled"
        )
        self.intervene_button.pack(side="left", padx=(6, 0))

        ttk.Button(settings_row, text=t("export_button"), command=self._export_clicked).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(settings_row, text=t("copy_all_button"), command=self._copy_all_clicked).pack(
            side="left", padx=(6, 0)
        )

        status_row = ttk.Frame(self)
        status_row.pack(fill="x")
        self.status_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self.status_var, foreground=theme.get_palette(get_theme_code())["muted_fg"]).pack(side="left")
        self.cost_var = tk.StringVar(value="")
        if _resolve_provider(self.config_data).get("has_cost_tracking", True):
            ttk.Label(status_row, textvariable=self.cost_var, foreground="#2e7d32").pack(side="right")

    # ---------- Image attachment ----------

    def _attach_image_clicked(self):
        path = filedialog.askopenfilename(
            title=t("attach_image_dialog_title"),
            filetypes=[(t("image_files_filter"), "*.png *.jpg *.jpeg *.gif *.webp *.bmp")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            messagebox.showwarning(APP_TITLE, t("image_read_error", error=e))
            return

        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/png"  # reasonable fallback — most APIs sniff actual content anyway

        # No resizing/compression on purpose — that needs an image
        # library beyond the standard library this app is built on. A
        # size warning is the honest alternative: let the person decide
        # whether a large file is worth the extra request cost, rather
        # than silently degrading quality or silently sending something huge.
        size_mb = len(data) / (1024 * 1024)
        if size_mb > 5 and not messagebox.askyesno(APP_TITLE, t("image_large_warning", size=f"{size_mb:.1f}")):
            return

        self.attached_image_path = path
        self.attached_image_data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
        self._update_image_attachment_display()
        logger.info(t("log_image_attached", filename=os.path.basename(path), size=f"{size_mb:.2f}"))

    def _remove_image_clicked(self):
        self.attached_image_path = None
        self.attached_image_data_url = None
        self._update_image_attachment_display()
        logger.info(t("log_image_removed"))

    def _update_image_attachment_display(self):
        if self.attached_image_path:
            filename = os.path.basename(self.attached_image_path)
            self.attached_image_label.config(text=t("attached_image_label", filename=filename))
            self.remove_image_button.pack(side="left", padx=(6, 0))
        else:
            self.attached_image_label.config(text="")
            self.remove_image_button.pack_forget()

    # ---------- Speaker-selection / intervention panel ----------

    def _build_input_panel(self):
        self.input_panel = ttk.Frame(self, padding=8, relief="ridge")
        # Not packed yet — shown only when user input is actually needed.

    def _show_input_panel(self, mode, payload=None):
        for widget in self.input_panel.winfo_children():
            widget.destroy()

        if mode == "choose_speaker":
            label_text = (
                t("final_reply_choose_speaker")
                if payload.get("is_final_reply")
                else t("your_turn_choose_speaker")
            )
            ttk.Label(self.input_panel, text=label_text).pack(anchor="w")

            comment_entry = tk.Text(self.input_panel, height=2, wrap="word")
            comment_entry.pack(fill="x", pady=(4, 4))
            theme.apply_text_widget_theme(comment_entry, get_theme_code())
            ttk.Label(
                self.input_panel, text=t("optional_comment_hint"),
                foreground=theme.get_palette(get_theme_code())["muted_fg"],
            ).pack(anchor="w")

            def choose(pid):
                comment = comment_entry.get("1.0", "end").strip()
                self._resolve_pending({"next": pid, "comment": comment})

            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x", pady=(6, 0))
            for participant in payload["participants"]:
                ttk.Button(
                    btn_row, text=participant["label"],
                    command=lambda pid=participant["participant_id"]: choose(pid),
                ).pack(side="left", padx=4, pady=2)
            if payload.get("allow_user"):
                ttk.Button(
                    btn_row, text=t("speak_myself_button"), command=lambda: choose("user")
                ).pack(side="left", padx=4, pady=2)
            ttk.Button(
                btn_row, text=t("end_discussion_button"),
                command=lambda: self._resolve_pending({"end": True}),
            ).pack(side="right", padx=4, pady=2)

        elif mode == "user_turn":
            ttk.Label(self.input_panel, text=t("moderator_passed_you_the_floor")).pack(anchor="w")
            entry = tk.Text(self.input_panel, height=3, wrap="word")
            entry.pack(fill="x", pady=4)
            theme.apply_text_widget_theme(entry, get_theme_code())
            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x")
            ttk.Button(
                btn_row, text=t("send_button"),
                command=lambda: self._resolve_pending(entry.get("1.0", "end").strip() or None),
            ).pack(side="left", padx=4)
            ttk.Button(
                btn_row, text=t("skip_button"), command=lambda: self._resolve_pending(None)
            ).pack(side="left", padx=4)
            entry.focus_set()

        elif mode == "intervene":
            ttk.Label(self.input_panel, text=t("intervene_hint")).pack(anchor="w")
            entry = tk.Text(self.input_panel, height=3, wrap="word")
            entry.pack(fill="x", pady=4)
            theme.apply_text_widget_theme(entry, get_theme_code())
            btn_row = ttk.Frame(self.input_panel)
            btn_row.pack(fill="x")
            ttk.Button(
                btn_row, text=t("continue_with_note_button"),
                command=lambda: self._resolve_pending(
                    {"action": "continue", "text": entry.get("1.0", "end").strip()}
                ),
            ).pack(side="left", padx=4)
            ttk.Button(
                btn_row, text=t("end_session_button"),
                command=lambda: self._resolve_pending({"action": "end"}),
            ).pack(side="left", padx=4)
            entry.focus_set()

        self.input_panel.pack(fill="x", pady=(0, 8), before=self.chat_log)

    def _hide_input_panel(self):
        self.input_panel.pack_forget()

    def _resolve_pending(self, response):
        """Called from the main thread (button click) — hands the user's
        answer back to the waiting background thread."""
        self._pending_response = response
        if self._pending_event:
            self._pending_event.set()
        self._hide_input_panel()

    def _sync_ui_request(self, mode, payload=None):
        """Called ONLY from the background thread. Blocks until the user
        responds via the input panel."""
        event = threading.Event()
        self._pending_event = event
        self._pending_response = None
        self.ui_queue.put(("ui_request", mode, payload, None))
        event.wait()
        return self._pending_response

    # ---------- Chat log ----------

    def _build_chat_log(self):
        self.chat_log = scrolledtext.ScrolledText(
            self, wrap="word", state="disabled", font=("Segoe UI", 10)
        )
        self.chat_log.pack(fill="both", expand=True)
        theme.apply_text_widget_theme(self.chat_log, get_theme_code())
        theme.replace_scrollbar_with_ttk(self.chat_log)

        tag_colors = theme.theme_tag_colors(get_theme_code())
        self.chat_log.tag_config("system", foreground=tag_colors["muted_fg"])
        self.chat_log.tag_config("error", foreground="#c62828")
        self.chat_log.tag_config("user_note", foreground="#1565c0", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("summary", foreground="#2e7d32", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("web_lookup", foreground="#0e7490", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("separator", foreground=tag_colors["separator"])
        self.chat_log.tag_config("code", font=("Consolas", 9), background=tag_colors["code_bg"])
        self.chat_log.tag_config("bold", font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config(
            "cost_line", foreground=tag_colors["muted_fg"], font=("Segoe UI", 9, "italic"), justify="right"
        )

        self.chat_log.bind("<Control-Key>", _make_hotkey_handler({
            "c": lambda e: self._copy_selection(),
            "a": lambda e: self._select_all_log(),
        }))
        self.chat_log.bind("<Button-1>", lambda e: self.chat_log.focus_set())

    def _copy_selection(self, _event=None):
        self.chat_log.event_generate("<<Copy>>")
        return "break"

    def _select_all_log(self, _event=None):
        self.chat_log.tag_add("sel", "1.0", "end")
        return "break"

    @staticmethod
    def _clipboard_op(widget, virtual_event):
        """Explicitly fires Copy/Cut/Paste — a fallback in case a given
        Tk build doesn't handle Ctrl+C/V/X by default."""
        widget.event_generate(virtual_event)
        return "break"

    def _select_all_topic(self, _event=None):
        self.topic_text.tag_add("sel", "1.0", "end")
        return "break"

    def _ensure_model_tags(self, full_catalog):
        for model in full_catalog:
            self.chat_log.tag_config(
                model["participant_id"], foreground=model["color"], font=("Segoe UI", 10, "bold")
            )

    def _insert_inline_formatted(self, text):
        """Handles **bold**, `inline code`, headers (# ...) and bullet
        lists (- ...) inside plain (non-fenced) text."""
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
        """Renders a reply: ```code blocks``` in monospace with a
        background, everything else with basic Markdown formatting
        (useful when the topic involves code or structured replies)."""
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
        self.export_log.append((speaker_label, tag, text.replace(_COST_MARKER, "\n\n")))

        body, _sep, cost_line = text.partition(_COST_MARKER)

        self.chat_log.config(state="normal")
        self.chat_log.insert("end", f"{speaker_label}\n", (tag,))
        self._insert_body_with_code(body)
        self.chat_log.insert("end", "\n")
        if cost_line:
            self.chat_log.insert("end", cost_line + "\n", ("cost_line",))
        self.chat_log.insert("end", "\n")
        self.chat_log.insert("end", "─" * 70 + "\n\n", ("separator",))
        self.chat_log.config(state="disabled")
        self.chat_log.see("end")

    # ---------- Export / copy ----------

    def _build_markdown_export(self):
        """Builds .md from the RAW messages (self.export_log), not from
        the widget's rendered text — the widget already replaces markdown
        syntax with visual tags (bold/code), so exporting from it gave
        "bare" text with no markup. Here the original reply text (with
        every **, ```, etc. exactly as the model wrote it) is just
        wrapped in headers — so the .md file opens with real formatting
        in any markdown viewer/editor."""
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
        """Plain .txt: the same raw messages, no markdown syntax (for
        people who don't specifically need .md)."""
        parts = []
        for speaker_label, _tag, text in self.export_log:
            parts.append(f"{speaker_label}\n{text}")
        return ("\n\n" + "-" * 60 + "\n\n").join(parts) + "\n"

    def _export_clicked(self):
        if not self.export_log:
            messagebox.showinfo(APP_TITLE, t("export_log_empty"))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[(t("markdown_filetype"), "*.md"), (t("text_filetype"), "*.txt"), (t("all_files_filetype"), "*.*")],
            title=t("export_dialog_title"),
        )
        if not path:
            return

        as_markdown = path.lower().endswith(".md")
        content = self._build_markdown_export() if as_markdown else self._build_plain_export()

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            messagebox.showerror(APP_TITLE, t("save_file_failed", error=e))
            return
        logger.info(t("log_export_done", path=path))
        self.status_var.set(t("exported_to", path=path))

    def _copy_all_clicked(self):
        content = self.chat_log.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_var.set(t("log_copied_to_clipboard"))

    # ---------- Start/stop session ----------

    def _intervene_clicked(self):
        self.intervene_requested = True
        self.intervene_button.config(state="disabled")
        self.status_var.set(t("intervene_pending_status"))
        logger.info(t("log_intervene_requested"))

    def _start_brainstorm(self):
        # Auto-save Settings first — the two tabs share the same
        # config_data dict, but only Settings' own widgets hold
        # whatever's currently typed there; without this, clicking
        # "Start" right after editing Settings (without remembering to
        # click "Save Settings" first) would silently start with the
        # OLD saved values instead. If the form doesn't validate (e.g.
        # a missing model ID), the warning is already shown by Settings'
        # own _save() — don't start with stale/inconsistent data either way.
        if self.save_settings_callback and not self.save_settings_callback():
            return

        api_key = self.config_data.get("api_key", "")
        full_catalog = build_full_catalog(self.config_data)
        topic = self.topic_text.get("1.0", "end").strip()
        if self.attached_image_data_url:
            # The moderator never sees the actual image (only participant
            # replies get the multi-part image content) — this note lets
            # it assign visually-relevant tasks anyway, e.g. "describe
            # what's shown", without literally seeing anything itself.
            topic += t("topic_image_attached_note")

        if not api_key:
            messagebox.showwarning(APP_TITLE, t("set_api_key_first"))
            return
        if self.config_data.get("api_provider") == "custom" and not self.config_data.get("custom_base_url", "").strip():
            messagebox.showwarning(APP_TITLE, t("enter_custom_url_first"))
            return
        if len(full_catalog) < MIN_MODELS:
            messagebox.showwarning(APP_TITLE, t("select_min_models_in_settings", min=MIN_MODELS))
            return
        if not topic:
            messagebox.showwarning(APP_TITLE, t("enter_topic_warning"))
            return

        self.chat_log.config(state="normal")
        self.chat_log.delete("1.0", "end")
        self.chat_log.config(state="disabled")
        self.export_log.clear()
        self._hide_input_panel()
        self._append_log(t("user_topic_label"), "user_note", topic)

        budget = float(self.config_data.get("session_budget_usd", 0.5))
        max_replies = self.max_replies_var.get()
        moderator_mode = self.config_data.get("moderator_mode", "ai")
        moderator_model = self.config_data.get("moderator_model", MODERATOR_DEFAULT_MODEL)
        user_participation = self.config_data.get("user_participation", False)
        moderator_summary = self.config_data.get("moderator_summary", False)
        moderator_web_lookup = self.config_data.get("moderator_web_lookup", False)
        current_provider = _resolve_provider(self.config_data)
        base_url = current_provider["base_url"]
        reasoning_format = current_provider.get("reasoning_format", "tokens")

        # Persist the current "max replies" value so it's picked up next
        # run too, same as other settings.
        self.config_data["max_replies"] = max_replies
        save_config(self.config_data)

        self._ensure_model_tags(full_catalog)

        currency = current_provider.get("currency", "USD")
        self.cost_var.set(t("spent_status", spent=format_money(0, currency), budget=format_money(budget, currency, decimals=2)))
        self.status_var.set(t("discussion_in_progress"))
        self.start_button.config(state="disabled")
        if moderator_mode == "human":
            # In human-moderator mode, the comment/end-session actions
            # already live in the speaker-selection panel — a separate
            # button would just be a confusing second way to do the same thing.
            self.intervene_button.config(state="disabled")
        else:
            self.intervene_button.config(state="normal")
        self.abort_requested = False
        self.intervene_requested = False

        logger.info(t(
            "log_session_started", topic=topic, count=len(full_catalog), mode=moderator_mode,
            max_replies=max_replies, budget=f"{budget:.2f}", summary=moderator_summary,
        ))

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(api_key, full_catalog, topic, max_replies, budget,
                  moderator_mode, moderator_model, user_participation, moderator_summary,
                  moderator_web_lookup, base_url, reasoning_format, self.attached_image_data_url),
            daemon=True,
        )
        self.worker_thread.start()

    def _get_spend_snapshot(self, api_key, provider):
        """Returns the current usage/balance indicator for end-of-session
        reconciliation, or None if unavailable (provider doesn't support
        it, or the snapshot request itself failed — a network hiccup
        here just means we skip showing "actually charged" at the end,
        not a session-ending error)."""
        if not provider.get("has_key_info"):
            return None
        try:
            info = get_key_info(
                api_key, base_url=provider["base_url"],
                key_info_path=provider.get("key_info_path", "/key"),
                key_info_format=provider.get("key_info_format", "openrouter"),
            )
        except OpenRouterError:
            return None
        if provider.get("key_info_format") == "polza":
            value = info.get("balance")
        else:
            value = info.get("usage")
        return value if isinstance(value, (int, float)) else None

    def _run_worker(self, api_key, full_catalog, topic, max_replies, budget,
                     moderator_mode, moderator_model, user_participation, moderator_summary,
                     moderator_web_lookup, base_url, reasoning_format, image_data_url):
        """Runs in the background thread — doesn't block the UI."""
        current_provider = _resolve_provider(self.config_data)
        currency = current_provider.get("currency", "USD")
        # Snapshotted now (before any requests go out) and again at the
        # very end — the difference is the REAL amount charged by the
        # provider, catching spend our own client-side tracking misses
        # entirely (e.g. a request that timed out on our side but still
        # got processed and billed on theirs). See _get_spend_snapshot.
        start_spend_snapshot = self._get_spend_snapshot(api_key, current_provider)
        transcript_lines = []
        total_cost = 0.0
        pending_moderator_cost = 0.0  # accumulates, shown together with the next visible reply
        replies_done = 0
        cost_unknown_calls = 0
        speak_counts = {p["participant_id"]: 0 for p in full_catalog}
        unavailable_until = {}  # model_id -> time.time() until which it's considered unavailable
        finish_reason = t("discussion_finished")

        def is_available(model_id):
            until = unavailable_until.get(model_id)
            return until is None or time.time() >= until

        def mark_unavailable(model_id, seconds=45):
            unavailable_until[model_id] = time.time() + seconds

        def pick_fallback_speaker(pool):
            pool = pool or full_catalog
            return min(pool, key=lambda p: speak_counts[p["participant_id"]])["participant_id"]

        def process_intervene_if_pending():
            """Checked both at the top of the loop AND right after the
            moderator's own decision call resolves (not just once per
            full iteration) — halves the worst-case wait before an
            intervention actually shows up, since a full iteration can
            otherwise involve TWO back-to-back blocking network calls
            (moderator decision, then participant reply) before this
            gets rechecked. Returns True if something was pending and
            got handled — the caller should `continue` the loop right after."""
            if not self.intervene_requested:
                return False
            self.intervene_requested = False
            resp = self._sync_ui_request("intervene")
            # Handled either way (submitted or closed) — button becomes
            # clickable again now that the request is no longer queued.
            self.after(0, lambda: self.intervene_button.config(state="normal"))
            if not resp or resp.get("action") == "end":
                self.abort_requested = True
                return True
            clarification = (resp.get("text") or "").strip()
            if clarification:
                transcript_lines.append(t("user_clarification_transcript", text=clarification))
                self.ui_queue.put(("message", t("user_label"), "user_note", clarification))
            return True

        just_invited_user = False  # prevents the moderator from inviting
                                    # the user two turns in a row — user
                                    # turns don't count toward replies_done,
                                    # so without this the AI moderator could
                                    # keep picking "user" forever with no
                                    # natural stopping condition ever hit.
        last_speaker_id = None  # the most recent participant with a
                                    # successful, visible reply — excluded
                                    # from the very next pick so the same
                                    # model never appears twice in a row.
                                    # This also covers the case where the
                                    # turn in between silently failed (a
                                    # 429, etc.), which would otherwise let
                                    # the same model get picked again right
                                    # after itself with nothing in between.
        loop_guard = 0
        loop_guard_limit = max(max_replies * 4, 40)  # absolute safety net:
                                    # guarantees the loop terminates even
                                    # under some other, unforeseen pathological
                                    # moderator behavior.

        if moderator_web_lookup:
            self.ui_queue.put(("status", t("status_web_lookup"), None, None))
            try:
                lookup_text, lookup_usage = ask_moderator_web_lookup(
                    api_key, moderator_model, topic, base_url=base_url, reasoning_format=reasoning_format,
                )
                lookup_cost = lookup_usage.get("cost")
                lookup_shown = lookup_text
                if isinstance(lookup_cost, (int, float)):
                    total_cost += lookup_cost
                    lookup_shown += f"{_COST_MARKER}{t('cost_line_web_lookup', cost=format_money(lookup_cost, currency))}"
                model_short = short_model_name(moderator_model)
                self.ui_queue.put((
                    "message", t("web_lookup_label", model=model_short), "web_lookup", lookup_shown,
                ))
                self.ui_queue.put(("cost", format_money(total_cost, currency), format_money(budget, currency, decimals=2), None))
                # Folded into the transcript (not just shown once in chat)
                # so every participant sees it from their very first reply.
                transcript_lines.append(t("web_lookup_transcript_entry", text=lookup_text))
            except OpenRouterError as e:
                logger.warning(t("log_web_lookup_failed", error=e))

        while True:
            loop_guard += 1
            if loop_guard > loop_guard_limit:
                finish_reason = t("safety_loop_limit_reached")
                break
            if total_cost >= budget:
                finish_reason = t("budget_limit_reached", budget=format_money(budget, currency, decimals=2))
                break
            if replies_done >= max_replies:
                finish_reason = t("reply_limit_reached", max_replies=max_replies)
                break
            if self.abort_requested:
                finish_reason = t("session_ended_by_user")
                break

            if process_intervene_if_pending():
                continue

            transcript = "\n".join(transcript_lines) if transcript_lines else t("discussion_just_starting")
            available_participants = [p for p in full_catalog if is_available(p["id"])] or full_catalog
            is_final_reply = (replies_done == max_replies - 1)

            # --- pick the next speaker ---
            task, reaction_type, wrap_up = "", "", False

            if moderator_mode == "human":
                status_text = (
                    t("final_reply_status_human") if is_final_reply else t("your_turn_status_human")
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
                    transcript_lines.append(t("user_comment_transcript", comment=comment))
                    self.ui_queue.put(("message", t("user_label"), "user_note", comment))

                next_id = resp.get("next")
                if next_id is None:
                    continue
                if is_final_reply:
                    task = t("final_summary_task")
                    wrap_up = True
            else:
                self.ui_queue.put(("status", t("moderator_choosing_status"), None, None))
                effective_allow_user = user_participation and not just_invited_user

                # Excluded here (AI-mode only) so the moderator can't
                # immediately repeat whoever just spoke — including when
                # a turn in between silently failed. A human moderator
                # isn't restricted this way; repeating a speaker on
                # purpose is their call, not an oversight to guard against.
                ai_candidate_pool = available_participants
                if last_speaker_id is not None:
                    without_last_speaker = [
                        p for p in available_participants if p["participant_id"] != last_speaker_id
                    ]
                    if without_last_speaker:
                        ai_candidate_pool = without_last_speaker

                try:
                    decision, mod_usage = ask_moderator(
                        api_key, moderator_model, topic, transcript, ai_candidate_pool,
                        effective_allow_user, replies_done, max_replies, is_final_reply,
                        base_url=base_url, reasoning_format=reasoning_format,
                    )
                except OpenRouterError as e:
                    logger.error(t("log_moderator_error", error=e))
                    decision, mod_usage = {"next": None, "task": "", "reason": "", "reaction_type": "", "wrap_up": False}, {}

                mod_cost = mod_usage.get("cost") if mod_usage else None
                if isinstance(mod_cost, (int, float)):
                    total_cost += mod_cost
                    pending_moderator_cost += mod_cost
                    self.ui_queue.put(("cost", format_money(total_cost, currency), format_money(budget, currency, decimals=2), None))

                next_id = decision["next"]
                task, reaction_type, wrap_up = decision["task"], decision["reaction_type"], decision["wrap_up"]

                if next_id is None:
                    next_id = pick_fallback_speaker(ai_candidate_pool)
                    logger.info(t("log_moderator_fallback", id=next_id))

                # Guarantee a wrap-up on the last reply even if the
                # moderator ignored wrap_up in its response — don't rely
                # solely on it following the prompt.
                if is_final_reply:
                    wrap_up = True
                    if not task:
                        task = t("final_summary_task")

            # Second check point — the moderator's decision call above
            # (or the human "choose speaker" wait) has just resolved, but
            # the participant reply call below is ANOTHER full blocking
            # network call. Checking again here — not just once at the
            # very top of the loop — means an intervention doesn't have
            # to wait through both back-to-back before it's noticed.
            if process_intervene_if_pending():
                continue

            if next_id == "user":
                just_invited_user = True
                self.ui_queue.put(("status", t("moderator_passed_floor_status"), None, None))
                user_reply = self._sync_ui_request("user_turn")
                if user_reply:
                    transcript_lines.append(t("user_reply_transcript", reply=user_reply))
                    self.ui_queue.put(("message", t("user_label"), "user_note", user_reply))
                continue  # user replies don't count toward the reply limit/budget

            just_invited_user = False

            model_info = find_in_catalog(next_id, full_catalog)
            if model_info is None:
                logger.warning(t("log_unknown_model_chosen", id=next_id))
                continue

            label = model_info["label"]
            persona = model_info["persona"]
            reasoning_max_tokens = model_info.get("reasoning_max_tokens")
            reasoning_raw = model_info.get("reasoning_raw")

            self.ui_queue.put(("status", t("model_preparing_status", label=label), None, None))

            guidance = ""
            if task:
                guidance += t("moderator_task_guidance", task=task)
            if reaction_type:
                guidance += t("moderator_reaction_guidance", reaction_type=reaction_type)
            if wrap_up:
                guidance += t("wrap_up_guidance")

            user_prompt = t(
                "participant_user_prompt", topic=topic, transcript=transcript, guidance=guidance,
            )

            try:
                reply, usage = ask_model(
                    api_key, model_info["id"], persona, user_prompt,
                    reasoning_max_tokens=reasoning_max_tokens, base_url=base_url,
                    reasoning_format=reasoning_format, reasoning_raw=reasoning_raw,
                    image_data_url=image_data_url,
                )
            except OpenRouterError as e:
                # Not shown in chat — the moderator will just pick someone
                # else right away, and the reason stays visible in the "Log" tab.
                logger.warning(t("log_model_unavailable", id=next_id, error=e))
                # Real model id, not participant_id — if this model is
                # rate-limited/erroring, EVERY duplicate slot using the
                # same underlying model shares that same cooldown, not
                # just the one that happened to be picked this time.
                mark_unavailable(model_info["id"])
                transcript_lines.append(t("transcript_skipped_unavailable", label=label))
                continue

            cost = usage.get("cost")
            if isinstance(cost, (int, float)):
                total_cost += cost
                if pending_moderator_cost > 0:
                    display_cost = cost + pending_moderator_cost
                    cost_line = t(
                        "cost_line_with_moderator",
                        cost=format_money(cost, currency), mod=format_money(pending_moderator_cost, currency),
                        total=format_money(display_cost, currency),
                    )
                else:
                    cost_line = t("cost_line", cost=format_money(cost, currency))
                pending_moderator_cost = 0.0
                reply_shown = f"{reply}{_COST_MARKER}{cost_line}"
            else:
                cost_unknown_calls += 1
                reply_shown = reply

            speak_counts[next_id] = speak_counts.get(next_id, 0) + 1
            replies_done += 1
            last_speaker_id = next_id

            self.ui_queue.put(("message", label, next_id, reply_shown))
            self.ui_queue.put(("cost", format_money(total_cost, currency), format_money(budget, currency, decimals=2), None))
            transcript_lines.append(t("transcript_reply_line", label=label, reply=reply))

        if moderator_summary and transcript_lines:
            self.ui_queue.put(("status", t("status_moderator_summarizing"), None, None))
            transcript = "\n".join(transcript_lines)
            summary_system = t("moderator_summary_system_prompt")
            summary_user = t("moderator_summary_user_prompt", topic=topic, transcript=transcript)
            try:
                summary_text, summary_usage = ask_model(
                    api_key, moderator_model, summary_system, summary_user,
                    max_tokens=500, reasoning_max_tokens=None, base_url=base_url,
                    reasoning_format=reasoning_format,
                )
                summary_cost = summary_usage.get("cost")
                if isinstance(summary_cost, (int, float)):
                    total_cost += summary_cost
                    summary_text += f"{_COST_MARKER}{t('cost_line_summary', cost=format_money(summary_cost, currency))}"
                    self.ui_queue.put(("cost", format_money(total_cost, currency), format_money(budget, currency, decimals=2), None))
                model_short = short_model_name(moderator_model)
                self.ui_queue.put((
                    "message", t("moderator_summary_label", model=model_short), "summary", summary_text,
                ))
            except OpenRouterError as e:
                logger.warning(t("log_summary_failed", error=e))

        if cost_unknown_calls and current_provider.get("has_cost_tracking", True):
            finish_reason += t("unknown_cost_note", count=cost_unknown_calls)

        # Reconcile against the provider's own records, if possible —
        # catches spend our client-side tracking missed (e.g. requests
        # that errored/timed out on our end but were still processed
        # and billed on theirs). Silently skipped if either snapshot
        # failed or wasn't available.
        end_spend_snapshot = self._get_spend_snapshot(api_key, current_provider)
        if start_spend_snapshot is not None and end_spend_snapshot is not None:
            key_info_format = current_provider.get("key_info_format", "openrouter")
            if key_info_format == "polza":
                # Prepaid balance — spending DECREASES it.
                actual_spent = start_spend_snapshot - end_spend_snapshot
            else:
                # OpenRouter-style cumulative usage — spending INCREASES it.
                actual_spent = end_spend_snapshot - start_spend_snapshot
            finish_reason += t(
                "cost_reconciliation_note",
                tracked=format_money(total_cost, currency), actual=format_money(actual_spent, currency),
            )

        logger.info(t("log_session_finished", reason=finish_reason, total=format_money(total_cost, currency)))
        self.ui_queue.put(("finished", finish_reason, None, None))

    def _poll_queue(self):
        """Periodically checks the message queue from the background worker."""
        try:
            while True:
                kind, label, tag, text = self.ui_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(label)
                elif kind == "message":
                    self._append_log(label, tag, text)
                elif kind == "error":
                    self._append_log(t("error_speaker_suffix", label=label), "error", text)
                elif kind == "cost":
                    spent, budget_str = label, tag
                    self.cost_var.set(t("spent_status", spent=spent, budget=budget_str))
                elif kind == "ui_request":
                    self._show_input_panel(mode=label, payload=tag)
                elif kind == "finished":
                    self._append_log(t("system_label"), "system", label)
                    self.status_var.set(t("discussion_finished"))
                    self.start_button.config(state="normal")
                    self.intervene_button.config(state="disabled")
                    self._hide_input_panel()
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # Language must be loaded before ANY widget that calls t() is
        # built — including LogTab below. Bootstraps locale files on
        # first run, falls back to English if the saved code is missing
        # (e.g. a custom language file was deleted), and persists that
        # fallback so it's remembered next time.
        saved_lang = get_language_code()
        applied_lang = i18n.load_language(saved_lang)
        language_fallback_happened = applied_lang != saved_lang
        if language_fallback_happened:
            set_language_code(applied_lang)

        # Theme must also be applied before any widgets are built —
        # ttk.Style() is global, so this colors every ttk widget created
        # from this point on automatically.
        theme.apply_theme(self, get_theme_code())

        self.title(WINDOW_TITLE)

        # Layout-independent Ctrl+C/V/X/A for every Entry/Combobox/
        # Spinbox/Text in the whole app at once — one registration here
        # covers all current AND future widgets of these classes,
        # including ones created after tab rebuilds (theme/profile/
        # language switches), no per-widget wiring needed.
        for widget_class in ("TEntry", "TCombobox", "TSpinbox", "Text"):
            self.bind_class(widget_class, "<Control-Key>", _GENERIC_EDITABLE_HOTKEYS)

        icon_path = _resource_path("favicon.ico")
        if os.path.exists(icon_path):
            try:
                # default=... applies the icon not just to this window but
                # as the default for all subsequent app windows (e.g.
                # simpledialog) — also more reliable for the Windows taskbar.
                self.iconbitmap(default=icon_path)
            except tk.TclError as e:
                logger.warning("Could not set the window icon: %s", e)

            if sys.platform.startswith("win"):
                def _apply_taskbar_icon():
                    self.update_idletasks()  # make sure the HWND actually exists yet
                    try:
                        # Keep a reference on self — handles aren't regular
                        # Python objects, but hold on to them anyway for safety.
                        self._windows_icons = _set_windows_taskbar_icon(
                            self.winfo_id(), icon_path
                        )
                        logger.debug("WinAPI icon (16px/256px) applied to the window")
                    except OSError as e:
                        logger.warning("Could not apply the WinAPI icon: %s", e)

                # after(...) on top of update_idletasks(): on some Windows/DWM
                # builds the icon sticks better once the window has painted
                # once, rather than sending WM_SETICON right at creation.
                self.after(200, _apply_taskbar_icon)

        self.geometry("1060x780")
        self.minsize(900, 560)

        self.config_data = load_config()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # The "Log" tab is created once and lives for the whole app
        # session (just shown/hidden via notebook.add/forget) — so
        # accumulated log history isn't lost when toggling visibility.
        self.log_tab = LogTab(self.notebook)
        self._log_handler = QueueLogHandler(self.log_tab.ui_queue)
        logger.addHandler(self._log_handler)

        if language_fallback_happened:
            logger.info(t("log_language_fallback", saved=saved_lang, applied=applied_lang))

        self._build_tabs()

    def _build_tabs(self):
        self.chat_tab = ChatTab(
            self.notebook, self.config_data,
            save_settings_callback=lambda: self.settings_tab._save(),
        )
        self.settings_tab = SettingsTab(
            self.notebook, self.config_data,
            on_saved=self._on_settings_saved,
            on_profile_switched=self._on_profile_switched,
        )

        self.notebook.add(self.settings_tab, text=t("tab_settings"))
        self.notebook.add(self.chat_tab, text=t("tab_chat"))

        self._apply_debug_visibility()

        if not self.config_data.get("api_key"):
            self.notebook.select(self.settings_tab)

    def _apply_debug_visibility(self):
        enabled = get_debug_tab_enabled()
        is_shown = str(self.log_tab) in self.notebook.tabs()
        if enabled and not is_shown:
            self.notebook.add(self.log_tab, text=t("tab_log"))
        elif not enabled and is_shown:
            self.notebook.forget(self.log_tab)

    def _on_settings_saved(self):
        # Settings live in the shared self.config_data dict, already used
        # by the chat tab — nothing else to sync. The "Log" tab's
        # visibility may have changed, though — apply that.
        self._apply_debug_visibility()

    def _on_profile_switched(self):
        """Called by SettingsTab after loading/deleting a profile, or
        after switching the UI language or theme — either way,
        self.config_data (or i18n's/theme's active state) has already
        changed, but existing widgets were built against the old values
        and won't update themselves. Simplest and safest: rebuild the
        tabs from scratch."""
        self.notebook.forget(self.settings_tab)
        self.notebook.forget(self.chat_tab)
        if str(self.log_tab) in self.notebook.tabs():
            self.notebook.forget(self.log_tab)
        self.settings_tab.destroy()
        self.chat_tab.destroy()

        # LogTab is a singleton (kept alive across rebuilds to preserve
        # its history), so it isn't recreated above — its plain tk.Text
        # widget needs an explicit recolor if the theme just changed.
        theme.apply_text_widget_theme(self.log_tab.log_text, get_theme_code())

        self._build_tabs()


if __name__ == "__main__":
    app = App()
    app.mainloop()
