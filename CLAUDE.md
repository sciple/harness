# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A self-contained interactive REPL and agent framework for local LLMs via any OpenAI-compatible endpoint (LM Studio, Ollama, llama.cpp, vLLM). Everything runs locally — no cloud dependency.

## Running & Testing

The examples below use `python` and `pytest`. If they are not on your PATH (e.g. under a miniconda/conda install), substitute the full path to your interpreter, such as `& "<path-to-python>\python.exe" main.py`.

```powershell
# Start the REPL
python main.py
python main.py --model "granite-4.1-8b" --base-url http://127.0.0.1:1234/v1/
python main.py --load <session_id>

# Tests (no live LLM required — all mocked)
pytest tests/ -v
pytest tests/test_file_tools.py -v
pytest tests/ -k "protected" -v
pytest tests/ -x -v
```

Dependencies: `python -m pip install openai prompt_toolkit`

## Architecture

```
User Input → main.py (REPL)
  ├─ /command? → commands/__init__.py → response
  └─ natural language → agent.chat()
      ├─ _stream_or_tools() → single streaming call
      │   ├─ text → stream to stdout
      │   └─ tool calls → tools.dispatch() → loop (up to 10 rounds)
      ├─ _maybe_compress() → auto-summarize when context > 80%
      └─ session.save() → data/sessions/<id>.jsonl
```

**Key files:**
- [agent.py](agent.py) — Core agentic loop, streaming, tool dispatch, context compression, thinking block rendering
- [main.py](main.py) — REPL entry point, CLI arg parsing, session bootstrap
- [config.py](config.py) — All constants: endpoint, model defaults, context thresholds, tool limits, workspace paths
- [commands/\_\_init\_\_.py](commands/__init__.py) — ~30 slash commands (conversation, model params, sessions, tools, skills)
- [tools/\_\_init\_\_.py](tools/__init__.py) — Tool registry with auto-discovery, dispatch, output truncation, safeguards
- [ui.py](ui.py) — prompt_toolkit REPL, tab completion, status toolbar

## Extensibility

**Adding a tool:** Drop a `.py` file in [tools/](tools/), call `tools.register()` with an OpenAI-style JSON schema. The registry auto-discovers it on startup.

**Adding a skill:** Create a `.py` in [skills/](skills/) exporting `SKILL_META` (metadata dict) and `run(agent, args)`. Skills spawn isolated subagents for focused tasks.

**Adding a command:** Call `commands.register()` in [commands/\_\_init\_\_.py](commands/__init__.py) with a handler function and `/name`.

## Safety & Workspace

- `config.py` defines `WORKSPACE_ROOT` and `PROTECTED_PATHS` — file tools are confined to workspace; harness infrastructure files cannot be modified by the agent.
- Python tool executes in a sandboxed subprocess.
- Destructive tool operations require confirmation.
- Output is truncated by default; full output retrievable with `/last`.

## Session & Context

- Sessions persist as JSONL in `data/sessions/` (gitignored).
- Context auto-compresses when token usage exceeds threshold (default 80% of model context window).
- `/drop <n>`, `/drop <n>-<m>`, or `/drop <a>,<b>,<c>` prune individual turns; prints updated history after removal. `/compact` summarises and replaces history.

## Testing Conventions

- Tests use `conftest.py` fixtures: `tmp_workspace` (isolated temp dir), `state` (mocked agent state).
- LLM calls are monkeypatched — no running server needed.
- Test files mirror source modules: `test_file_tools.py` ↔ `tools/file_*.py`, etc.

## Documentation Maintenance

**Keep `README.md` and `harness_docs.md` in sync with every code change.** This is a hard requirement, not optional cleanup:

- **New tool** → add a row to the Built-in Tools table in both files.
- **New skill** → add a row to the Built-in Skills / Skills table in both files.
- **New command** → add a row to the Commands Reference / Commands table in both files.
- **Modified feature** (renamed, changed behaviour, removed flag, new flag) → update every mention in both files.
- **Deleted tool / skill / command** → remove its row from both files.
- **Config constant changed** → update the Configuration / Key config table in both files.

`harness_docs.md` is the condensed reference the model reads at runtime via the `read_harness_docs` tool — stale entries there actively mislead the model during a session.

## Design Invariants

Non-obvious rules that will trip you up if you don't know them:

**ANSI / terminal output**
- ANSI codes work in `print()` calls but **not** in strings passed to `ui.prompt()` — prompt_toolkit renders them as literal `^[[2m` text. Keep all ANSI formatting out of prompt strings.
- Never wrap terminal output in `prompt_toolkit.patch_stdout` — it corrupts ESC sequences on Windows via the Win32 Console API. All output uses direct `print()`.
- ANSI palette used: `\033[96m` bright cyan (assistant text), `\033[2;3m` dim+italic (thinking content), `\033[2m` dim (frames, info lines), `\033[96;1m` bright cyan+bold ("Assistant:" label), `\033[0m` reset.

**`agent.py` imports config values at load time**
- `agent.py` imports `CONTEXT_SUMMARY_KEEP_RECENT` as a plain value, not a reference. Patching `config.CONTEXT_PRESSURE_THRESHOLD` alone is not enough — `/compress` must also patch `agent.CONTEXT_SUMMARY_KEEP_RECENT` directly, and restore both in a `finally` block.

**Thinking tokens never enter context**
- Thinking content (`reasoning_content` field or `<think>` tag content) is rendered to the terminal but never added to `answer_chunks` or `state["messages"]`. The model's chain-of-thought does not pollute the conversation history.

**`_stream_or_tools` return discriminant**
- Returns `(text, None, usage)` for a text response and `("", [tool_calls], usage)` for tool calls. The discriminant is `tool_calls is None`, not whether `text` is empty.

**Session writes are atomic**
- `session.save()` writes to a temp file then calls `os.replace()`. A crash mid-write leaves a stale `.tmp` file but never corrupts the `.jsonl`. `session.save()` and `session.load()` silently swallow all exceptions — persistence must never crash the REPL.

**`/compress` double-patch**
- Must patch both `config.CONTEXT_PRESSURE_THRESHOLD` and `agent.CONTEXT_SUMMARY_KEEP_RECENT` to force compression. Restoring only one leaves the agent module permanently misconfigured for the session.

**Skills contract**
- Skills must use an isolated message list or `agent.run_subagent()` — never append directly to `state["messages"]` unless the intent is to permanently modify the conversation.
- Use `agent._stream_response()` for simple text-only calls; use `agent.run_subagent()` when the skill needs tool access.
- `/skill` always reloads the file from disk — no caching. Edit and re-run without restarting.

**`sanitize_for_file()` Unicode map**
- Applied to all LLM-generated code before writing to disk. Key replacements: `‘`/`’` → `'`, `“`/`”` → `"`, `—` → `--`, `–` → `-`, `…` → `...`, ` ` → ` `, `−` → `-`.
