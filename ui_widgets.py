# -*- coding: utf-8 -*-
"""
Composite widgets the reference design needs and ttk doesn't provide.

Three of them, each because a stock widget genuinely can't do the job:

  TabView      — a ttk.Notebook tab cannot carry the mockup's 2px
                 underline indicator, nor a status chip pinned to the
                 right of the tab strip. Drawn from frames instead.
  Card         — the numbered 01..06 panels. ttk.Labelframe draws a
                 grooved box with the title cut into the border, which
                 is not the same object at all.
  MessageList  — chat messages as separate blocks with their own
                 background, left accent stripe and per-message cost
                 line. A single Text widget can't do that: a tag's
                 background only covers the glyphs, so wrapped lines
                 come out ragged instead of forming a block.

Everything here reads its colors from theme.get_palette() at build time
and is rebuilt (not re-colored) on a theme switch, matching how the rest
of the app already handles that — see App._on_profile_switched.
"""

import tkinter as tk
from tkinter import ttk

import theme


def _hline(parent, color, height=1):
    """A 1px rule. tk.Frame rather than ttk.Separator: a separator's
    thickness comes from the theme's element geometry and can't be
    pinned to exactly one pixel."""
    line = tk.Frame(parent, background=color, height=height, borderwidth=0, highlightthickness=0)
    line.pack(fill="x")
    return line


# --------------------------------------------------------------- tab strip

