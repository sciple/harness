"""Shared test helpers — importable by test modules (not a conftest fixture file)."""

from unittest.mock import MagicMock


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
    final = MagicMock()
    final.choices = []
    final.usage = None
    yield final
