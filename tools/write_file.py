import os
import config
import tools


def write_file(path: str, content: str) -> str:
    """
    Write text content to a file at the given path.
    The path may include subdirectories, which are created automatically.
    Writing outside the workspace root or to protected harness files is refused.
    """
    root = config.WORKSPACE_ROOT  # read at call time so tests can override

    # Resolve to an absolute path (follows symlinks, collapses ../)
    target = os.path.realpath(os.path.join(root, path))

    # Security check 1: resolved path must stay inside root
    if not (target.startswith(root + os.sep) or target == root):
        return (
            f"Error: '{path}' resolves outside the allowed root directory '{root}'. "
            "Write refused."
        )

    # Security check 2: must not touch protected harness files
    from tools import is_protected_path
    protected, reason = is_protected_path(target)
    if protected:
        return f"Error: Write refused. {reason}"

    # Create parent directories if needed
    parent = os.path.dirname(target)
    try:
        os.makedirs(parent, exist_ok=True)
    except Exception as e:
        return f"Error creating directories for '{path}': {e}"

    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File written: {target}"
    except Exception as e:
        return f"Error writing '{target}': {e}"


TOOL_SCHEMA = {
    "type": "function",
    "confirm": True,
    "function": {
        "name": "write_file",
        "description": (
            "Write text content to a file. The path can include subdirectories "
            "(they are created automatically). Any file type is supported. "
            "The path must be relative to the workspace root — "
            "writing outside that root is not allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path of the file to write, e.g. 'notes/summary.md' "
                        "or 'output/report.txt'. Must not escape the root directory."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write into the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
}

tools.register(TOOL_SCHEMA, write_file)
