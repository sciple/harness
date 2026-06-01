import os
import config
import tools


def append_to_file(path: str, content: str, newline: bool = True) -> str:
    """
    Append text to an existing file (or create it if it does not exist).
    The path must be relative to the workspace root.
    """
    root = config.WORKSPACE_ROOT
    target = os.path.realpath(os.path.join(root, path))

    if not (target.startswith(root + os.sep) or target == root):
        return f"Error: '{path}' resolves outside the workspace root. Append refused."

    from tools import is_protected_path
    protected, reason = is_protected_path(target)
    if protected:
        return f"Error: Append refused. {reason}"

    try:
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            if newline and os.path.getsize(target) > 0 if os.path.exists(target) else False:
                f.write("\n")
            f.write(content)
        return f"Appended {len(content)} chars to {target}"
    except Exception as e:
        return f"Error appending to '{target}': {e}"


TOOL_SCHEMA = {
    "type": "function",
    "confirm": False,
    "function": {
        "name": "append_to_file",
        "description": (
            "Append text to the end of a file without overwriting its existing content. "
            "Creates the file if it does not exist. "
            "Path must be relative to the workspace root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file, e.g. 'notes/log.md'.",
                },
                "content": {
                    "type": "string",
                    "description": "Text to append to the file.",
                },
                "newline": {
                    "type": "boolean",
                    "description": (
                        "Insert a blank line before appending if the file already has content "
                        "(default true)."
                    ),
                },
            },
            "required": ["path", "content"],
        },
    },
}

tools.register(TOOL_SCHEMA, append_to_file)
