"""Tests for commands/__init__.py — /reset, /drop, /model, /set, /unset, /system, /compress."""

import sys
import pytest
from unittest.mock import MagicMock, patch


def _dispatch(cmd: str, state: dict):
    """Helper: call commands.dispatch and return the output string."""
    import commands
    handled, output = commands.dispatch(cmd, state)
    assert handled, f"Command '{cmd}' was not handled"
    return output or ""


def _make_messages():
    return [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "Fine"},
    ]


# ---------------------------------------------------------------------------
# /reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_clears_non_system_messages(self, state):
        state["messages"] = _make_messages()
        _dispatch("/reset", state)
        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "system"

    def test_clears_usage(self, state):
        state["messages"] = _make_messages()
        state["usage"] = {"prompt_tokens": 50, "total_tokens": 100}
        _dispatch("/reset", state)
        assert state["usage"] == {}

    def test_clears_context_length(self, state):
        state["messages"] = _make_messages()
        state["context_length"] = 4096
        _dispatch("/reset", state)
        assert state["context_length"] is None

    def test_preserves_system_message(self, state):
        state["messages"] = _make_messages()
        _dispatch("/reset", state)
        assert state["messages"][0]["content"] == "You are helpful."


# ---------------------------------------------------------------------------
# /drop
# ---------------------------------------------------------------------------

class TestDrop:
    def test_drop_single_message(self, state):
        state["messages"] = _make_messages()
        original_len = len(state["messages"])
        _dispatch("/drop 1", state)
        assert len(state["messages"]) == original_len - 1

    def test_drop_range(self, state, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        state["messages"] = _make_messages()
        _dispatch("/drop 1-2", state)
        # Should remove indices 1 and 2 (2 messages)
        assert len(state["messages"]) <= 3

    def test_drop_out_of_range(self, state):
        state["messages"] = _make_messages()
        result = _dispatch("/drop 99", state)
        assert "Error" in result or "invalid" in result.lower() or "out of range" in result.lower()

    def test_drop_negative_index(self, state):
        state["messages"] = _make_messages()
        result = _dispatch("/drop -1", state)
        # Negative indices should be rejected
        assert "Error" in result or "invalid" in result.lower()

    def test_drop_pair_aware_tool_call(self, state, monkeypatch):
        """Dropping a tool-call assistant message should also remove its result."""
        monkeypatch.setattr("builtins.input", lambda _: "y")
        import json
        state["messages"] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "do something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "calculator",
                                             "arguments": '{"expression": "1+1"}'}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "2"},
        ]
        original_len = len(state["messages"])
        _dispatch("/drop 2", state)
        # Both the tool-call message and its result should be gone
        assert len(state["messages"]) <= original_len - 2


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------

class TestModel:
    def _mock_ui(self, monkeypatch):
        fake_ui = MagicMock()
        fake_ui.toolbar_state = {}
        monkeypatch.setitem(sys.modules, "ui", fake_ui)

    def _mock_agent(self, monkeypatch):
        import agent as agent_mod
        monkeypatch.setattr(agent_mod, "load_model", lambda c, m: (False, "not supported"))
        monkeypatch.setattr(agent_mod, "unload_model", lambda c, m: (False, "not supported"))

    # --- no-args: interactive list ---

    def test_list_shows_models(self, state, monkeypatch, capsys):
        import commands as cmd_mod
        monkeypatch.setattr(cmd_mod, "AVAILABLE_MODELS", ["model-a", "model-b"])
        monkeypatch.setitem(sys.modules, "ui", MagicMock(toolbar_state={}))
        monkeypatch.setattr("builtins.input", lambda _: "")  # cancel
        result = _dispatch("/model", state)
        out = capsys.readouterr().out
        assert "model-a" in out
        assert "model-b" in out
        assert "Cancelled" in result

    def test_list_empty_shows_current(self, state, monkeypatch):
        import commands as cmd_mod
        state["model"] = "my-model"
        monkeypatch.setattr(cmd_mod, "AVAILABLE_MODELS", [])
        result = _dispatch("/model", state)
        assert "my-model" in result

    def test_list_pick_switches_model(self, state, monkeypatch):
        import commands as cmd_mod
        monkeypatch.setattr(cmd_mod, "AVAILABLE_MODELS", ["model-a", "model-b"])
        self._mock_ui(monkeypatch)
        self._mock_agent(monkeypatch)
        monkeypatch.setattr("builtins.input", lambda _: "2")  # pick model-b
        _dispatch("/model", state)
        assert state["model"] == "model-b"

    def test_list_pick_same_model_no_op(self, state, monkeypatch):
        import commands as cmd_mod
        state["model"] = "model-a"
        monkeypatch.setattr(cmd_mod, "AVAILABLE_MODELS", ["model-a", "model-b"])
        monkeypatch.setitem(sys.modules, "ui", MagicMock(toolbar_state={}))
        monkeypatch.setattr("builtins.input", lambda _: "1")  # pick model-a (current)
        result = _dispatch("/model", state)
        assert "Already using" in result

    def test_list_invalid_choice(self, state, monkeypatch):
        import commands as cmd_mod
        monkeypatch.setattr(cmd_mod, "AVAILABLE_MODELS", ["model-a"])
        monkeypatch.setitem(sys.modules, "ui", MagicMock(toolbar_state={}))
        monkeypatch.setattr("builtins.input", lambda _: "99")
        result = _dispatch("/model", state)
        assert "Invalid" in result

    # --- with-args: direct switch ---

    def test_set_model(self, state, monkeypatch):
        self._mock_ui(monkeypatch)
        self._mock_agent(monkeypatch)
        _dispatch("/model new-model-name", state)
        assert state["model"] == "new-model-name"

    def test_set_model_resets_context_length(self, state, monkeypatch):
        self._mock_ui(monkeypatch)
        self._mock_agent(monkeypatch)
        state["context_length"] = 8192
        _dispatch("/model another-model", state)
        assert state["context_length"] is None

    def test_set_same_model_no_op(self, state, monkeypatch):
        state["model"] = "test-model"
        result = _dispatch("/model test-model", state)
        assert "Already using" in result


