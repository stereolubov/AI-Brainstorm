# AI Brainstorm

A desktop app for group brainstorming with several AI models at once,
through OpenRouter, Requesty, or your own OpenAI-compatible server
(local or self-hosted). Claude, ChatGPT, Grok, Gemini and MistralAI
argue, riff on, and build on each other's ideas — orchestrated by a
moderator (AI or you) — while you watch, join in, or steer.

Pure Python + standard library (`tkinter`, `urllib`, `json`, `threading`,
`re`, `logging`) — no `pip install` needed to run it.

Русская версия: [README.ru.md](README.ru.md)

## API Providers

Pick one from the dropdown right above the API key field on Settings —
each profile remembers its own choice, key, and (for Custom) URL.

- **OpenRouter** (default) — the most complete option: model families,
  free-models filter, balance check, moderator web search, and $ cost
  tracking all work.
- **Requesty** — a similarly-shaped hosted router (same `provider/model`
  ID convention, so families work the same way, and it reports request
  cost too, so budget tracking works). No free-models filter (its
  model list doesn't expose pricing), no balance-check button, no
  moderator web search — see `providers.py` for exactly why each one
  doesn't fit cleanly rather than being half-implemented.
- **Custom** — any other OpenAI-compatible endpoint: a local server
  (LM Studio, Ollama, etc.), a self-hosted proxy, or another cloud
  provider. Type its base URL in Settings. No families (there's no
  fixed vendor-prefix convention to match against for an arbitrary
  server), no balance/free-filter/web-search UI, no $ budget tracking
  (such servers essentially never report a cost) — just chat plus an
  optional raw JSON reasoning fragment per participant, see below.
  **Experimental** — request/response shapes vary enough between local
  servers that some rough edges are expected; see Known issues below
  for local-model response-time guidance.

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

Useful for multiple accounts/providers or different participant sets
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

**Standard families** (up to 5, OpenRouter/Requesty only) — Claude,
ChatGPT, Grok, Gemini, MistralAI. Each family is matched against the
provider's live model list by regex (both use the same `vendor/model`
ID convention), so the dropdown of concrete models self-updates as new
ones ship — click "Refresh Model List" any time. Pick which concrete
model to use within a family, edit its persona, and set a reasoning
level (see below). Not available for Custom — an arbitrary server has
no fixed vendor-prefix naming to match against.

**Custom models** (up to 3 alongside families, or all 8 in flat mode —
the only option for Custom, see below) — any other model by exact ID,
with its own name, persona, and reasoning setting. The ID field
autocompletes from the refreshed model list when the provider makes
one available. The same model ID can be used in more than one slot on
purpose — handy for giving one model several distinct personas (e.g.
two instances of a local model, one sarcastic, one earnest); each
still counts as a genuinely separate participant with its own voice,
its own place in the speaking order, and its own "who spoke last"
tracking. A custom slot still can't reuse a model already claimed by a
selected family, though — families keep their own separate uniqueness.

2 to 8 participants total. In chat, each one's label shows the exact
model in use, e.g. "Claude (claude-sonnet-5)".

