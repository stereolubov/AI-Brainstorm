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
        "accent": "#1a73e8",  # confident blue — distinct from dark theme's coral on purpose
    },
    "dark": {
        # Sampled pixel-for-pixel from a companion dark-themed app for a
        # consistent, deliberately-matched look across the two projects.
        "window_bg": "#1e1e1e",
        "surface_bg": "#2d2d2d",
        "fg": "#ffffff",
        "muted_fg": "#9c9c9c",
        "entry_bg": "#393939",
        "button_bg": "#393939",
        "button_active_bg": "#454545",
        "select_bg": "#4a3a35",
        "border": "#2d2d2d",
        "separator": "#3a3a3a",
        "code_bg": "#161616",
        "accent": "#f38064",  # warm coral, sampled from the reference app's checkbox
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
    style.map("TCheckbutton",
              background=[("active", p["surface_bg"])],
              indicatorcolor=[("selected", p["accent"]), ("!selected", p["entry_bg"])])
    style.configure("TRadiobutton", background=p["surface_bg"], foreground=p["fg"])
    style.map("TRadiobutton",
              background=[("active", p["surface_bg"])],
              indicatorcolor=[("selected", p["accent"]), ("!selected", p["entry_bg"])])

    style.configure("TButton", background=p["button_bg"], foreground=p["fg"],
                     bordercolor=p["border"])
    style.map("TButton", background=[
        ("active", p["button_active_bg"]), ("pressed", p["button_active_bg"]),
    ])

    style.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     bordercolor=p["border"], insertcolor=p["fg"])
    style.map("TEntry", bordercolor=[("focus", p["accent"])])
    style.configure("TCombobox", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     background=p["button_bg"], bordercolor=p["border"], arrowcolor=p["fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", p["entry_bg"])],
              foreground=[("readonly", p["fg"])],
              bordercolor=[("focus", p["accent"])])
    style.configure("TSpinbox", fieldbackground=p["entry_bg"], foreground=p["fg"],
                     bordercolor=p["border"], arrowcolor=p["fg"])
    style.map("TSpinbox", bordercolor=[("focus", p["accent"])])

    style.configure("TNotebook", background=p["window_bg"], bordercolor=p["border"])
    style.configure("TNotebook.Tab", background=p["button_bg"], foreground=p["fg"], padding=(10, 4))
    style.map("TNotebook.Tab",
              background=[("selected", p["surface_bg"])],
              foreground=[("selected", p["fg"])])

    style.configure("TSeparator", background=p["border"])
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=p["button_bg"],
                         troughcolor=p["surface_bg"], bordercolor=p["border"],
                         arrowcolor=p["fg"], lightcolor=p["button_bg"], darkcolor=p["button_bg"])
        style.map(f"{orient}.TScrollbar",
                   background=[("active", p["button_active_bg"])])


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
