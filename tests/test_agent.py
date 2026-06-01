"""Tests for agent.py — _find_think_open, chat(), _execute_tool_with_retry."""

import json
import pytest
from unittest.mock import MagicMock, patch
from helpers import make_text_stream, make_tool_call_stream


# ---------------------------------------------------------------------------
# _find_think_open — pure function, no mocking
# ---------------------------------------------------------------------------

class TestFindThinkOpen:
    def setup_method(self):
        from agent import _find_think_open
        self._fn = _find_think_open

    def test_no_tag_returns_none(self):
        assert self._fn("just some text") is None

    def test_finds_think_tag(self):
        result = self._fn("prefix <think> reasoning here")
        assert result is not None
        pos, open_tag, close_tag = result
        assert open_tag == "<think>"
        assert close_tag == "</think>"
        assert pos == 7

    def test_finds_gemma_tag(self):
        result = self._fn("<|channel>thought hello")
        assert result is not None
        _, open_tag, close_tag = result
        assert open_tag == "<|channel>thought"
        assert close_tag == "<channel|>"

    def test_returns_earliest_of_two_tags(self):
        # Both tags present — should return the leftmost one
        text = "<think>first</think> some text <|channel>thought second"
        result = self._fn(text)
        assert result is not None
        pos, open_tag, _ = result
        assert open_tag == "<think>"
        assert pos == 0

    def test_gemma_tag_before_think_tag(self):
        text = "<|channel>thought first <think> second"
        result = self._fn(text)
        assert result is not None
        _, open_tag, _ = result
        assert open_tag == "<|channel>thought"


# ---------------------------------------------------------------------------
# chat() — mocked _stream_or_tools
# ---------------------------------------------------------------------------

class TestChat:
    """Tests for agent.chat() with _stream_or_tools mocked out."""

    def _make_state(self, tmp_workspace):
        return {
            "model": "test-model",
            "messages": [{"role": "system", "content": "sys"}],
            "running": True,
            "client": MagicMock(),
            "usage": {},
            "context_length": None,
            "session_id": "test",
            "gen_params": {},
            "skip_confirm": True,
        }

    def test_plain_text_response(self, monkeypatch, tmp_workspace):
        import agent
        monkeypatch.setattr(
            agent, "_stream_or_tools",
            lambda *a, **kw: ("Hello world", [], {"prompt_tokens": 5,
                              "completion_tokens": 3, "total_tokens": 8}),
        )
        monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)

        state = self._make_state(tmp_workspace)
        result = agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=False, state=state,
        )
        assert result == "Hello world"
        # Assistant message appended
        assert state["messages"][-1] == {"role": "assistant", "content": "Hello world"}

    def test_usage_out_populated(self, monkeypatch, tmp_workspace):
        import agent
        monkeypatch.setattr(
            agent, "_stream_or_tools",
            lambda *a, **kw: ("reply", [], {"prompt_tokens": 10,
                              "completion_tokens": 5, "total_tokens": 15}),
        )
        monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)

        state = self._make_state(tmp_workspace)
        usage_out = {}
        agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=False, state=state, usage_out=usage_out,
        )
        assert usage_out.get("total_tokens") == 15

    def test_single_tool_call_then_text(self, monkeypatch, tmp_workspace):
        import agent, tools as tr

        # Register a test tool
        def _test_tool(msg: str) -> str:
            return f"tool_result:{msg}"

        schema = {"type": "function",
                  "function": {"name": "_chat_test_tool", "description": "t",
                  "parameters": {"type": "object",
                  "properties": {"msg": {"type": "string"}}, "required": ["msg"]}}}
        tr.register(schema, _test_tool)

        call_count = {"n": 0}

        def fake_stream(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: tool call — return _ToolCall-compatible objects
                tc = MagicMock()
                tc.id = "call_001"
                tc.function.name = "_chat_test_tool"
                tc.function.arguments = json.dumps({"msg": "hello"})
                return (None, [tc], {})
            else:
                # Second call: text response
                return ("Final answer", [], {"prompt_tokens": 5,
                        "completion_tokens": 3, "total_tokens": 8})

        monkeypatch.setattr(agent, "_stream_or_tools", fake_stream)
        monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)

        state = self._make_state(tmp_workspace)
        result = agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=False, state=state,
        )
        assert result == "Final answer"
        # Tool result message should be in history
        tool_results = [m for m in state["messages"]
                        if m.get("role") == "tool"]
        assert len(tool_results) == 1
        assert "tool_result:hello" in tool_results[0]["content"]

    def test_bad_tool_args_json(self, monkeypatch, tmp_workspace):
        import agent, tools as tr

        def _test_tool(x: str) -> str:
            return "ok"

        schema = {"type": "function",
                  "function": {"name": "_bad_args_tool", "description": "t",
                  "parameters": {"type": "object",
                  "properties": {"x": {"type": "string"}}, "required": ["x"]}}}
        tr.register(schema, _test_tool)

        call_count = {"n": 0}

        def fake_stream(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                tc = MagicMock()
                tc.id = "call_001"
                tc.function.name = "_bad_args_tool"
                tc.function.arguments = "NOT VALID JSON {{{{"
                return (None, [tc], {})
            return ("Done", [], {})

        monkeypatch.setattr(agent, "_stream_or_tools", fake_stream)
        monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)

        state = self._make_state(tmp_workspace)
        # Should not raise — bad JSON results in an error tool message
        result = agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=False, state=state,
        )
        assert result == "Done"

    def test_max_rounds_forces_final_answer(self, monkeypatch, tmp_workspace):
        import agent
        from config import MAX_TOOL_ROUNDS

        call_count = {"n": 0}

        def fake_stream(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] <= MAX_TOOL_ROUNDS:
                tc = MagicMock()
                tc.id = f"call_{call_count['n']}"
                tc.function.name = "noop"
                tc.function.arguments = "{}"
                return (None, [tc], {})
            return ("Forced final", [], {})

        monkeypatch.setattr(agent, "_stream_or_tools", fake_stream)
        monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)
        monkeypatch.setattr(
            "tools.dispatch",
            lambda name, args: "tool output",
        )

        state = self._make_state(tmp_workspace)
        result = agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=False, state=state,
        )
        assert result == "Forced final"


