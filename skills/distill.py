# skills/distill.py — Goal-anchored context distillation
#
# Usage: /skill distill [optional goal]
#
# 1. Resolves the active goal (from args or via LLM extraction)
# 2. User confirms or corrects the goal
# 3. LLM produces a structured distilled context block
# 4. User approves, edits, or aborts
# 5. On approval: saves a snapshot, then replaces the context in-place

import agent
import session as session_mod
import ui as ui_mod

SKILL_META = {
    "name":        "distill",
    "description": "Rebuild context as a laser-focused structured block. User reviews before anything changes.",
    "version":     "1.0",
}

_DIM   = "\033[2m"
_BOLD  = "\033[1m"
_RESET = "\033[0m"
_CYAN  = "\033[96m"

_STRUCTURED_TEMPLATE = """\
[DISTILLED CONTEXT]

GOAL
----
{goal}

ESTABLISHED FACTS
-----------------
{facts}

WORK COMPLETED
--------------
{work}

PENDING / NEXT STEPS
--------------------
{pending}

ARTIFACTS
---------
{artifacts}"""

_DISTILL_PROMPT = """\
You are rebuilding a conversation context from scratch.
The user's goal is: {goal}

Read the transcript below and produce a distilled context using EXACTLY \
this format (no markdown fences, no commentary outside the block):

[DISTILLED CONTEXT]

GOAL
----
{goal}

ESTABLISHED FACTS
-----------------
- <confirmed fact, decision, or constraint>

WORK COMPLETED
--------------
- <completed step and its outcome>

PENDING / NEXT STEPS
--------------------
- <outstanding action or open question>

ARTIFACTS
---------
- <key file path, identifier, value, or reference worth preserving>

Include ONLY information directly relevant to the goal. \
Omit failed attempts, abandoned threads, and verbose tool output. \
If a section has no relevant content, write a single line: (none)

TRANSCRIPT:
{transcript}"""

_GOAL_PROMPT = """\
Given this conversation transcript, state in ONE sentence what the user is \
trying to accomplish. Be specific about the concrete goal, not generic. \
Output only the sentence, nothing else.

TRANSCRIPT:
{transcript}"""

_REFINE_PROMPT = """\
Here is a distilled context draft:

{draft}

The user says the following is wrong or missing:
"{correction}"

Produce a corrected version using the exact same format. \
Output only the corrected block, nothing else."""


def _build_transcript(messages: list, max_chars_per_msg: int = 800) -> str:
    lines = []
    for m in messages:
        role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) or ""
        if role in ("system", "tool"):
            continue
        content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
        if not content:
            continue
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if not content.strip():
            continue
        label = "USER" if role == "user" else "ASSISTANT"
        if len(content) > max_chars_per_msg:
            content = content[:max_chars_per_msg] + " [truncated]"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)


def _llm(client, model: str, prompt: str, gen_params: dict | None) -> str:
    messages = [{"role": "user", "content": prompt}]
    text, _ = agent._stream_response(client, model, messages, gen_params)
    return text.strip()


def _gate(prompt_text: str, allow_edit: bool = True) -> tuple[str, str]:
    """
    Show a prompt and return (action, extra_text).
    action is one of: "y", "e", "a"
    extra_text is the user's typed correction (only when action == "e").
    """
    choices = "[y]approve / [e]edit / [a]abort" if allow_edit else "[y]approve / [a]abort"
    # No ANSI codes in the prompt string — prompt_toolkit renders them literally.
    try:
        raw = ui_mod.prompt(f"\n{prompt_text} {choices}: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return "a", ""

    if raw == "y" or raw == "":
        return "y", ""
    if raw == "a":
        return "a", ""
    if allow_edit and raw == "e":
        try:
            correction = ui_mod.prompt("  What to change: ").strip()
        except (KeyboardInterrupt, EOFError):
            return "a", ""
        return "e", correction
    # Treat anything else typed as an inline correction
    if allow_edit:
        return "e", raw
    return "a", ""


def run(args: str, state: dict, client) -> str:
    messages = state.get("messages", [])
    model     = state["model"]
    gen_p     = state.get("gen_params") or None
    sid       = state.get("session_id", "unknown")

    if not messages:
        return "Nothing to distill — the conversation is empty."

    # Count non-system, non-empty turns
    turns = [m for m in messages
             if (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) not in ("system",)
             and (m.get("content") if isinstance(m, dict) else getattr(m, "content", ""))]
    if len(turns) < 2:
        return "Not enough conversation to distill (need at least one exchange)."

    print(f"\n{_DIM}  Session ID: {sid} — use /load {sid} to recover if needed{_RESET}\n")

    transcript = _build_transcript(messages)

    # --- Step 1: Goal resolution ---
    goal = args.strip()
    if goal:
        print(f"{_BOLD}Goal (provided):{_RESET} {goal}\n")
    else:
        print("Extracting goal from conversation...\n")
        goal = _llm(client, model, _GOAL_PROMPT.format(transcript=transcript), gen_p)
        if not goal:
            return "Distillation aborted — goal extraction returned empty response."

        action, correction = _gate("Is this the right goal?", allow_edit=True)
        if action == "a":
            return "Distillation aborted."
        if action == "e" and correction:
            goal = correction
            print(f"\n{_BOLD}Updated goal:{_RESET} {goal}\n")

    # --- Step 2: Draft distillation ---
    print("\nBuilding distilled context...\n")
    draft = _llm(client, model, _DISTILL_PROMPT.format(goal=goal, transcript=transcript), gen_p)
    if not draft:
        return "Distillation aborted — draft generation returned empty response."

    print(f"\n{_CYAN}{'─' * 60}{_RESET}")
    print(draft)
    print(f"{_CYAN}{'─' * 60}{_RESET}\n")

    # --- Step 3: User review gate ---
    action, correction = _gate("Approve this distilled context?", allow_edit=True)
    if action == "a":
        return "Distillation aborted — context unchanged."

    if action == "e" and correction:
        print("\nRefining...\n")
        refined = _llm(client, model, _REFINE_PROMPT.format(draft=draft, correction=correction), gen_p)
        if not refined:
            return "Distillation aborted — refinement returned empty response."
        draft = refined
        print(f"\n{_CYAN}{'─' * 60}{_RESET}")
        print(draft)
        print(f"{_CYAN}{'─' * 60}{_RESET}\n")

        action2, _ = _gate("Approve refined context?", allow_edit=False)
        if action2 == "a":
            return "Distillation aborted — context unchanged."

    # --- Step 4: Snapshot ---
    session_mod.save(state)
    print(f"{_DIM}  Snapshot saved as session '{sid}'{_RESET}")

    # --- Step 5: Replace context in-place ---
    # Preserve the original system prompt only (index 0 if role == system)
    orig_system = None
    if messages and (messages[0].get("role") if isinstance(messages[0], dict)
                     else getattr(messages[0], "role", "")) == "system":
        orig_system = messages[0]

    messages.clear()
    if orig_system:
        messages.append(orig_system)
    messages.append({"role": "system", "content": draft})

    state["usage"] = {}
    state["context_length"] = None

    print(f"\n{_BOLD}Context distilled.{_RESET} {len(messages)} message(s) in history. "
          f"Use /history to inspect.\n")
    return ""
