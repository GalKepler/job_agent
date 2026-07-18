"""Tests for src/llm — provider dispatch logic."""

import json
from unittest.mock import MagicMock, patch


def _anthropic_score_client(score: int = 8) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "score_posting"
    block.input = {
        "relevance_score": score,
        "level_match": "match",
        "one_line_rationale": "Good fit.",
        "dealbreakers_hit": [],
    }
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.__class__.__module__ = "anthropic"
    client.messages.create.return_value = resp
    return client


def _openai_score_client(score: int = 7) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(
        {
            "relevance_score": score,
            "level_match": "match",
            "one_line_rationale": "Decent fit.",
            "dealbreakers_hit": [],
        }
    )
    choice = MagicMock()
    choice.message.tool_calls = [tool_call]
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.__class__.__module__ = "openai.something"
    client.chat.completions.create.return_value = resp
    return client


def _anthropic_chat_client(text: str = "## Verdict\nStrong.") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.__class__.__module__ = "anthropic"
    client.messages.create.return_value = resp
    return client


def _openai_chat_client(text: str = "## Verdict\nGood.") -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.__class__.__module__ = "openai.something"
    client.chat.completions.create.return_value = resp
    return client


def test_score_posting_anthropic_path() -> None:
    from src.llm import score_posting_call

    client = _anthropic_score_client(score=9)
    result = score_posting_call(client, "claude-haiku-4-5-20251001", "prompt")
    assert result["relevance_score"] == 9
    assert result["level_match"] == "match"
    client.messages.create.assert_called_once()


def test_score_posting_openai_path() -> None:
    from src.llm import score_posting_call

    client = _openai_score_client(score=7)
    result = score_posting_call(client, "qwen2.5:7b", "prompt")
    assert result["relevance_score"] == 7
    client.chat.completions.create.assert_called_once()


def test_chat_call_anthropic_path() -> None:
    from src.llm import chat_call

    client = _anthropic_chat_client("## Verdict\nStrong.")
    text = chat_call(client, "claude-sonnet-4-6", "system", "user")
    assert "Verdict" in text
    client.messages.create.assert_called_once()


def test_chat_call_openai_path() -> None:
    from src.llm import chat_call

    client = _openai_chat_client("## Verdict\nGood.")
    text = chat_call(client, "llama3.1:8b", "system", "user")
    assert "Verdict" in text
    client.chat.completions.create.assert_called_once()


def test_make_client_anthropic(monkeypatch: object) -> None:
    import os

    with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
        # Reload the module so _PROVIDER re-reads env — use importlib
        import importlib

        import src.llm as llm_mod

        importlib.reload(llm_mod)
        with patch("anthropic.Anthropic") as mock_cls:
            llm_mod.make_client()
            mock_cls.assert_called_once()


def test_default_models_switch_by_provider() -> None:
    import importlib
    import os

    import src.llm as llm_mod

    with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
        importlib.reload(llm_mod)
        assert "haiku" not in llm_mod.default_rank_model()
        assert "claude" not in llm_mod.default_gen_model()

    with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
        importlib.reload(llm_mod)
        assert "haiku" in llm_mod.default_rank_model()
        assert "sonnet" in llm_mod.default_gen_model()
