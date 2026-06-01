# ui.py — Shared prompt_toolkit session, tab completion, and toolbar state
#
# All interactive I/O goes through this module:
#   - prompt()  : replaces input() everywhere
#   - patch_stdout : used as context manager around streaming output
#   - toolbar_state: dict updated by main.py and /model to keep the bar current
#
# Multiline input:
#   Press Alt+Enter (or Esc then Enter) to insert a newline.
#   Press Enter alone to submit.
#
# Syntax highlighting:
#   /commands are shown in cyan; their arguments in the default colour.
#
# Ghost completions:
#   The most-recently-used matching input appears as a dim ghost after the
#   cursor; press → or End to accept it.

import os

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.patch_stdout import patch_stdout  # re-exported for callers
from prompt_toolkit.shortcuts import clear            # re-exported for /cls

# ---------------------------------------------------------------------------
# Toolbar state — mutable dict; updated at runtime without recreating session
# ---------------------------------------------------------------------------

toolbar_state: dict = {
    "model":      "",
    "session_id": "",
}


def get_toolbar() -> HTML:
    """Called by prompt_toolkit on every redraw of the bottom toolbar."""
    m = toolbar_state.get("model", "")
    s = toolbar_state.get("session_id", "")
    return HTML(
        f" <b>model:</b> {m}"
        f"  \u2502  "
        f"<b>session:</b> {s}"
        f"  \u2502  "
        f"<style fg='ansidarkgray'>/help \u00b7 /exit</style>"
    )


# ---------------------------------------------------------------------------
# Tab completer — reads _commands registry lazily to avoid circular imports
# ---------------------------------------------------------------------------

class SlashCompleter(Completer):
    """Complete /commands from the live commands registry."""

    def get_completions(self, document, complete_event):
        import commands as cmd_mod
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        word = text[1:]  # everything typed after the slash
        for name in sorted(cmd_mod._commands.keys()):
            if name.startswith(word):
                _, help_text = cmd_mod._commands[name]
                yield Completion(
                    "/" + name,
                    start_position=-len(text),
                    display_meta=help_text,
                )


# ---------------------------------------------------------------------------
# Syntax highlighter — colours /commands cyan, arguments default
# ---------------------------------------------------------------------------

class SlashLexer(Lexer):
    """
    Highlight the first token as a command (cyan+bold) when the line starts
    with '/', leaving the rest of the line in the default colour.
    """

    def lex_document(self, document):
        lines = document.lines

        def get_line(lineno):
            line = lines[lineno]
            if lineno == 0 and line.startswith("/"):
                # Split into command token and everything after
                parts = line.split(" ", 1)
                cmd   = parts[0]
                rest  = (" " + parts[1]) if len(parts) > 1 else ""
                tokens = [("class:slash-command", cmd)]
                if rest:
                    tokens.append(("", rest))
                return tokens
            return [("", line)]

        return get_line


# ---------------------------------------------------------------------------
# Key bindings — Alt+Enter inserts newline; plain Enter submits
# ---------------------------------------------------------------------------

_bindings = KeyBindings()


@_bindings.add("enter")
def _submit(event):
    """Plain Enter always submits."""
    event.current_buffer.validate_and_handle()


@_bindings.add("escape", "enter")   # Alt+Enter on most terminals
def _insert_newline(event):
    """Alt+Enter inserts a literal newline for multiline messages."""
    event.current_buffer.insert_text("\n")


# ---------------------------------------------------------------------------
# History file — persists across sessions
# ---------------------------------------------------------------------------

_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".harness_history")


# ---------------------------------------------------------------------------
# Singleton PromptSession — created once, reused for every input
# ---------------------------------------------------------------------------

session: PromptSession = PromptSession(
    completer=SlashCompleter(),
    complete_while_typing=False,      # complete only on Tab
    auto_suggest=AutoSuggestFromHistory(),
    history=FileHistory(_HISTORY_FILE),
    lexer=SlashLexer(),
    key_bindings=_bindings,
    multiline=True,                   # allows \n in the buffer
    prompt_continuation=lambda w, l, ws: " " * w,  # indent continuation lines
    bottom_toolbar=get_toolbar,
    refresh_interval=1.0,
    style_transformation=None,
    # Colour for /command tokens defined via style
)

# Patch the style so slash-command tokens render in cyan+bold.
# We do it after session creation to avoid importing Style before session.
from prompt_toolkit.styles import Style as _Style
session.app.style = _Style.from_dict({
    "slash-command": "bold ansicyan",
})


def prompt(message: str = "") -> str:
    """
    Display a prompt and return the user's input.
    Raises EOFError on Ctrl+D and KeyboardInterrupt on Ctrl+C.

    Multiline note: plain Enter submits; Alt+Enter inserts a newline.
    """
    return session.prompt(message)
