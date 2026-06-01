# skills/compact.py — Summarise, reset, and print the summary
#
# Usage: /skill compact
#
# 1. Builds a transcript of the current conversation
# 2. Asks the model for a concise summary (outside main history)
# 3. Saves the summary to a note under key '__compact_tmp__'
# 4. Resets the conversation history (keeps system prompt)
# 5. Prints the summary
# 6. Deletes the temporary note

import agent
import tools as tool_registry

SKILL_META = {
    "name":        "compact",
    "description": "Summarise the conversation, reset history, and print the summary.",
    "version":     "1.0",
}

_NOTE_KEY = "__compact_tmp__"


def run(args: str, state: dict, client) -> str:
    messages = state.get("messages", [])
    model    = state["model"]

    # Build transcript (skip system messages and tool scaffolding)
    lines = []
    for m in messages:
        is_dict = isinstance(m, dict)
        role    = (m.get("role") if is_dict else getattr(m, "role", "?")) or "?"
        content = (m.get("content") if is_dict else getattr(m, "content", "")) or ""
        if role in ("system", "tool"):
            continue
        if role == "assistant" and not content:
            continue   # tool-call assistant messages have no text content
        if content:
            lines.append(f"{role.upper()}: {content[:1000]}")

    if not lines:
        return "Nothing to compact — the conversation is empty."

    transcript = "\n".join(lines)
    summary_prompt = [
        {
            "role": "user",
            "content": (
                "Produce a concise but complete summary of the following conversation. "
                "Capture the main topics, decisions, and any important conclusions. "
                "Write in plain prose, 3-8 sentences.\n\n"
                + transcript
            ),
        }
    ]

    print("\nCompacting conversation...\n")
    summary_text, _ = agent._stream_response(client, model, summary_prompt,
                                             gen_params=state.get("gen_params") or None)

    if not summary_text.strip():
        return "Compaction failed — model returned an empty summary. History not reset."

    # Save summary to a temporary note
    tool_registry.dispatch("save_note", {"key": _NOTE_KEY, "content": summary_text})

    # Reset conversation history (keeps system prompt, clears usage)
    import commands
    commands.dispatch("/reset", state)

    # Print summary
    print("\n\033[1mConversation summary:\033[0m\n")
    print(summary_text)
    print()

    # Delete the temporary note
    tool_registry.dispatch("delete_note", {"key": _NOTE_KEY})

    return ""
