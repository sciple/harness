"""Tests for skills — uses monkeypatch to avoid any real LLM calls."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture()
def base_state():
    return {
        "model": "test-model",
        "messages": [],
        "gen_params": {},
    }


class TestTranslateFr:
    def _make_state(self, messages=None):
        return {
            "model": "test-model",
            "messages": messages or [],
            "gen_params": {},
        }

    def test_translate_fr_with_args(self, monkeypatch):
        calls = []

        def fake_stream(client, model, messages, gen_params=None):
            calls.append(messages)
            return ("", None)

        monkeypatch.setattr("agent._stream_response", fake_stream)

        import skills.translate_fr as skill
        state = self._make_state()
        result = skill.run("Hello world", state, MagicMock())

        assert result == ""
        assert len(calls) == 1
        prompt = calls[0][0]["content"]
        assert "Hello world" in prompt
        assert "French" in prompt

    def test_translate_fr_fallback_to_last_user_msg(self, monkeypatch):
        calls = []

        def fake_stream(client, model, messages, gen_params=None):
            calls.append(messages)
            return ("", None)

        monkeypatch.setattr("agent._stream_response", fake_stream)

        import skills.translate_fr as skill
        state = self._make_state(messages=[
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "The sky is blue."},
            {"role": "assistant", "content": "Yes indeed."},
        ])
        result = skill.run("", state, MagicMock())

        assert result == ""
        assert len(calls) == 1
        prompt = calls[0][0]["content"]
        assert "The sky is blue." in prompt

    def test_translate_fr_no_text(self, monkeypatch):
        monkeypatch.setattr("agent._stream_response", lambda *a, **kw: ("", None))

        import skills.translate_fr as skill
        state = self._make_state(messages=[])
        result = skill.run("", state, MagicMock())

        assert "Usage" in result

    def test_translate_fr_skips_non_user_messages(self, monkeypatch):
        monkeypatch.setattr("agent._stream_response", lambda *a, **kw: ("", None))

        import skills.translate_fr as skill
        state = self._make_state(messages=[
            {"role": "system", "content": "System prompt."},
            {"role": "assistant", "content": "Some assistant text."},
        ])
        result = skill.run("", state, MagicMock())

        assert "Usage" in result
