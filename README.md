# Local LLM Harness

An interactive agent framework and REPL for local LLMs via any OpenAI-compatible endpoint (LM Studio, Ollama, llama.cpp, vLLM, etc.). It provides a multi-turn conversational agent with tool calling, skills, subagents, session persistence, context management, and runtime extensibility — all running entirely on your machine.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [CLI Options](#cli-options)
- [Commands Reference](#commands-reference)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Tools](#tools)
  - [Built-in Tools](#built-in-tools)
  - [Tool Schema Flags](#tool-schema-flags)
  - [Adding a Tool](#adding-a-tool)
  - [Generating a Tool at Runtime](#generating-a-tool-at-runtime)
- [Skills](#skills)
  - [Built-in Skills](#built-in-skills)
  - [Adding a Skill](#adding-a-skill)
  - [Generating a Skill at Runtime](#generating-a-skill-at-runtime)
- [Subagents](#subagents)
- [Session Management](#session-management)
- [Context Management](#context-management)
  - [Context Pollution](#context-pollution)
  - [Auto-Compression](#auto-compression)
  - [Manual Pruning](#manual-pruning)
  - [Context Distillation](#context-distillation)
- [Notes System](#notes-system)
- [Thinking Block Rendering](#thinking-block-rendering)
- [Safety and Safeguards](#safety-and-safeguards)
- [Architecture](#architecture)

---

## Features

- **Multi-turn REPL** with persistent conversation history and input history across restarts
- **Agentic tool-calling loop** — single streaming call per round detects both text and tool-call deltas
- **Streaming output** with token-by-token display and live token counter
- **Thinking block rendering** — `reasoning_content` fields and `<think>` tags (DeepSeek, Qwen, etc.) rendered in a dim `┌─ thinking` / `└─ done` box, visually separated from the final answer
- **Subagent support** — spawn an isolated LLM instance for a focused task without polluting the main conversation
- **Sandboxed Python execution** — run Python snippets in a subprocess with configurable timeout and workspace confinement
- **Session persistence** — every session auto-saves to disk and can be resumed later
- **Context management** — pollution reports, per-message token estimates, auto-compression, manual pruning
- **Tool registry** with auto-discovery, runtime loading, and LLM-assisted tool generation
- **Skill system** — higher-level composable behaviours with their own isolated message context
- **Persistent notes** — key-value store that survives across sessions and context resets
- **Configurable generation parameters** — temperature, top_p, max_tokens, seed at runtime
- **File safeguards** — protected paths prevent the agent from modifying harness infrastructure
- **Tool confirmation** — destructive tools require user approval before execution
- **Tool failure recovery** — automatic retry with optional user confirmation
- **Structured tool output** — dict results are JSON-serialised, long outputs truncated with retrieval
- **prompt_toolkit UI** — tab completion for commands, ghost completions from history, syntax highlighting, persistent bottom toolbar showing model and session

---

## Requirements

Python 3.12+ and an OpenAI-compatible local LLM server.

```bash
pip install openai prompt_toolkit
```

Supported backends:
- [LM Studio](https://lmstudio.ai/) (default endpoint: `http://127.0.0.1:1234/v1/`)
- [Ollama](https://ollama.ai/) (typically: `http://127.0.0.1:11434/v1/`)
- [llama.cpp server](https://github.com/ggerganov/llama.cpp)
- [vLLM](https://github.com/vllm-project/vllm)
- Any server exposing an OpenAI-compatible `/v1/chat/completions` endpoint

---

## Quick Start

1. Start your local LLM server (e.g. load a model in LM Studio)
2. Run the harness:

```bash
python main.py
```

3. Start chatting:

```
You: What is the capital of France?
Assistant: The capital of France is Paris.
```

4. Use tools naturally — the model will call them when appropriate:

```
You: Create a file called notes.txt with a summary of our conversation.
  [tool] write_file
  [write_file] -> File written: ...
Assistant: Done — I created notes.txt with the summary.
```

5. Type `/help` for a list of commands, or `/exit` to quit.

**Input tips:**
- Press `Tab` to complete `/commands`
- Press `→` or `End` to accept a ghost completion from history
- Press `Alt+Enter` to insert a newline for multi-paragraph messages; `Enter` alone submits

---

## CLI Options

```
python main.py [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--model NAME` | `granite-4.1-8b` | Model name to request from the server |
| `--base-url URL` | `http://127.0.0.1:1234/v1/` | API base URL |
| `--system PROMPT` | *(built-in)* | Override the default system prompt |
| `--quiet` | off | Suppress verbose tool-call output |
| `--load SESSION_ID` | *(none)* | Resume a previously saved session |

Examples:

```bash
# Use Ollama instead of LM Studio
python main.py --base-url http://127.0.0.1:11434/v1/

# Resume a previous session
python main.py --load 20260410T143022
```

---

## Commands Reference

All commands start with `/` and are entered at the `You:` prompt. Tab completion is available for all commands.

### Conversation

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/reset` | Clear conversation history (keeps the system prompt) |
| `/history` | Print conversation with per-message token estimates and indices |
| `/drop <n>` | Remove message at index `n`; also accepts a range (`/drop 3-7`) or comma-separated list (`/drop 3,4,8`). Prints updated history after removal. |
| `/exit`, `/quit` | Quit the harness |

### Model and Parameters

| Command | Description |
|---|---|
| `/model [name]` | Show or change the active model |
| `/set [param] [value]` | Set a generation parameter, or show current params if called with no arguments |
| `/params` | Show active generation parameter overrides |
| `/unset <param>` | Remove a generation parameter override |

Supported parameters: `temperature` (float), `top_p` (float), `max_tokens` (int), `seed` (int).

### Context

| Command | Description |
|---|---|
| `/ctx` | Show context window usage and token counts with a fill bar |
| `/pollution` | Context health report: scaffolding ratio, stale results, error noise |
| `/compress` | Manually trigger context compression without waiting for the auto threshold |
| `/system [prompt]` | Show the current system prompt, or replace it in-place |

### Sessions

| Command | Description |
|---|---|
| `/sessions` | List all saved sessions with message counts and timestamps |
| `/load <id>` | Resume a saved session by its ID |

### Tools

| Command | Description |
|---|---|
| `/tools` | List registered tools (and any that failed to load) |
| `/reloadtools [file]` | Retry loading tools that failed during startup |
| `/loadtool <path>` | Load a tool from a `.py` file at runtime |
| `/newtool <desc>` | Ask the LLM to generate and load a new tool from a description |

### Skills

| Command | Description |
|---|---|
| `/skills` | List available skills |
| `/skill <name> [args]` | Run a skill (e.g. `/skill summarise`) |
| `/newskill <desc>` | Ask the LLM to generate and save a new skill from a description |

### Subagents

| Command | Description |
|---|---|
| `/subagent <task>` | Spawn an isolated LLM instance for a focused task |

### Utilities

| Command | Description |
|---|---|
| `/time` | Show current UTC and local date/time |
| `/calendar [month]` | Show a mini calendar — current month, or specify `/calendar 6` or `/calendar 2026 9` |
| `/cls` | Clear the terminal screen and reprint the startup banner |
| `/open <url>` | Open a URL in the default system browser |

---

## Configuration

All tuneable parameters live in `config.py`. Key settings:

| Setting | Default | Purpose |
|---|---|---|
| `LOCAL_API_BASE` | `http://127.0.0.1:1234/v1/` | LLM server endpoint |
| `DEFAULT_MODEL` | `granite-4.1-8b` | Model name |
| `SYSTEM_PROMPT` | *(built-in)* | Default system prompt — includes OS hint, workspace path, and ASCII-only file writing rule |
| `MAX_TOOL_ROUNDS` | `10` | Max consecutive tool-call rounds per turn |
| `DEFAULT_GEN_PARAMS` | `{"max_tokens": 32768}` | Generation parameters sent with every request (overrides server-side defaults) |
| `CONTEXT_PRESSURE_THRESHOLD` | `0.80` | Auto-compress when this fraction of context is used |
| `CONTEXT_SUMMARY_KEEP_RECENT` | `4` | Recent turns preserved during compression |
| `TOOL_RETRY_MAX` | `2` | Max retries after a tool error |
| `TOOL_RETRY_CONFIRM` | `False` | Ask user before each retry |
| `TOOL_OUTPUT_MAX_CHARS` | `16000` | Truncate tool output beyond this length (tools with `no_truncate: True` are exempt) |
| `TOOL_OUTPUT_STORE` | `True` | Keep full outputs retrievable via `get_tool_output` |
| `SESSION_AUTOSAVE` | `True` | Save session after every turn |

---

## Project Structure

```
harness/
  main.py                    # REPL entry point and CLI arg parsing
  agent.py                   # Core agentic loop: streaming, tool execution, thinking blocks, compression
  config.py                  # Central configuration
  session.py                 # Session persistence (JSONL save/load)
  ui.py                      # prompt_toolkit session, tab completion, toolbar, history
  commands/
    __init__.py              # Slash-command registry and all built-in commands
  tools/
    __init__.py              # Tool registry, auto-discovery, dispatch, safeguards
    write_file.py            # File writer with workspace confinement
    append_to_file.py        # Append to a file without overwriting
    patch_file.py            # Targeted find-and-replace inside a file
    read_file_content.py     # File reader (.txt, .csv, .py, .md, .ics, .json, .yaml)
    make_dir.py              # Directory creation
    fetch_url.py             # HTTP fetch with HTML stripping (stdlib only)
    create_calendar_event.py # Generate and save .ics calendar event files (local timezone)
    notes.py                 # Persistent key-value note store (save/get/list/delete)
    get_current_date.py      # Return today's date with day-of-week
    run_python.py            # Execute Python snippets in a sandboxed subprocess
    grep.py                  # Regex search across workspace files (returns file:line: match)
    glob.py                  # Find files by glob pattern (e.g. **/*.py)
    read_file_lines.py       # Read a specific line range from a file with line-number prefixes
    read_harness_docs.py     # Return harness_docs.md (outside workspace; no_truncate)
  skills/
    summarise.py             # Summarise the current conversation
    explain_file.py          # Read and explain a local file
    compact.py               # Summarise, reset context, print summary, delete temp note
    distill.py               # Goal-anchored context distillation with user-gated approval
    business_analyst.py      # Decompose an idea into structured components via subagent
    svg_artist.py            # Generate SVG files from natural language via subagent
    fetch_url.py             # Fetch and display a URL (skill wrapper)
  sessions/                  # Auto-saved session files (JSONL)
  notes/
    notes.json               # Persistent notes store (auto-created)
  events/                    # Default output directory for .ics files (auto-created)
  svg/                       # Default output directory for generated SVG files (auto-created)
```

---

## Tools

Tools are functions the LLM can call autonomously during a conversation. They are auto-discovered from the `tools/` directory and exposed to the model via the OpenAI function-calling API.

### Built-in Tools

| Tool | Confirm | Description |
|---|---|---|
| `write_file` | Yes | Write text to a file (workspace-confined) |
| `append_to_file` | No | Append text to an existing file without overwriting it |
| `patch_file` | No | Replace a specific string inside a file (targeted edit) |
| `read_file_content` | No | Read a file's contents (.txt, .csv, .py, .md, .ics) |
| `make_dir` | Yes | Create a directory with parent directories |
| `fetch_url` | No | Fetch a web page and return plain text (HTML stripped, stdlib only, truncated at 16 000 chars) |
| `create_calendar_event` | Yes | Generate and save an Outlook-compatible `.ics` event file (local timezone) |
| `save_note` | No | Save a persistent note under a named key |
| `get_note` | No | Retrieve a saved note by key |
| `list_notes` | No | List all note keys with previews |
| `delete_note` | Yes | Delete a saved note |
| `get_current_date` | No | Return today's date and day-of-week |
| `get_tool_output` | No | Retrieve the full untruncated output of a previous tool call |
| `run_python` | Yes | Execute a Python snippet in a sandboxed subprocess (default 15 s timeout, max 120 s) |
| `grep` | No | Search file contents by regex pattern within the workspace; returns matching lines with file path and line number |
| `glob` | No | Find files by glob pattern (e.g. `*.py`, `**/*.yaml`); returns matching paths relative to the workspace root |
| `read_file_lines` | No | Read a specific line range from a file (1-indexed, end inclusive); prefixes each line with its number — pairs naturally with `grep` hits |
| `read_harness_docs` | No | Return the harness reference document (`harness_docs.md`); the model calls this automatically when asked about harness behaviour, commands, or configuration (`no_truncate`) |

### Tool Schema Flags

Tools can include optional top-level flags in their schema alongside `"type"` and `"function"`:

| Flag | Type | Effect |
|---|---|---|
| `confirm` | bool | Pause and ask the user for `y/n` approval before executing |
| `no_truncate` | bool | Bypass `TOOL_OUTPUT_MAX_CHARS` — tool manages its own output size |

### Adding a Tool

Create a `.py` file in the `tools/` directory:

```python
# tools/my_tool.py
import tools

def my_tool(param: str) -> str:
    """Do something useful."""
    return f"Result: {param}"

TOOL_SCHEMA = {
    "type": "function",
    "confirm": False,
    "function": {
        "name": "my_tool",
        "description": "A short description of what the tool does.",
        "parameters": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "What this parameter controls.",
                }
            },
            "required": ["param"],
        },
    },
}

tools.register(TOOL_SCHEMA, my_tool)
```

The tool is auto-discovered on startup. Hot-load it at runtime with `/loadtool tools/my_tool.py`.

To remove a tool, delete its `.py` file from `tools/` and restart. The registry is rebuilt from scratch each startup.

### Generating a Tool at Runtime

```
/newtool A tool that counts the number of words in a file
```

The harness sends the description to the LLM, validates the generated code with `py_compile`, checks that it calls `tools.register()`, shows you the code, and asks for confirmation before saving and loading it. Retries up to 3 times on validation failure.

---

## Skills

Skills are higher-level behaviours that call the LLM with their own isolated message context. Unlike tools, skills are invoked by the user via `/skill <name>` — the model cannot call them autonomously. Skills do not modify the main conversation history unless they explicitly do so.

Skills that need a focused, tool-capable LLM instance should use `agent.run_subagent()` rather than calling `agent._stream_response()` directly.

### Built-in Skills

| Skill | Description |
|---|---|
| `summarise` | Summarise the current conversation without modifying history |
| `explain_file` | Read a local file and provide an explanation |
| `compact` | Summarise the conversation, reset context, print the summary, delete temp note |
| `business_analyst` | Decompose an idea into core subject, objectives, implied constraints, and missing information via a focused subagent |
| `svg_artist` | Generate a complete SVG file from a natural language description via a subagent; offers to open the result in a browser |
| `fetch_url` | Fetch and display the plain-text content of a URL |
| `distill` | Rebuild context as a goal-anchored structured block — user reviews and approves before anything changes (see [Context Distillation](#context-distillation)) |
| `translate_fr` | Translate a given text (or the last user message) into French |

### Adding a Skill

Create a `.py` file in the `skills/` directory:

```python
# skills/my_skill.py
import agent

SKILL_META = {
    "name": "my_skill",
    "description": "What the skill does in one line.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    result = agent.run_subagent(
        client,
        state["model"],
        f"Do something with: {args}",
        system_prompt="You are a focused assistant...",
        verbose=True,
        gen_params=state.get("gen_params") or None,
        state=state,
    )
    return ""
```

For simple skills that only need a single LLM response (no tools), use `agent._stream_response()` with an isolated message list instead of `run_subagent()`.

Skills are loaded fresh from disk on every `/skill` invocation — edit the file and run it again without restarting.

### Generating a Skill at Runtime

```
/newskill A skill that translates the last assistant message to French
```

The harness validates the generated code for `SKILL_META` and a `run()` function, then saves it to `skills/`.

---

## Subagents

`/subagent <task>` and `agent.run_subagent()` spawn a fresh, isolated LLM conversation dedicated to a focused task. The subagent:

- Has its own message history — nothing leaks into or out of the main conversation
- Has access to all registered tools
- Streams its output (tool calls, intermediate steps, final answer) to the terminal, visually bracketed by a `┌─ subagent` / `└─ subagent done` frame
- Returns its final answer string without appending anything to your main chat history

```
/subagent Read config.py and list every configurable parameter with its current value
/subagent Fetch https://example.com and summarise the page in 3 bullet points
/subagent What Python files are in the current directory and how large are they?
```

Skills can also spawn subagents internally (e.g. `business_analyst`, `svg_artist`) with a custom system prompt tailored to a specific role.

Use subagents for self-contained tasks where you want full tool access but don't want the intermediate steps polluting your conversation context.

---

## Session Management

Sessions are automatically saved after every turn as JSONL files in the `sessions/` directory.

- **Auto-save**: enabled by default (`SESSION_AUTOSAVE = True` in config)
- **Session IDs**: UTC timestamp-based (e.g. `20260410T143022`)
- **Atomic writes**: uses a temporary file + `os.replace` to prevent corruption
- **Resume**: use `--load <id>` on the command line or `/load <id>` during a session
- **List**: `/sessions` shows all saved sessions with message count and timestamp

Each session file stores the full message list (user, assistant, system, tool calls and results) so context is fully restored on resume.

Input history (your typed messages) is separately persisted to `~/.harness_history` and is available across sessions via the `↑`/`↓` arrow keys.

---

## Context Management

### Context Pollution

Use `/pollution` to get a health report on your context window. The report includes:

- **Role breakdown**: percentage of tokens used by system, user, assistant, and tool messages
- **Scaffolding ratio**: how much of the context is tool-call overhead vs. actual content
- **Stale results**: tool results that haven't been referenced in recent turns
- **Error noise**: failed tool calls still occupying context
- **Repeated tools**: the same tool called multiple times with identical arguments
- **Suggestions**: actionable advice (e.g. which message indices to `/drop`)

### Auto-Compression

When context usage exceeds the pressure threshold (default 80%), the harness automatically:

1. Sends the older portion of the conversation to the LLM with a summarisation prompt
2. Replaces those messages with a single summary message
3. Preserves the most recent turns (default: last 4) to maintain conversational continuity

Compression respects tool-call/result pairs — it never cuts a pair in half.
Use `/compress` to trigger it manually at any time.

### Manual Pruning

- `/drop <n>` — remove a single message by index
- `/drop <n>-<m>` — remove a contiguous range
- `/drop <a>,<b>,<c>` — remove an arbitrary set of indices in one command
- `/history` — view all messages with indices and approximate token counts

After every successful drop the updated history is printed automatically, since indices shift when messages are removed.

The `/drop` command is pair-aware: if you drop a tool-call message its results are auto-included, and vice versa. When auto-expansion adds messages you didn't request, you are prompted: `y` drops all, `n` drops only what you specified, `a` aborts.

### Context Distillation

`/skill distill [optional goal]` is the most aggressive context management tool. Rather than summarising old turns into prose, it rebuilds the entire context from scratch as a structured, goal-anchored block:

```
[DISTILLED CONTEXT]

GOAL
----
What the user is trying to accomplish.

ESTABLISHED FACTS
-----------------
- Confirmed data, decisions, and constraints.

WORK COMPLETED
--------------
- Completed steps and their outcomes.

PENDING / NEXT STEPS
--------------------
- Outstanding actions or open questions.

ARTIFACTS
---------
- Key file paths, identifiers, or values worth preserving.
```

The skill never modifies the context without explicit user approval:

1. **Goal resolution** — if you provide a goal as an argument it is used directly; otherwise the LLM infers it from the transcript and you confirm or correct it
2. **Draft generation** — the LLM produces the structured block anchored to the confirmed goal
3. **User review** — the draft is printed and you choose to approve (`y`), request edits (`e`), or abort (`a`); edits trigger a refinement pass before a second approval prompt
4. **Snapshot** — the current session is saved to disk before anything changes (recovery: `/load <session_id>`)
5. **Replace** — the original system prompt is preserved; everything else is replaced with the approved block

Use `/compress` for quick mid-session pressure relief without interruption. Use `/skill distill` when you want to intentionally reset between phases of work with a clean, structured slate.

---

## Notes System

The notes tools provide a persistent key-value store saved to `notes/notes.json`. Notes survive across sessions and are unaffected by `/reset` or context compression.

```
You: remember that the staging server is at 192.168.1.50
You: what was the staging server address?
You: show me all my notes
You: delete the staging_server note
```

The model picks key names automatically from context. Notes can store any text: URLs, decisions, code snippets, summaries, todos.

---

## Thinking Block Rendering

For models that expose chain-of-thought reasoning, the harness renders thinking content in a visually distinct dim box:

```
  ┌─ thinking ──────────────────────────────────────
  The user wants to know about X. Let me reason...
  First I should consider...

  └─ done ──────────────────────────────────────────

The answer is Paris.
```

Two delivery mechanisms are supported:

| Mechanism | Models | How it works |
|---|---|---|
| `reasoning_content` field | DeepSeek R1, QwQ, some LM Studio builds | Thinking arrives in a separate API field, cleanly separated |
| `<think>...</think>` tags | Most OSS reasoning models (DeepSeek, Qwen) | Tags embedded in `delta.content` are parsed out of the stream |
| `<\|channel>thought...<channel\|>` tags | Gemma 4 | Alternative tag format, also parsed from `delta.content` |

**LM Studio note:** For models served through LM Studio, the **Reasoning** toggle must be enabled in the model's settings panel to receive `reasoning_content` in the API response. If the toggle is off, LM Studio streams thinking as plain text without any separator and the harness cannot distinguish it from the answer.

---

## Safety and Safeguards

### Protected Files

Three tiers of protection prevent tools from modifying harness infrastructure:

1. **Specific files**: `main.py`, `agent.py`, `config.py`, `session.py`, and all `__init__.py` files in `commands/`, `tools/`, `skills/`
2. **Filename patterns**: any `__init__.py`, `.env`, `*.env`, `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`
3. **Protected directories**: `.git/`, `sessions/`, `__pycache__/` — all contents are off-limits

### Workspace Confinement

File-writing tools resolve all paths to absolute form and verify they remain inside the workspace root. Path traversal attempts (e.g. `../../etc/passwd`) are refused.

### Tool Confirmation

Tools with `"confirm": True` pause the agentic loop, display the tool name and arguments, and require the user to type `y` before executing. If cancelled, the model receives an explicit message that the action was not performed and is instructed not to claim success.

### Tool Retry Policy

When a tool fails, the harness can automatically retry up to `TOOL_RETRY_MAX` times. If `TOOL_RETRY_CONFIRM` is enabled, it asks the user before each retry.

### Output Truncation

Tool outputs longer than `TOOL_OUTPUT_MAX_CHARS` (16 000 chars) are truncated. The full output is stored internally and retrievable with `get_tool_output`. Tools that manage their own output size can set `"no_truncate": True` in their schema to bypass the cap.

### Sandboxed Python Execution

The `run_python` tool runs code in a subprocess isolated from the harness process, with a configurable timeout (default 15 s, max 120 s) and the working directory set to the workspace root. It requires user confirmation before each run.

---

## Architecture

```
User Input
    |
    v
main.py (REPL loop, prompt_toolkit UI)
    |
    +--> /command?  -->  commands/__init__.py  -->  response
    |
    +--> natural language
            |
            v
        agent.chat()
            |
            +--> _stream_or_tools()  -->  single streaming call
            |       |
            |       +--> text response: stream to stdout, return
            |       |      |- thinking tokens: dim ┌─ thinking / └─ done box
            |       |      |- answer tokens: bright cyan
            |       |
            |       +--> tool calls: accumulate silently, execute, loop back
            |
            +--> _maybe_compress()  -->  auto-summarise if over threshold
            |
            v
        final assistant message
            |
            v
        session.save()  -->  sessions/<id>.jsonl
```

The agent loop (`agent.py`) handles the core cycle:
1. Make a single streaming API call that detects both text and tool-call deltas in one pass
2. If tool calls are returned, execute them via `tools.dispatch()`, append results, loop back
3. If plain text is returned, it was already streamed to stdout — append and return
4. After the final response, check context pressure and compress if needed
5. Return control to the REPL for the next user input

Each component is independently extensible: add tools by dropping `.py` files in `tools/`, add skills in `skills/`, add commands by calling `register()` in `commands/__init__.py`.
