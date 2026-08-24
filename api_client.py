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

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_INFO_URL = "https://openrouter.ai/api/v1/key"
MODELS_LIST_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT_SECONDS = 60
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


def ask_model(api_key, model_id, system_prompt, user_prompt, max_tokens=DEFAULT_MAX_TOKENS, reasoning_max_tokens=None):
    """
    Sends a single chat request to `model_id` via OpenRouter.

    reasoning_max_tokens: None/0 disables reasoning entirely
    (payload["reasoning"] = {"enabled": False}); a positive number sets a
    token budget for hidden reasoning before the visible reply
    (payload["reasoning"] = {"max_tokens": N}). Models without reasoning
    support just ignore the field, no error.

    Returns (reply_text, usage), where usage is
    {"prompt_tokens": int, "completion_tokens": int, "cost": float|None}.

    Raises OpenRouterError on a network error or API error (incl. 429).
    """
    if not api_key:
        raise OpenRouterError(t("no_api_key_error"))

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }
    if reasoning_max_tokens and reasoning_max_tokens > 0:
        payload["reasoning"] = {"max_tokens": reasoning_max_tokens}
    else:
        payload["reasoning"] = {"enabled": False}

    logger.debug(t("log_model_request", model=model_id, max_tokens=max_tokens))
    result = _request(CHAT_URL, api_key, method="POST", payload=payload)

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


def get_key_info(api_key):
    """Returns {usage, limit, limit_remaining, label} for the given key."""
    if not api_key:
        raise OpenRouterError(t("no_api_key_short_error"))
    result = _request(KEY_INFO_URL, api_key, method="GET")
    data = result.get("data", {})
    return {
        "usage": data.get("usage"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "label": data.get("label"),
    }


def fetch_all_model_ids(api_key=None):
    """Full list of OpenRouter model IDs (public endpoint, key optional
    but passed along if present — doesn't hurt)."""
    result = _request(MODELS_LIST_URL, api_key, method="GET")
    return [m.get("id", "") for m in result.get("data", []) if m.get("id")]


def build_family_options(api_key=None):
    """
    Groups the full OpenRouter model list by family (see
    models_catalog.FAMILIES) via regex.

    Returns (options, all_ids):
      options — {family_key: [sorted matching model_id, ...]}
      all_ids — the full unfiltered ID list (used e.g. for autocomplete
                in custom-model slots, where a model might not match any family).
    """
    all_ids = fetch_all_model_ids(api_key)
    options = {}
    for fam in FAMILIES:
        pattern = re.compile(fam["pattern"])
        matched = sorted({model_id for model_id in all_ids if pattern.match(model_id)})
        options[fam["key"]] = matched
    return options, all_ids


# ---------- Moderator ----------

_MODERATOR_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _resolve_participant(raw_value, participants, allow_user):
    """
    Softly matches whatever the moderator returned in "next" against a
    real participant id. Moderator models (especially weaker ones) often
    write a short name ("claude-sonnet-5") instead of the full id
    ("anthropic/claude-sonnet-5"), a family name ("Claude", "MistralAI"),
    or an alias without the provider prefix ("grok-latest"). This used to
    make EVERY moderator answer get rejected as invalid, falling back
    every single time — the moderator effectively never worked.

    Returns a participant id, "user" (if allowed), or None.
    """
    if not raw_value:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    if raw.lower() == "user":
        return "user" if allow_user else None

    # 1. exact match on the full id
    for p in participants:
        if p["id"] == raw:
            return p["id"]

    def tail(model_id):
        return model_id.lstrip("~").split("/", 1)[-1].lower()

    raw_lower = raw.lstrip("~").lower()

    # 2. match on the id's "tail" after the provider (and without ~latest)
    for p in participants:
        if tail(p["id"]) == raw_lower:
            return p["id"]

    # 3. match on family name/label, e.g. "Gemini", "MistralAI"
    #    (a label like "Claude (claude-sonnet-5)" -> base part "claude")
    for p in participants:
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower == base_label:
            return p["id"]

    # 4. last resort: substring match either way
    for p in participants:
        id_lower = p["id"].lower()
        base_label = p["label"].split("(")[0].strip().lower()
        if raw_lower in id_lower or id_lower in raw_lower or raw_lower in base_label or base_label in raw_lower:
            return p["id"]

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
                   allow_user, replies_done=0, max_replies=0, is_final_reply=False):
    """
    Asks the moderator model who should speak next, what they should do,
    why, what type of reaction is needed, and whether it's time to wrap
    up (useful as the reply limit approaches).

    is_final_reply=True means this reply is guaranteed to be the last one
    in the session. wrap_up/task are force-set by the caller (main.py)
    regardless of what the moderator returns — here it only strengthens
    the prompt so the moderator picks a participant well-suited to close things out.

    participants — list of {id, label, persona} dicts (from full_catalog,
    covering both standard and custom models); MUST contain only
    currently available participants (see the "temporarily unavailable"
    mechanism in main.py) so the moderator can't physically pick a model
    that's erroring out right now.

    Returns (decision, usage); decision is _parse_moderator_reply's dict
    (next may be None if the moderator gave no recognizable answer — the
    caller then picks a fallback).
    """
    participants_desc = "\n".join(
        f"- {p['id']}: {p['label']} — {p['persona'][:100]}" for p in participants
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
        max_tokens=220, reasoning_max_tokens=None,
    )
    decision = _parse_moderator_reply(content, participants, allow_user)
    if decision["next"] is None:
        logger.warning(t("log_moderator_unrecognized", content=content))
    else:
        logger.debug(t("log_moderator_decision", id=decision["next"], task=decision["task"], reason=decision["reason"]))
    return decision, usage
