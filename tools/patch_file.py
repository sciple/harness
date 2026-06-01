import os
import config
import tools


def patch_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """
    Replace the first (or all) occurrence(s) of old_text with new_text in a file.
    The file is read, patched in memory, and written back atomically.
    Path must be relative to the workspace root.
    """
    import tempfile

    root = config.WORKSPACE_ROOT
    target = os.path.realpath(os.path.join(root, path))

    if not (target.startswith(root + os.sep) or target == root):
        return f"Error: '{path}' resolves outside the workspace root. Patch refused."

    from tools import is_protected_path
    protected, reason = is_protected_path(target)
    if protected:
        return f"Error: Patch refused. {reason}"

    if not os.path.isfile(target):
        return f"Error: file not found: {target}"

    try:
        with open(target, "r", encoding="utf-8") as f:
            original = f.read()
    except Exception as e:
        return f"Error reading '{target}': {e}"

    if old_text not in original:
        return f"Error: the text to replace was not found in '{path}'."

    count = original.count(old_text)
    if replace_all:
        patched = original.replace(old_text, new_text)
        replaced = count
    else:
        patched = original.replace(old_text, new_text, 1)
        replaced = 1

    # Atomic write
    dir_ = os.path.dirname(target) or root
    try:
        fd, tmp = tempfile.mkstemp(dir=dir_)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(patched)
        os.replace(tmp, target)
    except Exception as e:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        return f"Error writing patch to '{target}': {e}"

    noun = "occurrence" if replaced == 1 else "occurrences"
    skipped = f" ({count - replaced} occurrence(s) left unchanged)" if not replace_all and count > 1 else ""
    return f"Patched '{path}': replaced {replaced} {noun}.{skipped}"


TOOL_SCHEMA = {
    "type": "function",
    "confirm": False,
    "function": {
        "name": "patch_file",
        "description": (
            "Replace a specific string inside a file without rewriting the whole file. "
            "Finds old_text and replaces it with new_text. "
            "By default only the first occurrence is replaced; set replace_all to true "
            "to replace every occurrence. "
            "Path must be relative to the workspace root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to patch, e.g. 'src/main.py'.",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace. Must match exactly including whitespace.",
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to substitute in place of old_text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence of old_text (default false — only the first).",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
}

tools.register(TOOL_SCHEMA, patch_file)