# ---------------------------------------------------------------------------
# /set, /params, /unset
# ---------------------------------------------------------------------------

class TestGenParams:
    def test_set_temperature(self, state):
        _dispatch("/set temperature 0.7", state)
        assert state["gen_params"].get("temperature") == pytest.approx(0.7)

    def test_set_max_tokens(self, state):
        _dispatch("/set max_tokens 1024", state)
        assert state["gen_params"].get("max_tokens") == 1024

    def test_set_temperature_out_of_range(self, state):
        result = _dispatch("/set temperature 5.0", state)
        assert "between" in result or "Error" in result or "invalid" in result.lower()
        assert state["gen_params"].get("temperature") != 5.0

    def test_set_unknown_param(self, state):
        result = _dispatch("/set unknown_param 42", state)
        assert "Error" in result or "unknown" in result.lower()

    def test_unset_removes_key(self, state):
        state["gen_params"]["temperature"] = 0.5
        _dispatch("/unset temperature", state)
        assert "temperature" not in state["gen_params"]

    def test_unset_unknown_key(self, state):
        result = _dispatch("/unset no_such_param", state)
        # Should not crash; may return an info or error message
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# /system
# ---------------------------------------------------------------------------

class TestSystem:
    def test_show_system_prompt(self, state):
        state["messages"] = [{"role": "system", "content": "my system prompt"}]
        result = _dispatch("/system", state)
        assert "my system prompt" in result

    def test_replace_system_prompt(self, state):
        state["messages"] = [{"role": "system", "content": "old"}]
        _dispatch("/system new prompt text", state)
        assert state["messages"][0]["content"] == "new prompt text"


# ---------------------------------------------------------------------------
# /compress — verify both config copies are restored
# ---------------------------------------------------------------------------

class TestCompress:
    def test_compress_restores_config_values(self, state, monkeypatch):
        import config
        import agent as agent_mod

        state["messages"] = _make_messages()
        state["context_length"] = 1000
        state["usage"] = {"total_tokens": 900}

        original_threshold = config.CONTEXT_PRESSURE_THRESHOLD
        original_keep = agent_mod.CONTEXT_SUMMARY_KEEP_RECENT

        # Mock the actual compress call so we don't hit the LLM
        monkeypatch.setattr(agent_mod, "_maybe_compress", lambda *a, **kw: True)

        _dispatch("/compress", state)

        assert config.CONTEXT_PRESSURE_THRESHOLD == original_threshold
        assert agent_mod.CONTEXT_SUMMARY_KEEP_RECENT == original_keep


# ---------------------------------------------------------------------------
# dispatch itself
# ---------------------------------------------------------------------------

def test_dispatch_unknown_command(state):
    import commands
    handled, output = commands.dispatch("/no_such_command_xyz", state)
    assert handled
    assert output is not None
    assert "unknown" in output.lower() or "no_such_command" in output.lower()


def test_dispatch_non_command_not_handled(state):
    import commands
    handled, output = commands.dispatch("just a message", state)
    assert not handled
    assert output is None
