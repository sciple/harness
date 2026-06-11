# Harness reference

Local LLM harness — OpenAI-compatible API client (LM Studio / Ollama).
Entry point: `main.py`. Core loop: `agent.py`. Config: `config.py`.

## Key config (config.py)

| Setting | Default | Purpose |
|---|---|---|
| LOCAL_API_BASE | http://127.0.0.1:1234/v1/ | LLM endpoint |
| DEFAULT_MODEL | granite-4.1-8b | Active model |
| AVAILABLE_MODELS | ["granite-4.1-8b"] | Models listed by /model for interactive selection |
| DEFAULT_GEN_PARAMS | max_tokens: 32768 | Sent with every request |
| MAX_TOOL_ROUNDS | 10 | Max consecutive tool calls before forced answer |
| WORKSPACE_ROOT | process cwd at startup | Root for all file operations |
| CONTEXT_PRESSURE_THRESHOLD | 0.80 | Auto-compress when context is this full |
| CONTEXT_SUMMARY_KEEP_RECENT | 4 | Turns preserved during compression |
| TOOL_RETRY_MAX | 2 | Retries after a tool error |
| TOOL_OUTPUT_MAX_CHARS | 16000 | Truncation limit for tool results |
| SESSION_AUTOSAVE | True | Save session after every turn |

## Tools

| Tool | Description |
|---|---|
| write_file | Write text to a file (relative to WORKSPACE_ROOT). Confirm required. |
| append_to_file | Append text to a file. Creates if missing. |
| patch_file | Find-and-replace inside a file. replace_all flag available. |
| read_file_content | Read .txt .py .md .csv .ics files. |
| make_dir | Create a directory (nested). |
| run_python | Execute Python code in a subprocess. Timeout capped at 120s. |
| notes | Key-value store: save_note, get_note, list_notes, delete_note. |
| fetch_url | Fetch a web page and return plain text (HTML stripped, stdlib only). |
| get_current_date | Return current local date and time. |
| create_calendar_event | Generate and save an .ics calendar event file. Confirm required. |
| get_tool_output | Retrieve full (untruncated) output of a previous tool call by key. |
| grep | Regex search across workspace files; returns file:line: matches. |
| glob | Find files by glob pattern (e.g. **/*.py); returns matching paths. |
| read_file_lines | Read a specific line range from a file with line-number prefixes. |
| read_harness_docs | Return the harness reference document (harness_docs.md). no_truncate; auto-called by the model when asked about the harness. |

Protected from writing: main.py, agent.py, config.py, session.py, __init__.py files,
.env files, requirements.txt, sessions/ dir, .git/ dir.

## Commands (type at the You: prompt)

| Command | Purpose |
|---|---|
| /help | List all commands |
| /model [name] | No args: numbered list from AVAILABLE_MODELS in config.py, pick to load; with name: switch directly. Unloads current + loads new on backend (best-effort). |
| /set param value | Set generation param (temperature, top_p, max_tokens, seed) |
| /unset param | Remove a generation param override |
| /params | Show active overrides |
| /reset | Clear conversation (keeps system prompt) |
| /history | Show messages with token estimates |
| /ctx | Show context window usage |
| /drop n or n-m or a,b,c | Remove message(s) by index. Accepts single, range, or comma-separated list. Prints updated history after removal. Pair-aware: prompts before auto-including tool-call partners. |
| /compress | Manually summarise history to free context |
| /pollution | Context health report |
| /system [text] | Show or replace system prompt |
| /sessions | List saved sessions |
| /load id | Resume a saved session |
| /tools | List registered tools |
| /reloadtools [file] | Retry loading tools that failed at startup |
| /loadtool path | Load a tool from a .py file at runtime |
| /newtool desc | Ask LLM to write and load a new tool |
| /skills | List available skills |
| /skill name [args] | Run a skill |
| /newskill desc | Ask LLM to write a new skill |
| /subagent task | Spawn an isolated subagent for a focused task |
| /calendar [y] [m] | Show a mini calendar |
| /time | Show current date/time |
| /open url | Open URL in browser |
| /cls | Clear terminal |
| /exit | Quit |

## Skills (slash commands with LLM logic)

| Skill | Purpose |
|---|---|
| summarise | Summarise the current conversation without modifying history |
| explain_file | Read a local file and provide an explanation |
| compact | Summarise conversation, reset context, print summary |
| distill | Rebuild context as a goal-anchored structured block; user approves before context is replaced |
| business_analyst | Decompose an idea into subject, objectives, constraints, and unknowns via subagent |
| svg_artist | Generate an SVG file from a natural language description via subagent |
| fetch_url | Fetch a URL via skill (wraps the fetch_url tool) |
| translate_fr | Translate a given text (or the last user message) into French |

## Architecture

- `main.py` — REPL loop, command dispatch, session save/load
- `agent.py` — `chat()` agentic loop, `_stream_or_tools()` streaming, `run_subagent()`
- `config.py` — all tuneable constants
- `session.py` — JSONL session persistence
- `commands/__init__.py` — all slash commands
- `tools/__init__.py` — tool registry, dispatch, truncation, protection checks
- `tools/*.py` — one file per tool, each calls `tools.register()` at import
- `skills/*.py` — one file per skill; loaded dynamically by `commands/__init__.py` on `/skill` invocation
- `ui.py` — prompt_toolkit REPL input, toolbar, syntax highlight
