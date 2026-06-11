# config.py — Central configuration for the local LLM harness

import os

# Harness installation directory (where this file lives)
_HARNESS_ROOT = os.path.dirname(os.path.realpath(__file__))

# LM Studio / Ollama / any OpenAI-compatible endpoint
LOCAL_API_BASE = "http://127.0.0.1:1234/v1/"
DUMMY_API_KEY = "lmstudio-dummy-key"

# Default model name — override at runtime with /model <name>
# DEFAULT_MODEL = "google/gemma-4-e4b"
# DEFAULT_MODEL =  "mistralai/ministral-3-3b"
# DEFAULT_MODEL = "ibm/granite-4-h-tiny"
# DEFAULT_MODEL = "nvidia/nemotron-3-nano-4b"
DEFAULT_MODEL = "granite-4.1-8b"

# Models available for selection via /model (edit this list freely)
AVAILABLE_MODELS: list[str] = [
    "granite-4.1-8b",
]
# DEFAULT_MODEL = "apertus-8b-instruct-2509"

# Root directory that write_file (and similar tools) must stay inside.
WORKSPACE_ROOT: str = os.path.join(_HARNESS_ROOT, "workspace")

# System prompt injected at the start of every conversation
SYSTEM_PROMPT = (
    "You are a helpful AI assistant running locally on a Windows machine. "
    "You have access to tools — use them whenever they are the right fit. "
    "Be concise and accurate. "
    f"The workspace root is: {WORKSPACE_ROOT}. "
    "All files you write or create land inside the workspace root. "
    "When looking for a file you created, always search the workspace root first. "
    "Use the glob tool (pattern='*' or '**/*') to see workspace contents. "
    "When referring to paths, always use Windows-style absolute paths or paths "
    "relative to the workspace root. Never assume Unix paths like /tmp or /home. "
    "When writing code or any text that will be saved to a file, use only "
    "plain ASCII characters. Do not use typographic quotes (‘’“”), "
    "em-dashes (—), ellipsis (…), or any other non-ASCII Unicode characters. "
    "Always use straight ASCII quotes (' and \\\"), hyphens (-), and three dots (...). "
    "You must never write to or modify harness infrastructure files such as main.py, "
    "agent.py, config.py, session.py, any __init__.py, .env files, or the sessions/ "
    "and .git/ directories. These are protected and any attempt will be refused."
)

# Maximum number of consecutive tool-call rounds before forcing a final answer
MAX_TOOL_ROUNDS = 10

# Runtime data directory (sessions, notes — gitignored)
DATA_DIR: str = os.path.join(_HARNESS_ROOT, "data")

# --- Session persistence ---
SESSIONS_DIR: str = os.path.join(DATA_DIR, "sessions")
SESSION_AUTOSAVE: bool = True

# --- Context window auto-management ---
CONTEXT_PRESSURE_THRESHOLD: float = 0.80   # compress when this fraction is used
CONTEXT_SUMMARY_KEEP_RECENT: int = 4        # number of recent turns to always preserve

# --- Tool retry policy ---
TOOL_RETRY_MAX: int = 2          # max retries after a tool error (0 = no retry)
TOOL_RETRY_CONFIRM: bool = False  # ask the user before each retry

# --- Tool output truncation ---
TOOL_OUTPUT_MAX_CHARS: int = 16000    # truncate tool results longer than this
TOOL_OUTPUT_STORE: bool = True       # keep full outputs for get_tool_output

# --- Generation parameters (overridable at runtime with /set) ---
ALLOWED_GEN_PARAMS: dict = {
    "temperature": float,
    "top_p":       float,
    "max_tokens":  int,
    "seed":        int,
}

# Default generation parameters sent with every request.
# max_tokens overrides the server-side default (LM Studio defaults to 4000).
DEFAULT_GEN_PARAMS: dict = {
    "max_tokens": 32768,
}

# --- Skills ---
SKILLS_DIR: str = os.path.join(_HARNESS_ROOT, "skills")

# ---------------------------------------------------------------------------
# File safeguards
# ---------------------------------------------------------------------------
# Absolute paths of harness core files that tools must never overwrite.
PROTECTED_FILES: frozenset = frozenset(
    os.path.realpath(os.path.join(_HARNESS_ROOT, name))
    for name in (
        "main.py",
        "agent.py",
        "config.py",
        "session.py",
        "commands/__init__.py",
        "tools/__init__.py",
        "skills/__init__.py",
    )
)

# Filename patterns that are always protected regardless of location.
# Matched against the bare filename (case-insensitive on Windows).
PROTECTED_FILENAME_PATTERNS: tuple = (
    "__init__.py",          # any package init
    ".env",                 # secrets
    "*.env",                # any .env variant
    "requirements.txt",     # dependencies
    "pyproject.toml",       # build config
    "setup.py",             # legacy build
    "setup.cfg",            # legacy build
)

# Directory names whose contents are always protected.
PROTECTED_DIRS: frozenset = frozenset(
    os.path.realpath(os.path.join(_HARNESS_ROOT, name))
    for name in (
        ".git",
        "data",
        "__pycache__",
    )
)
