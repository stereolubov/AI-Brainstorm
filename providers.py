# -*- coding: utf-8 -*-
"""
Registry of supported OpenAI-compatible API providers/aggregators.

OpenRouter is the original, full-featured provider this app was built
around. Requesty is a similarly-shaped hosted multi-vendor router (same
"provider/model" model-ID convention, OpenAI-compatible chat
completions endpoint), confirmed against Requesty's own docs
(docs.requesty.ai) rather than assumed:

- Cost: Requesty returns a per-request USD cost in usage.cost — the
  EXACT same field name OpenRouter uses — automatically, no special
  request parameter needed (for non-streaming, which is all we send).
  Our existing budget tracking already works here with zero code
  changes; no capability flag needed for it.
- Reasoning: supported, but shaped differently — a flat top-level
  "reasoning_effort": "low"/"medium"/"high"/"none" string, not
  OpenRouter's nested {"reasoning": {"max_tokens": N}} numeric budget.
  See reasoning_format below and the translation in api_client.ask_model.
- Free-models filter: NOT available — Requesty's public /models
  endpoint only returns {id, object, created, owned_by}, no pricing.
- Balance/key-info: Requesty DOES have a per-key usage endpoint, but
  it lives on a different host (api-v2.requesty.ai, not
  router.requesty.ai), needs the key's ID as a URL path parameter, and
  expects a JSON body with a date range even on a GET request — a
  meaningfully different flow from OpenRouter's single-bearer-token
  GET /key, not just a URL swap. Deferred rather than half-implemented.
- Web search: Requesty DOES support web search, but per model family
  via native provider tools (Anthropic's web_search_preview for Claude
  models, Google's web_search function for Gemini models) — not a
  single universal flag that works for any model like OpenRouter's
  "web" plugin. Since our moderator's web-lookup step is designed to
  work with whichever model the user picked as moderator, this doesn't
  drop in cleanly; deferred rather than restricting moderator choice.

Custom covers any other OpenAI-compatible endpoint (local servers like
LM Studio/Ollama, a self-hosted proxy, etc.) — genuinely unknowable in
advance, so it makes no promises: no families (its ID convention is
whatever the person's server uses, not OpenRouter's vendor-prefix
style), no pricing/cost UI, no web plugin, and reasoning is a raw
per-slot JSON fragment the person writes themselves rather than a
guessed shape (see reasoning_format="raw" and
api_client.ask_model's handling of reasoning_raw).
"""

DEFAULT_PROVIDER = "openrouter"

PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "has_pricing_data": True,     # /models includes per-model pricing -> free-models filter works
        "has_cost_tracking": True,    # usage.cost in every response -> budget UI is meaningful
        "has_web_plugin": True,       # plugins: [{"id": "web"}] web-search support, any model
        "has_key_info": True,         # single-token GET /key for balance checking
        "uses_families": True,
        "reasoning_format": "tokens",  # {"reasoning": {"max_tokens": N}} / {"enabled": false}
        "models_docs_url": "https://openrouter.ai/models",
        "reasoning_docs_url": "https://openrouter.ai/docs/use-cases/reasoning-tokens",
    },
    "requesty": {
        "name": "Requesty",
        "base_url": "https://router.requesty.ai/v1",
        "has_pricing_data": False,    # /models doesn't return pricing — no free-models filter
        "has_cost_tracking": True,    # usage.cost confirmed in every response too (same field name
                                       # as OpenRouter) — separate from has_pricing_data above, which
                                       # is only about /models NOT having per-model prices listed
        "has_web_plugin": False,      # web search exists but is per-model-family (Claude/Gemini only),
                                       # not a universal flag — doesn't fit a "any moderator model" design
        "has_key_info": False,        # usage endpoint exists but on a different host, needs key ID +
                                       # a date-range body — not a drop-in for our single-token balance check
        "uses_families": True,
        "reasoning_format": "effort",  # top-level "reasoning_effort": "low"/"medium"/"high"/"none"
        "models_docs_url": "https://www.requesty.ai/models",
        "reasoning_docs_url": "https://docs.requesty.ai/features/reasoning",
    },
    "custom": {
        "name": "Custom",
        "base_url": None,   # unknowable in advance — user types their own (see config's custom_base_url)
        "has_pricing_data": False,
        "has_cost_tracking": False,  # local/self-hosted servers essentially never report a $ cost —
                                      # budget UI (session budget field, running spent/total in Chat)
                                      # is hidden entirely rather than showing meaningless $0.0000
        "has_web_plugin": False,
        "has_key_info": False,
        "uses_families": False,  # families match OpenRouter's vendor-prefix convention, meaningless
                                  # for an arbitrary/local server — forced flat mode, checkbox hidden
        "reasoning_format": "raw",  # no guessable shape at all (OpenRouter/Requesty/LM Studio all
                                    # differ) — the person writes the exact JSON fragment themselves,
                                    # per participant slot (varies model to model on local servers),
                                    # merged into the request body as-is. Empty = send nothing.
        "models_docs_url": None,
        "reasoning_docs_url": None,
    },
}


def get_provider(provider_id):
    return PROVIDERS.get(provider_id, PROVIDERS[DEFAULT_PROVIDER])


def provider_ids_in_order():
    """Stable display order — OpenRouter first (the default/richest), then the rest."""
    return [DEFAULT_PROVIDER] + [pid for pid in PROVIDERS if pid != DEFAULT_PROVIDER]
