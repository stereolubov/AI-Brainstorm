# -*- coding: utf-8 -*-
"""
OpenRouter API wrapper. Standard library only (urllib, json, re) — no
third-party dependencies to bundle into the exe.
"""

import json
import logging
import re
import urllib.request
import urllib.error

from models_catalog import FAMILIES
from i18n import t
from providers import get_provider, DEFAULT_PROVIDER

DEFAULT_BASE_URL = get_provider(DEFAULT_PROVIDER)["base_url"]
TIMEOUT_SECONDS = 180  # generous — local reasoning models on modest hardware can genuinely
                        # take a couple of minutes; a longer ceiling costs nothing for fast
                        # cloud providers (they return well before it's ever reached)
DEFAULT_MAX_TOKENS = 800  # generous margin so a reply doesn't get cut off mid-sentence

logger = logging.getLogger("ai_brainstorm.api_client")


class OpenRouterError(Exception):
    """Base exception for OpenRouter request failures."""


def _headers(api_key=None):
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-ai-brainstorm-app",
        "X-Title": "AI Brainstorm Desktop",
    }
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    return headers


def _request(url, api_key=None, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
            error_json = json.loads(error_body)
            message = error_json.get("error", {}).get("message", error_body)
        except Exception:
            message = str(e)
        logger.error(t("log_http_error", code=e.code, url=url, message=message))
        raise OpenRouterError(t("api_error", code=e.code, message=message)) from e
    except urllib.error.URLError as e:
        logger.error(t("log_url_error", url=url, reason=e.reason))
        raise OpenRouterError(t("network_error", reason=e.reason)) from e
    except TimeoutError as e:
        # NOT a subclass of urllib.error.URLError — a read that times out
        # mid-response (as opposed to failing to connect at all) raises
        # this directly from the socket layer, bypassing urllib's own
        # error wrapping entirely. Confirmed live: a local reasoning
        # model that took longer than the old 60s ceiling to finish
        # generating crashed the worker thread with an unhandled
        # TimeoutError instead of being treated as a normal API failure.
        logger.error(t("log_timeout_error", url=url, seconds=TIMEOUT_SECONDS))
        raise OpenRouterError(t("timeout_error", seconds=TIMEOUT_SECONDS)) from e


# Maps our fixed token-budget levels (see models_catalog.REASONING_LEVELS)
# to the effort words that "effort"-style providers (Requesty) expect —
# their API takes "low"/"medium"/"high"/"none", not a raw token count.
# "none"/"min" are documented Requesty synonyms that disable/minimize
# reasoning across all supported models, so that's what an absent or
# zero budget maps to.
_TOKENS_TO_EFFORT = {
    None: "none",
    0: "none",
    1024: "low",
    4096: "medium",
    16000: "high",
}


def ask_model(api_key, model_id, system_prompt, user_prompt, max_tokens=DEFAULT_MAX_TOKENS,
              reasoning_max_tokens=None, web_search_max_results=None, base_url=DEFAULT_BASE_URL,
              reasoning_format="tokens", reasoning_raw=None, image_data_url=None):
    """
    Sends a single chat request to `model_id` via the given provider's
    OpenAI-compatible chat completions endpoint (base_url + "/chat/completions").

    reasoning_max_tokens: None/0 disables reasoning; our 3 fixed budget
    levels (1024/4096/16000) otherwise. How this actually gets sent
    depends on reasoning_format (see providers.py, confirmed against
    each provider's own docs rather than guessed):
      "tokens" (OpenRouter) — payload["reasoning"] = {"max_tokens": N},
        or {"enabled": False} to disable. Models without reasoning
        support just ignore the field, no error.
      "effort" (Requesty) — a flat top-level payload["reasoning_effort"]
        string ("low"/"medium"/"high"/"none"), NOT nested — our fixed
        token budgets are mapped to the closest effort word via
        _TOKENS_TO_EFFORT, since Requesty's own API doesn't take a raw
        token count for this.
      "raw" (Custom) — there's no guessable shape for an arbitrary
        endpoint (confirmed OpenRouter/Requesty/LM Studio already differ
        from each other), so `reasoning_max_tokens` is ignored entirely
        and `reasoning_raw` is used instead: a JSON object fragment the
        person wrote themselves for this specific participant (local
        servers vary the shape model to model), merged into the request
        body as-is via payload.update(...). Empty/None sends nothing.
        Invalid JSON is logged as a warning and skipped — one typo in
        one participant's settings shouldn't break their reply.

    web_search_max_results: if set, enables OpenRouter's "web" plugin
    for this one request — it runs a single web search (via Exa, or the
    provider's own native search where supported) and injects the
    results as an extra system message before generating the reply.
    Declarative and one-shot on purpose (vs. the newer tool-calling
    "openrouter:web_search" server tool, which lets the model call
    search adaptively/repeatedly within a turn) — a single bounded
    search keeps cost predictable and needs no tool-call round-trip
    loop on our side. Its cost is already included in the returned
    usage["cost"], same as everything else. Only meaningful for
    providers with has_web_plugin=True — the caller is responsible for
    not passing this otherwise (see providers.py).

    image_data_url: if set, a "data:image/...;base64,..." URL attached
    to the user message via the standard OpenAI-compatible multi-part
    content shape ({"type": "image_url", "image_url": {"url": ...}}) —
    unlike reasoning/web search, this format is genuinely uniform across
    every provider we support (all OpenAI-compatible), so no
    per-provider translation is needed. Models without vision support
    typically either ignore the image or the call errors out — handled
    the same as any other model failure by the caller (cooldown + retry
    with someone else), not something we can detect in advance.

    Returns (reply_text, usage), where usage is
    {"prompt_tokens": int, "completion_tokens": int, "cost": float|None}.
    Requesty returns "cost" under this exact same key too (confirmed
    against its docs), so budget tracking works unchanged there.

    Raises OpenRouterError on a network error or API error (incl. 429).
    """
    if not api_key:
        raise OpenRouterError(t("no_api_key_error"))

    user_content = user_prompt
    if image_data_url:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
    }
    if reasoning_format == "raw":
        raw = (reasoning_raw or "").strip()
        if raw:
            try:
                extra = json.loads(raw)
                if isinstance(extra, dict):
                    payload.update(extra)
                else:
                    logger.warning(t("log_reasoning_raw_not_object", model=model_id))
            except json.JSONDecodeError as e:
                logger.warning(t("log_reasoning_raw_invalid", model=model_id, error=e))
        # else: empty field on purpose — send nothing reasoning-related at all
    elif reasoning_format == "effort":
        payload["reasoning_effort"] = _TOKENS_TO_EFFORT.get(reasoning_max_tokens, "none")
    else:
        if reasoning_max_tokens and reasoning_max_tokens > 0:
            payload["reasoning"] = {"max_tokens": reasoning_max_tokens}
        else:
            payload["reasoning"] = {"enabled": False}
    if web_search_max_results:
        payload["plugins"] = [{"id": "web", "max_results": web_search_max_results}]

    logger.debug(t("log_model_request", model=model_id, max_tokens=max_tokens))
    result = _request(f"{base_url}/chat/completions", api_key, method="POST", payload=payload)

    try:
        content = result["choices"][0]["message"]["content"].strip()
        finish_reason = result["choices"][0].get("finish_reason")
    except (KeyError, IndexError) as e:
        raise OpenRouterError(t("parse_error", error=e, result=result)) from e

    if finish_reason == "length":
        logger.warning(t("log_model_truncated", model=model_id, max_tokens=max_tokens))
        content += t("truncated_note")

    usage_raw = result.get("usage", {}) or {}
    usage = {
        "prompt_tokens": usage_raw.get("prompt_tokens"),
        "completion_tokens": usage_raw.get("completion_tokens"),
        "cost": usage_raw.get("cost"),
    }
    logger.debug(t(
        "log_model_response", model=model_id,
        tokens=usage.get("completion_tokens"), cost=usage.get("cost"),
    ))

    return content, usage


