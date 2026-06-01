# Running the test suite

From the harness root directory:

```bash
pytest tests/ -v
```

## Common variants

```bash
# Single module (faster when you only changed one layer)
pytest tests/test_file_tools.py -v

# Filter by keyword
pytest tests/ -k "protected" -v

# Stop on first failure
pytest tests/ -x -v

# Quiet — just pass/fail count
pytest tests/
```

## Workflow when adding a new feature

1. Add the feature (new tool, command, agent change, etc.)
2. Run the full suite to check for regressions: `pytest tests/ -v`
3. Add tests for the new behavior in the relevant file:

| What you changed | Test file |
|---|---|
| A tool in `tools/` | `test_file_tools.py`, `test_notes.py`, `test_run_python.py`, or a new `test_<tool>.py` |
| Tool registry logic | `test_tools_registry.py` |
| A command in `commands/` | `test_commands.py` |
| `agent.py` | `test_agent.py` |
| `session.py` | `test_session.py` |
| `tools/calculator.py` | `test_calculator.py` |

4. Run again to confirm your new tests pass: `pytest tests/ -v`

## Key fixtures (defined in `tests/conftest.py`)

| Fixture | What it does |
|---|---|
| `tmp_workspace` | Redirects `config.WORKSPACE_ROOT` and `notes._NOTES_FILE` to an isolated temp dir |
| `state` | Minimal harness state dict with a mocked LLM client; depends on `tmp_workspace` |
| `clean_tool_registry` | Auto-use: snapshots and restores tool registry state around every test |

Use `tmp_workspace` in any test that writes files. Use `state` in command and agent tests.

## Mocking the LLM

The suite never calls a real LLM. Patch `agent._stream_or_tools` with a lambda:

```python
def test_something(monkeypatch, tmp_workspace):
    import agent
    monkeypatch.setattr(agent, "_stream_or_tools",
        lambda *a, **kw: ("Hello", [], {"prompt_tokens": 5,
                          "completion_tokens": 3, "total_tokens": 8}))
    monkeypatch.setattr(agent, "_maybe_compress", lambda *a, **kw: False)
    ...
```

For tool-call responses, return a list of `MagicMock` objects with `.id`, `.function.name`, `.function.arguments`:

```python
from unittest.mock import MagicMock

tc = MagicMock()
tc.id = "call_001"
tc.function.name = "my_tool"
tc.function.arguments = '{"arg": "value"}'
return (None, [tc], {})
```

## Notes

- All tests run fully offline — no LM Studio or network required.
- The `ui` module (prompt_toolkit) cannot be imported outside a real console on Windows.
  Mock it in sys.modules before any test that triggers its import:
  ```python
  fake_ui = MagicMock()
  fake_ui.toolbar_state = {}
  monkeypatch.setitem(sys.modules, "ui", fake_ui)
  ```
- Commands that prompt for confirmation (`/drop` on multiple messages) call `builtins.input`.
  Suppress it with: `monkeypatch.setattr("builtins.input", lambda _: "y")`
