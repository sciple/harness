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
        answers = iter(["0.2,0.5", "2", "y"])
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
        answers = iter(["Explain gravity", "0.7", "1", "y"])
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
        answers = iter(["0.2,0.5", "1", "n"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        stream_mock = MagicMock()
        monkeypatch.setattr("agent._stream_response", stream_mock)

        result = _dispatch("/experiment some prompt", state)
        assert result == "Cancelled."
        stream_mock.assert_not_called()
        assert not (tmp_workspace / "experiments").exists()


class TestExperimentInterrupt:
    def test_keyboard_interrupt_writes_partial_report(self, state, tmp_workspace, monkeypatch):
        answers = iter(["0.1,0.2,0.3", "1", "y"])
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
