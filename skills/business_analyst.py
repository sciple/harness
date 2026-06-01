# skills/business_analyst.py — Idea decomposition via a focused subagent
#
# Usage: /skill business_analyst [idea]
#
# If no idea is passed as an argument, the skill prompts the user for one.
# A subagent named "business_analyst" then analyses the idea and produces:
#   - Core Subject        : domain, actor, and central problem or opportunity
#   - Objectives          : primary and secondary goals
#   - Implied Constraints : unstated but realistic limitations
#   - Missing Information : open questions that must be answered before proceeding

import agent
import ui

SKILL_META = {
    "name":        "business_analyst",
    "description": "Decompose an idea into core subject, objectives, implied constraints, and missing information.",
    "version":     "1.0",
}

_SYSTEM_PROMPT = """\
You are a senior business analyst. Your role is to rigorously decompose ideas submitted \
by the user into structured components. For every idea you receive, produce the following \
sections — always in this order, always using these exact headings:

## Core Subject
What this idea is fundamentally about. Identify the domain, the actor, and the problem \
or opportunity at its centre. One short paragraph.

## Objectives
What the idea aims to achieve. Use bullet points. Be specific and action-oriented. \
Distinguish between primary objectives (must achieve) and secondary ones (nice to have).

## Implied Constraints
Limitations, boundaries, or assumptions that are not stated explicitly but are implied \
by the idea itself. Include technical, organisational, financial, regulatory, or \
time-related constraints that any realistic execution would face.

## Missing Information
What is currently unclear, undefined, or needs to be answered before this idea can \
be properly evaluated or executed. Frame every item as a direct question.

Be thorough but concise. Do not add commentary outside these sections."""


def run(args: str, state: dict, client) -> str:
    idea = args.strip()

    if not idea:
        print()
        try:
            idea = ui.prompt("  Describe your idea: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "Cancelled."

    if not idea:
        return "No idea provided — nothing to analyse."

    print(f"\n\033[2m┌─ business_analyst {'─' * 32}\033[0m")
    print(f"\033[2m│ idea: {idea[:100]}{'...' if len(idea) > 100 else ''}\033[0m")
    print("\033[2m│\033[0m")

    agent.run_subagent(
        client,
        state["model"],
        f"Please analyse the following idea:\n\n{idea}",
        system_prompt=_SYSTEM_PROMPT,
        verbose=False,   # no tool calls expected — suppress tool scaffolding
        gen_params=state.get("gen_params") or None,
        state=state,
    )

    print(f"\033[2m└─ business_analyst done {'─' * 28}\033[0m\n")
    return ""
