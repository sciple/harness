"""Tests for the /experiment command — temperature sweep + logging + report."""

import json
import os

from unittest.mock import MagicMock


def _dispatch(cmd: str, state: dict):
    import commands
    handled, output = commands.dispatch(cmd, state)
    assert handled, f"Command '{cmd}' was not handled"
    return output or ""


def _fake_usage(prompt_tok=10, completion_tok=5):
    return {
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "total_tokens": prompt_tok + completion_tok,
    }


def _experiment_dirs(tmp_workspace):
    exp_root = tmp_workspace / "experiments"
    assert exp_root.is_dir(), "experiments/ directory was not created"
    subdirs = list(exp_root.iterdir())
    assert len(subdirs) == 1, f"expected exactly one experiment dir, got {subdirs}"
    return subdirs[0]


class TestExperimentHappyPath:
    def test_two_temps_two_repeats(self, state, tmp_workspace, monkeypatch):
        answers = iter(["0.2,0.5", "2", "", "y"])  # temps, repeats, tools=blank(off), confirm
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        calls = []

        def fake_stream(client, model, messages, gen_params=None):
            calls.append((messages, gen_params))
            return (f"response for temp={gen_params['temperature']}", _fake_usage())

        monkeypatch.setattr("agent._stream_response", fake_stream)

        result = _dispatch("/experiment Write a haiku", state)

        assert "Completed 4/4" in result
        assert len(calls) == 4

        # Each trial must be built from a fresh, isolated message list (history reset)
        for messages, _ in calls:
            assert len(messages) == 2  # system + single user turn
            assert messages[0]["role"] == "system"
            assert messages[1] == {"role": "user", "content": "Write a haiku"}

        exp_dir = _experiment_dirs(tmp_workspace)
        results_path = exp_dir / "results.jsonl"
        report_path = exp_dir / "report.md"
        assert results_path.is_file()
        assert report_path.is_file()

        lines = results_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4
        records = [json.loads(l) for l in lines]
        temps_seen = sorted(r["temperature"] for r in records)
        assert temps_seen == [0.2, 0.2, 0.5, 0.5]
        repeats_seen = sorted(r["repeat"] for r in records)
        assert repeats_seen == [1, 1, 2, 2]
        for r in records:
            assert r["prompt_tokens"] == 10
            assert r["completion_tokens"] == 5
            assert r["tokens_per_sec"] is not None

        report_text = report_path.read_text(encoding="utf-8")
        assert "Write a haiku" in report_text
        assert "temperature=0.2" in report_text
        assert "temperature=0.5" in report_text
        assert "response for temp=0.2" in report_text
        assert "response for temp=0.5" in report_text

    def test_prompts_for_prompt_text_when_args_empty(self, state, tmp_workspace, monkeypatch):
        answers = iter(["Explain gravity", "0.7", "1", "", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        monkeypatch.setattr(
            "agent._stream_response",
            lambda client, model, messages, gen_params=None: ("gravity is a force", _fake_usage()),
        )

        result = _dispatch("/experiment", state)
        assert "Completed 1/1" in result


class TestExperimentValidation:
    def test_invalid_temperature_value(self, state, tmp_workspace, monkeypatch):
        answers = iter(["abc"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        stream_mock = MagicMock()
        monkeypatch.setattr("agent._stream_response", stream_mock)

        result = _dispatch("/experiment some prompt", state)
        assert "Invalid temperature value" in result
        stream_mock.assert_not_called()

    def test_temperature_out_of_range(self, state, tmp_workspace, monkeypatch):
        answers = iter(["3.5"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        stream_mock = MagicMock()
        monkeypatch.setattr("agent._stream_response", stream_mock)

        result = _dispatch("/experiment some prompt", state)
        assert "between 0.0 and 2.0" in result
        stream_mock.assert_not_called()

    def test_invalid_repeat_count(self, state, tmp_workspace, monkeypatch):
        answers = iter(["0.5", "abc"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        stream_mock = MagicMock()
        monkeypatch.setattr("agent._stream_response", stream_mock)

        result = _dispatch("/experiment some prompt", state)
        assert "Invalid repeat count" in result
        stream_mock.assert_not_called()

    def test_confirm_declined_cancels(self, state, tmp_workspace, monkeypatch):
        answers = iter(["0.2,0.5", "1", "", "n"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        stream_mock = MagicMock()
        monkeypatch.setattr("agent._stream_response", stream_mock)

        result = _dispatch("/experiment some prompt", state)
        assert result == "Cancelled."
        stream_mock.assert_not_called()
        assert not (tmp_workspace / "experiments").exists()


class TestExperimentInterrupt:
    def test_keyboard_interrupt_writes_partial_report(self, state, tmp_workspace, monkeypatch):
        answers = iter(["0.1,0.2,0.3", "1", "", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        call_count = {"n": 0}

        def fake_stream(client, model, messages, gen_params=None):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise KeyboardInterrupt()
            return ("ok", _fake_usage())

        monkeypatch.setattr("agent._stream_response", fake_stream)

        result = _dispatch("/experiment some prompt", state)
        assert "Completed 1/3" in result

        exp_dir = _experiment_dirs(tmp_workspace)
        lines = (exp_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert (exp_dir / "report.md").is_file()


class TestTruncateLines:
    def test_short_text_unchanged(self):
        import commands
        text = "line1\nline2"
        assert commands._truncate_lines(text) == text

    def test_long_text_truncated_with_ellipsis(self):
        import commands
        text = "\n".join(f"line{i}" for i in range(1, 11))  # 10 lines
        result = commands._truncate_lines(text)
        assert result == "line1\nline2\nline3\nline4\nline5\n..."


class TestExperimentToolCalls:
    """Multi-step trials: model calls a tool, gets a result, then answers."""

    def _fake_chat_factory(self, calls):
        def fake_chat(client, model, messages, verbose=True, usage_out=None,
                       gen_params=None, context_length=None, state=None):
            calls.append({"messages_len_at_call": len(messages), "state": state})
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file_content",
                        "arguments": json.dumps({"path": "config.py"}),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "MAX_TOOL_ROUNDS = 10",
            })
            if usage_out is not None:
                usage_out.update({"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28})
            return "The value is 10."
        return fake_chat

    def test_tool_enabled_captures_trace(self, state, tmp_workspace, monkeypatch):
        # temps, repeats, tools=y, skip-confirm=y, confirm=y
        answers = iter(["0.2,0.5", "1", "y", "y", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        calls = []
        monkeypatch.setattr("agent.chat", self._fake_chat_factory(calls))
        chat_mock_stream = MagicMock()
        monkeypatch.setattr("agent._stream_response", chat_mock_stream)

        result = _dispatch("/experiment Read config.py and find MAX_TOOL_ROUNDS", state)

        assert "Completed 2/2" in result
        assert len(calls) == 2
        chat_mock_stream.assert_not_called()

        # Each trial must start from a fresh, isolated conversation (system + user only)
        assert all(c["messages_len_at_call"] == 2 for c in calls)

        exp_dir = _experiment_dirs(tmp_workspace)
        lines = (exp_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
        records = [json.loads(l) for l in lines]
        assert len(records) == 2
        for r in records:
            assert r["tool_enabled"] is True
            assert len(r["tool_calls"]) == 1
            step = r["tool_calls"][0]
            assert step["name"] == "read_file_content"
            assert step["arguments"] == {"path": "config.py"}
            assert step["result"] == "MAX_TOOL_ROUNDS = 10"
            assert r["response"] == "The value is 10."

        report_text = (exp_dir / "report.md").read_text(encoding="utf-8")
        assert "Tool calls: enabled" in report_text
        assert "read_file_content" in report_text
        assert "MAX_TOOL_ROUNDS = 10" in report_text

    def test_long_tool_result_truncated_in_report_but_not_in_jsonl(self, state, tmp_workspace, monkeypatch):
        long_result = "\n".join(f"line{i}" for i in range(1, 21))  # 20 lines

        def fake_chat(client, model, messages, verbose=True, usage_out=None,
                      gen_params=None, context_length=None, state=None):
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file_content", "arguments": "{}"},
                }],
            })
            messages.append({"role": "tool", "tool_call_id": "call_1", "content": long_result})
            if usage_out is not None:
                usage_out.update(_fake_usage())
            return "full response text " * 20  # deliberately long, must stay intact

        answers = iter(["0.5", "1", "y", "y", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        monkeypatch.setattr("agent.chat", fake_chat)

        _dispatch("/experiment some prompt", state)

        exp_dir = _experiment_dirs(tmp_workspace)
        record = json.loads((exp_dir / "results.jsonl").read_text(encoding="utf-8").strip())
        assert record["tool_calls"][0]["result"] == long_result  # jsonl keeps full result
        assert record["response"] == "full response text " * 20  # jsonl keeps full response

        report_text = (exp_dir / "report.md").read_text(encoding="utf-8")
        assert "line1\nline2\nline3\nline4\nline5\n..." in report_text  # tool result truncated
        assert "line6" not in report_text
        assert ("full response text " * 20) in report_text  # response NOT truncated

    def test_skip_confirm_override_does_not_mutate_session_state(self, state, tmp_workspace, monkeypatch):
        state["skip_confirm"] = True  # simulate a main session that stays interactive by default
        # temps, repeats, tools=y, skip-confirm=n (explicit opt-out), confirm=y
        answers = iter(["0.3", "1", "y", "n", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        calls = []
        monkeypatch.setattr("agent.chat", self._fake_chat_factory(calls))

        _dispatch("/experiment Read config.py", state)

        assert len(calls) == 1
        trial_state = calls[0]["state"]
        assert trial_state is not state
        assert trial_state["skip_confirm"] is False
        assert state["skip_confirm"] is True  # the real session state is untouched

    def test_tool_disabled_by_default_uses_plain_text(self, state, tmp_workspace, monkeypatch):
        # temps, repeats, tools=blank(off), confirm
        answers = iter(["0.4", "1", "", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        chat_mock = MagicMock()
        monkeypatch.setattr("agent.chat", chat_mock)
        monkeypatch.setattr(
            "agent._stream_response",
            lambda client, model, messages, gen_params=None: ("plain answer", _fake_usage()),
        )

        result = _dispatch("/experiment Say hi", state)
        assert "Completed 1/1" in result
        chat_mock.assert_not_called()

        exp_dir = _experiment_dirs(tmp_workspace)
        lines = (exp_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["tool_enabled"] is False
        assert record["tool_calls"] == []