# ---------------------------------------------------------------------------
# _execute_tool_with_retry
# ---------------------------------------------------------------------------

class TestExecuteToolWithRetry:
    def _state(self, skip_confirm=True):
        return {
            "skip_confirm": skip_confirm,
            "model": "test",
            "messages": [],
            "client": MagicMock(),
            "gen_params": {},
        }

    def test_skip_confirm_executes_without_prompt(self, monkeypatch):
        import agent
        monkeypatch.setattr("tools.dispatch", lambda name, args: "ok_result")
        monkeypatch.setattr("tools.requires_confirmation", lambda name: True)

        state = self._state(skip_confirm=True)
        result = agent._execute_tool_with_retry(
            "some_tool", {}, "id1", verbose=False, state=state
        )
        assert result == "ok_result"

    def test_confirm_accepted(self, monkeypatch):
        import agent, sys
        fake_ui = MagicMock()
        fake_ui.prompt = lambda msg: "y"
        monkeypatch.setitem(sys.modules, "ui", fake_ui)
        monkeypatch.setattr("tools.dispatch", lambda name, args: "confirmed_result")
        monkeypatch.setattr("tools.requires_confirmation", lambda name: True)

        state = self._state(skip_confirm=False)
        result = agent._execute_tool_with_retry(
            "confirm_tool", {}, "id1", verbose=False, state=state
        )
        assert result == "confirmed_result"

    def test_confirm_declined_returns_cancelled(self, monkeypatch):
        import agent, sys
        fake_ui = MagicMock()
        fake_ui.prompt = lambda msg: "n"
        monkeypatch.setitem(sys.modules, "ui", fake_ui)
        monkeypatch.setattr("tools.requires_confirmation", lambda name: True)

        state = self._state(skip_confirm=False)
        result = agent._execute_tool_with_retry(
            "confirm_tool", {}, "id1", verbose=False, state=state
        )
        assert "CANCELLED" in result

    def test_retry_on_error(self, monkeypatch):
        import agent
        call_count = {"n": 0}

        def flaky(name, args):
            call_count["n"] += 1
            if call_count["n"] < 2:
                return "Error: temporary failure"
            return "success_after_retry"

        monkeypatch.setattr("tools.dispatch", flaky)
        monkeypatch.setattr("tools.requires_confirmation", lambda name: False)
        monkeypatch.setattr("config.TOOL_RETRY_MAX", 2)
        monkeypatch.setattr("config.TOOL_RETRY_CONFIRM", False)

        state = self._state(skip_confirm=True)
        result = agent._execute_tool_with_retry(
            "flaky_tool", {}, "id1", verbose=False, state=state
        )
        assert result == "success_after_retry"
        assert call_count["n"] == 2

    def test_retry_stops_at_max(self, monkeypatch):
        import agent
        call_count = {"n": 0}

        def always_fails(name, args):
            call_count["n"] += 1
            return "Error: always fails"

        monkeypatch.setattr("tools.dispatch", always_fails)
        monkeypatch.setattr("tools.requires_confirmation", lambda name: False)
        monkeypatch.setattr("config.TOOL_RETRY_MAX", 2)
        monkeypatch.setattr("config.TOOL_RETRY_CONFIRM", False)

        state = self._state(skip_confirm=True)
        result = agent._execute_tool_with_retry(
            "bad_tool", {}, "id1", verbose=False, state=state
        )
        assert result.startswith("Error")
        assert call_count["n"] == 3  # 1 original + 2 retries