def get_key_info(api_key, base_url=DEFAULT_BASE_URL, key_info_path="/key", key_info_format="openrouter"):
    """
    Returns balance/usage info for the given key. Shape depends on
    key_info_format (see providers.py — only meaningful for providers
    with has_key_info=True; the caller is responsible for not exposing
    this action otherwise):

      "openrouter" — {usage, limit, limit_remaining, label}, from
        GET {base_url}/key -> {"data": {...}}. "usage" is cumulative
        spend so far; "limit"/"limit_remaining" are None if the key has
        no cap set (pay-as-you-go).

      "polza" — {balance}, from GET {base_url}/balance ->
        {"amount": "9.28591714"} (a string). Polza's model is a prepaid
        balance, not a usage/cap pair — there's no equivalent of
        OpenRouter's "usage so far" or an optional limit, just "how
        much is left". Denominated in RUB, not USD (see providers.py's
        "currency" field and providers.format_money()).
    """
    if not api_key:
        raise OpenRouterError(t("no_api_key_short_error"))
    result = _request(f"{base_url}{key_info_path}", api_key, method="GET")

    if key_info_format == "polza":
        amount = result.get("amount")
        try:
            balance = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            balance = None
        return {"balance": balance}

    data = result.get("data", {})
    return {
        "usage": data.get("usage"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "label": data.get("label"),
    }


def _fetch_all_models_raw(api_key=None, base_url=DEFAULT_BASE_URL):
    """Raw model list (list of dicts with id/pricing/etc.) — fetched once
    and reused to derive all_ids, free_ids, and family groupings without
    hitting the network three times for one refresh click."""
    result = _request(f"{base_url}/models", api_key, method="GET")
    return result.get("data", []) or []


def _is_free_model(model_data):
    """OpenRouter's /models response includes a "pricing" object with
    per-token prices as strings (to dodge float precision issues) — a
    model is free when both prompt and completion pricing are exactly
    "0". More robust than checking for a ":free" suffix in the id,
    though that convention also happens to hold in practice. Only
    meaningful for providers with has_pricing_data=True — for others,
    model dicts simply won't have a "pricing" field and this always
    returns False, so free_ids from build_family_options() comes back
    empty rather than erroring."""
    pricing = model_data.get("pricing") or {}
    try:
        return float(pricing.get("prompt", "1")) == 0 and float(pricing.get("completion", "1")) == 0
    except (TypeError, ValueError):
        return False


def fetch_all_model_ids(api_key=None, base_url=DEFAULT_BASE_URL):
    """Full list of model IDs from the given provider (public endpoint,
    key optional but passed along if present — doesn't hurt)."""
    return [m.get("id", "") for m in _fetch_all_models_raw(api_key, base_url) if m.get("id")]


def build_family_options(api_key=None, base_url=DEFAULT_BASE_URL):
    """
    Groups the full model list by family (see models_catalog.FAMILIES)
    via regex — works the same for any provider using the same
    "provider/model" ID convention as OpenRouter (confirmed for Requesty
    too).

    Returns (options, all_ids, free_ids):
      options — {family_key: [sorted matching model_id, ...]}
      all_ids — the full unfiltered ID list (used e.g. for autocomplete
                in custom-model slots, where a model might not match any family).
      free_ids — subset of all_ids priced at $0 for both prompt and
                completion (see _is_free_model) — empty for providers
                without pricing data in their /models response.
    """
    raw = _fetch_all_models_raw(api_key, base_url)
    all_ids = [m.get("id", "") for m in raw if m.get("id")]
    free_ids = [m.get("id", "") for m in raw if m.get("id") and _is_free_model(m)]

    options = {}
    for fam in FAMILIES:
        pattern = re.compile(fam["pattern"])
        matched = sorted({model_id for model_id in all_ids if pattern.match(model_id)})
        options[fam["key"]] = matched
    return options, sorted(all_ids), sorted(free_ids)


# ---------- Moderator ----------

_MODERATOR_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _resolve_participant(raw_value, participants, allow_user):
    """
    Softly matches whatever the moderator returned in "next" against a
    real participant. Moderator models (especially weaker ones) often
    write a short name ("claude-sonnet-5") instead of the full id
    ("anthropic/claude-sonnet-5"), a family name ("Claude", "MistralAI"),
    or an alias without the provider prefix ("grok-latest"). This used to
    make EVERY moderator answer get rejected as invalid, falling back
    every single time — the moderator effectively never worked.

    Matches against participant_id (not the raw model id) — the two
    differ only when the same underlying model appears in more than one
    custom slot (allowed, so one model can be given several different
    personas); the 2nd/3rd/... occurrence's participant_id carries a
    "#2"/"#3"/... suffix precisely so it can still be told apart here.

    Returns a participant_id, "user" (if allowed), or None.
    """
    if not raw_value:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    if raw.lower() == "user":
        return "user" if allow_user else None

    # 1. exact match on the full participant_id
    for p in participants:
        if p["participant_id"] == raw:
            return p["participant_id"]

    def tail(participant_id):
        return participant_id.lstrip("~").split("/", 1)[-1].lower()

    raw_lower = raw.lstrip("~").lower()

    # 2. match on the id's "tail" after the provider (and without ~latest)
    for p in participants:
        if tail(p["participant_id"]) == raw_lower:
            return p["participant_id"]

    # 3. match on family name/label, e.g. "Gemini", "MistralAI"
    #    (a label like "Claude (claude-sonnet-5)" -> base part "claude")
    for p in participants:
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower == base_label:
            return p["participant_id"]

    # 4. last resort: substring match either way
    for p in participants:
        id_lower = p["participant_id"].lower()
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower in id_lower or id_lower in raw_lower or raw_lower in base_label or base_label in raw_lower:
            return p["participant_id"]

    return None


def _parse_moderator_reply(raw_text, participants, allow_user):
    """
    Extracts the moderator's structured decision from its reply. Models
    sometimes wrap the JSON in ```-fences or add surrounding text — grab
    the first { ... } substring.

    Returns {"next": id_or_"user"_or_None, "task": str, "reason": str,
    "reaction_type": str, "wrap_up": bool}.
    """
    empty = {"next": None, "task": "", "reason": "", "reaction_type": "", "wrap_up": False}
    match = _MODERATOR_JSON_RE.search(raw_text or "")
    if not match:
        return empty
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return empty

    next_id = _resolve_participant(data.get("next"), participants, allow_user)
    return {
        "next": next_id,
        "task": str(data.get("task", "") or ""),
        "reason": str(data.get("reason", "") or ""),
        "reaction_type": str(data.get("reaction_type", "") or ""),
        "wrap_up": bool(data.get("wrap_up", False)),
    }


def ask_moderator(api_key, moderator_model_id, topic, transcript_text, participants,
                   allow_user, replies_done=0, max_replies=0, is_final_reply=False,
                   base_url=DEFAULT_BASE_URL, reasoning_format="tokens"):
    """
    Asks the moderator model who should speak next, what they should do,
    why, what type of reaction is needed, and whether it's time to wrap
    up (useful as the reply limit approaches).

    is_final_reply=True means this reply is guaranteed to be the last one
    in the session. wrap_up/task are force-set by the caller (main.py)
    regardless of what the moderator returns — here it only strengthens
    the prompt so the moderator picks a participant well-suited to close things out.

    participants — list of {id, participant_id, label, persona} dicts
    (from full_catalog, covering both standard and custom models); MUST
    contain only currently available participants (see the "temporarily
    unavailable" mechanism in main.py) so the moderator can't physically
    pick a model that's erroring out right now. The moderator is shown
    and picks by participant_id (unique even when the same underlying
    model appears in multiple custom slots), not the raw model id.

    Returns (decision, usage); decision is _parse_moderator_reply's dict
    (next may be None if the moderator gave no recognizable answer — the
    caller then picks a fallback).
    """
    participants_desc = "\n".join(
        f"- {p['participant_id']}: {p['label']} — {p['persona'][:100]}" for p in participants
    )
    if allow_user:
        # "user" used to only be mentioned in a sentence AFTER this list,
        # while the system prompt demanded picking "ONLY from the list
        # below" — that contradiction meant the moderator almost never
        # invited the user (it technically wasn't "in the list"). Now
        # user is a real line in the list itself.
        participants_desc += t("moderator_user_entry")

    if is_final_reply:
        progress_note = t("moderator_final_reply_note", max_replies=max_replies)
    else:
        progress_note = t("moderator_progress_note", done=replies_done, max_replies=max_replies) if max_replies else ""

    system_prompt = t("moderator_system_prompt_prefix")
    if allow_user:
        system_prompt += t("moderator_system_prompt_user_clause")
    system_prompt += t("moderator_system_prompt_suffix")

    user_prompt = t(
        "moderator_user_prompt",
        topic=topic, progress_note=progress_note, participants_desc=participants_desc,
        transcript=transcript_text or t("discussion_just_starting"),
    )

    content, usage = ask_model(
        api_key, moderator_model_id, system_prompt, user_prompt,
        max_tokens=220, reasoning_max_tokens=None, base_url=base_url,
        reasoning_format=reasoning_format,
    )
    decision = _parse_moderator_reply(content, participants, allow_user)
    if decision["next"] is None:
        logger.warning(t("log_moderator_unrecognized", content=content))
    else:
        logger.debug(t("log_moderator_decision", id=decision["next"], task=decision["task"], reason=decision["reason"]))
    return decision, usage


def ask_moderator_web_lookup(api_key, moderator_model_id, topic, base_url=DEFAULT_BASE_URL,
                              reasoning_format="tokens"):
    """
    Optional pre-session step: asks the moderator model to check the web
    for the topic (current date, recent events, any real-world context
    the participants might otherwise miss — e.g. a topic that
    unknowingly lines up with today's actual date) and summarize
    anything worth keeping in mind. Runs once, before the discussion
    starts; the summary gets folded into the transcript so every
    participant sees it from their very first reply onward.

    Only meaningful for providers with has_web_plugin=True (see
    providers.py) — the caller is responsible for not exposing this
    action otherwise.

    Returns (summary_text, usage). Raises OpenRouterError on failure —
    the caller should treat that as "skip it, don't block the session".
    """
    system_prompt = t("web_lookup_system_prompt")
    user_prompt = t("web_lookup_user_prompt", topic=topic)
    return ask_model(
        api_key, moderator_model_id, system_prompt, user_prompt,
        max_tokens=400, reasoning_max_tokens=None, web_search_max_results=5,
        base_url=base_url, reasoning_format=reasoning_format,
    )