**Skip families entirely** — a "Use families" checkbox in the standard
models block (hidden for Custom, where it's forced off); uncheck it to
turn the 5 standard + 3 custom layout into 8 flat, fully generic slots
instead (no preset personas or brand colors tied to a vendor).
Unchecking it migrates your currently-configured families into the
newly available slots (in a fixed Claude → ChatGPT → Grok → Gemini →
MistralAI order, regardless of which were checked, so the visual order
stays predictable) — your prior 3 custom slots aren't touched or
reshuffled. Checking it back on restores your family configuration
exactly as it was; both are always kept in the saved profile
regardless of which is currently active.

**Free models only** (OpenRouter only) — a checkbox that filters the ID
autocomplete down to $0-priced models, detected via OpenRouter's own
per-model pricing data and refreshed together with the main model
list. Switches instantly, no extra network call. Not available for
Requesty (its model list doesn't expose pricing) or Custom.

### Reasoning levels

Optional budget for a model's hidden "thinking" before its visible
reply. For OpenRouter/Requesty, pick one of 4 levels — Off / Low /
Medium / High — from a dropdown per participant; the app translates
that into whatever the provider's API actually expects under the hood
(a numeric token budget for OpenRouter, an effort word for Requesty —
confirmed against each provider's own docs, not guessed). Off by
default: rarely helps a casual brainstorm and can quietly inflate the
bill. Not every model supports it; the setting just has no effect
where it isn't.

For **Custom**, there's no guessable shape — OpenRouter, Requesty, and
LM Studio all format this differently from each other, so a generic
translation isn't possible. Instead, each participant gets its own
"Reasoning (JSON, optional)" text field: write the exact fragment your
server expects (e.g. `{"reasoning": {"effort": "low"}}`), merged into
the request body as-is. Empty sends nothing. Invalid JSON is skipped
with a warning in the Log tab rather than failing that reply.

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

**Web check before starting** (OpenRouter only) — off by default. When
enabled, the moderator runs a single web search (OpenRouter's built-in
`web` plugin, no separate search API key needed) before the discussion
begins, looking for anything relevant to the topic — recent events, or
a non-obvious tie-in with today's actual date the participants might
otherwise miss entirely. The findings appear as their own message in
the chat and are folded into the transcript, so every participant sees
them from their first reply onward. Adds a small extra cost for the
search itself, shown like any other cost line. Not offered for
Requesty (its web search is per-model-family, not a universal flag) or
Custom.

**Intervene** — pause the discussion mid-flight, leave a note for the
participants, or end the session right there. A dedicated button in
AI-moderator mode; built into the speaker-picker panel in human mode.

The very last reply of a session is always steered toward a wrap-up,
regardless of whether the moderator remembered to ask for one.

## Budget and length

Two independent stop conditions, whichever hits first:

- **Budget** ($, set in Settings; OpenRouter/Requesty only — the field
  is hidden entirely for Custom, which essentially never reports a $
  cost) — includes both participant replies and moderator calls. The
  provider returns an exact cost per request; it's shown under each
  reply (in italic gray, right-aligned), split out when a moderator
  call is folded in (e.g. "$0.0031 + moderator $0.0012 = $0.0043").
- **Max replies** (set on the Chat tab) — counts only participant
  replies, not the moderator's own calls or your own turns. The only
  stop condition that applies to Custom.

A model that starts erroring (rate limits, timeouts, etc.) is put on a
short cooldown and excluded from the moderator's choices — quietly,
without spamming the chat; the reason stays visible in the Log tab.

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
├── api_client.py        — provider-agnostic API calls: chat, moderator, model list, key balance
├── i18n.py               — translation loading/fallback, built-in RU/EN dictionaries
├── theme.py               — Light/Dark palettes, ttk.Style() + plain Text/Canvas theming
├── providers.py           — provider registry (OpenRouter/Requesty/Custom) and capability flags
├── favicon.ico           — app icon (optional, add your own)
├── README.md / README.ru.md
```

## Known issues

- **Profiles from before 2026-08-30 that had already used the family ↔
  flat-slots toggle may show the wrong models in the 3 "own" slots
  after updating.** The internal storage order changed (families now
  always occupy fixed slots 1-5, "own" custom slots moved to 6-8, so
  toggling never reshuffles the list) — profiles that never used the
  toggle aren't affected. If yours is, open the profile's `.json` file
  in `~/.ai_brainstorm/profiles/` and reorder the `custom_models` array
  so entries 1-5 are your families (in Claude/ChatGPT/Grok/Gemini/
  MistralAI order) and 6-8 are your own custom models — or just
  re-enter the custom slots by hand in Settings, whichever's less typing.
- **Locale self-healing only adds missing keys, not corrected wording.**
  If an existing translation's text is ever fixed in a future update,
  your saved `Russian.json`/`English.json` in `~/.ai_brainstorm/locales/`
  keeps whatever it already has for that key — self-healing only fills
  in keys that are entirely absent. If a label looks outdated after an
  update, delete the corresponding file (the app regenerates it from
  the current built-in defaults on next launch).
- **For Custom/local models, avoid heavy models whose replies take
  longer than about 3 minutes.** That's the app's request timeout
  ceiling — comfortably generous for cloud providers, but a large local
  reasoning model on modest hardware can genuinely exceed it, which
  aborts that one reply (the model gets a short cooldown and the
  session continues — nothing crashes, but that reply is lost). If you
  hit this often, pick a smaller/faster local model or lower its
  reasoning effort.

## Changelog

- **2026-08-23** — First release.
- **2026-08-24** — Added localization (multi-language interface, prompts,
  and log) and various logic bug fixes.
- **2026-08-29** — Added a Light/Dark theme, and an optional pre-session web check by the moderator.
- **2026-08-30** — Added an option to skip families entirely for 8 flat
  custom slots, and a "free models only" filter for that mode's
  autocomplete.
- **2026-09-01** — Added support for the Requesty provider, and
  (experimental) support for your own OpenAI-compatible pools/servers
  via the new Custom provider.
- **2026-09-04** — Added support for the Polza.ai provider, for users
  connecting from Russia.