class TabView(ttk.Frame):
    """Tab strip + content area, with a Notebook-compatible surface
    (add/forget/select/tabs) so the calling code reads the same.

    Pages must be built with `.content` as their parent, not with the
    TabView itself — Tk has no way to reparent an existing widget, so
    the content frame has to be the parent from the start.
    """

    def __init__(self, parent, theme_code):
        super().__init__(parent, style="App.TFrame")
        self.theme_code = theme_code
        self.palette = theme.get_palette(theme_code)

        self.strip = tk.Frame(self, background=self.palette["tab_bg"], highlightthickness=0)
        self.strip.pack(fill="x")

        self.buttons = tk.Frame(self.strip, background=self.palette["tab_bg"], highlightthickness=0)
        self.buttons.pack(side="left", padx=(16, 0))

        # Right-hand slot for the provider/balance chip the mockup shows
        # level with the tabs. Public so the app can fill it in.
        self.status_slot = tk.Frame(self.strip, background=self.palette["tab_bg"], highlightthickness=0)
        self.status_slot.pack(side="right", padx=(0, 18))

        self.strip_border = _hline(self, self.palette["chrome_border"])

        self.content = ttk.Frame(self, style="App.TFrame")
        self.content.pack(fill="both", expand=True)

        self._pages = []      # [(page_widget, tab_frame, label, indicator), ...] in tab order
        self._current = None

    # ---- Notebook-compatible API ----

    def add(self, page, text=""):
        if any(entry[0] is page for entry in self._pages):
            self.select(page)
            return

        tab = tk.Frame(self.buttons, background=self.palette["tab_bg"], highlightthickness=0)
        tab.pack(side="left")

        label = tk.Label(
            tab, text=text, background=self.palette["tab_bg"],
            foreground=self.palette["tab_inactive_fg"], font=theme.font("tab"),
            padx=14, pady=10, cursor="hand2",
        )
        label.pack()

        # The underline. Always present, just colored to match the strip
        # when inactive — so switching tabs never changes the strip height.
        indicator = tk.Frame(tab, background=self.palette["tab_bg"], height=2, highlightthickness=0)
        indicator.pack(fill="x")

        entry = (page, tab, label, indicator)
        self._pages.append(entry)

        for widget in (tab, label):
            widget.bind("<Button-1>", lambda _e, p=page: self.select(p))

        if self._current is None:
            self.select(page)

    def forget(self, page):
        for index, entry in enumerate(self._pages):
            if entry[0] is page:
                entry[1].destroy()
                self._pages.pop(index)
                if self._current is page:
                    page.pack_forget()
                    self._current = None
                    if self._pages:
                        self.select(self._pages[min(index, len(self._pages) - 1)][0])
                return

    def select(self, page=None):
        if page is None:
            return self._current
        if self._current is page:
            return None

        if self._current is not None:
            self._current.pack_forget()

        self._current = page
        page.pack(in_=self.content, fill="both", expand=True)

        for entry_page, _tab, label, indicator in self._pages:
            active = entry_page is page
            label.configure(
                foreground=self.palette["tab_active_fg"] if active else self.palette["tab_inactive_fg"],
                font=theme.font("tab_active") if active else theme.font("tab"),
            )
            indicator.configure(
                background=self.palette["tab_indicator"] if active else self.palette["tab_bg"]
            )
        return None

    def tabs(self):
        """Widget pathnames of the visible pages, matching what
        ttk.Notebook.tabs() returns (so `str(widget) in view.tabs()`
        keeps working)."""
        return [str(entry[0]) for entry in self._pages]

    def retheme(self, theme_code):
        """Recolors the strip in place after a theme switch.

        The tab strip can't just be rebuilt along with the pages: the Log
        tab is a singleton that lives in `.content` for the whole session
        (so its history survives being hidden and shown), and destroying
        this widget would take it with it.
        """
        self.theme_code = theme_code
        self.palette = theme.get_palette(theme_code)
        bg = self.palette["tab_bg"]

        for widget in (self.strip, self.buttons, self.status_slot):
            widget.configure(background=bg)
        for _page, tab, label, indicator in self._pages:
            tab.configure(background=bg)
            label.configure(background=bg)
            indicator.configure(background=bg)
        self.strip_border.configure(background=self.palette["chrome_border"])

        for entry_page, _tab, label, indicator in self._pages:
            active = entry_page is self._current
            label.configure(
                foreground=self.palette["tab_active_fg"] if active else self.palette["tab_inactive_fg"],
                font=theme.font("tab_active") if active else theme.font("tab"),
            )
            indicator.configure(background=self.palette["tab_indicator"] if active else bg)

    def set_status(self, text, dot_color=None):
        """Fills the chip to the right of the tabs. Pass text="" to clear it."""
        for child in self.status_slot.winfo_children():
            child.destroy()
        if not text:
            return
        if dot_color:
            tk.Label(self.status_slot, text="●", background=self.palette["tab_bg"],
                      foreground=dot_color, font=theme.font("mono_micro")).pack(side="left", padx=(0, 6))
        tk.Label(self.status_slot, text=text, background=self.palette["tab_bg"],
                  foreground=self.palette["mono_fg"], font=theme.font("mono")).pack(side="left")


# ------------------------------------------------------------------- cards

class Card(ttk.Frame):
    """A titled panel: `01  Профиль настроек   каждый профиль хранит…`

    Add content to `.body`, not to the card itself — the card's own
    children are the 1px border and the header row.
    """

    def __init__(self, parent, theme_code, number=None, title="", subtitle="",
                 nested=False, padding=(20, 18)):
        palette = theme.get_palette(theme_code)
        # tk.Frame as the border: a ttk.Frame's border is drawn by the
        # theme's element geometry and won't hold still at 1px.
        self.border = tk.Frame(parent, background=palette["card_border"], highlightthickness=0)

        surface = "CardNested.TFrame" if nested else "Card.TFrame"
        super().__init__(self.border, style=surface, padding=padding)
        # Straight to ttk's pack, not self.pack — the override below
        # redirects that to the border frame, which is what callers want
        # but the exact opposite of what's needed here.
        ttk.Frame.pack(self, fill="both", expand=True, padx=1, pady=1)

        self.theme_code = theme_code
        self.palette = palette
        self._suffix = "OnNested" if nested else ""

        if number or title or subtitle:
            header = ttk.Frame(self, style=surface)
            header.pack(fill="x", pady=(0, 12))
            if number:
                ttk.Label(header, text=number,
                           style="Mono.TLabel" if nested else "CardNum.TLabel").pack(side="left", padx=(0, 10))
            if title:
                ttk.Label(header, text=title, style="Section.TLabel").pack(side="left")
            if subtitle:
                ttk.Label(header, text=subtitle,
                           style=f"Muted{self._suffix}.TLabel").pack(side="left", padx=(10, 0))

        self.body = ttk.Frame(self, style=surface)
        self.body.pack(fill="both", expand=True)

    # The card is really the border frame as far as layout goes, so
    # forward geometry calls to it — `card.pack(...)` then does the
    # obvious thing instead of packing the inner surface into nothing.
    def pack(self, **kwargs):
        return self.border.pack(**kwargs)

    def pack_forget(self):
        return self.border.pack_forget()

    def grid(self, **kwargs):
        return self.border.grid(**kwargs)

    def grid_forget(self):
        return self.border.grid_forget()

    def destroy(self):
        border = getattr(self, "border", None)
        super().destroy()
        if border is not None:
            border.destroy()


