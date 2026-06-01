import os
import re
import config
import tools


def grep(pattern: str, path: str = None, recursive: bool = True) -> str:
    """Search file contents for a regex pattern within the workspace."""
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid pattern: {e}"

    root = os.path.realpath(config.WORKSPACE_ROOT)

    if path:
        expanded = os.path.expanduser(os.path.expandvars(path))
        target = expanded if os.path.isabs(expanded) else os.path.join(config.WORKSPACE_ROOT, expanded)
    else:
        target = config.WORKSPACE_ROOT
    target = os.path.realpath(target)

    if not (target == root or target.startswith(root + os.sep)):
        return "Error: path is outside the workspace"

    if not os.path.exists(target):
        return f"Error: path does not exist: '{target}'"

    if os.path.isfile(target):
        files = [target]
    else:
        files = []
        if recursive:
            for dirpath, _dirs, filenames in os.walk(target):
                for name in filenames:
                    files.append(os.path.join(dirpath, name))
        else:
            for name in os.listdir(target):
                full = os.path.join(target, name)
                if os.path.isfile(full):
                    files.append(full)

    lines = []
    for filepath in sorted(files):
        try:
            with open(filepath, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if rx.search(line):
                        rel = os.path.relpath(filepath, root)
                        lines.append(f"{rel}:{lineno}: {line.rstrip()}")
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return f"Error: {e}"

    return "\n".join(lines) if lines else "No matches found."


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "grep",
        "description": (
            "Search file contents for a regex pattern within the workspace. "
            "Returns matching lines with file path and line number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex search pattern.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative file or directory to search "
                        "(default: workspace root)."
                    ),
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Search subdirectories (default: true).",
                },
            },
            "required": ["pattern"],
        },
    },
}

tools.register(TOOL_SCHEMA, grep)
