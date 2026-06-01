import agent

SKILL_META = {
    "name":        "translate_fr",
    "description": "Translate the given text (or the last user message) into French.",
    "version":     "1.0",
}


def run(args: str, state: dict, client) -> str:
    text = args.strip()

    if not text:
        for msg in reversed(state.get("messages", [])):
            is_dict = isinstance(msg, dict)
            role    = (msg.get("role") if is_dict else getattr(msg, "role", "")) or ""
            content = (msg.get("content") if is_dict else getattr(msg, "content", "")) or ""
            if role == "user" and content:
                text = content
                break

    if not text:
        return "Usage: /skill translate_fr <text>  -- or run after a user message to translate it."

    prompt = (
        "Translate the following text into French. "
        "Output the translation only, no commentary.\n\n"
        + text
    )

    messages = [{"role": "user", "content": prompt}]
    print("\nTranslating to French...\n")
    agent._stream_response(client, state["model"], messages,
                           gen_params=state.get("gen_params") or None)
    return ""