# ------------------------------------------------------------ message list

class MessageList(ttk.Frame):
    """The chat transcript, one block per message.

    Each block is: a left stripe in the speaker's color, then the
    speaker's name and model id, the body, an optional fenced code
    block, and the cost, right-aligned. User messages additionally get a
    tinted background, exactly as the mockup has them.

    Bodies are read-only tk.Text widgets rather than labels so that
    selecting and copying inside a message still works, and so the
    existing **bold**/`code` rendering has somewhere to put its tags.
    Selection does not span messages — the "copy all" and export paths
    cover that and always did, since they read the raw log, not the
    widget.
    """

    def __init__(self, parent, theme_code):
        super().__init__(parent, style="Msg.TFrame")
        self.theme_code = theme_code
        self.palette = theme.get_palette(theme_code)

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        theme.apply_canvas_theme(self.canvas, theme_code, surface="msg")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas, style="Msg.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

        self._bodies = []        # every message body, for theme-wide font/tag work
        self._autoscroll = True

    # ---- scrolling plumbing ----

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self._autoscroll:
            self.canvas.yview_moveto(1.0)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # Once the reader scrolls up, stop yanking them back to the
        # bottom on every new message; resume when they return to it.
        top, bottom = self.canvas.yview()
        self._autoscroll = bottom > 0.999
        return "break"

    def see_end(self):
        self._autoscroll = True
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    # ---- content ----

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self._bodies.clear()
        self._autoscroll = True

    def add_message(self, name, color, version="", cost="", is_user=False, render=None):
        """Appends one message block.

        `render(text_widget)` is called with the body widget while it is
        still editable — that's where the caller inserts the reply and
        applies its own markdown tags. Keeping it a callback means this
        module owns the layout and the chat tab keeps owning how a reply
        is formatted.
        """
        palette = self.palette
        row_bg = palette["user_msg_bg"] if is_user else palette["msg_bg"]
        row_style = "MsgUser.TFrame" if is_user else "Msg.TFrame"

        row = tk.Frame(self.inner, background=row_bg, highlightthickness=0)
        row.pack(fill="x")

        # Left accent stripe, in the speaker's own color. The mockup
        # draws this only for the user's own messages; extending it to
        # every speaker leans on the participant colors the app already
        # assigns, and keeps the blocks distinguishable at a glance.
        stripe = tk.Frame(row, background=color or palette["accent"], width=2, highlightthickness=0)
        stripe.pack(side="left", fill="y")

        body_wrap = tk.Frame(row, background=row_bg, highlightthickness=0)
        body_wrap.pack(side="left", fill="both", expand=True, padx=(16, 18), pady=(14, 12))

        header = tk.Frame(body_wrap, background=row_bg, highlightthickness=0)
        header.pack(fill="x")
        tk.Label(header, text="●", background=row_bg, foreground=color or palette["accent"],
                  font=theme.font("mono_micro")).pack(side="left", padx=(0, 7))
        tk.Label(header, text=name, background=row_bg, foreground=color or palette["heading_fg"],
                  font=theme.font("speaker")).pack(side="left")
        if version:
            tk.Label(header, text=version, background=row_bg, foreground=palette["mono_fg"],
                      font=theme.font("mono")).pack(side="left", padx=(9, 0))

        body = tk.Text(
            body_wrap, wrap="word", height=1, borderwidth=0, highlightthickness=0,
            background=row_bg, foreground=palette["body_fg"], font=theme.font("body"),
            selectbackground=palette["select_bg"], selectforeground=palette["input_fg"],
            padx=0, pady=0, cursor="xterm", spacing1=0, spacing3=3,
        )
        body.pack(fill="x", pady=(7, 0))
        if render is not None:
            render(body)
            # Markdown rendering leaves trailing blank lines behind (a
            # closing code fence, a final newline). Left in, they push
            # the cost line a line or two away from the reply it belongs
            # to and make every message look loosely padded.
            while body.index("end-1c") != "1.0" and body.get("end-2c", "end-1c") in ("\n", " ", "\t"):
                body.delete("end-2c")
        body.configure(state="disabled")
        _AutoHeight(body)
        self._bodies.append(body)

        if cost:
            tk.Label(body_wrap, text=cost, background=row_bg, foreground=palette["faint_fg"],
                      font=theme.font("cost"), anchor="e").pack(fill="x", pady=(8, 0))

        _hline(self.inner, palette["msg_divider"])

        return body


