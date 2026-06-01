"""
Shared pytest fixtures for the harness test suite.

Key challenges solved here:
- config.WORKSPACE_ROOT is evaluated at import time from os.getcwd(); must be patched per test.
- tools/notes.py captures _NOTES_FILE at import time; must be patched separately.
- tools/__init__.py auto-discovers and registers all tools at import time; registry state
  must be snapshotted and restored between tests to prevent cross-test pollution.
"""

import pytest
from unittest.mock import MagicMock
from helpers import make_text_stream, make_tool_call_stream  # noqa: F401 re-exported for tests


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_workspace(tmp_path, monkeypatch):
    """
    Redirect all file-writing tools to an isolated temp directory.
    Patches config.WORKSPACE_ROOT and notes._NOTES_FILE for the duration of the test.
    """
    import config
    monkeypatch.setattr(config, "WORKSPACE_ROOT", str(tmp_path))

    import tools.notes as notes_mod
    monkeypatch.setattr(
        notes_mod, "_NOTES_FILE",
        str(tmp_path / "notes" / "notes.json"),
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tool registry isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_tool_registry():
    """
    Snapshot the tool registry before each test and restore it after.
    Prevents tools registered inside one test from leaking into the next.
    """
    import tools as tr
    from collections import OrderedDict

    snap_reg   = dict(tr._registry)
    snap_conf  = set(tr._confirm_tools)
    snap_notr  = set(tr._no_truncate_tools)
    snap_store = OrderedDict(tr._tool_output_store)
    snap_ctr   = tr._call_counter[0]

    yield

    tr._registry.clear()
    tr._registry.update(snap_reg)
    tr._confirm_tools.clear()
    tr._confirm_tools.update(snap_conf)
    tr._no_truncate_tools.clear()
    tr._no_truncate_tools.update(snap_notr)
    tr._tool_output_store.clear()
    tr._tool_output_store.update(snap_store)
    tr._call_counter[0] = snap_ctr


# ---------------------------------------------------------------------------
# Fake LLM stream builders
# ---------------------------------------------------------------------------

def make_text_stream(tokens: list[str], usage: tuple[int, int] = (10, 5)):
    """Yield fake streaming chunks that look like a plain-text response."""
    for tok in tokens:
        delta = MagicMock()
        delta.content = tok
        delta.tool_calls = None
        delta.reasoning_content = None
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = None
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk
    # Final usage chunk
    final = MagicMock()
    final.choices = []
    final.usage = MagicMock()
    final.usage.prompt_tokens = usage[0]
    final.usage.completion_tokens = usage[1]
    final.usage.total_tokens = sum(usage)
    yield final


def make_tool_call_stream(name: str, args_json: str):
    """Yield fake streaming chunks that look like a single tool call."""
    tc = MagicMock()
    tc.index = 0
    tc.id = "call_001"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = args_json
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = [tc]
    delta.reasoning_content = None
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = "tool_calls"
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None
    yield chunk
    # Final empty chunk
    final = MagicMock()
    final.choices = []
    final.usage = None
    yield final


# ---------------------------------------------------------------------------
# Minimal state dict
# ---------------------------------------------------------------------------

@pytest.fixture()
def state(tmp_workspace):
    """A minimal harness state dict suitable for command and agent tests."""
    return {
        "model":          "test-model",
        "messages":       [],
        "running":        True,
        "client":         MagicMock(),
        "usage":          {},
        "context_length": None,
        "session_id":     "test_session",
        "gen_params":     {},
        "skip_confirm":   True,
    }
