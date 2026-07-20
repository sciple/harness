# commands/__init__.py — Slash-command registry and built-in commands
#
# How to add a command:
#   1. Define a function with signature: fn(args: str, state: dict) -> str | None
#      - args: everything after the command name (may be empty string)
#      - state: mutable session dict
#      - return a string to print, or None for no output
#   2. Call register("/name", fn, help="one-line description")

import importlib.util
import itertools
import json
import os
import py_compile
import re
import sys
import tempfile
import threading
import time
import unicodedata

import tools as tool_registry
import session as session_mod
from config import ALLOWED_GEN_PARAMS, AVAILABLE_MODELS, SKILLS_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHAR_REPLACEMENTS = str.maketrans({
    "\u2018": "'",  "\u2019": "'",  "\u201c": '"',  "\u201d": '"',
    "\u2014": "--", "\u2013": "-",  "\u2026": "...", "\u00a0": " ",
    "\u2212": "-",
})


def sanitize_for_file(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_CHAR_REPLACEMENTS)
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text


def _spinner(label: str, stop_event: threading.Event) -> None:
    frames = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
    while not stop_event.is_set():
        print(f"\r  {next(frames)} {label}", end="", flush=True)
        time.sleep(0.08)
    print("\r" + " " * (len(label) + 6) + "\r", end="", flush=True)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_commands: dict[str, tuple[callable, str]] = {}


def register(name: str, fn: callable, help: str = "") -> None:
    _commands[name.lstrip("/")] = (fn, help)


def dispatch(raw: str, state: dict) -> tuple[bool, str | None]:
    raw = raw.strip()
    if not raw.startswith("/"):
        return False, None
    parts = raw[1:].split(None, 1)
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    if name not in _commands:
        return True, f"Unknown command '/{name}'. Type /help for a list of commands."
    fn, _ = _commands[name]
    return True, fn(args, state)

# ---------------------------------------------------------------------------
# Built-in commands
# ---------------------------------------------------------------------------

def _cmd_help(args: str, state: dict) -> str:
    lines = ["Available commands:"]
    for name, (_, help_text) in sorted(_commands.items()):
        lines.append(f"  /{name:<14} {help_text}")
    return "\n".join(lines)


def _cmd_reset(args: str, state: dict) -> str:
    msgs = state["messages"]
    system = [m for m in msgs if (
        m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
    ) == "system"]
    msgs.clear()
    msgs.extend(system)
    state["usage"] = {}
    state["context_length"] = None
    return "Conversation reset."


def _cmd_model(args: str, state: dict) -> str:
    import agent as agent_mod

    current = state["model"]

    # --- No args: show numbered list and let user pick ---
    if not args.strip():
        if not AVAILABLE_MODELS:
            return f"Current model: {current}\n(AVAILABLE_MODELS list in config.py is empty.)"

        lines = ["Available models (* = active):"]
        for i, name in enumerate(AVAILABLE_MODELS, 1):
            marker = " *" if name == current else ""
            lines.append(f"  [{i}] {name}{marker}")
        print("\n".join(lines))

        try:
            choice = input("\n  Select model number (or Enter to cancel): ").strip()
        except (EOFError, KeyboardInterrupt):
            return "Cancelled."

        if not choice:
            return "Cancelled."
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(AVAILABLE_MODELS)):
                raise ValueError
        except ValueError:
            return f"Invalid choice: '{choice}'"

        new_model = AVAILABLE_MODELS[idx]
        if new_model == current:
            return f"Already using {current}."
    else:
        new_model = args.strip()
        if new_model == current:
            return f"Already using {current}."

    # --- Unload previous model, then load new one (both best-effort with spinner) ---
    stop = threading.Event()
    t = threading.Thread(target=_spinner,
                         args=(f"Unloading {current}...", stop), daemon=True)
    t.start()
    unloaded, umsg = agent_mod.unload_model(state["client"], current)
    stop.set(); t.join()

    stop = threading.Event()
    t = threading.Thread(target=_spinner,
                         args=(f"Loading {new_model}...", stop), daemon=True)
    t.start()
    loaded, lmsg = agent_mod.load_model(state["client"], new_model)
    stop.set(); t.join()

    state["model"] = new_model
    state["context_length"] = None
    import ui as ui_mod
    ui_mod.toolbar_state["model"] = new_model

    notes = []
    if not unloaded:
        notes.append(f"could not unload {current} — unload it manually in LM Studio ({umsg})")
    if not loaded:
        notes.append(f"explicit load not supported — {new_model} loads on next chat request ({lmsg})")

    result = f"Model switched to: {new_model}"
    if notes:
        result += "\n  \033[2m(" + "; ".join(notes) + ")\033[0m"
    return result


def _cmd_tools(args: str, state: dict) -> str:
    names = tool_registry.list_tools()
    lines = []
    if names:
        lines.append("Registered tools:")
        for n in names:
            confirm_tag = " [confirm]" if tool_registry.requires_confirmation(n) else ""
            lines.append(f"  - {n}{confirm_tag}")
    else:
        lines.append("No tools registered.")

    failed = tool_registry.list_failed_tools()
    if failed:
        lines.append("\nFailed to load:")
        for filename, err in failed.items():
            lines.append(f"  - {filename}: {err}")

    return "\n".join(lines)


def _cmd_reloadtools(args: str, state: dict) -> str:
    specific = args.strip() or None
    results = tool_registry.reload_failed(specific)
    if not results:
        return "No failed tools to reload."
    lines = []
    for filename, status in results.items():
        mark = "OK" if status == "ok" else f"FAIL: {status}"
        lines.append(f"  {filename}: {mark}")
    return "\n".join(lines)




def _cmd_exit(args: str, state: dict) -> None:
    state["running"] = False
    return None


# --- /time ---

