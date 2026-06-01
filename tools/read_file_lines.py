import os
import config
import tools


def read_file_lines(file_path: str, start: int, end: int) -> str:
    """Read a line range from a workspace file. Lines are 1-indexed; end is inclusive."""
    if not isinstance(start, int) or not isinstance(end, int):
        return "Error: start and end must be integers"
    if start < 1:
        return "Error: start must be >= 1"
    if end < start:
        return "Error: end must be >= start"

    root = os.path.realpath(config.WORKSPACE_ROOT)
    expanded = os.path.expanduser(os.path.expandvars(file_path))
    target = expanded if os.path.isabs(expanded) else os.path.join(config.WORKSPACE_ROOT, expanded)
    target = os.path.realpath(target)

    if not (target == root or target.startswith(root + os.sep)):
        return "Error: path is outside the workspace"

    if not os.path.exists(target):
        return f"Error: file does not exist: '{target}'"

    if not os.path.isfile(target):
        return f"Error: path is not a file: '{target}'"

    try:
        with open(target, encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return f"Error: file is not valid UTF-8: '{target}'"
    except Exception as e:
        return f"Error: {e}"

    total = len(lines)
    if start > total:
        return f"Error: start ({start}) exceeds file length ({total} lines)"

    end_clamped = min(end, total)
    selected = lines[start - 1 : end_clamped]
    return "".join(f"{i}: {line}" for i, line in enumerate(selected, start=start)).rstrip("\n")


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file_lines",
        "description": (
            "Read a specific line range from a workspace file. "
            "Lines are 1-indexed and the end line is inclusive. "
            "Returns each line prefixed with its line number (e.g. '142: ...'). "
            "Useful for following up a grep hit by reading surrounding context "
            "without loading the entire file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Workspace-relative path to the file.",
                },
                "start": {
                    "type": "integer",
                    "description": "First line to read (1-indexed).",
                },
                "end": {
                    "type": "integer",
                    "description": "Last line to read (inclusive). Clamped to end-of-file.",
                },
            },
            "required": ["file_path", "start", "end"],
        },
    },
}

tools.register(TOOL_SCHEMA, read_file_lines)
