# -*- coding: utf-8 -*-
"""
Light/Dark theme support.

Built on ttk's "clam" base theme — unlike platform-native themes
(e.g. "vista"/"winnative" on Windows), "clam" actually respects custom
style colors instead of ignoring them in favor of native OS chrome.

Applied globally via ttk.Style() (affects every ttk widget app-wide the
moment it's called) plus a small set of colors for plain tk.Text
widgets, which don't follow ttk styling and must be recolored
explicitly — see apply_text_widget_theme().
"""

DEFAULT_THEME_CODE = "light"
THEME_CODES = ["light", "dark"]

THEMES = {
    "light": {
        "window_bg": "#f3f3f3",
        "surface_bg": "#ffffff",
        "fg": "#1a1a1a",
        "muted_fg": "#555555",
        "entry_bg": "#ffffff",
        "button_bg": "#e8e8e8",
        "button_active_bg": "#dcdcdc",
        "select_bg": "#cfe8ff",
        "border": "#cccccc",
        "separator": "#cccccc",
        "code_bg": "#f0f0f0",
    },
    "dark": {
        "window_bg": "#1e1e1e",
        "surface_bg": "#252526",
        "fg": "#e0e0e0",
        "muted_fg": "#9a9a9a",
        "entry_bg": "#2d2d30",
        "button_bg": "#3a3a3d",
        "button_active_bg": "#48484c",
        "select_bg": "#264f78",
        "border": "#3a3a3a",
        "separator": "#444444",
        "code_bg": "#161616",
    },
}


def get_palette(code):
    return THEMES.get(code, THEMES[DEFAULT_THEME_CODE])


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

    p = get_palette(code)
    style = ttk.Style(root)
    style.theme_use("clam")  # the only bundled theme that reliably honors custom colors on Windows

    root.winfo_toplevel().configure(bg=p["window_bg"])

    style.configure(".", background=p["surface_bg"], foreground=p["fg"],
                     fieldbackground=p["entry_bg"])
    style.configure("TFrame", background=p["surface_bg"])
    style.configure("TLabelframe", background=p["surface_bg"], foreground=p["fg"])
    style.configure("TLabelframe.Label", background=p["surface_bg"], foreground=p["fg"])
    style.configure("TLabel", background=p["surface_bg"], foreground=p["fg"])

    style.configure("TCheckbutton", background=p["surface_bg"], foreground=p["fg"])
    style.map("TCheckbutton", background=[("active", p["surface_bg"])])
    style.configure("TRadiobutton", background=p["surface_bg"], foreground=p["fg"])
    style.map("TRadiobutton", background=[("active", p["surface_bg"])])

    style.configure("TButton", background=p["button_bg"], foreground=p["fg"],
                     bordercolor=p["border"])
    style.map("TButton", background=[
        ("active", p["button_active_bg"]), ("pressed", p["button_active_bg"]),
    ])

    style.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     bordercolor=p["border"], insertcolor=p["fg"])
    style.configure("TCombobox", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     background=p["button_bg"], bordercolor=p["border"], arrowcolor=p["fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", p["entry_bg"])],
              foreground=[("readonly", p["fg"])])
    style.configure("TSpinbox", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     bordercolor=p["border"], arrowcolor=p["fg"])

    style.configure("TNotebook", background=p["window_bg"], bordercolor=p["border"])
    style.configure("TNotebook.Tab", background=p["button_bg"], foreground=p["fg"], padding=(10, 4))
    style.map("TNotebook.Tab",
              background=[("selected", p["surface_bg"])],
              foreground=[("selected", p["fg"])])

    style.configure("TSeparator", background=p["border"])
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=p["button_bg"],
                         troughcolor=p["surface_bg"], bordercolor=p["border"],
                         arrowcolor=p["fg"])


def apply_text_widget_theme(widget, code):
    """Recolors a plain tk.Text/ScrolledText widget — ttk styling doesn't
    reach these, they need bg/fg/cursor/selection set directly."""
    p = get_palette(code)
    widget.configure(
        bg=p["entry_bg"], fg=p["fg"],
        insertbackground=p["fg"],
        selectbackground=p["select_bg"], selectforeground=p["fg"],
    )


def apply_canvas_theme(canvas, code):
    """Recolors a plain tk.Canvas (used by ScrollableFrame) so its
    background matches the surrounding theme instead of showing through
    as a mismatched strip at the edges."""
    canvas.configure(bg=get_palette(code)["window_bg"], highlightthickness=0)


def theme_tag_colors(code):
    """Colors for the handful of chat-log tags that should adapt to the
    theme (separator line, code-block background, muted/status text).
    Participant/accent colors (Claude orange, error red, etc.) stay
    constant across themes on purpose — they're brand colors, not chrome."""
    p = get_palette(code)
    return {"separator": p["separator"], "code_bg": p["code_bg"], "muted_fg": p["muted_fg"]}
