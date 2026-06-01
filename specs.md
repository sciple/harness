# Local LLM Harness — Technical Specification

A complete specification for implementing the harness from scratch.
All design decisions, contracts, data structures, and behavioural rules are captured here.

---

## Table of Contents

1. [Overview](#overview)
2. [File Layout](#file-layout)
3. [Dependencies](#dependencies)
4. [Module: config.py](#module-configpy)
5. [Module: session.py](#module-sessionpy)
6. [Module: ui.py](#module-uipy)
7. [Module: tools/__init__.py](#module-toolsinitpy)
8. [Module: agent.py](#module-agentpy)
9. [Module: commands/__init__.py](#module-commandsinitpy)
10. [Module: main.py](#module-mainpy)
11. [Built-in Tools](#built-in-tools)
12. [Built-in Skills](#built-in-skills)
13. [Skills System Contract](#skills-system-contract)
14. [Tool Authoring Contract](#tool-authoring-contract)
15. [State Dict Contract](#state-dict-contract)
16. [ANSI Rendering Rules](#ansi-rendering-rules)
17. [Security and Safeguard Rules](#security-and-safeguard-rules)

---

## Overview

The harness is an interactive REPL that sends user messages to a local LLM via any
OpenAI-compatible HTTP endpoint and renders the response to the terminal.

Core loop:
1. Read a line of input from the user via prompt_toolkit.
2. If the line starts with `/`, dispatch to the command registry; print the result.
3. Otherwise append a `user` message, call `agent.chat()`, print the response, autosave.
4. Repeat until the user exits.

The agent loop inside `agent.chat()` handles multi-round tool calling: a single streaming
API call detects both text and tool-call deltas. If the model calls tools, they are
executed and the loop repeats. When the model produces a plain text response, it was already
streamed to stdout; the loop ends and control returns to the REPL.

---

## File Layout

```
harness/
  main.py
  agent.py
  config.py
  session.py
  ui.py
  commands/
    __init__.py            # all slash commands live here
  tools/
    __init__.py            # tool registry, auto-discovery, dispatch, safeguards
    calculator.py
    write_file.py
    append_to_file.py
    patch_file.py
    read_file_content.py
    list_directory.py
    browse_directories.py
    make_dir.py
    fetch_url.py
    create_calendar_event.py
    notes.py               # provides save_note, get_note, list_notes, delete_note
    get_current_date.py
    run_python.py
    spell_check_file.py
  skills/
    __init__.py            # empty, package marker only
    summarise.py
    explain_file.py
    compact.py
    business_analyst.py
    svg_artist.py
    fetch_url.py
  sessions/                # auto-created; one .jsonl file per session
  notes/
    notes.json             # persistent notes store; auto-created
  events/                  # default output dir for .ics files; auto-created
  svg/                     # default output dir for SVG files; auto-created
```

---

## Dependencies

- Python 3.12+
- `openai` (PyPI) — LLM API client
- `prompt_toolkit` (PyPI) — interactive input, history, completion, toolbar

Import order convention: stdlib first, then third-party (`openai`, `prompt_toolkit`), then local modules.

---

## Module: config.py

Central configuration. No classes. Only module-level constants evaluated once at import time.

### Constants

```python
LOCAL_API_BASE: str  = "http://127.0.0.1:1234/v1/"
DUMMY_API_KEY: str   = "lmstudio-dummy-key"
DEFAULT_MODEL: str   = "google/gemma-4-e4b"
MAX_TOOL_ROUNDS: int = 10

SYSTEM_PROMPT: str   # multi-line string — see content rules below

WORKSPACE_ROOT: str  = os.path.realpath(os.getcwd())   # evaluated at startup
SESSIONS_DIR: str    = os.path.join(os.path.dirname(__file__), "sessions")
SKILLS_DIR: str      = os.path.join(os.path.dirname(__file__), "skills")
SESSION_AUTOSAVE: bool = True

CONTEXT_PRESSURE_THRESHOLD: float = 0.80
CONTEXT_SUMMARY_KEEP_RECENT: int  = 4

TOOL_RETRY_MAX: int    = 2
TOOL_RETRY_CONFIRM: bool = False

TOOL_OUTPUT_MAX_CHARS: int = 16000
TOOL_OUTPUT_STORE: bool    = True

ALLOWED_GEN_PARAMS: dict = {
    "temperature": float,
    "top_p":       float,
    "max_tokens":  int,
    "seed":        int,
}

# Sent with every API request; overrides server-side defaults.
DEFAULT_GEN_PARAMS: dict = {
    "max_tokens": 32768,
}
```

### SYSTEM_PROMPT content rules

The prompt must:
- Identify the OS (Windows) and include the workspace root path.
- Instruct the model to be concise and use tools when appropriate.
- Instruct the model to use only ASCII characters in any text saved to files
  (no typographic quotes, em-dashes, ellipsis, non-ASCII Unicode).
- State that harness infrastructure files are protected and must never be modified.

### File safeguards (evaluated once at module load)

```python
_HARNESS_ROOT: str = os.path.dirname(os.path.realpath(__file__))

PROTECTED_FILES: frozenset   # absolute real paths of:
    # main.py, agent.py, config.py, session.py,
    # commands/__init__.py, tools/__init__.py, skills/__init__.py

PROTECTED_FILENAME_PATTERNS: tuple[str, ...]   # matched case-insensitively against basename:
    # "__init__.py", ".env", "*.env",
    # "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"

PROTECTED_DIRS: frozenset    # absolute real paths of:
    # .git/, sessions/, __pycache__/
    # All content inside these directories is off-limits.
```

---

## Module: session.py

Handles read/write of session files. Must never raise an exception that reaches the REPL.

### Session file format

- Location: `SESSIONS_DIR/<session_id>.jsonl`
- One JSON object per line, each representing one message dict.
- Written atomically: write to a temp file in `SESSIONS_DIR`, then `os.replace()`.

### Session ID format

UTC timestamp: `datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")`

### Functions

```python
def new_id() -> str:
    """Generate a session ID from the current UTC timestamp."""

def ensure_dir() -> None:
    """Create SESSIONS_DIR if missing (os.makedirs with exist_ok=True)."""

def save(state: dict) -> None:
    """
    Write state["messages"] to SESSIONS_DIR/<state["session_id"]>.jsonl.
    - Convert each message with _msg_to_dict() before JSON-serialising.
    - Messages that fail serialisation are silently skipped.
    - All exceptions are silently swallowed — persistence must never crash.
    """

def load(session_id: str) -> list[dict] | None:
    """
    Return the message list for a session, or None if not found.
    Lines that fail JSON parsing are silently skipped.
    """

def list_sessions() -> list[tuple[str, int, str]]:
    """
    Scan SESSIONS_DIR for .jsonl files.
    Return list of (session_id, message_count, iso_timestamp) sorted newest-first.
    Timestamp is file mtime formatted as "%Y-%m-%d %H:%M:%S UTC".
    """
```

### _msg_to_dict helper

Messages in state["messages"] may be either plain dicts or OpenAI SDK objects
(`ChatCompletionMessage`). Normalise to a plain dict:

1. If already a dict, return as-is.
2. If object has `.model_dump()`, call it.
3. Fallback: manually reconstruct `{"role": ..., "content": ..., "tool_calls": ..., "tool_call_id": ...}`
   from attributes, skipping None fields.

---

## Module: ui.py

Wraps prompt_toolkit to provide an enhanced interactive input experience.
The module exposes a **module-level singleton `PromptSession`** (not a factory) plus a
mutable `toolbar_state` dict that the REPL and commands update in place.

### Module-level state

```python
toolbar_state: dict = {"model": "", "session_id": ""}
# Mutated by main.py at startup and by /model when the active model changes.

session: PromptSession = PromptSession(
    completer=SlashCompleter(),
    complete_while_typing=False,            # completions only on Tab
    auto_suggest=AutoSuggestFromHistory(),
    history=FileHistory("~/.harness_history"),
    lexer=SlashLexer(),
    key_bindings=_bindings,
    multiline=True,
    prompt_continuation=lambda w, l, ws: " " * w,
    bottom_toolbar=get_toolbar,
    refresh_interval=1.0,
)
# After creation: session.app.style = Style.from_dict({"slash-command": "bold ansicyan"}).
```

### SlashCompleter

Custom `Completer` subclass. Reads `commands._commands` **lazily inside
`get_completions`** (to avoid circular imports). Only yields completions when the text
before the cursor starts with `/`. Each completion uses `display_meta` set to the
command's registered help text.

### SlashLexer

Custom `Lexer` subclass. On the first line only: if it begins with `/`, splits the first
token (the command) and yields it with the token class `"class:slash-command"`; the
remainder is emitted with the default token. All other lines are default-styled.

### Key bindings

```python
_bindings = KeyBindings()

@_bindings.add("enter")
def _submit(event):
    event.current_buffer.validate_and_handle()    # plain Enter submits

@_bindings.add("escape", "enter")
def _insert_newline(event):
    event.current_buffer.insert_text("\n")        # Alt+Enter / Esc+Enter inserts \n
```

### Bottom toolbar

`get_toolbar()` returns an `HTML(...)` object on every redraw (triggered by
`refresh_interval=1.0`). Format:

```
 model: {model}  │  session: {session_id}  │  /help · /exit
```

The last segment is in the `ansidarkgray` style.

### Re-exports

```python
from prompt_toolkit.patch_stdout import patch_stdout     # re-exported for callers
from prompt_toolkit.shortcuts import clear               # re-exported for /cls
```

### Public API

```python
def prompt(message: str = "") -> str:
    """Thin wrapper around the singleton session's .prompt(). Raises EOFError on
    Ctrl+D and KeyboardInterrupt on Ctrl+C. Plain Enter submits; Alt+Enter inserts
    a newline."""

def get_toolbar() -> HTML:
    """Called by prompt_toolkit on every redraw of the bottom toolbar."""
```

Skills and confirmation dialogs call `ui.prompt("  label ")` directly. The toolbar
and ghost-completions remain active during those calls.

---

## Module: tools/__init__.py

The tool registry. Self-contained; tool files register themselves by calling `tools.register()`.

### Internal state (module-level)

```python
_registry: dict[str, tuple[dict, callable]] = {}
    # name -> (schema_dict, function)

_confirm_tools: set[str] = set()
    # tool names that require user confirmation before execution

_no_truncate_tools: set[str] = set()
    # tool names exempt from TOOL_OUTPUT_MAX_CHARS truncation

_failed_tools: dict[str, str] = {}
    # filename -> error message, for tools that failed to load

_tool_output_store: OrderedDict = OrderedDict()
    # store_key -> full output string; store_key = f"{tool_name}_{counter}"
    # max 50 entries; evict oldest on overflow (popitem(last=False))

_call_counter: list[int] = [0]
    # mutable int wrapped in list so it can be modified from nested scopes
```

### Public API

```python
def register(schema: dict, fn: callable) -> None:
    """
    Store schema + fn under schema["function"]["name"].
    The "confirm" flag may be either at the top level of the schema OR nested inside
    schema["function"] — both locations are checked and both add the tool to
    _confirm_tools.
    If schema has top-level "no_truncate": True, add to _no_truncate_tools.
    """

def get_schemas() -> list[dict]:
    """
    Return all schemas for passing to the LLM API.
    Strip the top-level "confirm" key (harness-only; rejected by the API).
    The "no_truncate" key is left in place — some backends ignore unknown keys,
    and the harness uses it internally rather than forwarding its semantics.
    """

def dispatch(name: str, args: dict) -> str:
    """
    Execute the named tool with args as kwargs.
    - If name not in registry: return "Error: unknown tool '<name>'"
    - If the function raises: return "Error executing tool '<name>': <exc>"
    - If result is a dict: JSON-serialise with indent=2.
    - Convert result to str.
    - Store full result in _tool_output_store under key f"{name}_{counter}".
    - If TOOL_OUTPUT_STORE and name not in _no_truncate_tools
      and len(result) > TOOL_OUTPUT_MAX_CHARS:
        truncate result and append:
        "\n[Output truncated. Full output available via get_tool_output('<key>')]"
    - Return the (possibly truncated) string.
    """

def requires_confirmation(name: str) -> bool:
    return name in _confirm_tools

def list_tools() -> list[str]:
    return list(_registry.keys())

def list_failed_tools() -> dict[str, str]:
    return dict(_failed_tools)

def get_stored_output(key: str) -> str:
    """Return stored full output, or error string if key missing."""

def reload_failed(specific_file: str | None = None) -> dict[str, str]:
    """
    Retry loading failed tool files.
    - If specific_file given, target only that filename.
    - For each target: clear sys.modules entry, remove from _failed_tools,
      re-import via importlib.util, update results.
    - Returns {filename: "ok" | error_message}.
    """

def is_protected_path(path: str) -> tuple[bool, str]:
    """
    Check the three protection tiers (see config.py):
    1. Exact match against PROTECTED_FILES (resolved absolute paths).
    2. fnmatch against PROTECTED_FILENAME_PATTERNS (case-insensitive on basename).
    3. Prefix match against PROTECTED_DIRS (check both dir == path and dir/ prefix).
    Return (True, human_reason) or (False, "").
    """
```

### Built-in meta-tool: get_tool_output

Registered directly in `__init__.py` before `_autodiscover()`:

```
name: "get_tool_output"
description: "Retrieve the full (untruncated) output from a previous tool call that was truncated."
parameters: { key: string (required) }
```

Calls `get_stored_output(key)`.

### Auto-discovery

Called at the bottom of `__init__.py` after registering the meta-tool:

```python
def _autodiscover() -> None:
    """
    Import every .py file in tools/ that does not start with '_'.
    Each file self-registers by calling tools.register() at module level.
    On import error: add to _failed_tools and print a warning line.
    Skip files already in sys.modules.
    Module name: "tools.<stem>"
    """
```

---

## Module: agent.py

The agentic loop. All LLM communication goes through this module.

### Constants and ANSI codes

```python
ASSISTANT_COLOR = "\033[96m"     # bright cyan — used in main.py for "Assistant:" label
_THINK_CONTENT  = "\033[2;3m"   # dim + italic — thinking token content
_THINK_BOX      = "\033[2m"     # dim only     — box frame lines (┌─ / └─)
_RESET          = "\033[0m"
_DIM            = "\033[2m"
_SPINNER_FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
```

### Thinking tag registry

```python
_THINK_TAG_PAIRS: list[tuple[str, str]] = [
    ("<think>",           "</think>"),   # DeepSeek, Qwen, most OSS models
    ("<|channel>thought", "<channel|>"), # Gemma 4
]
```

New model variants are added here. Each entry is `(open_tag, close_tag)`.

### Thinking box helpers

```python
_BOX_WIDTH = 52

def _think_open() -> None:
    """Print the ┌─ thinking ──... opening frame on its own line."""

def _think_close() -> None:
    """Print the └─ done ──... closing frame followed by a blank line."""
```

### _find_think_open(text) -> tuple[int, str, str] | None

Scan `text` for the earliest occurrence of any open tag in `_THINK_TAG_PAIRS`.
Returns `(position, open_tag, close_tag)` or `None`.

### Functions

#### make_client() -> OpenAI

```python
return OpenAI(api_key=DUMMY_API_KEY, base_url=LOCAL_API_BASE)
```

#### get_context_length(client, model) -> int | None

Query `/v1/models`. For the matching model entry, read `max_context_length` or
`context_length` attribute (whichever is present). Return as int or None on failure.

#### new_conversation(system_prompt) -> list[dict]

```python
return [{"role": "system", "content": system_prompt}]
```

#### _set_title(text: str) -> None

Emit OSC terminal escape to set the title bar: `\033]0;{text}\007`

#### _run_spinner(stop: threading.Event, token_counter: list) -> None

Background thread function. Braille spinner cycling at ~80ms intervals.
Display format:
- While `token_counter[0] == 0`: `"{frame} thinking…"`
- Otherwise: `"{frame} generating… {n} tok"`
On stop: clear line with `\r` + spaces + `\r`.

#### _stream_response(client, model, messages, gen_params) -> tuple[str, dict | None]

Streaming-only response function used by skills and the subagent path when no tools
are registered. Shares the thinking-block rendering logic with `_stream_or_tools`.

**API call:**
```python
stream = client.chat.completions.create(
    model=model,
    messages=messages,
    stream=True,
    stream_options={"include_usage": True},
    **(gen_params or {}),
)
```

**Spinner:** Start before the API call; stop on first content chunk.

**Thinking block state (same logic as _stream_or_tools):**
```python
in_think_tag: bool = False
think_close_tag: str = "</think>"   # updated when an open tag is matched
using_reasoning_field: bool = False # True when thinking came via reasoning_content
pending: str = ""
```

**Thinking token rendering — two mechanisms:**

1. `delta.reasoning_content` field: print each chunk in `_THINK_CONTENT`.
   Call `_think_open()` on the first chunk. Set `using_reasoning_field = True`.

2. `<think>` / `<|channel>thought` tags in `delta.content`: parse with `pending` buffer.
   Use `_find_think_open()` to detect open tags. Print content inside tags with
   `_THINK_CONTENT`. Call `_think_open()` / `_think_close()` at boundaries.

**reasoning_content close rule:** When `in_think_tag and using_reasoning_field` is True
and the first `delta.content` token arrives, call `_think_close()` and clear both flags.
Before adding the token to `pending`, strip any leading thinking open tag from it
(models like Gemma 4 emit the open tag marker in `delta.content` immediately after
`reasoning_content` ends — stripping it prevents re-entering thinking mode for the answer).

**Token counter and title:**
- Increment `token_counter[0]` on each chunk with content.
- Call `_set_title(f"⟨{token_counter[0]} tok⟩")` on each increment.
- Reset title to `"harness"` after streaming ends.

**Usage extraction:**
- The final chunk may have `chunk.usage` (because of `include_usage: True`).
- Extract `prompt_tokens`, `completion_tokens`, `total_tokens` into a dict.

**After streaming:**
- Print a blank line.
- Print a dim summary line:
  `"  ↳ {completion_tok} tokens out · {prompt_tok} in · {elapsed:.1f}s · {tok_per_sec:.1f} tok/s"`

**Return:** `("".join(answer_chunks), usage_dict | None)`
- `answer_chunks` contains only non-thinking content (text outside thinking blocks).

#### _stream_or_tools(client, model, messages, schemas, gen_params) -> tuple[str, list | None, dict | None]

Single streaming call that handles both plain text and tool-call deltas. This is the
primary path used by `agent.chat()`.

Return discriminant is **`tool_calls`** (second slot), not `text`:
- **Text response:** `("".join(answer_chunks), None, usage)`
- **Tool call response:** `("", [_ToolCall, ...], usage)`

Tool-call deltas are accumulated into a `dict[int, dict]` keyed by `tc_delta.index`.
Each entry collects `id`, `name`, and concatenated `arguments`. After streaming ends,
wrap each entry in a `_ToolCall` namespace object (mimics the OpenAI SDK shape so
downstream code can use `tc.id`, `tc.function.name`, `tc.function.arguments`).

An optional debug file is written when the environment variable
`HARNESS_DEBUG_STREAM` is set — each chunk's `delta.content` and
`delta.reasoning_content` are appended to that file (one line per chunk). `_stream_response`
opens the same path for writing at the start of its call. Useful for diagnosing new
thinking-tag formats.

**API call:** Same as `_stream_response` but with `tools=schemas` and `tool_choice="auto"`
added when schemas is non-empty.

**Tool-call accumulation:**
```python
tool_acc: dict[int, dict] = {}   # index -> {id, name, arguments}
is_tool_call: bool = False
```
On `delta.tool_calls` chunks: accumulate `id`, `name`, `arguments` by index. Skip text
processing for these chunks.

**Text path:** Identical thinking-block rendering as `_stream_response` (shared logic).
Normal answer tokens go into `answer_chunks` and are printed in `ASSISTANT_COLOR`.

**After streaming:**
- If `is_tool_call`: return `(None, list(tool_acc.values()), usage)`.
- Else: print summary line and return `("".join(answer_chunks), [], usage)`.

#### _execute_tool_with_retry(fn_name, fn_args, tool_call_id, verbose, state) -> str

```
1. If tool requires confirmation AND state["skip_confirm"] is False:
   - Print: "  [confirm] Run '{fn_name}'?"
   - Print: "  Args: {json.dumps(fn_args, indent=2)}"
   - Input: "  Proceed? [y/N] "
   - If answer != "y": return the CANCELLED sentinel string:
     "CANCELLED: The user explicitly declined to run this tool. The action was NOT
      performed and NO changes were made. Inform the user that the action was cancelled
      and do not claim or imply that it succeeded."

2. result = tool_registry.dispatch(fn_name, fn_args)

3. Retry loop (up to min(TOOL_RETRY_MAX, 5) times):
   - While result.startswith("Error:") and retries_left > 0:
     - If verbose: print retry attempt info
     - If TOOL_RETRY_CONFIRM: ask user; break if "n"
     - result = tool_registry.dispatch(fn_name, fn_args)
     - decrement retries_left

4. Return result
```

#### _safe_compress_boundary(messages, sys_end, keep_from) -> int

Adjust the `keep_from` split index so it never bisects a tool-call / tool-result group.
A group is **one assistant message with `tool_calls` + all immediately-following `tool`
messages**. Iterates until stable:
- If `messages[keep_from]` is role `"tool"`: push `keep_from` forward (it is an orphaned
  result; its paired call is still in the compressible slice).
- If the message just before `keep_from` is an assistant with `tool_calls`: pull
  `keep_from` back so the whole group stays together on one side of the cut.

Called by `_maybe_compress` before building the compressible slice.

#### _maybe_compress(client, model, messages, usage, context_length, gen_params) -> bool

Triggered after each final assistant response. Returns True if compression happened.

```
1. If context_length is None or usage is empty: return False.
2. ratio = usage["total_tokens"] / context_length
3. If ratio < CONTEXT_PRESSURE_THRESHOLD: return False.
4. Identify sys_end: index 1 if messages[0]["role"] == "system", else 0.
5. Walk backwards through messages to find keep_from:
   - Count user + assistant messages from the end.
   - Stop when count >= CONTEXT_SUMMARY_KEEP_RECENT * 2.
   - keep_from = that index.
6. compressible = messages[sys_end:keep_from]
7. If len(compressible) < 2: return False.
8. Build a plaintext transcript from compressible:
   - Skip messages with no content.
   - Format: "ROLE: content[:500]"
9. Call LLM (non-streaming) with a summarisation prompt.
10. Replace messages[sys_end:keep_from] with one system message:
    {"role": "system", "content": "[SUMMARY OF EARLIER CONVERSATION]: {summary}"}
11. Print dim compression notice.
12. Return True.
```

#### chat(client, model, messages, *, verbose, usage_out, gen_params, context_length, state) -> str

Main entry point. Modifies `messages` in-place. Called by the REPL for every user turn.

```
schemas = tool_registry.get_schemas()
compressed = False

for _ in range(MAX_TOOL_ROUNDS):
    text, tool_calls, usage = _stream_or_tools(client, model, messages, schemas, gen_params)

    if tool_calls is None:
        # Model produced a text response (already streamed to stdout)
        messages.append({"role": "assistant", "content": text})
        if usage_out is not None:
            usage_out.update(usage or {})
        if not compressed:
            _maybe_compress(client, model, messages, usage or {}, context_length, gen_params)
        return text

    # Model called tools
    if verbose:
        print "  [tool] {comma-joined tool names}"

    # Build and append assistant tool-call message
    # (reconstructed from tool_calls list as a plain dict)
    messages.append(assistant_tool_call_message)

    for tc in tool_calls:
        fn_name = tc["name"]
        try:
            fn_args = json.loads(tc["arguments"])
        except json.JSONDecodeError:
            fn_args = {}
        result = _execute_tool_with_retry(fn_name, fn_args, tc["id"], verbose, state)
        if verbose:
            print "  [{fn_name}] -> {result[:200]}"
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": result,
        })
    # loop back

# Safety valve: MAX_TOOL_ROUNDS exceeded — force a final text response
text, _, usage = _stream_or_tools(client, model, messages, [], gen_params)
messages.append({"role": "assistant", "content": text or ""})
if usage_out is not None:
    usage_out.update(usage or {})
return text or ""
```

#### run_subagent(client, model, task, *, system_prompt, verbose, gen_params, state) -> str

Spawn a fresh, isolated conversation for a focused task.

```python
sys_msg = system_prompt or "You are a focused subagent. Complete the task and stop."
messages = new_conversation(sys_msg)
messages.append({"role": "user", "content": task})
usage_out: dict = {}
return chat(
    client, model, messages,
    verbose=verbose,
    usage_out=usage_out,
    gen_params=gen_params,
    context_length=None,
    state=state,
)
```

The subagent uses the full tool registry. Its message history is never appended to the
caller's `state["messages"]`. The return value is the final assistant text.

---

## Module: commands/__init__.py

All slash commands. Also contains the command registry, shared helpers, and
the token-estimation utilities.

### Registry

```python
_commands: dict[str, tuple[callable, str]] = {}
    # name (without /) -> (handler_fn, help_string)

def register(name: str, fn: callable, help: str = "") -> None:
    _commands[name.lstrip("/")] = (fn, help)

def dispatch(raw: str, state: dict) -> tuple[bool, str | None]:
    """
    If raw does not start with '/': return (False, None).
    Parse: name = first word after '/' (lowercased), args = rest.
    If name not in registry: return (True, "Unknown command...").
    Call fn(args, state) and return (True, result).
    """
```

All command handlers have signature: `fn(args: str, state: dict) -> str | None`
- `args`: everything after the command name (stripped), may be empty string.
- `state`: mutable session dict.
- Return a string to print, or `None` for no output.

### Shared helpers

#### sanitize_for_file(text: str) -> str

Applied to all LLM-generated code before writing to disk:
1. `unicodedata.normalize("NFC", text)`
2. Translate a hardcoded map of common Unicode replacements to ASCII equivalents:
   - `\u2018` / `\u2019` -> `'`
   - `\u201c` / `\u201d` -> `"`
   - `\u2014` -> `--`, `\u2013` -> `-`
   - `\u2026` -> `...`, `\u00a0` -> ` `, `\u2212` -> `-`
3. `.encode("utf-8", errors="replace").decode("utf-8")`

#### _spinner(label: str, stop_event: threading.Event) -> None

Background thread spinner (braille frames, 80ms). On stop: clear line.

#### _extract_code(text: str) -> str

Strip markdown fences and leading prose from LLM output:
1. Try `re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)` — return group 1.
2. Otherwise scan lines top-to-bottom for the first line whose stripped form starts with
   `"import "`, `"from "`, or `"def "` — return everything from that line onward.
3. Fallback: return `text.strip()`.

#### Token estimation

```python
def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def _msg_token_estimate(m) -> int:
    """Sum _estimate_tokens over content + tool call arguments, plus 4 for overhead."""
```

### Command implementations

#### /help

List all registered commands sorted alphabetically, formatted as a table.

#### /reset

Preserve only messages with `role == "system"`. Clear and re-extend `state["messages"]`.
Also reset `state["usage"] = {}` and `state["context_length"] = None`.

#### /model [name]

Without args: print current model. With args: set `state["model"]`, reset
`state["context_length"]` to None.

#### /ctx

Display the last turn's token usage from `state["usage"]`.
If `state["context_length"]` is None, fetch it now via `agent.get_context_length()`.
Print a 30-character block bar showing fill percentage.

#### /set <param> <value>

Validate param against `ALLOWED_GEN_PARAMS`. Cast value to the expected type.
Apply range guards: `temperature` in [0.0, 2.0]; `top_p` in [0.0, 1.0]; `max_tokens > 0`.
Store in `state["gen_params"]`.

#### /params

Print active `state["gen_params"]` overrides, or a "using model defaults" message.

#### /unset <param>

Remove a key from `state["gen_params"]`.

#### /history

For each message in `state["messages"]`, print:
- Index, role (uppercased), estimated token count.
- If message has `tool_calls`: show `name(args)` for each call.
- Otherwise: show a 160-character preview of content (truncate with `...`).

#### /pollution

Context health analysis. Must compute and print:
- **Role breakdown**: percentage of estimated tokens per role (system, user, assistant, tool).
- **Scaffolding ratio**: (tool + assistant-with-tool-calls tokens) / total tokens, as percentage.
- **Stale results**: tool result messages not referenced in the last `_STALE_TURNS` turns.
  `_MUTABLE_TOOLS = {"list_directory", "read_file_content", "make_dir", "write_file"}`.
- **Error noise**: tool result messages whose content starts with `"Error:"`.
- **Repeated tool calls**: same tool called with identical arguments more than once.
- **Suggestions**: actionable text (e.g. which message indices to `/drop`).

#### /drop <n> or /drop <n>-<m>

Remove messages by index. Pair-aware:
- If dropping a tool-call assistant message, also remove its paired tool-result messages.
- If dropping a tool-result message, also remove the paired tool-call message.
Guard against out-of-range indices.

#### /compress

Manually trigger context compression. Temporarily sets both `config.CONTEXT_PRESSURE_THRESHOLD`
and the module-level `agent.CONTEXT_SUMMARY_KEEP_RECENT` to force compression. Restores both
after the call completes (in a `finally` block). Patches both the `config` module attribute
and the `agent` module's local copy (imported as a value at load time).

#### /sessions

Call `session.list_sessions()`. Print a table with columns: ID, message count, timestamp.
Mark the current session with `*`.

#### /load <id>

Load session from disk into `state["messages"]` and update `state["session_id"]`.

#### /tools

List registered tools (marking `[confirm]` ones). Also list failed-to-load tools with errors.

#### /reloadtools [filename]

Call `tool_registry.reload_failed(specific_file or None)`. Print results.

#### /loadtool <path>

Load a `.py` file by path using `importlib.util`. Check for new tool names before/after to
report which tools were registered. Path must end in `.py` and exist on disk.

#### /newtool <description>

LLM-assisted tool generation. Up to 3 attempts:

1. Build prompt from `_TOOL_TEMPLATE` (see template content in Security section).
   On retry: append the previous error to the prompt.
2. Show spinner. Call LLM (non-streaming, no tools).
3. Extract code with `_extract_code()`.
4. Validate with `_validate_tool_code()`:
   - Write to temp `.py` file.
   - Run `py_compile.compile(tmp_path, doraise=True)`.
   - Check that `"tools.register("` appears in the code.
5. On validation pass: print code, ask `"Save and load this tool? [y/N]"`.
6. If confirmed: write with `sanitize_for_file()`, load with `_load_tool_from_path()`.

Tool generation prompt (`_TOOL_TEMPLATE`) rules:
- Output must start with `import tools` (first character must be `i`).
- Define exactly one public function.
- Define `TOOL_SCHEMA` dict.
- End with `tools.register(TOOL_SCHEMA, <function>)`.
- No markdown, no prose, no code fences.

#### /skills

Scan `SKILLS_DIR` for `.py` files not starting with `_`. Import each, read `SKILL_META`,
print a table of name, version, description.

#### /skill <name> [args]

Load `SKILLS_DIR/<name>.py` fresh each time (always re-read from disk).
Verify presence of `SKILL_META` dict and callable `run` function.
Call `run(skill_args, state, state["client"])`. Print the return value.

#### /newskill <description>

Same generation flow as `/newtool`, but using `_SKILL_TEMPLATE` and `_validate_skill_code()`.
Validation checks: syntax via `py_compile`, presence of `SKILL_META`, presence of `def run(`.
Derive filename from `SKILL_META["name"]`. Save to `SKILLS_DIR/`.
Do not auto-load the skill (skills are loaded on-demand by `/skill`).

Skill generation prompt (`_SKILL_TEMPLATE`) rules:
- Import `agent` at the top.
- Define `SKILL_META = {"name": ..., "description": ..., "version": ...}`.
- Define `run(args: str, state: dict, client) -> str`.
- Use `agent.run_subagent()` for tool-capable isolated LLM calls.
- Use `agent._stream_response()` for simple text-only LLM calls.
- Do not append to `state["messages"]` unless explicitly desired.

#### /subagent <task>

Spawn a fresh subagent for `task`. Prints a `┌─ subagent` / `└─ subagent done` frame
around the output. Calls `agent.run_subagent()` with `verbose=True`. Returns `""`.

#### /system [prompt]

Without args: print current system prompt (the content of `state["messages"][0]`).
With args: replace the content of the system message in-place.

#### /calendar [args]

Display a mini ASCII calendar. No args: current month. Args: `"6"` for month 6 of current
year, or `"2026 9"` for September 2026.

#### /time

Print current UTC time and local time.

#### /cls

Clear the terminal screen and reprint the startup banner.

#### /open <url>

Open a URL in the default system browser via `webbrowser.open()`. If the URL does
not start with `http://` or `https://`, prepend `https://` before opening.

#### /exit, /quit

Set `state["running"] = False`. Return None.

---

## Module: main.py

Entry point. REPL loop.

### CLI arguments

```
--model     str    default: DEFAULT_MODEL
--base-url  str    default: LOCAL_API_BASE
--system    str    default: SYSTEM_PROMPT
--quiet     flag   suppress verbose tool output
--load      str    session ID to resume
```

### State dict

See [State Dict Contract](#state-dict-contract).

### Startup sequence

1. `argparse` parse args.
2. `agent.make_client()` — exit(1) with error message if the client cannot be built.
3. `session.ensure_dir()`.
4. `session_id = session.new_id()`.
5. Build `state` dict including `gen_params = DEFAULT_GEN_PARAMS.copy()` and
   `skip_confirm = False`.
6. If `--load`: load session; on missing ID print error and exit(1); else replace
   `state["messages"]` and `state["session_id"]`.
7. Else if `SESSION_AUTOSAVE`: save immediately (creates the file).
8. Populate `ui.toolbar_state["model"]` and `ui.toolbar_state["session_id"]` so the
   bottom toolbar reflects the current session from the first keystroke.
9. `print_banner(model, base_url, session_id)` — prints the cyan ASCII-art logo then
   four dim-labelled lines (`Model`, `Endpoint`, `Session`, `Commands`).
10. Fetch context length lazily on the first non-command turn via
    `agent.get_context_length()` — NOT at startup.
11. Enter REPL loop.

### ASCII-art banner

Printed by `print_banner()`. The logo is a fixed 7-line tessellation in bright cyan
(`\033[96m`) followed by a bold `"LOCAL LLM HARNESS"` title and a dim tagline, then
the four info lines. `/cls` reprints it after clearing the screen.

### REPL loop

```python
while state["running"]:
    try:
        user_input = pt_session.prompt("\nYou: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not user_input:
        continue

    handled, output = commands.dispatch(user_input, state)
    if handled:
        if output:
            print(output)
        if SESSION_AUTOSAVE:
            session.save(state)
        continue

    # Regular turn
    state["messages"].append({"role": "user", "content": user_input})

    print(f"\n\033[96;1mAssistant:\033[0m ", end="", flush=True)

    try:
        agent.chat(
            state["client"], state["model"], state["messages"],
            verbose=not args.quiet,
            usage_out=state["usage"],
            gen_params=state["gen_params"] or None,
            context_length=state["context_length"],
            state=state,
        )
    except RuntimeError as e:
        print(f"\nError: {e}")
        state["messages"].pop()
        continue

    if SESSION_AUTOSAVE:
        session.save(state)
```

---

## Built-in Tools

### calculator.py

- Function: `calculator(expression: str) -> str`
- Uses AST (`ast.parse`, `ast.literal_eval`) — never `eval()`.
- Supported node types: `Expression`, `BinOp`, `UnaryOp`, `Num`, `Constant`,
  operators `Add`, `Sub`, `Mult`, `Div`, `Pow`, `FloorDiv`, `Mod`, `USub`, `UAdd`.
- On unsupported node: raise `ValueError("Unsupported operation")`.
- Return the result as a string, or an error string on exception.
- `confirm: False`

### write_file.py

- Function: `write_file(path: str, content: str) -> str`
- Resolve `path` as `os.path.realpath(os.path.join(WORKSPACE_ROOT, path))`.
- Security check 1: resolved path must start with `WORKSPACE_ROOT + os.sep` or equal `WORKSPACE_ROOT`.
- Security check 2: call `is_protected_path(resolved)`.
- Create parent directories with `os.makedirs(parent, exist_ok=True)`.
- Write with `encoding="utf-8"`.
- `confirm: True`

### append_to_file.py

- Function: `append_to_file(path: str, content: str, add_newline: bool = True) -> str`
- Workspace confinement and protection check same as `write_file`.
- If file exists and has content, prepend a newline before `content` when `add_newline=True`.
- Create parent directories automatically.
- `confirm: False`

### patch_file.py

- Function: `patch_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str`
- Read file, perform in-memory find-and-replace.
- If `replace_all=False` and more than one occurrence exists: return error (use `replace_all=True`).
- Write atomically via temp file + `os.replace`.
- Return feedback including number of replacements made.
- `confirm: False`

### read_file_content.py

- Function: `read_file_content(path: str) -> str`
- Allowed extensions: `.txt`, `.csv`, `.py`, `.md`, `.ics`.
- Read with `encoding="utf-8"`, `errors="replace"`.
- Return file contents or an error string.
- `confirm: False`

### list_directory.py

- Function: `list_directory(path: str = ".") -> str`
- Expand environment variables in `path`.
- Return a newline-joined sorted list of entries (directories marked with trailing `/`),
  or an error string.
- `confirm: False`

### browse_directories.py

- Function: `browse_directories() -> str`
- Use `pathlib.Path(WORKSPACE_ROOT).rglob("*")` to collect all file paths.
- Return newline-joined absolute path strings.
- `confirm: False`

### make_dir.py

- Function: `make_dir(path: str) -> str`
- Call `is_protected_path(os.path.realpath(path))`.
- Call `os.makedirs(path, exist_ok=True)`.
- `confirm: True`

### fetch_url.py

- Function: `fetch_url(url: str) -> str`
- Uses only stdlib `urllib` — no external dependencies.
- Strips HTML tags for plain text output; respects charset headers.
- Truncates at 16 000 chars, appending a source reference line.
- Returns error string on HTTP errors or exceptions.
- `confirm: False`

### create_calendar_event.py

- Function signature:
  `create_calendar_event(summary: str, date: str, time: str, duration_hours: float = 1.0, timezone_name: str = "", output_path: str = "") -> str`
  - `date` must be `YYYY-MM-DD`; `time` must be `HH:MM` (24-hour).
  - `duration_hours` defaults to 1.0.
  - `timezone_name` is an optional IANA name (e.g. `Europe/Zurich`); when empty the
    local timezone is auto-detected.
  - `output_path` is relative to the workspace; when empty, defaults to
    `events/<date>_<slugified-summary>.ics` (slug: lowercase, punctuation stripped,
    spaces→underscores, capped at 40 chars).
- Local timezone detection (when `timezone_name` is empty): on Windows, read
  `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\TimeZoneInformation\TimeZoneKeyName`
  via `winreg` and map through a Windows→IANA table (Romance/W. Europe/Central Europe/
  GMT/Eastern/Central/Mountain/Pacific Standard Time plus UTC). On failure, try
  `ZoneInfo("localtime")`, then fall back to `timezone.utc`.
- Workspace confinement + `is_protected_path` check enforced before writing.
- Generates a minimal VCALENDAR/VEVENT with `DTSTART;TZID={tz_id}:...` (local wall-clock
  time, not UTC `Z` suffix), `DTSTAMP` in UTC, and a random `UID`.
- CRLF line endings, `newline=""` on `open()` so Python does not double-translate.
- `confirm: True`

### notes.py

Provides four registered tools:

| Tool | Signature | confirm |
|---|---|---|
| `save_note` | `(key: str, value: str) -> str` | No |
| `get_note` | `(key: str) -> str` | No |
| `list_notes` | `() -> str` | No |
| `delete_note` | `(key: str) -> str` | Yes |

- Persists to `notes/notes.json` using atomic writes (temp file + `os.replace`).
- JSON serialisation: `{"key": "content", ...}`.
- `list_notes` returns each key with a 60-char content preview.

### get_current_date.py

- Function: `get_current_date() -> str`
- Returns current date with day-of-week in local timezone.
- Format: `"Monday, 2026-04-18"`
- `confirm: False`

### run_python.py

- Function: `run_python(code: str, timeout: int = 15) -> str`
- Clamps timeout to `[1, 120]` seconds.
- Runs `[sys.executable, "-c", code]` as a subprocess with `cwd=WORKSPACE_ROOT`.
- Captures stdout and stderr separately.
- On timeout: returns a timeout error string.
- Returns `stdout + [stderr block if non-empty] + [exit code if non-zero]`.
- `confirm: True`, `no_truncate: True`

### spell_check_file.py

- Placeholder implementation.
- Function: `spell_check_file(path: str) -> str`
- Currently only replaces `"hello"` with `"HeLLo"` as a demonstration stub.
- `confirm: False`

---

## Built-in Skills

### summarise.py

```python
SKILL_META = {
    "name": "summarise",
    "description": "Summarise the current conversation and print the result.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # Build a transcript from state["messages"] (skip system messages).
    # Cap each message at 800 chars.
    # Call agent._stream_response() with an isolated message list.
    # Do NOT append to state["messages"].
    # Return "".
```

### explain_file.py

```python
SKILL_META = {
    "name": "explain_file",
    "description": "Read a local file and explain its content.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # args is the file path.
    # Read the file (respect WORKSPACE_ROOT). Truncate at 12000 chars.
    # Call agent._stream_response() with an isolated explanation prompt.
    # Return "".
```

### compact.py

```python
SKILL_META = {
    "name": "compact",
    "description": "Summarise conversation, reset context, print summary, delete temp note.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # 1. Build transcript from state["messages"] (skip system and tool messages).
    # 2. Call LLM (non-streaming) with summarisation prompt — 3-8 sentences.
    # 3. If summary is empty: print warning, return without resetting.
    # 4. Save summary to note key "__compact_tmp__".
    # 5. Call commands.dispatch("/reset", state) to clear conversation history.
    # 6. Retrieve and print the summary.
    # 7. Delete the "__compact_tmp__" note.
    # Return "".
```

### business_analyst.py

```python
SKILL_META = {
    "name": "business_analyst",
    "description": "Decompose an idea into core subject, objectives, implied constraints, and missing information.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # args is the idea text; if empty, prompt user via ui.prompt().
    # Spawn agent.run_subagent() with a specialist system prompt (verbose=False).
    # System prompt enforces four fixed sections in order:
    #   ## Core Subject, ## Objectives, ## Implied Constraints, ## Missing Information
    # Return "".
```

### svg_artist.py

```python
SKILL_META = {
    "name": "svg_artist",
    "description": "Generate an SVG file from a natural language description.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # args is the image description; if empty, prompt user via ui.prompt().
    # Spawn agent.run_subagent() with an SVG-specialist system prompt (verbose=True).
    # System prompt rules:
    #   - Produce complete SVG with explicit width/height and matching viewBox.
    #   - All colours as hex or named SVG colours; no currentColor.
    #   - No external files, fonts, or URLs.
    #   - Save via write_file to svg/<descriptive_name>.svg.
    #   - Emit exactly one line: SAVED:<path>.
    # Parse SAVED:<path> from result; print path; offer to open in browser.
    # Return "".
```

### fetch_url.py (skill)

```python
SKILL_META = {
    "name": "fetch_url",
    "description": "Fetches and retrieves the content from a given URL.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    # Validate args matches https?:// with regex.
    # Call tools.dispatch("fetch_web_content", {"url": args}).
    # Return result string.
```

Note: this skill calls `fetch_web_content` by name; the registered tool is `fetch_url`.
Align the dispatch name with the actual registered tool name if this discrepancy causes issues.

---

## Skills System Contract

A skill file must:

1. Define `SKILL_META: dict` with at minimum `"name"`, `"description"`, and `"version"` keys.
2. Define `run(args: str, state: dict, client) -> str`.
3. Not import from `commands` — only `agent`, `tools`, `ui`, stdlib.
4. Use an isolated message list or `agent.run_subagent()` to avoid polluting `state["messages"]`.
5. Return `""` if output was already streamed to stdout; return a non-empty string to have
   the command system print it.

The `/skill` command always reloads the file from disk — no caching. This allows live editing.

---

## Tool Authoring Contract

A tool file must:

1. `import tools` at the top.
2. Define exactly one public function implementing the tool logic.
3. Return a `str` (or a `dict`, which `tools.dispatch()` will JSON-serialise).
4. Define `TOOL_SCHEMA` at module level following the OpenAI function-calling format:
   ```python
   TOOL_SCHEMA = {
       "type": "function",
       "confirm": True | False,      # optional; True requires user approval
       "no_truncate": True | False,  # optional; True bypasses output truncation
       "function": {
           "name": "...",
           "description": "...",
           "parameters": {
               "type": "object",
               "properties": { ... },
               "required": [...],
           },
       },
   }
   ```
5. Call `tools.register(TOOL_SCHEMA, function)` at the bottom of the file.

The `confirm` and `no_truncate` keys are harness-only extensions stripped from schemas
sent to the LLM API.

---

## State Dict Contract

The `state` dict is the single source of truth for all mutable session data. It is passed
by reference into every command handler and `agent.chat()`. Keys must not be deleted;
only modified.

| Key | Type | Description |
|---|---|---|
| `model` | `str` | Model identifier |
| `messages` | `list` | Mutable message history. Modified in-place. |
| `running` | `bool` | Set to `False` by `/exit` to break the REPL loop |
| `client` | `OpenAI` | Shared client instance |
| `usage` | `dict` | Last turn's `{prompt_tokens, completion_tokens, total_tokens}` |
| `context_length` | `int \| None` | Fetched lazily; reset to `None` on model change or `/reset` |
| `session_id` | `str` | Current session file stem |
| `gen_params` | `dict` | Runtime generation overrides (temperature, etc.); initialised from `DEFAULT_GEN_PARAMS` |
| `skip_confirm` | `bool` | Suppress tool confirmation prompts (for non-interactive use) |

---

## ANSI Rendering Rules

| Content type | Code | Visual effect |
|---|---|---|
| Thinking token content | `\033[2;3m` | Dim + italic |
| Thinking box frame (`┌─` / `└─`) | `\033[2m` | Dim |
| Normal assistant text | `\033[96m` | Bright cyan |
| "Assistant:" label in main.py | `\033[96;1m` | Bright cyan + bold |
| Dim summary / info lines | `\033[2m` | Dim |
| Reset | `\033[0m` | — |

The "Assistant:" label is printed in `main.py` with `end=""` and `flush=True` **before**
calling `agent.chat()`. The streaming output continues on the same line.

Thinking blocks are visually framed:
```
  ┌─ thinking ──────────────────────────────────────────
  [thinking content in dim italic]

  └─ done ──────────────────────────────────────────────

[answer in bright cyan]
```

No ANSI output may be wrapped in `prompt_toolkit.patch_stdout` — this causes byte
corruption of ESC sequences on Windows via the Win32 Console API. All terminal output
uses direct `print()` calls.

---

## Security and Safeguard Rules

### Workspace confinement

`write_file` resolves the target path and verifies:
```python
target.startswith(WORKSPACE_ROOT + os.sep) or target == WORKSPACE_ROOT
```
This prevents `../../` path traversal. Any write that escapes is refused with an error string.

### Protected path check

`is_protected_path()` in `tools/__init__.py` is called by both `write_file` and `make_dir`
before any filesystem operation. Three tiers (see config.py section).

### Tool confirmation

Tools with `confirm: True` pause the agentic loop, display the tool name and arguments,
and require the user to type `y` before executing. Any other input cancels with the
CANCELLED sentinel message (see `_execute_tool_with_retry`). The model is instructed
not to claim success when cancelled.

### Generated code validation

Both `/newtool` and `/newskill` validate LLM output before saving:
1. Write to a temp file.
2. `py_compile.compile(tmp_path, doraise=True)` — syntax check.
3. Structural checks (presence of required identifiers).
4. Show code to user and ask confirmation before writing to `tools/` or `skills/`.
5. Apply `sanitize_for_file()` to strip non-ASCII before writing.

### Session file integrity

Writes use `tempfile.mkstemp()` + `os.replace()`. A crash mid-write leaves a `.tmp` file
but never corrupts the `.jsonl` session file.

### Error swallowing policy

`session.save()` and `session.load()` silently swallow all exceptions. Persistence failures
must never surface to the user as crashes. Tool dispatch wraps function calls in
`try/except Exception` and returns an error string — never raises.

### Context compression integrity

`/compress` patches both `config.CONTEXT_PRESSURE_THRESHOLD` and
`agent.CONTEXT_SUMMARY_KEEP_RECENT` (the module-level copy imported at load time)
to force compression. Both are restored in a `finally` block regardless of outcome.
Patching only the `config` attribute is insufficient because `agent.py` imports the
value once at module load time.

### Thinking token security

Thinking content (from `reasoning_content` or tag-delimited blocks) is rendered to the terminal and never appended to `state["messages"]` or included in `answer_chunks`. The model's internal chain-of-thought does not pollute the conversation context.