def _cmd_time(args: str, state: dict) -> str:
    from datetime import datetime, timezone
    now_utc   = datetime.now(timezone.utc)
    now_local = datetime.now().astimezone()
    return (
        f"  UTC   : {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"  Local : {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )


# --- /system ---

def _cmd_system(args: str, state: dict) -> str:
    msgs = state["messages"]
    # Find the first system message
    sys_idx = next(
        (i for i, m in enumerate(msgs)
         if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "system"),
        None,
    )

    if not args.strip():
        # Show current system prompt
        if sys_idx is None:
            return "No system prompt is set."
        content = (msgs[sys_idx].get("content") if isinstance(msgs[sys_idx], dict)
                   else getattr(msgs[sys_idx], "content", ""))
        return f"System prompt:\n\n{content}"

    # Replace (or insert) the system prompt
    new_prompt = args.strip()
    if sys_idx is not None:
        msgs[sys_idx] = {"role": "system", "content": new_prompt}
    else:
        msgs.insert(0, {"role": "system", "content": new_prompt})
    return "System prompt updated."


# --- /compress ---

def _cmd_compress(args: str, state: dict) -> str:
    import agent as agent_mod

    usage = state.get("usage", {})
    if not usage:
        # Build a rough usage estimate from message token counts so compression
        # can run even before the first LLM turn
        total = sum(_msg_token_estimate(m) for m in state["messages"])
        usage = {"prompt_tokens": total, "completion_tokens": 0, "total_tokens": total}

    if state.get("context_length") is None:
        state["context_length"] = agent_mod.get_context_length(
            state["client"], state["model"]
        )

    # Temporarily lower the threshold to 0 and keep window to 1 pair so
    # _maybe_compress always fires and has something to work with.
    import config
    original_threshold = config.CONTEXT_PRESSURE_THRESHOLD
    original_keep      = config.CONTEXT_SUMMARY_KEEP_RECENT
    config.CONTEXT_PRESSURE_THRESHOLD  = 0.0
    config.CONTEXT_SUMMARY_KEEP_RECENT = 1
    # Also patch agent module's imported copy (imported as a value at load time)
    original_agent_keep = agent_mod.CONTEXT_SUMMARY_KEEP_RECENT
    agent_mod.CONTEXT_SUMMARY_KEEP_RECENT = 1
    try:
        compressed = agent_mod._maybe_compress(
            state["client"],
            state["model"],
            state["messages"],
            usage,
            state.get("context_length") or 999_999,
            state.get("gen_params") or None,
        )
    finally:
        config.CONTEXT_PRESSURE_THRESHOLD  = original_threshold
        config.CONTEXT_SUMMARY_KEEP_RECENT = original_keep
        agent_mod.CONTEXT_SUMMARY_KEEP_RECENT = original_agent_keep

    if not compressed:
        return "Nothing to compress (not enough messages outside the recent window)."
    return ""   # _maybe_compress already printed the compression notice


# --- /ctx ---

def _cmd_ctx(args: str, state: dict) -> str:
    import agent as agent_mod
    usage = state.get("usage", {})
    if not usage:
        return "No usage data yet — send a message first."
    prompt_tokens     = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens      = usage.get("total_tokens", prompt_tokens + completion_tokens)
    if state.get("context_length") is None:
        state["context_length"] = agent_mod.get_context_length(state["client"], state["model"])
    ctx_len = state.get("context_length")
    lines = [
        f"  Prompt tokens     : {prompt_tokens:>7,}",
        f"  Completion tokens : {completion_tokens:>7,}",
        f"  Total tokens      : {total_tokens:>7,}",
    ]
    if ctx_len:
        pct = total_tokens / ctx_len * 100
        bar_width = 30
        filled = int(bar_width * total_tokens / ctx_len)
        bar = "█" * filled + "░" * (bar_width - filled)
        lines += [
            f"  Context window    : {ctx_len:>7,}",
            f"  Usage             : {pct:>6.1f}%  [{bar}]",
        ]
    else:
        lines.append("  Context window    : unknown (model info not available)")
    return "\n".join(lines)


# --- /set and /params ---

def _cmd_set(args: str, state: dict) -> str:
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        # No arguments — show current params just like /params
        return _cmd_params("", state)
    param, raw_value = parts[0].lower(), parts[1]
    if param not in ALLOWED_GEN_PARAMS:
        allowed = ", ".join(ALLOWED_GEN_PARAMS.keys())
        return f"Unknown parameter '{param}'. Allowed: {allowed}"
    cast = ALLOWED_GEN_PARAMS[param]
    try:
        value = cast(raw_value)
    except (ValueError, TypeError):
        return f"Invalid value '{raw_value}' for '{param}' (expected {cast.__name__})"
    # Basic range guards
    if param == "temperature" and not (0.0 <= value <= 2.0):
        return "temperature must be between 0.0 and 2.0"
    if param == "top_p" and not (0.0 <= value <= 1.0):
        return "top_p must be between 0.0 and 1.0"
    if param == "max_tokens" and value <= 0:
        return "max_tokens must be > 0"
    state["gen_params"][param] = value
    return f"Set {param} = {value}"


def _cmd_params(args: str, state: dict) -> str:
    gp = state.get("gen_params", {})
    if not gp:
        return "No generation parameters overridden (using model defaults)."
    lines = ["Active generation parameter overrides:"]
    for k, v in gp.items():
        lines.append(f"  {k} = {v}")
    return "\n".join(lines)


def _cmd_unset(args: str, state: dict) -> str:
    param = args.strip().lower()
    if not param:
        return "Usage: /unset <param>"
    if param not in state.get("gen_params", {}):
        return f"'{param}' is not currently set."
    del state["gen_params"][param]
    return f"Unset {param} (reverted to model default)"


# --- /sessions and /load ---

def _cmd_sessions(args: str, state: dict) -> str:
    sessions = session_mod.list_sessions()
    if not sessions:
        return "No saved sessions found."
    lines = [f"  {'ID':<18} {'Messages':>8}  {'Saved'}"]
    lines.append("  " + "-" * 50)
    for sid, count, ts in sessions:
        marker = " *" if sid == state.get("session_id") else ""
        lines.append(f"  {sid:<18} {count:>8}  {ts}{marker}")
    return "\n".join(lines)


def _cmd_load(args: str, state: dict) -> str:
    session_id = args.strip()
    if not session_id:
        return "Usage: /load <session-id>"
    messages = session_mod.load(session_id)
    if messages is None:
        return f"Session '{session_id}' not found."
    state["messages"].clear()
    state["messages"].extend(messages)
    state["session_id"] = session_id
    return f"Loaded session '{session_id}' ({len(messages)} messages)."


# --- /loadtool ---

def _load_tool_from_path(path: str) -> tuple[bool, str]:
    before = set(tool_registry.list_tools())
    module_name = f"_dynamic_tool_{os.path.splitext(os.path.basename(path))[0]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        del sys.modules[module_name]
        return False, f"Error loading '{path}': {e}"
    after = set(tool_registry.list_tools())
    new_tools = after - before
    if new_tools:
        return True, f"Registered tool(s): {', '.join(sorted(new_tools))}"
    return True, "Loaded (no new tools registered — did you call tools.register()?)"


def _cmd_loadtool(args: str, state: dict) -> str:
    path = args.strip()
    if not path:
        return "Usage: /loadtool <path/to/tool_file.py>"
    path = os.path.expanduser(os.path.expandvars(path))
    if not os.path.isfile(path):
        return f"File not found: {path}"
    if not path.endswith(".py"):
        return f"Expected a .py file, got: {path}"
    _, msg = _load_tool_from_path(path)
    return f"Loaded {path}\n{msg}"


# --- /newtool (with validation) ---

_TOOL_TEMPLATE = """\
You are a tool-writing assistant for a local LLM harness.
Generate a single self-contained Python file that implements the tool described below.

STRICT RULES:
1. The file must import `tools` at the top.
2. Define exactly one public function that does the work.
3. Define a TOOL_SCHEMA dict in the OpenAI function-calling format.
4. End the file with `tools.register(TOOL_SCHEMA, <function_name>)`.
5. Output ONLY the raw Python code. Do NOT include any explanation, commentary, \
bullet points, or markdown. The very first character of your response must be the \
letter 'i' (from `import tools`).

EXAMPLE STRUCTURE:
import tools

def my_tool(param: str) -> str:
    ...
    return result

TOOL_SCHEMA = {{
    "type": "function",
    "function": {{
        "name": "my_tool",
        "description": "...",
        "parameters": {{
            "type": "object",
            "properties": {{
                "param": {{"type": "string", "description": "..."}}
            }},
            "required": ["param"],
        }},
    }},
}}

tools.register(TOOL_SCHEMA, my_tool)

NOW WRITE THE TOOL FOR THIS DESCRIPTION:
{description}
"""

_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "tools")


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from ") or stripped.startswith("def "):
            return "\n".join(lines[i:]).strip()
    return text.strip()


