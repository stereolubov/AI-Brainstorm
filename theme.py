# -*- coding: utf-8 -*-
"""
Design tokens, fonts and ttk styling.

The palettes below are lifted value-for-value from the reference design
(project/AI Brainstorm.dc.html, screens 1a-1c dark / 2a-2c light) rather
than invented here, so "does this match the mockup" is answerable by
diffing hex strings instead of by eye.

Built on ttk's "clam" base theme — unlike platform-native themes
(e.g. "vista"/"winnative" on Windows), "clam" actually respects custom
style colors instead of ignoring them in favor of native OS chrome.

Three things Tk cannot do that the mockup uses freely: rounded corners,
drop shadows and gradients. Everything here is therefore square-edged;
the design survives that better than it survives wrong colors, so the
palette and the type scale are what this module spends its effort on.

Widgets that aren't ttk (tk.Text, tk.Canvas) don't follow ttk.Style()
and have to be recolored one at a time — see apply_text_widget_theme()
and apply_canvas_theme().
"""

import logging
import os
import sys

logger = logging.getLogger("ai_brainstorm.theme")

DEFAULT_THEME_CODE = "light"
THEME_CODES = ["light", "dark"]


# ---------------------------------------------------------------- palettes

# Key names ending in _bg/_fg/_border say where the value belongs, so a
# token can be traced back to the mockup element it came from. The first
# block of each palette (window_bg..accent) is the original, smaller key
# set the app was written against — kept verbatim so every existing
# `get_palette(code)["muted_fg"]` call site keeps working unchanged.
THEMES = {
    "light": {
        # --- original keys ---
        "window_bg": "#f4f5f7",
        "surface_bg": "#ffffff",
        "fg": "#16181d",
        "muted_fg": "#6a7080",
        "entry_bg": "#ffffff",
        "button_bg": "#f1f3f6",
        "button_active_bg": "#e8ebef",
        "select_bg": "#dfe3fb",
        "border": "#e3e6ec",
        "separator": "#eceef2",
        "code_bg": "#f6f7f9",
        "accent": "#D97757",

        # --- surfaces ---
        "card_bg": "#ffffff",
        "card_border": "#e3e6ec",
        "card_nested_bg": "#fafbfc",
        "chrome_bg": "#f7f8fa",
        "chrome_border": "#e6e8ee",

        # --- text ---
        "heading_fg": "#16181d",
        "body_fg": "#33384a",
        "label_fg": "#6a7080",
        "strong_fg": "#2b3038",
        "faint_fg": "#9aa0ad",
        "mono_fg": "#8a90a0",

        # --- inputs ---
        "input_bg": "#ffffff",
        "input_border": "#d6dae2",
        "input_fg": "#1b1d22",

        # --- buttons ---
        "btn_bg": "#f1f3f6",
        "btn_border": "#d9dde4",
        "btn_fg": "#3c414d",
        "btn_hover_bg": "#e8ebef",
        "ghost_bg": "#ffffff",
        "ghost_border": "#d9dde4",
        "ghost_fg": "#5c6272",
        "accent_fg": "#2b1409",       # near-black on orange: the mockup never uses white here
        "accent_hover": "#c96a4b",
        "danger_border": "#ebd0c9",
        "danger_fg": "#a8462f",

        # --- status ---
        "success": "#10A37F",
        "success_fg": "#1c6b52",
        "code_border": "#e0e3e9",
        "code_fg": "#2f5c4e",

        # --- chat ---
        "user_msg_bg": "#eef0fd",
        "user_msg_edge": "#7C8CF8",
        "msg_bg": "#ffffff",
        "msg_divider": "#eceef2",
        "send_bg": "#4550b8",
        "send_fg": "#ffffff",

        # --- tab strip ---
        "tab_bg": "#ffffff",
        "tab_active_fg": "#16181d",
        "tab_inactive_fg": "#767d90",
        "tab_indicator": "#16181d",

        # --- scrollbar ---
        "scroll_thumb": "#c9ced8",
        "scroll_thumb_active": "#b0b6c2",
        "scroll_trough": "#f4f5f7",

        # --- segmented control ---
        "seg_bg": "#f1f3f6",
        "seg_border": "#d9dde4",
        "seg_active_bg": "#ffffff",
        "seg_active_fg": "#16181d",
        "seg_inactive_fg": "#6a7080",
    },
    "dark": {
        # --- original keys ---
        "window_bg": "#0f1116",
        "surface_bg": "#161920",
        "fg": "#eceef3",
        "muted_fg": "#8b91a4",
        "entry_bg": "#1d212a",
        "button_bg": "#1d212a",
        "button_active_bg": "#242832",
        "select_bg": "#2b3050",
        "border": "#242832",
        "separator": "#1f232c",
        "code_bg": "#15181f",
        "accent": "#D97757",

        # --- surfaces ---
        "card_bg": "#161920",
        "card_border": "#242832",
        "card_nested_bg": "#1a1d25",
        "chrome_bg": "#171a21",
        "chrome_border": "#23262f",

        # --- text ---
        "heading_fg": "#eceef3",
        "body_fg": "#cfd3dd",
        "label_fg": "#8b91a4",
        "strong_fg": "#d3d7e2",
        "faint_fg": "#5f6576",
        "mono_fg": "#6f7688",

        # --- inputs ---
        "input_bg": "#1d212a",
        "input_border": "#2a2e39",
        "input_fg": "#e3e6ee",

        # --- buttons ---
        "btn_bg": "#1d212a",
        "btn_border": "#2c313d",
        "btn_fg": "#d3d7e2",
        "btn_hover_bg": "#242832",
        "ghost_bg": "#12141a",        # the mockup says transparent; Tk has no transparency,
                                       # so this is the window color showing "through"
        "ghost_border": "#2a2e39",
        "ghost_fg": "#9aa1b3",
        "accent_fg": "#1a0f0a",
        "accent_hover": "#e8896a",
        "danger_border": "#33262a",
        "danger_fg": "#c98070",

        # --- status ---
        "success": "#10A37F",
        "success_fg": "#7fbfa9",
        "code_border": "#262a35",
        "code_fg": "#a9c7bd",

        # --- chat ---
        "user_msg_bg": "#161824",     # mockup's rgba(124,140,248,0.06) flattened onto #0f1116
        "user_msg_edge": "#7C8CF8",
        "msg_bg": "#0f1116",
        "msg_divider": "#1f232c",
        "send_bg": "#7C8CF8",
        "send_fg": "#0d1024",

        # --- tab strip ---
        "tab_bg": "#12141a",
        "tab_active_fg": "#eceef3",
        "tab_inactive_fg": "#767d90",
        "tab_indicator": "#eceef3",

        # --- scrollbar ---
        "scroll_thumb": "#2c313d",
        "scroll_thumb_active": "#3a4050",
        "scroll_trough": "#12141a",

        # --- segmented control ---
        "seg_bg": "#1a1d25",
        "seg_border": "#2a2e39",
        "seg_active_bg": "#2c313d",
        "seg_active_fg": "#f0f2f7",
        "seg_inactive_fg": "#787f91",
    },
}


