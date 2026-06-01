# session.py — Session persistence (save / load / list)
#
# Each session is stored as a JSONL file in SESSIONS_DIR.
# One JSON object per line, representing a single message.
# Writes are atomic (temp file + rename) so a crash mid-save never corrupts.

import json
import os
import tempfile
from datetime import datetime, timezone

from config import SESSIONS_DIR


def new_id() -> str:
    """Generate a new session ID based on the current UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def ensure_dir() -> None:
    """Create the sessions directory if it does not exist."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def _msg_to_dict(m) -> dict:
    """
    Convert a message to a plain serialisable dict.
    Handles both plain dicts and OpenAI SDK message objects.
    """
    if isinstance(m, dict):
        return m
    # OpenAI SDK objects have model_dump() in openai >= 1.x
    if hasattr(m, "model_dump"):
        return m.model_dump()
    # Fallback: reconstruct manually
    d = {"role": getattr(m, "role", "assistant")}
    content = getattr(m, "content", None)
    if content is not None:
        d["content"] = content
    tool_calls = getattr(m, "tool_calls", None)
    if tool_calls:
        d["tool_calls"] = [
            tc.model_dump() if hasattr(tc, "model_dump") else tc
            for tc in tool_calls
        ]
    tool_call_id = getattr(m, "tool_call_id", None)
    if tool_call_id:
        d["tool_call_id"] = tool_call_id
    return d


def save(state: dict) -> None:
    """
    Persist the current session messages to disk.
    Silently swallows errors — persistence must never crash the REPL.
    """
    try:
        session_id = state.get("session_id", "unknown")
        path = os.path.join(SESSIONS_DIR, f"{session_id}.jsonl")
        messages = state.get("messages", [])

        # Write to temp file first, then rename atomically
        fd, tmp_path = tempfile.mkstemp(dir=SESSIONS_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for m in messages:
                    try:
                        f.write(json.dumps(_msg_to_dict(m), ensure_ascii=False) + "\n")
                    except Exception:
                        pass  # skip un-serialisable messages silently
        except Exception:
            os.unlink(tmp_path)
            return
        os.replace(tmp_path, path)
    except Exception:
        pass


def load(session_id: str) -> list[dict] | None:
    """
    Load a session from disk by ID.
    Returns the list of message dicts, or None if not found.
    """
    path = os.path.join(SESSIONS_DIR, f"{session_id}.jsonl")
    if not os.path.isfile(path):
        return None
    messages = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return None
    return messages


def list_sessions() -> list[tuple[str, int, str]]:
    """
    Scan SESSIONS_DIR and return session metadata sorted newest-first.
    Each entry is (session_id, message_count, iso_timestamp).
    """
    results = []
    try:
        for filename in os.listdir(SESSIONS_DIR):
            if not filename.endswith(".jsonl"):
                continue
            session_id = filename[:-6]
            path = os.path.join(SESSIONS_DIR, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    count = sum(1 for line in f if line.strip())
                mtime = os.path.getmtime(path)
                ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                results.append((session_id, count, ts))
            except Exception:
                results.append((session_id, 0, "?"))
    except Exception:
        pass
    results.sort(key=lambda x: x[0], reverse=True)
    return results
