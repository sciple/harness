# skills/explain_file.py — Ask the model to explain a local file
#
# Usage: /skill explain_file path/to/file.py
#
# Reads the file, sends it to the model with an explanation prompt,
# streams the response, and does NOT add anything to the main conversation.

import os
from pathlib import Path
import agent
import config

SKILL_META = {
    "name":        "explain_file",
    "description": "Read a local file and ask the model to explain it.",
    "version":     "1.0",
}


def _resolve(path: str) -> tuple[str | None, str | None]:
    """
    Return (resolved_path, error_message).
    1. Try the path as given (absolute or workspace-relative).
    2. If not found, glob the workspace for **/<basename> and pick the match.
    """
    candidate = os.path.expanduser(os.path.expandvars(path))
    if not os.path.isabs(candidate):
        candidate = os.path.join(config.WORKSPACE_ROOT, candidate)
    if os.path.isfile(candidate):
        return candidate, None

    # Fall back: search workspace by filename
    basename = os.path.basename(path)
    matches = [str(p) for p in Path(config.WORKSPACE_ROOT).rglob(basename) if p.is_file()]

    if not matches:
        return None, (
            f"File not found: '{path}'\n"
            f"Searched workspace for '{basename}' — no matches."
        )
    if len(matches) == 1:
        print(f"  (resolved '{path}' → '{matches[0]}')")
        return matches[0], None

    listing = "\n".join(f"  {m}" for m in sorted(matches))
    return None, (
        f"Ambiguous: '{basename}' matched {len(matches)} files — be more specific:\n{listing}"
    )


def run(args: str, state: dict, client) -> str:
    path = args.strip()
    if not path:
        return "Usage: /skill explain_file <path or filename>"

    resolved, err = _resolve(path)
    if err:
        return err

    try:
        with open(resolved, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    if len(content) > 12000:
        content = content[:12000] + "\n\n[... file truncated for context ...]"

    messages = [
        {
            "role": "user",
            "content": (
                f"Please explain the following file ('{os.path.basename(resolved)}') "
                "clearly and concisely. Describe what it does, its structure, "
                "and any important details.\n\n"
                f"```\n{content}\n```"
            ),
        }
    ]

    print(f"\nExplaining '{resolved}'...\n")
    agent._stream_response(client, state["model"], messages,
                           gen_params=state.get("gen_params") or None)
    return ""