# Log-row badge colors, keyed by logging level name. The mockup's badges
# are per-event-type (СЕССИЯ/ЗАПРОС/ОТВЕТ/ПОВТОР/ОШИБКА); the app only
# has log levels to go on, so these map level -> the nearest mockup badge.
LOG_BADGES = {
    "light": {
        "DEBUG":    ("#eceef2", "#4c525f"),
        "INFO":     ("#e8ebfd", "#4550b8"),
        "WARNING":  ("#fbf1d9", "#87651a"),
        "ERROR":    ("#fbe7e2", "#a24632"),
        "CRITICAL": ("#fbe7e2", "#a24632"),
    },
    "dark": {
        "DEBUG":    ("#1f232d", "#9aa1b3"),
        "INFO":     ("#2b3050", "#a8b3fb"),
        "WARNING":  ("#3a3524", "#d8c078"),
        "ERROR":    ("#3a2626", "#e08c7a"),
        "CRITICAL": ("#3a2626", "#e08c7a"),
    },
}


def get_palette(code):
    return THEMES.get(code, THEMES[DEFAULT_THEME_CODE])


def log_badge(code, level_name):
    table = LOG_BADGES.get(code, LOG_BADGES[DEFAULT_THEME_CODE])
    return table.get(level_name, table["DEBUG"])


