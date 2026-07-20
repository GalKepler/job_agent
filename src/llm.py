"""Provider abstraction: Anthropic or Ollama (OpenAI-compat API).

Set LLM_PROVIDER=ollama in .env (or environment) to route all LLM calls
through a local Ollama instance. Defaults to Anthropic.

Env vars:
  LLM_PROVIDER       anthropic (default) | ollama
  OLLAMA_BASE_URL    http://localhost:11434/v1 (default)
  OLLAMA_RANK_MODEL  qwen2.5:7b (default)
  OLLAMA_GEN_MODEL   llama3.1:8b (default)
"""

import json
import os
from typing import Any, cast

_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_OLLAMA_RANK_MODEL = os.getenv("OLLAMA_RANK_MODEL", "qwen2.5:7b")
_OLLAMA_GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "llama3.1:8b")

# Anthropic tool schema (used when PROVIDER=anthropic)
_SCORE_TOOL_ANTHROPIC: Any = {
    "name": "score_posting",
    "description": "Score a job posting against the candidate profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance_score": {
                "type": "integer",
                "description": "Raw fit score 0-10 before dealbreaker penalties.",
            },
            "level_match": {
                "type": "string",
                "enum": ["junior", "match", "stretch"],
                "description": "junior=below anchor, match=appropriate, stretch=above anchor",
            },
            "one_line_rationale": {"type": "string"},
            "dealbreakers_hit": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Dealbreaker ids triggered (empty list if none).",
            },
        },
        "required": [
            "relevance_score",
            "level_match",
            "one_line_rationale",
            "dealbreakers_hit",
        ],
    },
}


def make_client() -> Any:
    """Return the appropriate LLM client based on LLM_PROVIDER."""
    if _PROVIDER == "ollama":
        from openai import OpenAI

        return OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")
    import anthropic

    return anthropic.Anthropic()


def default_rank_model() -> str:
    return _OLLAMA_RANK_MODEL if _PROVIDER == "ollama" else "claude-haiku-4-5-20251001"


def default_gen_model() -> str:
    return _OLLAMA_GEN_MODEL if _PROVIDER == "ollama" else "claude-sonnet-4-6"


def score_posting_call(client: Any, model: str, prompt: str) -> dict[str, Any]:
    """Call score_posting tool. Works with both Anthropic and OpenAI clients."""
    if _is_openai(client):
        return _score_oai(client, model, prompt)
    return _score_anthropic(client, model, prompt)


def chat_call(client: Any, model: str, system: str, user: str) -> str:
    """Single-turn chat with a system prompt. Works with both client types."""
    if _is_openai(client):
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return str(resp.choices[0].message.content or "")
    # Anthropic path
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_block = next((b for b in resp.content if getattr(b, "type", None) == "text"), None)
    if text_block is None:
        raise RuntimeError("No text block in response")
    return str(getattr(text_block, "text", ""))


def _is_openai(client: Any) -> bool:
    return type(client).__module__.startswith("openai")


_JSON_SYSTEM = (
    "You are a job-fit scorer. Respond with ONLY a JSON object — no prose, no markdown. "
    'Required keys: "relevance_score" (integer 0-10), "level_match" ("junior"|"match"|"stretch"), '
    '"one_line_rationale" (string), "dealbreakers_hit" (array of strings).'
)


def _score_oai(client: Any, model: str, prompt: str) -> dict[str, Any]:
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _JSON_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return cast(dict[str, Any], json.loads(resp.choices[0].message.content or "{}"))


def _score_anthropic(client: Any, model: str, prompt: str) -> dict[str, Any]:
    from anthropic.types import ToolChoiceToolParam

    resp = client.messages.create(
        model=model,
        max_tokens=512,
        tools=[_SCORE_TOOL_ANTHROPIC],
        tool_choice=ToolChoiceToolParam(type="tool", name="score_posting"),
        messages=[{"role": "user", "content": prompt}],
    )
    for block in resp.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "score_posting"
        ):  # noqa: E501
            return cast(dict[str, Any], block.input)
    raise RuntimeError(f"No score_posting block in response: {resp}")
