"""
tools/notes.py — Persistent key-value note store.

Notes are saved to data/notes/notes.json (runtime state, not user workspace).
Two tools are registered: save_note and get_note.
A third helper, list_notes, is also registered.
"""

import json
import os
import tempfile
import tools
import config

_NOTES_FILE = os.path.join(config.DATA_DIR, "notes", "notes.json")


def _load() -> dict:
    if not os.path.isfile(_NOTES_FILE):
        return {}
    try:
        with open(_NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_NOTES_FILE), exist_ok=True)
    dir_ = os.path.dirname(_NOTES_FILE)
    fd, tmp = tempfile.mkstemp(dir=dir_)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _NOTES_FILE)


# ---------------------------------------------------------------------------

def save_note(key: str, value: str) -> str:
    """Save or overwrite a note under the given key."""
    key = key.strip()
    if not key:
        return "Error: key must not be empty."
    data = _load()
    existed = key in data
    data[key] = value
    try:
        _save(data)
    except Exception as e:
        return f"Error saving note: {e}"
    action = "Updated" if existed else "Saved"
    return f"{action} note '{key}' ({len(value)} chars)."


def get_note(key: str) -> str:
    """Retrieve a note by key."""
    key = key.strip()
    data = _load()
    if key not in data:
        keys = list(data.keys())
        hint = f" Available keys: {', '.join(keys)}" if keys else " No notes saved yet."
        return f"Error: note '{key}' not found.{hint}"
    return data[key]


def list_notes() -> str:
    """List all saved note keys with a short preview of each value."""
    data = _load()
    if not data:
        return "No notes saved yet."
    lines = []
    for k, v in data.items():
        preview = v[:80].replace("\n", " ")
        if len(v) > 80:
            preview += "…"
        lines.append(f"  {k}: {preview}")
    return f"{len(data)} note(s):\n" + "\n".join(lines)


def delete_note(key: str) -> str:
    """Delete a note by key."""
    key = key.strip()
    data = _load()
    if key not in data:
        return f"Error: note '{key}' not found."
    del data[key]
    try:
        _save(data)
    except Exception as e:
        return f"Error deleting note: {e}"
    return f"Deleted note '{key}'."


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

tools.register(
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Save a persistent note under a named key. "
                "Notes survive across sessions. "
                "If a note with the same key already exists it is overwritten."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Short identifier for the note, e.g. 'project_goal' or 'api_endpoint'.",
                    },
                    "value": {
                        "type": "string",
                        "description": "The content to store.",
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
    save_note,
)

tools.register(
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": (
                "Retrieve a previously saved note by its key. "
                "Use list_notes to see all available keys."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key of the note to retrieve.",
                    },
                },
                "required": ["key"],
            },
        },
    },
    get_note,
)

tools.register(
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "List all saved note keys with a short preview of each value.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    list_notes,
)

tools.register(
    {
        "type": "function",
        "confirm": True,
        "function": {
            "name": "delete_note",
            "description": "Permanently delete a saved note by its key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key of the note to delete.",
                    },
                },
                "required": ["key"],
            },
        },
    },
    delete_note,
)
