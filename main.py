# main.py — Interactive REPL for the local LLM harness
#
# Usage:
#   python main.py
#   python main.py --model "google/gemma-4-e4b"
#   python main.py --base-url http://127.0.0.1:11434/v1/   # Ollama
#
# Type /help inside the session for available commands.

import argparse
import sys

import agent
import commands  # noqa: F401 — registers built-in slash commands
import session
import tools     # noqa: F401 — registers built-in tools
import ui
from config import DEFAULT_MODEL, LOCAL_API_BASE, SYSTEM_PROMPT, SESSION_AUTOSAVE, DEFAULT_GEN_PARAMS


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local LLM harness")
    p.add_argument("--model",     default=DEFAULT_MODEL,  help="Model name (default: %(default)s)")
    p.add_argument("--base-url",  default=LOCAL_API_BASE, help="API base URL (default: %(default)s)")
    p.add_argument("--system",    default=SYSTEM_PROMPT,  help="Override the system prompt")
    p.add_argument("--quiet",     action="store_true",    help="Suppress tool-call verbose output")
    p.add_argument("--load",      default=None,           help="Resume a session by ID")
    return p.parse_args()


_ASCII_ART = """\
\033[96m    o─────o─────o─────o
    │╲   ╱│╲   ╱│╲   ╱│
    │ ╲ ╱ │ ╲ ╱ │ ╲ ╱ │
    o──X──o──X──o──X──o
    │ ╱ ╲ │ ╱ ╲ │ ╱ ╲ │
    │╱   ╲│╱   ╲│╱   ╲│
    o─────o─────o─────o\033[0m
\033[1m    LOCAL LLM HARNESS\033[0m  \033[2mrunning on your machine\033[0m"""


def print_banner(model: str, base_url: str, session_id: str) -> None:
    print()
    print(_ASCII_ART)
    print()
    print(f"  \033[2mModel   :\033[0m {model}")
    print(f"  \033[2mEndpoint:\033[0m {base_url}")
    print(f"  \033[2mSession :\033[0m {session_id}")
    print(f"  \033[2mCommands:\033[0m /help  /exit")
    print()


def repl(args: argparse.Namespace) -> None:
    try:
        client = agent.make_client()
    except Exception as e:
        print(f"Failed to initialize client: {e}")
        sys.exit(1)

    session.ensure_dir()
    session_id = session.new_id()

    # Mutable session state — shared with command handlers
    state: dict = {
        "model":          args.model,
        "messages":       agent.new_conversation(args.system),
        "running":        True,
        "client":         client,
        "usage":          {},     # last turn's token counts
        "context_length": None,   # fetched lazily
        "session_id":     session_id,
        "gen_params":     DEFAULT_GEN_PARAMS.copy(),  # runtime overrides: temperature, top_p, etc.
        "skip_confirm":   False,  # set True by skills that run non-interactively
    }

    # Resume a previous session if requested
    if args.load:
        loaded = session.load(args.load)
        if loaded is None:
            print(f"Session '{args.load}' not found.")
            sys.exit(1)
        state["messages"] = loaded
        state["session_id"] = args.load
        print(f"Resumed session '{args.load}' ({len(loaded)} messages).")
    elif SESSION_AUTOSAVE:
        session.save(state)  # create the file immediately

    # Initialise toolbar with current model and session
    ui.toolbar_state["model"]      = state["model"]
    ui.toolbar_state["session_id"] = state["session_id"]

    print_banner(state["model"], args.base_url, state["session_id"])

    while state["running"]:
        try:
            user_input = ui.prompt("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        # Check for slash commands first
        handled, output = commands.dispatch(user_input, state)
        if handled:
            if output:
                print(output)
            if SESSION_AUTOSAVE:
                session.save(state)
            continue

        # Regular message — append to history and call the agent
        state["messages"].append({"role": "user", "content": user_input})

        # Lazily fetch context length for compression
        if state["context_length"] is None:
            state["context_length"] = agent.get_context_length(client, state["model"])

        print(f"\n\033[96;1mAssistant:\033[0m ", end="", flush=True)
        try:
            agent.chat(
                client,
                state["model"],
                state["messages"],
                verbose=not args.quiet,
                usage_out=state["usage"],
                gen_params=state["gen_params"] or None,
                context_length=state["context_length"],
                state=state,
            )
        except KeyboardInterrupt:
            print("\n[interrupted]")
            state["messages"].pop()
            continue
        except Exception as e:
            print(f"\nError: {e}")
            state["messages"].pop()
            continue

        if SESSION_AUTOSAVE:
            session.save(state)


if __name__ == "__main__":
    repl(parse_args())
