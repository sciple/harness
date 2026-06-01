# tools/make_dir.py — Create a directory (and any missing parents)

import os
import tools

def make_dir(path: str) -> str:
    """Create a directory at the given path, including any missing parent directories."""
    from tools import is_protected_path
    protected, reason = is_protected_path(os.path.realpath(path))
    if protected:
        return f"Error: Directory creation refused. {reason}"
    try:
        os.makedirs(path, exist_ok=True)
        return f"Directory created: {path}"
    except Exception as e:
        return f"Error creating directory '{path}': {e}"

TOOL_SCHEMA = {
    "type": "function",
    "confirm": True,
    "function": {
        "name": "make_dir",
        "description": "Create a directory at the specified path. Creates all missing parent directories automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to create, e.g. '/tmp/my/new/folder'",
                }
            },
            "required": ["path"],
        },
    },
}

tools.register(TOOL_SCHEMA, make_dir)
