# AI Brainstorm

A desktop app for group brainstorming with several AI models at once,
through a single OpenRouter API key. Claude, ChatGPT, Grok, Gemini and
MistralAI argue, riff on, and build on each other's ideas — orchestrated
by a moderator (AI or you) — while you watch, join in, or steer.

Pure Python + standard library (`tkinter`, `urllib`, `json`, `threading`,
`re`, `logging`) — no `pip install` needed to run it.

Русская версия: [README.ru.md](README.ru.md)

## Running

Requires Python 3.9+ (on Windows, the python.org installer bundles
tkinter — just don't uncheck `tcl/tk` during setup).

```
python main.py
```

## Building a single exe (Windows)

```
pip install pyinstaller
pyinstaller --onefile --windowed --icon=favicon.ico --add-data "favicon.ico;." --name AIBrainstorm main.py
```

Drop a `favicon.ico` next to `main.py` before building if you want a
custom app icon — `--icon` embeds it into the exe file itself (what
Explorer shows), while `--add-data` bundles the actual file so the
running app can also set its own window/taskbar icon at runtime via
`iconbitmap()` and a direct WinAPI call (`WM_SETICON`) for a crisp
icon in Alt+Tab and jump lists, not just a blurry upscale. Skip both
flags if you don't have an icon.

If you rebuild with a different icon after an existing build, delete
`build/`, `dist/`, and the `.spec` file first — PyInstaller caches
aggressively.

The exe appears in `dist/AIBrainstorm.exe`. Drop `--windowed` while
debugging to see console output.

## Interface language

The UI, the app-side prompts sent to the models (personas, moderator
instructions), and the technical log are all localized together.
Available languages are plain JSON files in `~/.ai_brainstorm/locales/`:

```
{"code": "en", "name": "English", "translations": {"key": "text", ...}}
```

`Russian.json` and `English.json` are created automatically on first
run and self-heal if deleted or corrupted. Drop in your own file with
any `code`/`name` (e.g. `French.json`) to add a language — the app
rescans the folder on every launch, no code changes needed. If the
saved language can't be found (e.g. a custom file was deleted), the app
silently falls back to English and remembers that.

Switch languages from the dropdown on the Settings tab — it applies
immediately, rebuilding the interface in place.

## Theme

Light and Dark, switched from a dropdown right next to the language
selector on the Settings tab. Applies immediately, no restart needed.
Like the language, it's an app-wide setting stored in
`~/.ai_brainstorm/active_profile.json`, independent of which profile is
active. Participant/accent colors (Claude orange, error red, etc.) stay
the same in both themes on purpose — they're brand colors, not chrome.

## Profiles

Settings live in named profiles, each a standalone JSON file with its
own API key:

- Windows: `C:\Users\<name>\.ai_brainstorm\profiles\<name>.json`
- Linux/macOS: `~/.ai_brainstorm/profiles/<name>.json`

Useful for multiple OpenRouter accounts or different participant sets
for different occasions. The dropdown on the Settings tab applies a
profile the moment you pick it — no separate "load" step. "Save As…"
snapshots the current form under a new name without touching the old
active profile's file. "Open Settings Folder" opens
`~/.ai_brainstorm/` directly in the OS file manager.

The active profile name, interface language, and Log tab visibility are
app-wide settings, stored separately from profile content (in
`~/.ai_brainstorm/active_profile.json`) — they don't change when you
switch profiles.

## Participants

**Standard families** (up to 5) — Claude, ChatGPT, Grok, Gemini,
MistralAI. Each family is matched against OpenRouter's live model list
by regex, so the dropdown of concrete models self-updates as providers
ship new ones — click "Refresh Model List" any time. Pick which
concrete model to use within a family, edit its persona, and set a
reasoning-token budget (see below).

**Custom models** (up to 3) — any other OpenRouter model by exact ID
(e.g. `deepseek/deepseek-v4-flash-0731`), with its own name, persona,
and reasoning level. The ID field autocompletes from the same refreshed
model list.

2 to 8 participants total. In chat, each one's label shows the exact
model in use, e.g. "Claude (claude-sonnet-5)".

### Reasoning levels

Optional token budget for a model's hidden "thinking" before its
visible reply — Off / Low (≤1024) / Medium (≤4096) / High (≤16000).
Off by default: rarely helps a casual brainstorm and can quietly
inflate the bill. Not every model supports it; the setting just has no
effect where it isn't.

## Moderator

Instead of strict round-robin, a moderator decides who speaks next —
and what they should do, why, and whether it's time to wrap up.

- **AI moderator** (default) — a separate, usually cheap, model call
  after every reply. Hidden from the chat itself.
- **Human moderator** — you pick every speaker yourself, no extra API
  cost. The same panel lets you leave a comment or end the session on
  the spot.

**Participation** — if enabled, the moderator can occasionally hand the
floor to you too (capped so it can't happen twice in a row, so a
biased moderator can't stall the session on you forever). Your replies
don't count against the reply limit or budget.

**Session summary** — an optional extra call after the session ends,
asking the moderator model for a bullet-point recap: key ideas, points
of agreement/disagreement, an overall takeaway.

**Web check before starting** — off by default. When enabled, the
moderator runs a single web search (OpenRouter's built-in `web` plugin,
no separate search API key needed) before the discussion begins,
looking for anything relevant to the topic — recent events, or a
non-obvious tie-in with today's actual date the participants might
otherwise miss entirely. The findings appear as their own message in
the chat and are folded into the transcript, so every participant sees
them from their first reply onward. Adds a small extra cost for the
search itself, shown like any other cost line.

**Intervene** — pause the discussion mid-flight, leave a note for the
participants, or end the session right there. A dedicated button in
AI-moderator mode; built into the speaker-picker panel in human mode.

The very last reply of a session is always steered toward a wrap-up,
regardless of whether the moderator remembered to ask for one.

## Budget and length

Two independent stop conditions, whichever hits first:

- **Budget** ($, set in Settings) — includes both participant replies
  and moderator calls. OpenRouter returns an exact cost per request;
  it's shown under each reply (in italic gray, right-aligned), split
  out when a moderator call is folded in (e.g. "$0.0031 + moderator
  $0.0012 = $0.0043").
- **Max replies** (set on the Chat tab) — counts only participant
  replies, not the moderator's own calls or your own turns.

A model that starts erroring (rate limits, etc.) is put on a short
cooldown and excluded from the moderator's choices — quietly, without
spamming the chat; the reason stays visible in the Log tab.

## Chat display

- `**bold**`, `` `inline code` ``, fenced ` ```code blocks``` `,
  headers, and bullet lists render properly, not as raw markdown.
- Replies are visually separated with a rule.
- Your own notes (topic, comments, replies) are colored distinctly; the
  session summary gets its own accent color.
- **Ctrl+C** copies the selection, **Ctrl+A** selects everything,
  "Copy All" grabs the whole log in one click.
- **Export…** saves to `.md` or `.txt`, built from the original
  message text (with all its markdown intact), not from what's
  rendered on screen.

## Log tab

An optional tab mirroring what a console would show — model calls,
costs, moderator decisions, errors. Toggle it on the Settings tab; it
keeps its own history for the whole app session even while hidden.
Copies and selects the same way the chat log does.

## Project layout

```
ai_brainstorm/
├── main.py             — entry point, Tkinter UI, moderator/worker logic
├── config.py            — profiles, app-wide settings, locale folder paths
├── models_catalog.py    — model families, reasoning levels, catalog assembly
├── api_client.py        — OpenRouter calls: chat, moderator, model list, key balance
├── i18n.py               — translation loading/fallback, built-in RU/EN dictionaries
├── theme.py               — Light/Dark palettes, ttk.Style() + plain Text/Canvas theming
├── favicon.ico           — app icon (optional, add your own)
├── README.md / README.ru.md
```

## Changelog

- **2026-08-23** — First release.
- **2026-08-24** — Added localization (multi-language interface, prompts,
  and log) and various logic bug fixes.
- **2026-08-29** — Added a Light/Dark theme, and an optional pre-session web check by the moderator.