class _AutoHeight:
    """Keeps a wrapping tk.Text exactly as tall as its content.

    A Text widget's height is in LINES of its base font, but a message
    body is not uniform: fenced code is set in a smaller monospace face
    and carries extra leading. Counting display lines therefore gets the
    height wrong in both directions — a reply ending after a code block
    loses its last paragraph, while a plain one gains dead space.

    So the content is measured in pixels ("ypixels") and converted using
    the base font's line height. That accounts for mixed fonts and tag
    spacing, because the pixel figure already includes them.

    The width guard is not optional. A Text that hasn't been laid out
    yet reports a width of 1 pixel, at which point every word wraps onto
    its own line and the measurement is meaningless.
    """

    MIN_USABLE_WIDTH = 40  # px; below this the widget hasn't been laid out yet

    def __init__(self, widget):
        self.widget = widget
        self.lines = None
        self.pending = False
        widget.bind("<Configure>", self._schedule, add="+")

    def _schedule(self, _event=None):
        """Counting inside the <Configure> handler itself reads the
        layout as it was BEFORE the resize, so a freshly-widened widget
        still reports the line count for its old width — which is how a
        message ends up one line tall with the rest of it clipped.
        Deferring to after_idle lets Tk finish the relayout first."""
        if self.pending:
            return
        self.pending = True
        try:
            self.widget.after_idle(self._recompute)
        except tk.TclError:
            self.pending = False

    def _recompute(self):
        self.pending = False
        widget = self.widget
        try:
            if not widget.winfo_exists() or widget.winfo_width() < self.MIN_USABLE_WIDTH:
                return
            pixels = widget.count("1.0", "end-1c", "ypixels")
        except tk.TclError:
            return
        if isinstance(pixels, tuple):
            pixels = pixels[0] if pixels else 0
        pixels = int(pixels or 0)
        if pixels <= 0:
            return

        try:
            from tkinter import font as tkfont
            line_height = tkfont.Font(root=widget, font=widget.cget("font")).metrics("linespace")
        except tk.TclError:
            return
        if not line_height:
            return

        # Round up: a partial line still needs a whole one to show in.
        lines = max(1, -(-pixels // line_height))
        if lines != self.lines:
            self.lines = lines
            widget.configure(height=lines)
