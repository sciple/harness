# tools/run_python.py — Execute a Python snippet in a sandboxed subprocess
#
# The snippet runs in a fresh Python process with:
#   - cwd set to WORKSPACE_ROOT (workspace-confined by convention)
#   - a hard wall-clock timeout (default 15 s, overridable per-call)
#   - stdout + stderr captured and returned to the LLM
#   - no network or import restrictions (user approves each run via confirm:True)

import sys
import subprocess
import tools
import config

_DEFAULT_TIMEOUT = 15   # seconds


def run_python(code: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """
    Execute `code` in a subprocess and return captured stdout + stderr.
    The working directory is WORKSPACE_ROOT.
    """
    timeout = max(1, min(int(timeout), 120))   # clamp 1-120 s

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=config.WORKSPACE_ROOT,
        )
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {timeout} seconds."
    except Exception as e:
        return f"Error: could not launch subprocess: {e}"

    out  = result.stdout.rstrip()
    err  = result.stderr.rstrip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    if result.returncode != 0 and not err:
        parts.append(f"[exit code {result.returncode}]")
    return "\n".join(parts) if parts else "(no output)"


TOOL_SCHEMA = {
    "type": "function",
    "confirm": True,
    "no_truncate": True,
    "function": {
        "name": "run_python",
        "description": (
            "Execute a Python code snippet in a sandboxed subprocess and return its output. "
            "Use this to perform calculations, data processing, file parsing, or any task "
            "that benefits from running actual code rather than reasoning about it. "
            "The working directory is the workspace root. "
            "stdout and stderr are captured and returned. "
            "Do NOT use this to modify harness files or install packages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Valid Python source code to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        f"Maximum execution time in seconds (1-120). "
                        f"Defaults to {_DEFAULT_TIMEOUT}."
                    ),
                },
            },
            "required": ["code"],
        },
    },
}

tools.register(TOOL_SCHEMA, run_python)