# ------------------------------------------------------------------ fonts

# The mockup is set in Manrope (UI) and JetBrains Mono (code, IDs, money
# and timestamps). Neither ships with Windows, so both are bundled as
# .ttf files and registered into this process only — see
# register_bundled_fonts(). If that fails for any reason the app falls
# back to the closest thing Windows does have and keeps working; nothing
# here is allowed to be fatal.
FONT_DIR_NAME = "fonts"
# Only these three. A Tk font spec has exactly two weights, "normal" and
# "bold", so the design's SemiBold and ExtraBold are unreachable no
# matter how many files get shipped — and italic (used for the cost
# line) is left to GDI's own slant, which costs nothing and reads fine
# at 8pt. Three files instead of six, ~560 KB instead of ~1.1 MB.
BUNDLED_FONT_FILES = (
    "Manrope-Regular.ttf",
    "Manrope-Bold.ttf",
    "JetBrainsMono-Regular.ttf",
)

UI_FAMILY_PREFERRED = "Manrope"
UI_FAMILY_FALLBACK = "Segoe UI"
MONO_FAMILY_PREFERRED = "JetBrains Mono"
MONO_FAMILY_FALLBACK = "Consolas"

# Resolved by resolve_font_families() once a Tk interpreter exists.
UI_FAMILY = UI_FAMILY_FALLBACK
MONO_FAMILY = MONO_FAMILY_FALLBACK

_registered_font_paths = []


