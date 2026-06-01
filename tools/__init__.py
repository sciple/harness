# tools/__init__.py — Tool registry
#
# How to add a tool:
#   1. Create a new file in tools/ (e.g. tools/my_tool.py)
#   2. Define your function and a TOOL_SCHEMA dict at module level
#   3. Call register(TOOL_SCHEMA, my_function) at the bottom of that file
#
# Tools are discovered and loaded automatically at startup — no imports needed here.
# The agent reads `get_schemas()` to pass to the LLM and calls
# `dispatch(name, args)` to execute the chosen tool.

import fnmatch
import importlib.util
import json
import os
import sys
from collections import OrderedDict
from typing import Any

_registry: dict[str, tuple[dict, callable]] = {}
_confirm_tools: set[str] = set()


def is_protected_path(path: str) -> tuple[bool, str]:
    """
    Check whether a filesystem path is off-limits for tools to write or delete.

    Returns (protected: bool, reason: str).
    The reason is a human-readable explanation shown to the user and the model.
    """
    from config import PROTECTED_FILES, PROTECTED_FILENAME_PATTERNS, PROTECTED_DIRS

    resolved = os.path.normcase(os.path.realpath(path))
    basename = os.path.basename(resolved)

    # 1. Exact file match
    if resolved in {os.path.normcase(p) for p in PROTECTED_FILES}:
        return True, f"'{basename}' is a protected harness core file."

    # 2. Filename pattern match (e.g. __init__.py, .env, requirements.txt)
    for pattern in PROTECTED_FILENAME_PATTERNS:
        if fnmatch.fnmatch(basename.lower(), pattern.lower()):
            return True, f"'{basename}' matches protected filename pattern '{pattern}'."

    # 3. Inside a protected directory
    for protected_dir in PROTECTED_DIRS:
        nc_dir = os.path.normcase(protected_dir)
        if resolved.startswith(nc_dir + os.sep) or resolved == nc_dir:
            dir_name = os.path.basename(protected_dir)
            return True, f"'{resolved}' is inside the protected directory '{dir_name}/'."

    return False, ""
_failed_tools: dict[str, str] = {}       # filename -> error message
_tool_output_store: OrderedDict = OrderedDict()  # key -> full output string
_call_counter: list[int] = [0]
_OUTPUT_STORE_MAX = 50   # max entries kept in the store


_no_truncate_tools: set[str] = set()


def register(schema: dict, fn: callable) -> None:
    """Register a tool. schema must follow the OpenAI function-calling format."""
    name = schema["function"]["name"]
    _registry[name] = (schema, fn)
    # Honour the optional top-level "confirm" flag
    if schema.get("confirm") or schema.get("function", {}).get("confirm"):
        _confirm_tools.add(name)
    # Honour the optional top-level "no_truncate" flag
    if schema.get("no_truncate"):
        _no_truncate_tools.add(name)


def get_schemas() -> list[dict]:
    """Return all registered tool schemas for the LLM (confirm key stripped)."""
    schemas = []
    for schema, _ in _registry.values():
        # Deep-copy and strip non-standard keys so the LLM API doesn't choke
        clean = {k: v for k, v in schema.items() if k not in ("confirm",)}
        schemas.append(clean)
    return schemas


def dispatch(name: str, args: dict[str, Any]) -> str:
    """
    Call the registered function for `name` with `args`.
    Handles dict results (JSON-serialised), truncates long output,
    and stores the full output for later retrieval.
    Returns a string result.
    """
    if name not in _registry:
        return f"Error: unknown tool '{name}'"
    _, fn = _registry[name]
    try:
        result = fn(**args)
    except Exception as e:
        return f"Error executing tool '{name}': {e}"

    # Serialise dict results
    if isinstance(result, dict):
        try:
            result = json.dumps(result, indent=2, ensure_ascii=False)
        except Exception:
            result = str(result)
    else:
        result = str(result)

    # Store full output
    _call_counter[0] += 1
    store_key = f"{name}_{_call_counter[0]}"
    if _OUTPUT_STORE_MAX and len(_tool_output_store) >= _OUTPUT_STORE_MAX:
        _tool_output_store.popitem(last=False)  # evict oldest
    _tool_output_store[store_key] = result

    # Truncate if needed (skip for tools that manage their own output size)
    from config import TOOL_OUTPUT_MAX_CHARS, TOOL_OUTPUT_STORE
    if TOOL_OUTPUT_STORE and name not in _no_truncate_tools and len(result) > TOOL_OUTPUT_MAX_CHARS:
        result = (
            result[:TOOL_OUTPUT_MAX_CHARS]
            + f"\n[Output truncated. Full output available via get_tool_output('{store_key}')]"
        )

    return result


def requires_confirmation(name: str) -> bool:
    """Return True if this tool is marked as requiring user confirmation."""
    return name in _confirm_tools


def list_tools() -> list[str]:
    """Return a list of registered tool names."""
    return list(_registry.keys())


def list_failed_tools() -> dict[str, str]:
    """Return a copy of the failed-to-load tool files and their errors."""
    return dict(_failed_tools)


def get_stored_output(key: str) -> str:
    """Retrieve a previously stored full tool output by key."""
    if key not in _tool_output_store:
        return f"Error: no stored output for key '{key}'"
    return _tool_output_store[key]


def reload_failed(specific_file: str | None = None) -> dict[str, str]:
    """
    Retry loading failed tool files.
    If specific_file is given, retry only that filename.
    Returns {filename: "ok" | error_message}.
    """
    targets = [specific_file] if specific_file else list(_failed_tools.keys())
    results: dict[str, str] = {}
    tools_dir = os.path.dirname(__file__)

    for filename in targets:
        path = os.path.join(tools_dir, filename)
        if not os.path.isfile(path):
            results[filename] = f"File not found: {path}"
            continue

        module_name = f"tools.{filename[:-3]}"
        # Remove stale entry so we actually re-execute
        sys.modules.pop(module_name, None)
        _failed_tools.pop(filename, None)

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            results[filename] = "ok"
        except Exception as e:
            _failed_tools[filename] = str(e)
            results[filename] = str(e)

    return results


def _autodiscover() -> None:
    """
    Import every .py file in the tools/ directory (except __init__.py).
    Each file self-registers by calling tools.register() at module level.
    Errors are stored in _failed_tools and printed as warnings.
    """
    tools_dir = os.path.dirname(__file__)
    for filename in sorted(os.listdir(tools_dir)):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        module_name = f"tools.{filename[:-3]}"
        if module_name in sys.modules:
            continue
        path = os.path.join(tools_dir, filename)
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            _failed_tools[filename] = str(e)
            print(f"  [tools] Warning: could not load '{filename}': {e}")


# --- Built-in meta-tool: retrieve stored output ---
def _get_tool_output_fn(key: str) -> str:
    return get_stored_output(key)

_GET_OUTPUT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_tool_output",
        "description": "Retrieve the full (untruncated) output from a previous tool call that was truncated.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The output key shown in the truncation note, e.g. 'write_file_3'.",
                }
            },
            "required": ["key"],
        },
    },
}
register(_GET_OUTPUT_SCHEMA, _get_tool_output_fn)

_autodiscover()
