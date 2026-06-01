# skills/svg_artist.py — Generate an SVG file from a natural language prompt
#
# Usage: /skill svg_artist [prompt]
#
# Spawns a subagent with an SVG-specialist system prompt. The subagent
# generates a complete, valid SVG file and saves it to the workspace.
# The output path is printed so you can open it immediately.

import os
import re
import agent
import ui

SKILL_META = {
    "name":        "svg_artist",
    "description": "Generate an SVG file from a natural language description.",
    "version":     "1.0",
}

_SYSTEM_PROMPT = """\
You are an expert SVG illustrator. Your only output is valid, self-contained SVG markup.

Rules you must follow without exception:
1. Always produce a COMPLETE SVG file — opening <svg ...> tag through closing </svg>.
2. Set explicit width and height on the root <svg> element (e.g. width="800" height="600").
3. Use a viewBox that matches the width and height.
4. All colours must be explicit hex values or named SVG colours — never "currentColor".
5. Never rely on external files, fonts, or URLs. Embed everything inline.
6. Prefer clean, well-structured SVG: group related elements with <g>, use descriptive id attributes.
7. Add a <title> element inside <svg> that briefly describes the image.
8. Do not wrap the SVG in markdown code fences — output raw SVG only.
9. After generating the SVG, call write_file to save it. Choose a descriptive filename
   derived from the user's prompt, e.g. "sunset_landscape.svg", inside the "svg/" folder.
10. After saving, print exactly one line: SAVED:<path> where <path> is the full path returned
    by write_file. Do not print anything else after that line."""


def _extract_saved_path(text: str) -> str | None:
    """Parse the SAVED:<path> sentinel from the subagent output."""
    m = re.search(r"SAVED:(.+)", text)
    return m.group(1).strip() if m else None


def run(args: str, state: dict, client) -> str:
    prompt = args.strip()

    if not prompt:
        print()
        try:
            prompt = ui.prompt("  Describe the SVG image: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "Cancelled."

    if not prompt:
        return "No description provided — nothing to generate."

    print(f"\n\033[2m┌─ svg_artist {'─' * 38}\033[0m")
    print(f"\033[2m│ prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\033[0m")
    print("\033[2m│\033[0m")

    result = agent.run_subagent(
        client,
        state["model"],
        f"Generate an SVG image for the following description:\n\n{prompt}",
        system_prompt=_SYSTEM_PROMPT,
        verbose=True,
        gen_params=state.get("gen_params") or None,
        state=state,
    )

    print(f"\033[2m└─ svg_artist done {'─' * 33}\033[0m")

    saved = _extract_saved_path(result)
    if saved:
        print(f"\n\033[1mSaved:\033[0m {saved}")
        # Offer to open in the default browser
        try:
            ans = ui.prompt("  Open in browser? [y/N] ").strip().lower()
            if ans == "y":
                import subprocess, sys
                subprocess.Popen(
                    ["cmd", "/c", "start", "", saved] if sys.platform == "win32"
                    else (["open", saved] if sys.platform == "darwin" else ["xdg-open", saved])
                )
        except (EOFError, KeyboardInterrupt):
            pass

    return ""