def _font_dir():
    """Where the .ttf files live — next to this module when running from
    source, inside PyInstaller's extraction dir when frozen."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, FONT_DIR_NAME)


def register_bundled_fonts():
    """Makes the bundled .ttf files loadable by name, for this process
    only — nothing is installed into Windows and nothing needs admin.

    MUST be called BEFORE the Tk root is created: Tk snapshots the
    available font families when the interpreter starts, so a font added
    afterwards is invisible to it even though GDI itself can see it.

    No-op off Windows (Tk finds fonts through fontconfig there, which
    this would not affect) and on any failure — the app then renders in
    the fallback families, which is a cosmetic downgrade, not a break.
    """
    if not sys.platform.startswith("win"):
        return 0

    directory = _font_dir()
    if not os.path.isdir(directory):
        logger.debug("No bundled font directory at %s — using system fonts", directory)
        return 0

    try:
        import ctypes
        add_font = ctypes.windll.gdi32.AddFontResourceExW
    except (ImportError, AttributeError, OSError) as e:
        logger.warning("Cannot reach AddFontResourceExW, using system fonts: %s", e)
        return 0

    FR_PRIVATE = 0x10
    loaded = 0
    for filename in BUNDLED_FONT_FILES:
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            logger.debug("Bundled font missing: %s", filename)
            continue
        try:
            if add_font(path, FR_PRIVATE, 0) > 0:
                _registered_font_paths.append(path)
                loaded += 1
            else:
                logger.debug("AddFontResourceExW refused %s", filename)
        except OSError as e:
            logger.debug("AddFontResourceExW failed on %s: %s", filename, e)

    logger.debug("Registered %d/%d bundled fonts", loaded, len(BUNDLED_FONT_FILES))
    return loaded


def resolve_font_families(root):
    """Decides what UI_FAMILY/MONO_FAMILY actually are, now that there's
    a Tk interpreter to ask. Called once from apply_theme().

    Registration succeeding is not proof Tk can see the family (see the
    ordering note in register_bundled_fonts), so this asks Tk directly
    rather than trusting the earlier return value."""
    global UI_FAMILY, MONO_FAMILY
    try:
        from tkinter import font as tkfont
        available = {name.lower() for name in tkfont.families(root)}
    except Exception as e:  # any Tk hiccup here must not stop startup
        logger.debug("Could not enumerate font families: %s", e)
        return

    UI_FAMILY = (UI_FAMILY_PREFERRED if UI_FAMILY_PREFERRED.lower() in available
                 else UI_FAMILY_FALLBACK)
    MONO_FAMILY = (MONO_FAMILY_PREFERRED if MONO_FAMILY_PREFERRED.lower() in available
                   else MONO_FAMILY_FALLBACK)
    logger.debug("Fonts resolved: UI=%s, mono=%s", UI_FAMILY, MONO_FAMILY)


# Type scale. The mockup is specified in CSS pixels; these are Tk point
# sizes, which is what lets the UI scale with the system DPI setting
# instead of turning to ants on a 150% display. Roughly px * 0.75.
#   micro 11px | small 12-12.5px | base 13.5-14px | section 15px
FONT_SIZES = {"micro": 8, "small": 9, "base": 10, "section": 11}


def font(role):
    """Named font roles, so sizes and weights live in one place instead
    of being spelled out at every widget."""
    ui, mono = UI_FAMILY, MONO_FAMILY
    return {
        "body":        (ui, FONT_SIZES["base"]),
        "body_bold":   (ui, FONT_SIZES["base"], "bold"),
        "section":     (ui, FONT_SIZES["section"], "bold"),
        "speaker":     (ui, FONT_SIZES["base"], "bold"),
        "label":       (ui, FONT_SIZES["small"], "bold"),
        "small":       (ui, FONT_SIZES["small"]),
        "tab":         (ui, FONT_SIZES["base"]),
        "tab_active":  (ui, FONT_SIZES["base"], "bold"),
        "mono":        (mono, FONT_SIZES["small"]),
        "mono_micro":  (mono, FONT_SIZES["micro"]),
        "code":        (mono, FONT_SIZES["small"]),
        "cost":        (mono, FONT_SIZES["micro"], "italic"),
    }[role]


# ----------------------------------------------------------- check indicator

# clam draws a selected checkbutton as an ✗, which on an orange fill
# reads as "error" rather than "on" — the opposite of what the design
# means. There is no option to change that glyph: it's drawn in C.
#
# So the indicator is replaced with a pair of generated images. Doing it
# at the STYLE level rather than with a custom widget is what keeps every
# existing ttk.Checkbutton call site working untouched.
_CHECK_BOX_SIZE = 15
_check_image_cache = {}   # PhotoImages die when garbage collected — hold on to them
_check_element_seq = 0


def _segment_distance(px, py, ax, ay, bx, by):
    """Distance from a point to a line segment, for drawing the tick."""
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    nearest_x, nearest_y = ax + t * dx, ay + t * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def _make_check_image(root, fill, border, tick=None):
    """A checkbox indicator as a flat PhotoImage: 1px border, solid fill,
    and — when `tick` is given — a two-stroke checkmark drawn by testing
    each pixel's distance to the stroke path."""
    from tkinter import PhotoImage

    size = _CHECK_BOX_SIZE
    image = PhotoImage(master=root, width=size, height=size)
    # Stroke path, in pixel coordinates inside the box.
    ax, ay = 3.0, 7.6
    bx, by = 6.1, 10.5
    cx, cy = 11.4, 4.3

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            on_edge = x == 0 or y == 0 or x == size - 1 or y == size - 1
            color = border if on_edge else fill
            if tick and not on_edge:
                near = min(_segment_distance(x, y, ax, ay, bx, by),
                            _segment_distance(x, y, bx, by, cx, cy))
                if near <= 1.15:
                    color = tick
            row.append(color)
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows))
    return image