def _validate_tool_code(code: str) -> tuple[bool, str]:
    """
    Check the generated code for syntax errors and that tools.register() is called.
    Returns (ok, error_message).
    """
    # Syntax check via py_compile
    fd, tmp_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as e:
        os.unlink(tmp_path)
        return False, f"Syntax error: {e}"
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return False, f"Validation error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if "tools.register(" not in code:
        return False, "tools.register() not found — tool would not self-register."

    return True, ""


def _cmd_newtool(args: str, state: dict) -> str:
    description = args.strip()
    if not description:
        return "Usage: /newtool <description of what the tool should do>"

    client = state.get("client")
    if client is None:
        return "Error: LLM client not available in session state."

    max_retries = 3
    last_error = ""

    for attempt in range(1, max_retries + 1):
        prompt = _TOOL_TEMPLATE.format(description=description)
        if last_error:
            prompt += f"\n\nThe previous attempt had this error — fix it:\n{last_error}"

        stop = threading.Event()
        spinner_thread = threading.Thread(
            target=_spinner,
            args=(f"Generating tool (attempt {attempt}/{max_retries})...", stop),
            daemon=True,
        )
        spinner_thread.start()
        try:
            response = client.chat.completions.create(
                model=state["model"],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            stop.set()
            spinner_thread.join()
            return f"Error calling model: {e}"
        finally:
            stop.set()
            spinner_thread.join()

        code = _extract_code(response.choices[0].message.content or "")
        if not code:
            last_error = "Model returned an empty response."
            continue

        ok, err = _validate_tool_code(code)
        if not ok:
            last_error = err
            print(f"  [newtool] Validation failed (attempt {attempt}): {err}")
            continue

        # Validation passed — show code and ask to save
        name_match = re.search(r"^def (\w+)", code, re.MULTILINE)
        filename = (name_match.group(1) if name_match else "generated_tool") + ".py"
        save_path = os.path.normpath(os.path.join(_TOOLS_DIR, filename))

        print(f"\n  [newtool] Saving to {save_path}")
        print("  [newtool] Generated code:\n")
        print(code)
        print()

        confirm = input("  Save and load this tool? [y/N] ").strip().lower()
        if confirm != "y":
            return "Aborted — tool was not saved."

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(sanitize_for_file(code) + "\n")
        except Exception as e:
            return f"Error saving file: {e}"

        ok2, msg = _load_tool_from_path(save_path)
        return f"Saved to {save_path}\n{msg}"

    return f"Failed after {max_retries} attempts. Last error: {last_error}"


# --- /skill and /skills ---

_SKILL_TEMPLATE = """\
You are a skill-writing assistant for a local LLM harness.
Generate a single self-contained Python file that implements the skill described below.

A skill is a higher-level behaviour that can call the LLM, use tools, and interact with
the session. It is invoked by the user via: /skill <name> [args]

STRICT RULES:
1. The file must import `agent` at the top (and any other stdlib modules needed).
2. Define a SKILL_META dict with keys: name (str), description (str), version (str).
3. Define a `run(args: str, state: dict, client) -> str` function.
   - `args`: everything the user typed after the skill name (may be empty)
   - `state`: the session dict — keys include: model (str), messages (list),
     gen_params (dict), client (OpenAI client)
   - `client`: the OpenAI-compatible client (same as state["client"])
   - return a string to print, or "" for no extra output
4. To call the LLM and stream output, use:
   text, _ = agent._stream_response(client, state["model"], messages,
                                    gen_params=state.get("gen_params") or None)
5. To call a registered tool, use:
   import tools; result = tools.dispatch("tool_name", {{"arg": value}})
6. Do NOT append to state["messages"] unless you explicitly want the skill's
   work to become part of the main conversation history.
7. Output ONLY the raw Python code. No explanation, no markdown fences.
   The very first character must be the letter 'i' (from `import agent`).

EXAMPLE STRUCTURE:
import agent

SKILL_META = {{
    "name":        "my_skill",
    "description": "What this skill does.",
    "version":     "1.0",
}}

def run(args: str, state: dict, client) -> str:
    if not args.strip():
        return "Usage: /skill my_skill <something>"
    messages = [{{"role": "user", "content": f"Do something with: {{args}}"}}]
    print("\\nWorking...\\n")
    agent._stream_response(client, state["model"], messages,
                           gen_params=state.get("gen_params") or None)
    return ""

NOW WRITE THE SKILL FOR THIS DESCRIPTION:
{description}
"""


def _validate_skill_code(code: str) -> tuple[bool, str]:
    """Syntax-check the generated skill and verify required structure."""
    fd, tmp_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as e:
        try: os.unlink(tmp_path)
        except Exception: pass
        return False, f"Syntax error: {e}"
    except Exception as e:
        try: os.unlink(tmp_path)
        except Exception: pass
        return False, f"Validation error: {e}"
    finally:
        try: os.unlink(tmp_path)
        except Exception: pass

    if "SKILL_META" not in code:
        return False, "SKILL_META dict not found."
    if "def run(" not in code:
        return False, "run() function not found."
    return True, ""


def _cmd_newskill(args: str, state: dict) -> str:
    description = args.strip()
    if not description:
        return "Usage: /newskill <description of what the skill should do>"

    client = state.get("client")
    if client is None:
        return "Error: LLM client not available in session state."

    os.makedirs(SKILLS_DIR, exist_ok=True)
    max_retries = 3
    last_error = ""

    for attempt in range(1, max_retries + 1):
        prompt = _SKILL_TEMPLATE.format(description=description)
        if last_error:
            prompt += f"\n\nThe previous attempt had this error — fix it:\n{last_error}"

        stop = threading.Event()
        spinner_thread = threading.Thread(
            target=_spinner,
            args=(f"Generating skill (attempt {attempt}/{max_retries})...", stop),
            daemon=True,
        )
        spinner_thread.start()
        try:
            response = client.chat.completions.create(
                model=state["model"],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            stop.set()
            spinner_thread.join()
            return f"Error calling model: {e}"
        finally:
            stop.set()
            spinner_thread.join()

        code = _extract_code(response.choices[0].message.content or "")
        if not code:
            last_error = "Model returned an empty response."
            continue

        ok, err = _validate_skill_code(code)
        if not ok:
            last_error = err
            print(f"  [newskill] Validation failed (attempt {attempt}): {err}")
            continue

        # Extract skill name from SKILL_META or fall back to function name
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', code)
        skill_name = name_match.group(1) if name_match else "generated_skill"
        filename = skill_name.replace(" ", "_") + ".py"
        save_path = os.path.normpath(os.path.join(SKILLS_DIR, filename))

        print(f"\n  [newskill] Saving to {save_path}")
        print("  [newskill] Generated code:\n")
        print(code)
        print()

        confirm = input("  Save this skill? [y/N] ").strip().lower()
        if confirm != "y":
            return "Aborted — skill was not saved."

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(sanitize_for_file(code) + "\n")
        except Exception as e:
            return f"Error saving file: {e}"

        return f"Saved to {save_path}\nRun it with: /skill {skill_name}"

    return f"Failed after {max_retries} attempts. Last error: {last_error}"


def _cmd_skills(args: str, state: dict) -> str:
    if not os.path.isdir(SKILLS_DIR):
        return "No skills directory found. Create a 'skills/' folder and add skill files."
    entries = []
    for filename in sorted(os.listdir(SKILLS_DIR)):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        path = os.path.join(SKILLS_DIR, filename)
        try:
            spec = importlib.util.spec_from_file_location(f"_skill_meta_{filename}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            meta = getattr(mod, "SKILL_META", {})
            name = meta.get("name", filename[:-3])
            desc = meta.get("description", "(no description)")
            ver  = meta.get("version", "")
            entries.append(f"  {name:<18} {ver:<6} {desc}")
        except Exception as e:
            entries.append(f"  {filename:<18}        (error: {e})")
    if not entries:
        return "No skills found in skills/ directory."
    return "Available skills:\n" + "\n".join(entries)


def _cmd_skill(args: str, state: dict) -> str:
    parts = args.strip().split(None, 1)
    if not parts:
        return "Usage: /skill <name> [args]"
    skill_name = parts[0]
    skill_args = parts[1] if len(parts) > 1 else ""

    if not os.path.isdir(SKILLS_DIR):
        return "No skills directory found."

    path = os.path.join(SKILLS_DIR, f"{skill_name}.py")
    if not os.path.isfile(path):
        return f"Skill '{skill_name}' not found in {SKILLS_DIR}."

    # Always reload from disk (in case the file was edited)
    module_name = f"_skill_{skill_name}_{int(time.time())}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return f"Error loading skill '{skill_name}': {e}"

    if not hasattr(module, "SKILL_META"):
        return f"Skill '{skill_name}' is missing SKILL_META dict."
    if not hasattr(module, "run") or not callable(module.run):
        return f"Skill '{skill_name}' is missing a run(args, state, client) function."

    try:
        result = module.run(skill_args, state, state["client"])
        return str(result) if result is not None else ""
    except Exception as e:
        return f"Skill '{skill_name}' raised an error: {e}"


# ---------------------------------------------------------------------------
# Context management helpers
# ---------------------------------------------------------------------------

# Mutable resources whose tool results can go stale
_MUTABLE_TOOLS = {"read_file_content", "make_dir", "write_file"}

# How many turns back a tool result is considered stale
_STALE_TURNS = 5


def _estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 chars per token (GPT-style).
    Used when the backend does not expose a tokenize endpoint.
    """
    return max(1, len(text) // 4)


def _msg_token_estimate(m) -> int:
    """Estimate the token cost of a single message object or dict."""
    is_dict = isinstance(m, dict)
    parts = []

    content = (m.get("content") if is_dict else getattr(m, "content", None)) or ""
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    parts.append(content)

    tool_calls = (m.get("tool_calls") if is_dict else getattr(m, "tool_calls", None))
    if tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict):
                parts.append(tc.get("function", {}).get("arguments", ""))
            else:
                parts.append(getattr(tc.function, "arguments", ""))

    return _estimate_tokens(" ".join(parts)) + 4  # +4 for role/metadata overhead


def _get_role(m) -> str:
    is_dict = isinstance(m, dict)
    return ((m.get("role") if is_dict else getattr(m, "role", "?")) or "?").lower()


def _get_content(m) -> str:
    is_dict = isinstance(m, dict)
    content = (m.get("content") if is_dict else getattr(m, "content", None)) or ""
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return content


def _get_tool_calls(m):
    is_dict = isinstance(m, dict)
    return (m.get("tool_calls") if is_dict else getattr(m, "tool_calls", None))


# ---------------------------------------------------------------------------
# Improved /history with token cost per message
# ---------------------------------------------------------------------------

def _cmd_history(args: str, state: dict) -> str:
    msgs = state["messages"]
    if not msgs:
        return "No conversation history."

    _DIM = "\033[2m"
    _RST = "\033[0m"
    _YLW = "\033[33m"

    lines = []
    total_est = 0
    for i, m in enumerate(msgs):
        role = _get_role(m).upper()
        content = _get_content(m)
        tool_calls = _get_tool_calls(m)
        tok = _msg_token_estimate(m)
        total_est += tok
        tok_label = f"{_DIM}[~{tok} tok]{_RST}"

        if tool_calls:
            call_parts = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    name = tc.get("function", {}).get("name", "?")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                else:
                    name = tc.function.name
                    args_str = tc.function.arguments
                call_parts.append(f"{name}({args_str})")
            lines.append(f"{_YLW}[{i:2}]{_RST} [{role}] {tok_label} <tool calls: {', '.join(call_parts)}>")
            if content:
                lines.append(f"       {content}")
            continue

        preview = content[:160].replace("\n", " ")
        if len(content) > 160:
            preview += "…"
        lines.append(f"{_YLW}[{i:2}]{_RST} [{role}] {tok_label} {preview}")

    lines.append(f"\n{_DIM}Total messages: {len(msgs)}  |  Estimated tokens: ~{total_est:,}{_RST}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /pollution — context health report
# ---------------------------------------------------------------------------

def _cmd_pollution(args: str, state: dict) -> str:
    msgs = state["messages"]
    if not msgs:
        return "No conversation history."

    _DIM  = "\033[2m"
    _RST  = "\033[0m"
    _RED  = "\033[91m"
    _YLW  = "\033[33m"
    _GRN  = "\033[32m"

    total_msgs   = len(msgs)
    total_tokens = sum(_msg_token_estimate(m) for m in msgs)

    # Count by role
    role_counts: dict[str, int] = {}
    role_tokens: dict[str, int] = {}
    for m in msgs:
        r = _get_role(m)
        role_counts[r] = role_counts.get(r, 0) + 1
        role_tokens[r] = role_tokens.get(r, 0) + _msg_token_estimate(m)

    # Tool scaffolding: assistant tool-call messages + tool result messages
    tool_call_msgs  = sum(1 for m in msgs if _get_tool_calls(m))
    tool_result_msgs = role_counts.get("tool", 0)
    scaffolding_msgs = tool_call_msgs + tool_result_msgs
    scaffolding_pct  = scaffolding_msgs / total_msgs * 100 if total_msgs else 0

    # Longest single message
    msg_sizes = [(i, _msg_token_estimate(m), _get_role(m)) for i, m in enumerate(msgs)]
    largest = max(msg_sizes, key=lambda x: x[1])

    # Error/retry noise: tool results that start with "Error:"
    error_results = [
        (i, _get_content(m)[:80])
        for i, m in enumerate(msgs)
        if _get_role(m) == "tool" and _get_content(m).startswith("Error:")
    ]

    # Stale tool results: tool results from mutable tools more than _STALE_TURNS ago
    stale = []
    for i, m in enumerate(msgs):
        if _get_role(m) != "tool":
            continue
        turns_ago = total_msgs - 1 - i
        if turns_ago < _STALE_TURNS:
            continue
        # Find the tool name from the preceding assistant tool-call message
        tool_name = "unknown"
        for j in range(i - 1, -1, -1):
            tc = _get_tool_calls(msgs[j])
            if tc:
                t = tc[0]
                tool_name = (t.get("function", {}).get("name") if isinstance(t, dict)
                             else t.function.name) or "unknown"
                break
        if tool_name in _MUTABLE_TOOLS:
            stale.append((i, tool_name, turns_ago))

    # Repeated tool calls (same tool called 3+ times)
    tool_call_names: list[str] = []
    for m in msgs:
        tc = _get_tool_calls(m)
        if tc:
            for t in tc:
                name = (t.get("function", {}).get("name") if isinstance(t, dict)
                        else t.function.name) or "?"
                tool_call_names.append(name)
    from collections import Counter
    repeated = {n: c for n, c in Counter(tool_call_names).items() if c >= 3}

    # Context window pressure
    ctx_len = state.get("context_length")
    pressure_line = ""
    if ctx_len:
        pct = total_tokens / ctx_len * 100
        color = _RED if pct > 75 else _YLW if pct > 50 else _GRN
        pressure_line = f"  Context pressure  : {color}{pct:.1f}% of {ctx_len:,} tokens{_RST}"

    # Build report
    lines = ["Context Pollution Report", "=" * 40]
    lines.append(f"  Total messages    : {total_msgs}")
    lines.append(f"  Estimated tokens  : ~{total_tokens:,}")
    if pressure_line:
        lines.append(pressure_line)

    lines.append("\nToken budget by role:")
    for r, tok in sorted(role_tokens.items(), key=lambda x: -x[1]):
        pct = tok / total_tokens * 100 if total_tokens else 0
        bar = "█" * int(pct / 5)
        lines.append(f"  {r:<12} ~{tok:>5,} tok  {pct:5.1f}%  {bar}")

    lines.append(f"\nTool scaffolding  : {scaffolding_msgs} messages "
                 f"({scaffolding_pct:.0f}% of history)")

    if error_results:
        lines.append(f"\n{_RED}Error results in context ({len(error_results)}):{_RST}")
        for idx, preview in error_results:
            lines.append(f"  [{idx:2}] {preview}")

    if stale:
        lines.append(f"\n{_YLW}Potentially stale tool results:{_RST}")
        for idx, tool_name, turns_ago in stale:
            lines.append(f"  [{idx:2}] {tool_name}  ({turns_ago} turns ago)")

    if repeated:
        lines.append(f"\n{_YLW}Repeatedly called tools (possible loop):{_RST}")
        for name, count in repeated.items():
            lines.append(f"  {name}: called {count}x")

    largest_color = _RED if largest[1] > 800 else _YLW if largest[1] > 300 else _GRN
    lines.append(f"\nLargest message   : [{largest[0]}] {largest[2].upper()} "
                 f"~{largest_color}{largest[1]:,} tok{_RST}")

    # Suggestions
    suggestions = []
    if scaffolding_pct > 40:
        suggestions.append("High tool scaffolding — consider /reset after completing a task.")
    if stale:
        suggestions.append(f"Drop stale tool results with /drop {stale[0][0]} to free context.")
    if error_results:
        suggestions.append("Error results are polluting context — use /drop to remove them.")
    if ctx_len and total_tokens / ctx_len > 0.75:
        suggestions.append("Context >75% full — auto-compression will trigger soon.")
    if suggestions:
        lines.append(f"\n{_DIM}Suggestions:{_RST}")
        for s in suggestions:
            lines.append(f"  • {s}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /drop — remove a message by index (guards tool-call/result pairs)
# ---------------------------------------------------------------------------

def _cmd_drop(args: str, state: dict) -> str:
    msgs = state["messages"]

    if not args.strip():
        return (
            "Usage: /drop <n>  or  /drop <start>-<end>  or  /drop <a>,<b>,<c>\n"
            "Use /history to see message indices."
        )

    # Parse single index, range (n-m), or comma-separated list (a,b,c)
    try:
        if "," in args:
            indices = [int(p.strip()) for p in args.split(",")]
        elif "-" in args:
            parts = args.strip().split("-", 1)
            start, end = int(parts[0]), int(parts[1])
            indices = list(range(start, end + 1))
        else:
            indices = [int(args.strip())]
        indices = list(dict.fromkeys(indices))  # deduplicate, preserve order
    except ValueError:
        return f"Invalid index: '{args.strip()}'"

    # Validate bounds
    for idx in indices:
        if idx < 0 or idx >= len(msgs):
            return f"Index {idx} out of range (0–{len(msgs) - 1})."

    # Block dropping the system prompt (index 0 if role==system)
    if 0 in indices:
        role = _get_role(msgs[0])
        if role == "system":
            return "Cannot drop the system prompt (index 0)."

    # Detect and warn about breaking tool-call/result pairs
    # A tool-call message (assistant with tool_calls) must be followed by
    # one tool result per call. Dropping one without the other corrupts the API.
    expanded = set(indices)
    warnings = []

    for idx in list(expanded):
        m = msgs[idx]
        role = _get_role(m)

        # Dropping an assistant tool-call message → must also drop its results
        if role == "assistant" and _get_tool_calls(m):
            tcs = _get_tool_calls(m)
            n_calls = len(tcs)
            # Results immediately follow
            for offset in range(1, n_calls + 1):
                result_idx = idx + offset
                if result_idx < len(msgs) and _get_role(msgs[result_idx]) == "tool":
                    if result_idx not in expanded:
                        expanded.add(result_idx)
                        warnings.append(
                            f"  Auto-including [{result_idx}] (tool result paired with [{idx}])"
                        )

        # Dropping a tool result → must also drop its paired assistant tool-call
        if role == "tool":
            for j in range(idx - 1, -1, -1):
                if _get_tool_calls(msgs[j]):
                    if j not in expanded:
                        expanded.add(j)
                        warnings.append(
                            f"  Auto-including [{j}] (tool-call paired with result [{idx}])"
                        )
                    break

    final_indices = sorted(expanded, reverse=True)  # remove highest first

    # Confirm if auto-expansion added messages beyond what the user requested
    if len(final_indices) > len(indices):
        if warnings:
            print("\n".join(warnings))
        preview = ", ".join(str(i) for i in sorted(final_indices))
        confirm = input(
            f"  Drop messages [{preview}]? [y=all / n=requested only / a=abort] "
        ).strip().lower()
        if confirm == "a":
            return "Aborted."
        if confirm != "y":
            # Drop only what the user originally asked for
            final_indices = sorted(indices, reverse=True)

    removed = []
    for idx in final_indices:
        role = _get_role(msgs[idx])
        preview = _get_content(msgs[idx])[:60].replace("\n", " ")
        removed.append(f"  [{idx}] {role.upper()}  {preview}")
        del msgs[idx]

    return "Dropped:\n" + "\n".join(removed) + "\n\n" + _cmd_history("", state)


# ---------------------------------------------------------------------------
# /open — open a URL in the default browser
# ---------------------------------------------------------------------------

def _cmd_open(args: str, state: dict) -> str:
    import webbrowser
    url = args.strip()
    if not url:
        return "Usage: /open <url>"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    opened = webbrowser.open(url)
    if opened:
        return f"Opened {url}"
    return f"Could not open browser for {url}"


# ---------------------------------------------------------------------------
# /cls — clear the terminal screen
# ---------------------------------------------------------------------------

def _cmd_cls(args: str, state: dict) -> None:
    from prompt_toolkit.shortcuts import clear
    import main as main_mod
    clear()
    main_mod.print_banner(state["model"], "", state["session_id"])


# ---------------------------------------------------------------------------
# /calendar — mini calendar with today highlighted
# ---------------------------------------------------------------------------

def _cmd_calendar(args: str, state: dict) -> str:
    import calendar
    from datetime import date

    today = date.today()
    # Optional: /calendar 2026 3  or  /calendar 3  (month only, current year)
    parts = args.strip().split()
    try:
        if len(parts) == 2:
            year, month = int(parts[0]), int(parts[1])
        elif len(parts) == 1:
            year, month = today.year, int(parts[0])
        else:
            year, month = today.year, today.month
    except ValueError:
        return "Usage: /calendar [month] or /calendar [year] [month]"

    if not (1 <= month <= 12):
        return "Month must be between 1 and 12."

    _BOLD_GREEN = "\033[1;32m"
    _BOLD_CYAN  = "\033[1;36m"
    _RST        = "\033[0m"
    _DIM        = "\033[2m"

    month_name = calendar.month_name[month]
    header = f"  {month_name} {year}"

    # Day-of-week header: Mo Tu We Th Fr Sa Su
    dow_header = "  " + "  ".join(
        f"{_DIM}{calendar.day_abbr[i][:2]}{_RST}" for i in range(7)
    )

    # Build week rows
    cal = calendar.monthcalendar(year, month)
    rows = []
    for week in cal:
        cells = []
        for day in week:
            if day == 0:
                cells.append("  ")
            elif day == today.day and month == today.month and year == today.year:
                cells.append(f"{_BOLD_GREEN}{day:2}{_RST}")
            else:
                cells.append(f"{day:2}")
        rows.append("  " + "  ".join(cells))

    lines = [f"{_BOLD_CYAN}{header}{_RST}", dow_header] + rows
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /subagent — spawn an isolated LLM agent for a focused task
# ---------------------------------------------------------------------------

def _cmd_subagent(args: str, state: dict) -> str:
    import agent
    task = args.strip()
    if not task:
        return "Usage: /subagent <task description>"

    client = state["client"]
    model  = state["model"]

    print(f"\n\033[2m┌─ subagent  model: {model}\033[0m")
    print(f"\033[2m│ task: {task[:120]}\033[0m")
    print("\033[2m│\033[0m")

    agent.run_subagent(
        client,
        model,
        task,
        verbose=True,
        gen_params=state.get("gen_params") or None,
        state=state,
    )

    print("\033[2m└─ subagent done\033[0m\n")
    return ""


# ---------------------------------------------------------------------------
# /experiment — sweep temperature values over a fixed prompt, log + report
# ---------------------------------------------------------------------------

def _extract_tool_trace(messages: list) -> list:
    """
    Walk a trial's isolated message list (built by agent.chat()) and pull out
    the chronological tool-call trace: each assistant tool call paired with
    its matching tool-result message, by tool_call_id.
    """
    trace: list = []
    for i, m in enumerate(messages):
        if not (isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls")):
            continue
        results_by_id = {}
        for later in messages[i + 1:]:
            if isinstance(later, dict) and later.get("role") == "tool" and later.get("tool_call_id"):
                results_by_id[later["tool_call_id"]] = later.get("content", "")
        for tc in m["tool_calls"]:
            fn = tc.get("function", {})
            name = fn.get("name", "?")
            raw_args = fn.get("arguments", "")
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = raw_args
            trace.append({
                "name": name,
                "arguments": args,
                "result": results_by_id.get(tc.get("id"), ""),
            })
    return trace


def _truncate_lines(text: str, max_lines: int = 5) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n..."


def _build_experiment_report(
    prompt: str,
    model: str,
    temperatures: list,
    repeats: int,
    base_params: dict,
    tool_enabled: bool,
    results: list,
) -> str:
    from datetime import datetime, timezone

    lines = ["# Experiment Report", ""]
    lines.append(f"- Model: {model}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Temperature values: {', '.join(str(t) for t in temperatures)}")
    lines.append(f"- Repeats per value: {repeats}")
    if base_params:
        fixed = ", ".join(f"{k}={v}" for k, v in base_params.items())
        lines.append(f"- Fixed generation params: {fixed}")
    lines.append(f"- Tool calls: {'enabled' if tool_enabled else 'disabled'}")
    if tool_enabled:
        lines.append(
            "- Note: token counts below reflect only the *final* LLM call of "
            "each trial (agent.chat()'s usage tracking is last-round-only), "
            "not the full multi-round total for trials that used tools."
        )
    lines.append("")
    lines.append("## Prompt")
    lines.append("")
    lines.append("```")
    lines.append(prompt)
    lines.append("```")
    lines.append("")
    lines.append("## Results Summary")
    lines.append("")
    lines.append("| Trial | Temp | Repeat | Prompt tok | Completion tok | Elapsed (s) | Tok/s | Tool calls |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r['trial']} | {r['temperature']} | {r['repeat']} | "
            f"{r['prompt_tokens'] if r['prompt_tokens'] is not None else '-'} | "
            f"{r['completion_tokens'] if r['completion_tokens'] is not None else '-'} | "
            f"{r['elapsed_s']} | {r['tokens_per_sec'] if r['tokens_per_sec'] is not None else '-'} | "
            f"{len(r.get('tool_calls') or [])} |"
        )
    lines.append("")
    lines.append("## Trial Details")
    for r in results:
        lines.append("")
        lines.append(f"### Trial {r['trial']} — temperature={r['temperature']}, repeat={r['repeat']}")
        for step in r.get("tool_calls") or []:
            lines.append("")
            lines.append(f"**Tool call:** `{step['name']}({step['arguments']})`")
            lines.append("")
            lines.append("**Result:**")
            lines.append("```")
            lines.append(_truncate_lines(str(step["result"])))
            lines.append("```")
        lines.append("")
        lines.append("**Response:**")
        lines.append("")
        lines.append("```")
        lines.append(r["response"])
        lines.append("```")
    return "\n".join(lines) + "\n"


def _cmd_experiment(args: str, state: dict) -> str:
    import agent as agent_mod
    import config
    from datetime import datetime, timezone

    prompt_text = args.strip()
    if not prompt_text:
        try:
            prompt_text = input("  Prompt to test: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "Cancelled."
        if not prompt_text:
            return "Usage: /experiment <prompt text>  (or /experiment with no args to be prompted)"

    try:
        temps_raw = input(
            "  Temperature values (comma-separated, e.g. 0.2,0.5,0.8,1.0): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return "Cancelled."
    if not temps_raw:
        return "Cancelled — no temperature values given."

    temperatures: list = []
    for part in temps_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            t = float(part)
        except ValueError:
            return f"Invalid temperature value: '{part}'"
        if not (0.0 <= t <= 2.0):
            return f"Temperature must be between 0.0 and 2.0 (got {t})"
        temperatures.append(t)
    if not temperatures:
        return "Cancelled — no valid temperature values given."

    try:
        repeats_raw = input("  Repeats per temperature [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return "Cancelled."
    repeats = 1
    if repeats_raw:
        try:
            repeats = int(repeats_raw)
        except ValueError:
            return f"Invalid repeat count: '{repeats_raw}'"
        if repeats < 1:
            return "Repeats must be >= 1"

    try:
        tool_raw = input("  Allow tool calls during this experiment? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "Cancelled."
    tool_enabled = tool_raw == "y"

    experiment_skip_confirm = False
    if tool_enabled:
        try:
            skip_raw = input(
                "  Skip tool confirmation prompts for this experiment run? [y/N] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "Cancelled."
        experiment_skip_confirm = skip_raw == "y"

    total_trials = len(temperatures) * repeats
    if tool_enabled:
        tools_summary = "tools: enabled (skip-confirm)" if experiment_skip_confirm else "tools: enabled"
    else:
        tools_summary = "tools: disabled"
    print(
        f"\n  {total_trials} trial(s): {len(temperatures)} temperature value(s) x "
        f"{repeats} repeat(s)  [{tools_summary}]"
    )
    try:
        confirm = input("  Proceed? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "Cancelled."
    if confirm != "y":
        return "Cancelled."

    # Fixed params: whatever is currently set via /set, minus temperature (swept below)
    base_params = dict(state.get("gen_params") or {})
    base_params.pop("temperature", None)

    # Reuse the current session's system prompt so trials match live behaviour
    sys_msg = next(
        (m.get("content") for m in state["messages"]
         if isinstance(m, dict) and m.get("role") == "system"),
        config.SYSTEM_PROMPT,
    )

    client = state["client"]
    model = state["model"]

    experiment_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    exp_dir = os.path.join(config.WORKSPACE_ROOT, "experiments", experiment_id)
    os.makedirs(exp_dir, exist_ok=True)
    results_path = os.path.join(exp_dir, "results.jsonl")
    report_path = os.path.join(exp_dir, "report.md")

    results: list = []
    trial_num = 0
    try:
        for temp in temperatures:
            for rep in range(1, repeats + 1):
                trial_num += 1
                print(
                    f"\n\033[2m--- trial {trial_num}/{total_trials}  "
                    f"temperature={temp}  repeat={rep}/{repeats} ---\033[0m"
                )

                messages = agent_mod.new_conversation(sys_msg)
                messages.append({"role": "user", "content": prompt_text})

                gen_params = dict(base_params)
                gen_params["temperature"] = temp

                tool_trace: list = []
                t_start = time.monotonic()
                try:
                    if tool_enabled:
                        trial_state = dict(state)
                        trial_state["skip_confirm"] = experiment_skip_confirm
                        trial_usage: dict = {}
                        answer = agent_mod.chat(
                            client, model, messages,
                            verbose=True,
                            usage_out=trial_usage,
                            gen_params=gen_params,
                            context_length=None,
                            state=trial_state,
                        )
                        usage = trial_usage or None
                        tool_trace = _extract_tool_trace(messages[2:])
                    else:
                        answer, usage = agent_mod._stream_response(
                            client, model, messages, gen_params=gen_params
                        )
                except Exception as e:
                    answer = f"ERROR: {e}"
                    usage = None
                elapsed = time.monotonic() - t_start

                answer = sanitize_for_file(answer)
                completion_tok = usage.get("completion_tokens") if usage else None
                record = {
                    "trial": trial_num,
                    "temperature": temp,
                    "repeat": rep,
                    "model": model,
                    "prompt": prompt_text,
                    "response": answer,
                    "elapsed_s": round(elapsed, 3),
                    "prompt_tokens": usage.get("prompt_tokens") if usage else None,
                    "completion_tokens": completion_tok,
                    "total_tokens": usage.get("total_tokens") if usage else None,
                    "tokens_per_sec": (
                        round(completion_tok / elapsed, 2)
                        if completion_tok and elapsed > 0 else None
                    ),
                    "fixed_params": base_params,
                    "tool_enabled": tool_enabled,
                    "tool_calls": tool_trace,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                results.append(record)

                # Append incrementally so partial results survive a crash/interrupt
                try:
                    with open(results_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    pass
    except KeyboardInterrupt:
        print("\n  [experiment] interrupted — writing partial report...")

    report = _build_experiment_report(
        prompt_text, model, temperatures, repeats, base_params, tool_enabled, results
    )
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(sanitize_for_file(report))
    except Exception as e:
        return f"Ran {len(results)}/{total_trials} trial(s) but failed to save report: {e}"

    return (
        f"\n  Completed {len(results)}/{total_trials} trial(s).\n"
        f"  Results : {results_path}\n"
        f"  Report  : {report_path}"
    )


# ---------------------------------------------------------------------------
# Register all commands
# ---------------------------------------------------------------------------

register("/help",        _cmd_help,        help="Show this help message")
register("/reset",       _cmd_reset,       help="Clear conversation history (keeps system prompt)")
register("/model",       _cmd_model,       help="Show or set the active model: /model <name>")
register("/tools",       _cmd_tools,       help="List registered tools (and any that failed to load)")
register("/reloadtools", _cmd_reloadtools, help="Retry loading failed tools: /reloadtools [filename]")
register("/history",     _cmd_history,     help="Print conversation history with per-message token estimates")
register("/pollution",   _cmd_pollution,   help="Context health report: scaffolding, stale results, rot")
register("/drop",        _cmd_drop,        help="Remove messages by index: /drop <n>, /drop <n>-<m>, or /drop <a>,<b>,<c>")
register("/ctx",         _cmd_ctx,         help="Show context window usage and token counts")
register("/set",         _cmd_set,         help="Set a generation parameter: /set temperature 0.7")
register("/params",      _cmd_params,      help="Show active generation parameter overrides")
register("/unset",       _cmd_unset,       help="Remove a generation parameter override: /unset temperature")
register("/sessions",    _cmd_sessions,    help="List saved sessions")
register("/load",        _cmd_load,        help="Resume a saved session: /load <session-id>")
register("/loadtool",    _cmd_loadtool,    help="Load a tool from a .py file: /loadtool <path>")
register("/newtool",     _cmd_newtool,     help="Ask the LLM to write and load a new tool: /newtool <description>")
register("/skill",       _cmd_skill,       help="Run a skill: /skill <name> [args]")
register("/skills",      _cmd_skills,      help="List available skills")
register("/newskill",    _cmd_newskill,    help="Ask the LLM to write a new skill: /newskill <description>")
register("/calendar",    _cmd_calendar,    help="Show a mini calendar: /calendar [month] or /calendar [year] [month]")
register("/cls",         _cmd_cls,         help="Clear the terminal screen")
register("/open",        _cmd_open,        help="Open a URL in the default browser: /open <url>")
register("/time",        _cmd_time,        help="Show current UTC and local date/time")
register("/system",      _cmd_system,      help="Show or replace the system prompt: /system [new prompt]")
register("/compress",    _cmd_compress,    help="Manually compress conversation history to free context space")
register("/exit",        _cmd_exit,        help="Quit the harness")
register("/quit",        _cmd_exit,        help="Quit the harness (alias for /exit)")
register("/subagent",    _cmd_subagent,    help="Spawn an isolated subagent for a focused task: /subagent <task>")
register("/experiment",  _cmd_experiment,  help="Run a prompt across a sweep of temperature values, log each trial, and save a report: /experiment <prompt>")
