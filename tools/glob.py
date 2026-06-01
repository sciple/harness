import os
from pathlib import Path
import config
import tools


def glob(pattern: str, path: str = None) -> str:
    """Find files by glob pattern within the workspace."""
    root = os.path.realpath(config.WORKSPACE_ROOT)

    if path:
        expanded = os.path.expanduser(os.path.expandvars(path))
        base = expanded if os.path.isabs(expanded) else os.path.join(config.WORKSPACE_ROOT, expanded)
    else:
        base = config.WORKSPACE_ROOT
    base = os.path.realpath(base)

    if not (base == root or base.startswith(root + os.sep)):
        return "Error: path is outside the workspace"

    if not os.path.exists(base):
        return f"Error: path does not exist: '{base}'"

    if not os.path.isdir(base):
        return f"Error: path is not a directory: '{base}'"

    try:
        matches = sorted(str(p) for p in Path(base).glob(pattern))
    except Exception as e:
        return f"Error: {e}"

    if not matches:
        return "No matches found."

    rels = [os.path.relpath(m, root) for m in matches]
    return "\n".join(rels)


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "glob",
        "description": (
            "Find files by glob pattern within the workspace. "
            "Use '**' in the pattern to recurse (e.g. '**/*.py'). "
            "Returns one matching path per line, relative to the workspace root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern, e.g. '*.py' for the base dir only, "
                        "or '**/*.py' to recurse into subdirectories."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory to search from "
                        "(default: workspace root)."
                    ),
                },
            },
            "required": ["pattern"],
        },
    },
}

tools.register(TOOL_SCHEMA, glob)