def _install_check_indicator(root, style, palette):
    """Swaps clam's indicator element for the generated images.

    A new element name is minted each time because ttk has no way to
    redefine or remove an existing element — and this runs again on
    every theme switch.
    """
    global _check_element_seq

    try:
        unchecked = _make_check_image(root, palette["input_bg"], palette["input_border"])
        checked = _make_check_image(root, palette["accent"], palette["accent"],
                                     tick=palette["accent_fg"])
        disabled = _make_check_image(root, palette["card_nested_bg"], palette["input_border"])
    except Exception as e:
        logger.debug("Could not generate check indicator images: %s", e)
        return

    _check_element_seq += 1
    name = f"AIBCheck{_check_element_seq}.indicator"
    _check_image_cache[name] = (unchecked, checked, disabled)

    try:
        style.element_create(
            name, "image", checked,
            ("disabled", disabled), ("!selected", unchecked),
            sticky="", border=0, padding=0,
        )
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                (name, {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
    except Exception as e:
        # Falls back to clam's own indicator — wrong glyph, right colors.
        logger.debug("Could not install check indicator element: %s", e)
        _check_image_cache.pop(name, None)


# ------------------------------------------------------------------ styles

def apply_theme(root, code):
    """Applies the palette to every ttk widget app-wide via ttk.Style(),
    plus the root window's own background.

    `root` can be ANY widget belonging to the app's Tk interpreter (not
    necessarily the literal tk.Tk() instance) — ttk.Style() only needs
    it to find the interpreter. But plain-tk's "-bg" option isn't
    supported by ttk widgets (e.g. calling this from inside a
    ttk.Frame with `self` would crash with "unknown option -bg"), so we
    resolve the actual toplevel window before touching that option.
    """
    from tkinter import ttk

    resolve_font_families(root)

    p = get_palette(code)
    style = ttk.Style(root)
    style.theme_use("clam")  # the only bundled theme that reliably honors custom colors on Windows

    root.winfo_toplevel().configure(bg=p["window_bg"])

    # ---- base ----
    style.configure(".", background=p["card_bg"], foreground=p["heading_fg"],
                     fieldbackground=p["input_bg"], font=font("body"),
                     borderwidth=0, focuscolor=p["accent"])

    # ---- frames ----
    style.configure("TFrame", background=p["card_bg"])
    style.configure("App.TFrame", background=p["window_bg"])
    style.configure("Card.TFrame", background=p["card_bg"])
    style.configure("CardNested.TFrame", background=p["card_nested_bg"])
    style.configure("Chrome.TFrame", background=p["chrome_bg"])
    style.configure("Tabs.TFrame", background=p["tab_bg"])
    style.configure("Msg.TFrame", background=p["msg_bg"])
    style.configure("MsgUser.TFrame", background=p["user_msg_bg"])
    # 2px accent stripes down the left edge of a chat message, and the
    # 1px rules between cards. Color is set per-instance by the caller.
    style.configure("Edge.TFrame", background=p["accent"])
    style.configure("Divider.TFrame", background=p["msg_divider"])

    style.configure("TLabelframe", background=p["card_bg"], foreground=p["heading_fg"],
                     bordercolor=p["card_border"], borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=p["card_bg"], foreground=p["heading_fg"],
                     font=font("section"))

    # ---- labels ----
    style.configure("TLabel", background=p["card_bg"], foreground=p["heading_fg"], font=font("body"))
    style.configure("Muted.TLabel", background=p["card_bg"], foreground=p["muted_fg"], font=font("small"))
    style.configure("Section.TLabel", background=p["card_bg"], foreground=p["heading_fg"], font=font("section"))
    style.configure("CardNum.TLabel", background=p["card_bg"], foreground=p["mono_fg"], font=font("mono_micro"))
    style.configure("FieldLabel.TLabel", background=p["card_bg"], foreground=p["label_fg"], font=font("label"))
    style.configure("Mono.TLabel", background=p["card_bg"], foreground=p["mono_fg"], font=font("mono"))
    style.configure("Faint.TLabel", background=p["card_bg"], foreground=p["faint_fg"], font=font("small"))
    style.configure("Success.TLabel", background=p["card_bg"], foreground=p["success_fg"], font=font("mono"))
    style.configure("Danger.TLabel", background=p["card_bg"], foreground=p["danger_fg"], font=font("small"))
    # Same labels again, for use on the window background rather than on a card.
    for suffix, bg in (("OnApp", p["window_bg"]), ("OnChrome", p["chrome_bg"]),
                        ("OnNested", p["card_nested_bg"])):
        style.configure(f"{suffix}.TLabel", background=bg, foreground=p["heading_fg"], font=font("body"))
        style.configure(f"Muted{suffix}.TLabel", background=bg, foreground=p["muted_fg"], font=font("small"))
        style.configure(f"Mono{suffix}.TLabel", background=bg, foreground=p["mono_fg"], font=font("mono"))
        style.configure(f"FieldLabel{suffix}.TLabel", background=bg, foreground=p["label_fg"], font=font("label"))
        style.configure(f"Success{suffix}.TLabel", background=bg, foreground=p["success_fg"], font=font("mono"))

    # ---- check / radio ----
    # clam's indicator is filled from -indicatorcolor, NOT from
    # -indicatorbackground (which the ttk docs list but this engine
    # ignores) — setting only the latter leaves the stock dark box.
    # Both are set so the styling survives a different base theme.
    for base, bg in (("TCheckbutton", p["card_bg"]), ("OnApp.TCheckbutton", p["window_bg"]),
                      ("OnChrome.TCheckbutton", p["chrome_bg"]),
                      ("OnNested.TCheckbutton", p["card_nested_bg"])):
        style.configure(base, background=bg, foreground=p["strong_fg"], font=font("body"),
                         indicatorcolor=p["input_bg"], indicatorbackground=p["input_bg"],
                         indicatorforeground=p["accent_fg"], indicatorrelief="flat",
                         bordercolor=p["input_border"], focuscolor=bg, padding=(2, 3))
        style.map(base,
                   background=[("active", bg)],
                   indicatorcolor=[("selected", p["accent"]), ("!selected", p["input_bg"])],
                   indicatorbackground=[("selected", p["accent"]), ("!selected", p["input_bg"])],
                   bordercolor=[("selected", p["accent"]), ("!selected", p["input_border"])])

    _install_check_indicator(root, style, p)

    for base, bg in (("TRadiobutton", p["card_bg"]), ("OnApp.TRadiobutton", p["window_bg"]),
                      ("OnNested.TRadiobutton", p["card_nested_bg"])):
        style.configure(base, background=bg, foreground=p["strong_fg"], font=font("body"),
                         indicatorcolor=p["input_bg"], indicatorbackground=p["input_bg"],
                         bordercolor=p["input_border"], focuscolor=bg, padding=(2, 3))
        style.map(base,
                   background=[("active", bg)],
                   indicatorcolor=[("selected", p["accent"]), ("!selected", p["input_bg"])],
                   indicatorbackground=[("selected", p["accent"]), ("!selected", p["input_bg"])],
                   bordercolor=[("selected", p["accent"]), ("!selected", p["input_border"])])

    # ---- buttons ----
    # Secondary (the default): filled, quiet, 1px border. The mockup's
    # buttons are 34-38px tall, which is what the padding here is for.
    style.configure("TButton", background=p["btn_bg"], foreground=p["btn_fg"],
                     bordercolor=p["btn_border"], borderwidth=1, relief="solid",
                     font=font("label"), padding=(12, 7), focusthickness=0)
    style.map("TButton",
               background=[("pressed", p["btn_border"]), ("active", p["btn_hover_bg"])],
               bordercolor=[("focus", p["accent"])])

    # Primary: the one orange button per screen ("Начать брейншторм",
    # "Сохранить настройки"). Deliberately borderless so it reads as a
    # solid block of accent the way it does in the mockup.
    style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_fg"],
                     bordercolor=p["accent"], borderwidth=0, relief="flat",
                     font=font("body_bold"), padding=(16, 8))
    style.map("Accent.TButton",
               background=[("pressed", p["accent_hover"]), ("active", p["accent_hover"])],
               foreground=[("disabled", p["faint_fg"])])

    style.configure("Ghost.TButton", background=p["ghost_bg"], foreground=p["ghost_fg"],
                     bordercolor=p["ghost_border"], borderwidth=1, relief="solid",
                     font=font("label"), padding=(12, 7))
    style.map("Ghost.TButton",
               background=[("pressed", p["btn_bg"]), ("active", p["btn_bg"])])

    style.configure("Danger.TButton", background=p["ghost_bg"], foreground=p["danger_fg"],
                     bordercolor=p["danger_border"], borderwidth=1, relief="solid",
                     font=font("label"), padding=(12, 7))
    style.map("Danger.TButton",
               background=[("pressed", p["btn_bg"]), ("active", p["btn_bg"])])

    style.configure("Send.TButton", background=p["send_bg"], foreground=p["send_fg"],
                     bordercolor=p["send_bg"], borderwidth=0, relief="flat",
                     font=font("body_bold"), padding=(16, 8))
    style.map("Send.TButton", background=[("pressed", p["send_bg"]), ("active", p["send_bg"])])

    # ---- inputs ----
    style.configure("TEntry", fieldbackground=p["input_bg"], foreground=p["input_fg"],
                     bordercolor=p["input_border"], borderwidth=1, relief="solid",
                     insertcolor=p["input_fg"], padding=(8, 6), selectbackground=p["select_bg"],
                     selectforeground=p["input_fg"])
    style.map("TEntry", bordercolor=[("focus", p["accent"])])
    style.configure("Mono.TEntry", fieldbackground=p["input_bg"], foreground=p["input_fg"],
                     bordercolor=p["input_border"], borderwidth=1, relief="solid",
                     insertcolor=p["input_fg"], padding=(8, 6))
    style.map("Mono.TEntry", bordercolor=[("focus", p["accent"])])

    style.configure("TCombobox", fieldbackground=p["input_bg"], foreground=p["input_fg"],
                     background=p["input_bg"], bordercolor=p["input_border"], borderwidth=1,
                     relief="solid", arrowcolor=p["faint_fg"], padding=(8, 6),
                     selectbackground=p["input_bg"], selectforeground=p["input_fg"])
    style.map("TCombobox",
               fieldbackground=[("readonly", p["input_bg"])],
               foreground=[("readonly", p["input_fg"])],
               arrowcolor=[("active", p["muted_fg"])],
               bordercolor=[("focus", p["accent"])])
    # The dropdown list is a classic Tk listbox living inside the combobox,
    # out of ttk.Style()'s reach — it only answers to option-database keys.
    root.option_add("*TCombobox*Listbox.background", p["input_bg"])
    root.option_add("*TCombobox*Listbox.foreground", p["input_fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["accent_fg"])
    root.option_add("*TCombobox*Listbox.font", font("body"))

    style.configure("TSpinbox", fieldbackground=p["input_bg"], foreground=p["input_fg"],
                     bordercolor=p["input_border"], borderwidth=1, relief="solid",
                     arrowcolor=p["faint_fg"], padding=(8, 5))
    style.map("TSpinbox", bordercolor=[("focus", p["accent"])])

    # ---- notebook ----
    # The app draws its own tab strip (see ui_widgets.TabBar) because a
    # ttk Notebook tab can't carry the mockup's 2px underline indicator.
    # These stay configured anyway: messagebox/simpledialog and any
    # future stock Notebook should not fall back to clam's grey.
    style.configure("TNotebook", background=p["window_bg"], bordercolor=p["chrome_border"],
                     borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=p["tab_bg"], foreground=p["tab_inactive_fg"],
                     padding=(14, 10), borderwidth=0, font=font("tab"))
    style.map("TNotebook.Tab",
               background=[("selected", p["tab_bg"])],
               foreground=[("selected", p["tab_active_fg"])],
               font=[("selected", font("tab_active"))])

    # ---- misc ----
    style.configure("TSeparator", background=p["separator"])
    style.configure("TProgressbar", background=p["success"], troughcolor=p["scroll_trough"],
                     bordercolor=p["scroll_trough"], borderwidth=0, thickness=4)
    style.configure("Budget.Horizontal.TProgressbar", background=p["success"],
                     troughcolor=p["separator"], bordercolor=p["separator"],
                     borderwidth=0, thickness=4)

    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=p["scroll_thumb"],
                         troughcolor=p["scroll_trough"], bordercolor=p["scroll_trough"],
                         arrowcolor=p["muted_fg"], lightcolor=p["scroll_thumb"],
                         darkcolor=p["scroll_thumb"], borderwidth=0, relief="flat")
        style.map(f"{orient}.TScrollbar",
                   background=[("active", p["scroll_thumb_active"]),
                               ("pressed", p["scroll_thumb_active"])])


# ------------------------------------------------- non-ttk widget theming

def replace_scrollbar_with_ttk(scrolled_text):
    """
    scrolledtext.ScrolledText builds its own internal vertical scrollbar
    using the CLASSIC (non-ttk) tk.Scrollbar (exposed as `.vbar`). On
    Windows, classic widgets like this are drawn by the OS's own
    UxTheme engine, which simply ignores bg/troughcolor/etc — no amount
    of color configuration has any visible effect there (it looks fine
    on Linux/X11, where Tk draws it itself, which is why this wasn't
    obvious without a real Windows test). The only reliable fix is
    swapping it out for a themeable ttk.Scrollbar, wired up the same
    way. Once swapped, it follows ttk.Style() automatically forever —
    no re-theming call needed on later theme switches.

    Call this once, right after creating the ScrolledText.
    """
    from tkinter import ttk

    old = scrolled_text.vbar
    parent = old.master
    new = ttk.Scrollbar(parent, orient="vertical", command=scrolled_text.yview)
    old.destroy()
    new.pack(side="right", fill="y")
    scrolled_text.configure(yscrollcommand=new.set)
    scrolled_text.vbar = new
    return new


def apply_text_widget_theme(widget, code, surface="input", outline=False):
    """Recolors a plain tk.Text/ScrolledText widget — ttk styling doesn't
    reach these, they need bg/fg/cursor/selection set directly.

    `surface` picks which background the widget is sitting on: "input"
    for an editable field, "card"/"nested"/"msg" for read-only text that
    should disappear into the panel behind it.

    `outline` draws the 1px input border the design gives editable
    fields. It goes through highlightbackground rather than borderwidth
    because Tk's own Text border is a 3D relief that can't be made a
    flat single-pixel line.
    """
    p = get_palette(code)
    backgrounds = {
        "input": (p["input_bg"], p["input_fg"]),
        "card": (p["card_bg"], p["body_fg"]),
        "nested": (p["card_nested_bg"], p["body_fg"]),
        "msg": (p["msg_bg"], p["body_fg"]),
        "user_msg": (p["user_msg_bg"], p["body_fg"]),
    }
    bg, fg = backgrounds.get(surface, backgrounds["input"])
    widget.configure(
        bg=bg, fg=fg,
        insertbackground=p["input_fg"],
        selectbackground=p["select_bg"], selectforeground=p["input_fg"],
        borderwidth=0, font=font("body"),
        padx=10, pady=8,
    )
    if outline:
        widget.configure(highlightthickness=1,
                          highlightbackground=p["input_border"],
                          highlightcolor=p["accent"])
    else:
        widget.configure(highlightthickness=0)


def apply_canvas_theme(canvas, code, surface="window"):
    """Recolors a plain tk.Canvas (used by ScrollableFrame) so its
    background matches the surrounding theme instead of showing through
    as a mismatched strip at the edges."""
    p = get_palette(code)
    key = {"window": "window_bg", "card": "card_bg", "msg": "msg_bg"}.get(surface, "window_bg")
    canvas.configure(bg=p[key], highlightthickness=0, borderwidth=0)


def theme_tag_colors(code):
    """Colors for the handful of chat-log tags that should adapt to the
    theme (separator line, code-block background, muted/status text).
    Participant/accent colors (Claude orange, error red, etc.) stay
    constant across themes on purpose — they're brand colors, not chrome,
    and the reference design uses the very same hex values the app
    already had."""
    p = get_palette(code)
    return {
        "separator": p["separator"],
        "code_bg": p["code_bg"],
        "code_fg": p["code_fg"],
        "code_border": p["code_border"],
        "muted_fg": p["muted_fg"],
        "body_fg": p["body_fg"],
        "mono_fg": p["mono_fg"],
    }
