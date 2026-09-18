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
  free-models filter, balance check, moderator web search, and &#36; cost
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
  server), no balance/free-filter/web-search UI, no &#36; budget tracking
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
python build.py
```

The exe appears in `dist/AI-Brainstorm-release.exe` — about 10 MB, with
no external dependencies. PyInstaller caches aggressively, so `build.py`
always builds clean and clears `build/` afterwards.

Every build setting lives in `AI-Brainstorm.spec` rather than on the
command line: the list of excluded stdlib modules, the filter for Tcl
modules a plain Tk GUI never sources, the icon, and the `fonts/` folder.
That file is tracked in the repo — a build recipe should not exist only
on one machine.

```
python build.py --console
```

Builds the same thing with a console attached. This exists because a
windowed onefile exe that fails during startup dies silently with exit
code 1 and nothing to read; the console build prints the traceback
instead. If a release build suddenly stops launching, a too-aggressive
entry in the spec's `EXCLUDES` is the usual cause.

`favicon.ico` is embedded into the exe (what Explorer shows) and also
bundled inside it, so the running app can set its own window and taskbar
icon via `iconbitmap()` and a direct WinAPI call (`WM_SETICON`) — for a
crisp icon in Alt+Tab rather than a blurry upscale.

Manrope and JetBrains Mono (both SIL OFL) live in `fonts/` and are
bundled into the exe. The app registers them into its own process only,
via `AddFontResourceEx` — nothing is installed system-wide and no admin
rights are needed. If the files are missing or registration fails, the
UI quietly falls back to Segoe UI and Consolas.

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
autocomplete down to &#36;0-priced models, detected via OpenRouter's own
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

- **Budget** (&#36;, set in Settings; OpenRouter/Requesty only — the field
  is hidden entirely for Custom, which essentially never reports a &#36;
  cost) — includes both participant replies and moderator calls. The
  provider returns an exact cost per request; it's shown under each
  reply (in italic gray, right-aligned), split out when a moderator
  call is folded in (e.g. "&#36;0.0031 + moderator &#36;0.0012 = &#36;0.0043").
- **Max replies** (set on the Chat tab) — counts only participant
  replies, not the moderator's own calls or your own turns. The only
  stop condition that applies to Custom.

A model that starts erroring (rate limits, timeouts, etc.) is put on a
short cooldown and excluded from the moderator's choices — quietly,
without spamming the chat; the reason stays visible in the Log tab.

## Chat display

- Every reply is its own card, carrying the speaker's color as a stripe
  down its left edge, the exact model id next to the name, and what that
  reply cost, aligned right.
- Your own turns — the topic and any intervention — also get a tinted
  background; the session summary keeps its own accent color.
- `**bold**`, `` `inline code` ``, fenced ` ```code blocks``` `,
  headers, and bullet lists render properly, not as raw markdown.
- **Ctrl+C** copies the selection. Selecting works inside one reply, not
  across several — each reply is a separate widget, which is what lets
  it have its own background and stripe.
- **Copy All** and **Export…** are unaffected by that: both are built
  from the original message text, with all its markdown intact, rather
  than scraped off the screen. Export saves `.md` or `.txt`.

## Log tab

An optional tab mirroring what a console would show — model calls,
costs, moderator decisions, errors. Laid out as a table: timestamp, a
colored badge for the level, then the message. Toggle it on the Settings
tab; it keeps its own history for the whole app session even while
hidden. Unlike the chat, it is one text widget, so **Ctrl+A** and
**Ctrl+C** work across the whole log.

## Project layout

```
ai_brainstorm/
├── main.py              — entry point, Tkinter UI, moderator/worker logic
├── config.py            — profiles, app-wide settings, locale folder paths
├── models_catalog.py    — model families, reasoning levels, catalog assembly
├── api_client.py        — provider-agnostic API calls: chat, moderator, model list, key balance
├── i18n.py              — translation loading/fallback, built-in RU/EN dictionaries
├── theme.py             — design tokens for both themes, fonts, ttk.Style() + Text/Canvas theming
├── ui_widgets.py        — composite widgets ttk lacks: tab strip, cards, message feed
├── providers.py         — provider registry (OpenRouter/Requesty/Polza/Custom) and capability flags
├── build.py             — one-command single-exe build (--console for a diagnostic one)
├── AI-Brainstorm.spec   — every build setting: excludes, icon, bundled data
├── fonts/               — Manrope + JetBrains Mono (SIL OFL), bundled into the exe
├── favicon.ico          — app icon (optional, add your own)
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
- **Not every model can actually see an attached image.** There's no
  way to check vision support in advance, so a model without it will
  typically just error out on that reply — same handling as any other
  model failure: a short cooldown, and the moderator picks someone else
  instead. Confirmed working live: vision-capable models correctly saw
  and discussed the image, while the rest quietly dropped out and got
  replaced, without interrupting the session.

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
- **2026-09-05** — Added support for attaching an image to the topic
  for discussion.
- **2026-09-18** — New interface design. Settings are grouped into
  numbered cards 01–06; the chat is now a feed where every reply is its
  own card with the speaker's color stripe, model id and cost; the tabs
  have their own strip with an underline on the active one and a
  provider chip on the right. Both themes, Light and Dark, were redrawn
  from scratch. Manrope and JetBrains Mono are bundled into the exe and
  registered at startup — nothing has to be installed system-wide. The
  Log tab is now a table: time, colored level badge, message.
- **2026-09-18** — Building is one command, `python build.py`
  (`--console` produces a diagnostic build with a console attached).
  `AI-Brainstorm.spec` is no longer gitignored and lives in the repo.
  The exe shrank from 10.7 MB to 10.2 MB — with the bundled fonts
  already included.
- **2026-09-18** — Fixed end-of-session spend reconciliation. Paid
  providers always reported "actually charged: &#36;0.0000": the key's
  balance was read the instant the last reply landed, but providers post
  the charge asynchronously, so the difference was necessarily zero. The
  figure is now re-read a few times, and if the provider still hasn't
  posted it, the app says so instead of presenting a zero as fact.

