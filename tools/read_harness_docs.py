import os
import tools


def read_harness_docs() -> str:
    """Return the condensed harness reference document."""
    docs_path = os.path.join(os.path.dirname(__file__), "..", "harness_docs.md")
    docs_path = os.path.realpath(docs_path)
    try:
        with open(docs_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: harness_docs.md not found."


TOOL_SCHEMA = {
    "type": "function",
    "no_truncate": True,
    "function": {
        "name": "read_harness_docs",
        "description": (
            "Return the harness reference documentation. "
            "Call this when the user asks how the harness works, what tools or commands "
            "are available, how to configure it, what skills exist, or any question "
            "about the harness architecture or behaviour."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

tools.register(TOOL_SCHEMA, read_harness_docs)
