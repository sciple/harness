# skills/summarise.py — Summarise the current conversation
#
# Usage: /skill summarise
#
# This skill sends the current conversation history to the model and asks it
# to produce a concise summary. The summary is printed but NOT appended to
# the main conversation history.

import agent

SKILL_META = {
    "name":        "summarise",
    "description": "Summarise the current conversation and print the result.",
    "version":     "1.0",
}


def run(args: str, state: dict, client) -> str:
    messages = state.get("messages", [])
    model    = state["model"]

    # Build a readable transcript from the current history
    lines = []
    for m in messages:
        is_dict = isinstance(m, dict)
        role    = (m.get("role") if is_dict else getattr(m, "role", "?")) or "?"
        content = (m.get("content") if is_dict else getattr(m, "content", "")) or ""
        if role == "system":
            continue
        if content:
            lines.append(f"{role.upper()}: {content[:800]}")

    if not lines:
        return "Nothing to summarise yet — the conversation is empty."

    transcript = "\n".join(lines)
    summary_messages = [
        {
            "role": "user",
            "content": (
                "Please provide a concise summary of the following conversation. "
                "Highlight the main topics discussed and any conclusions reached.\n\n"
                + transcript
            ),
        }
    ]

    print("\nSummarising conversation...\n")
    # Use a fresh message list so the summary call doesn't pollute the main history
    summary_text, _ = agent._stream_response(client, model, summary_messages)
    return ""
