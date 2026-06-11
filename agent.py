# agent.py — Core agentic loop
#
# Responsibilities:
#   - Maintain a conversation (list of messages) across turns
#   - Send messages to the local LLM via the OpenAI-compatible API
#   - Handle tool calls returned by the model (auto dispatch, multi-round)
#   - Stream final text responses token-by-token to stdout
#   - Return the full assembled text to the caller

import itertools
import json
import sys
import threading
import time
from openai import OpenAI

import tools as tool_registry
from config import (
    LOCAL_API_BASE, DUMMY_API_KEY, SYSTEM_PROMPT, MAX_TOOL_ROUNDS,
    TOOL_RETRY_MAX, TOOL_RETRY_CONFIRM,
    CONTEXT_PRESSURE_THRESHOLD, CONTEXT_SUMMARY_KEEP_RECENT,
)

# ANSI styles
_THINK_CONTENT = "\033[2;3m"    # dim + italic — thinking token stream
_THINK_BOX     = "\033[2m"      # dim only    — box frame lines
_RESET         = "\033[0m"
_DIM           = "\033[2m"
ASSISTANT_COLOR = "\033[96m"    # bright cyan for assistant text

# Thinking box helpers
_BOX_WIDTH = 52

def _think_open() -> None:
    fill = "\u2500" * (_BOX_WIDTH - len(" thinking "))
    print(f"\n{_THINK_BOX}  \u250c\u2500 thinking {fill}{_RESET}", flush=True)

def _think_close() -> None:
    fill = "\u2500" * (_BOX_WIDTH - len(" done "))
    print(f"\n{_THINK_BOX}  \u2514\u2500 done {fill}{_RESET}\n", flush=True)

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ---------------------------------------------------------------------------
# Thinking tag registry — add new model variants here
# Each entry is (open_tag, close_tag).  The scanner tries all pairs.
# ---------------------------------------------------------------------------
_THINK_TAG_PAIRS: list[tuple[str, str]] = [
    ("<think>",          "</think>"),    # DeepSeek, Qwen, most OSS models
    ("<|channel>thought", "<channel|>"), # Gemma 4
]


def _find_think_open(text: str) -> tuple[int, str, str] | None:
    """
    Return (position, open_tag, close_tag) for the earliest thinking open tag
    found in *text*, or None if no open tag is present.
    """
    best: tuple[int, str, str] | None = None
    for open_tag, close_tag in _THINK_TAG_PAIRS:
        pos = text.find(open_tag)
        if pos != -1 and (best is None or pos < best[0]):
            best = (pos, open_tag, close_tag)
    return best


def _set_title(text: str) -> None:
    print(f"\033]0;{text}\007", end="", flush=True)


def _run_spinner(stop: threading.Event, token_counter: list) -> None:
    for frame in itertools.cycle(_SPINNER_FRAMES):
        if stop.is_set():
            break
        n = token_counter[0]
        label = f"{frame} generating… {n} tok" if n else f"{frame} thinking…"
        print(f"\r{label}   ", end="", flush=True)
        time.sleep(0.08)
    print("\r" + " " * 30 + "\r", end="", flush=True)


def make_client() -> OpenAI:
    return OpenAI(api_key=DUMMY_API_KEY, base_url=LOCAL_API_BASE)


def get_context_length(client: OpenAI, model: str) -> int | None:
    """Query /v1/models for the model's maximum context length.

    The OpenAI SDK strips unknown fields, so we use the raw HTTP client to
    preserve LM Studio's extra fields (max_context_length, context_length).
    """
    try:
        import httpx
        resp = httpx.get(
            str(client.base_url).rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {client.api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        for m in resp.json().get("data", []):
            if m.get("id") == model:
                ctx = m.get("max_context_length") or m.get("context_length")
                return int(ctx) if ctx else None
    except Exception:
        pass
    return None


def load_model(client, model_id: str) -> tuple[bool, str]:
    """Ask the LM Studio backend to load model_id. Best-effort — returns (ok, msg)."""
    import httpx
    base = str(client.base_url).rstrip("/").removesuffix("/v1")
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "application/json"}
    try:
        r = httpx.post(f"{base}/api/v0/models/load",
                       json={"identifier": model_id},
                       headers=headers, timeout=120)
        if r.status_code == 200:
            return True, "loaded"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def unload_model(client, model_id: str) -> tuple[bool, str]:
    """Ask the LM Studio backend to unload model_id. Best-effort — returns (ok, msg)."""
    import httpx
    base = str(client.base_url).rstrip("/").removesuffix("/v1")
    headers = {"Authorization": f"Bearer {client.api_key}",
               "Content-Type": "application/json"}
    try:
        r = httpx.post(f"{base}/api/v0/models/unload",
                       json={"identifier": model_id},
                       headers=headers, timeout=30)
        if r.status_code == 200:
            return True, "unloaded"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def _stream_response(
    client: OpenAI,
    model: str,
    messages: list[dict],
    gen_params: dict | None = None,
) -> tuple[str, dict | None]:
    """
    Stream a response from the model token-by-token.

    Thinking tokens (<think> tags or reasoning_content field) are shown in
    dim/italic yellow. Returns (final_answer_text, usage_dict | None).
    """
    token_counter = [0]
    stop_spinner = threading.Event()
    spinner = threading.Thread(target=_run_spinner, args=(stop_spinner, token_counter), daemon=True)
    spinner.start()
    t_start = time.monotonic()

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **(gen_params or {}),
        )
    except Exception:
        stop_spinner.set()
        spinner.join()
        _set_title("harness")
        raise

    answer_chunks: list[str] = []
    in_think_tag = False
    think_close_tag = "</think>"     # updated when an open tag is matched
    using_reasoning_field = False    # True when thinking came via reasoning_content field
    pending = ""
    usage: dict | None = None
    first_token = True

    for chunk in stream:
        if chunk.usage:
            usage = {
                "prompt_tokens":     chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens":      chunk.usage.total_tokens,
            }

        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        has_content = (delta.content or getattr(delta, "reasoning_content", None))

        if first_token and has_content:
            stop_spinner.set()
            spinner.join()
            first_token = False

        if has_content:
            token_counter[0] += 1
            _set_title(f"⟨{token_counter[0]} tok⟩")

        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            if not in_think_tag:
                _think_open()
                in_think_tag = True
                using_reasoning_field = True
            print(f"{_THINK_CONTENT}{reasoning}{_RESET}", end="", flush=True)

        token = delta.content or ""
        if not token:
            continue

        # For reasoning_content-based models the </think> tag never appears in
        # delta.content — close the thinking block as soon as answer tokens arrive.
        if in_think_tag and using_reasoning_field:
            _think_close()
            in_think_tag = False
            using_reasoning_field = False
            # Some models (e.g. Gemma4) emit a thinking open-tag marker at the
            # start of delta.content right after reasoning_content ends.
            # Strip it so we don't re-enter thinking mode for the answer.
            for _ot, _ in _THINK_TAG_PAIRS:
                if token.startswith(_ot):
                    token = token[len(_ot):]
                    break

        pending += token
        while pending:
            if in_think_tag:
                end = pending.find(think_close_tag)
                if end == -1:
                    print(f"{_THINK_CONTENT}{pending}{_RESET}", end="", flush=True)
                    pending = ""
                else:
                    print(f"{_THINK_CONTENT}{pending[:end]}{_RESET}", flush=True)
                    _think_close()
                    in_think_tag = False
                    pending = pending[end + len(think_close_tag):]
            else:
                match = _find_think_open(pending)
                if match is None:
                    print(f"{ASSISTANT_COLOR}{pending}{_RESET}", end="", flush=True)
                    answer_chunks.append(pending)
                    pending = ""
                else:
                    start, open_tag, close_tag = match
                    before = pending[:start]
                    if before:
                        print(f"{ASSISTANT_COLOR}{before}{_RESET}", end="", flush=True)
                        answer_chunks.append(before)
                    _think_open()
                    in_think_tag = True
                    think_close_tag = close_tag
                    pending = pending[start + len(open_tag):]

    stop_spinner.set()
    spinner.join()

    elapsed = time.monotonic() - t_start
    _set_title("harness")

    if in_think_tag:
        _think_close()

    print()

    completion_tok = usage["completion_tokens"] if usage else token_counter[0]
    prompt_tok = usage["prompt_tokens"] if usage else "?"
    tok_per_sec = completion_tok / elapsed if elapsed > 0 else 0
    print(
        f"{_DIM}  ↳ {completion_tok} tokens out · {prompt_tok} in · "
        f"{elapsed:.1f}s · {tok_per_sec:.1f} tok/s{_RESET}",
        flush=True,
    )

    return "".join(answer_chunks), usage


def _stream_or_tools(
    client: OpenAI,
    model: str,
    messages: list[dict],
    schemas: list[dict] | None,
    gen_params: dict | None = None,
) -> tuple[str, list | None, dict | None]:
    """
    Single streaming call that handles both text responses and tool calls.

    Returns one of:
      (text, None, usage)        — model responded with plain text (already printed)
      ("", tool_calls, usage)    — model wants to call tools (accumulated silently)

    Tool-call argument fragments are concatenated per tool index before being
    returned, so callers receive complete JSON strings ready for json.loads().
    """
    token_counter = [0]
    stop_spinner = threading.Event()
    spinner = threading.Thread(target=_run_spinner, args=(stop_spinner, token_counter), daemon=True)
    spinner.start()
    t_start = time.monotonic()

    create_kwargs: dict = {"stream": True, "stream_options": {"include_usage": True}}
    if schemas:
        create_kwargs["tools"] = schemas
        create_kwargs["tool_choice"] = "auto"
    if gen_params:
        create_kwargs.update(gen_params)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            **create_kwargs,
        )
    except Exception:
        stop_spinner.set()
        spinner.join()
        _set_title("harness")
        raise

    # Accumulators
    answer_chunks: list[str] = []
    tool_acc: dict[int, dict] = {}   # index -> {id, name, arguments}
    in_think_tag = False
    think_close_tag = "</think>"     # updated when an open tag is matched
    using_reasoning_field = False    # True when thinking came via reasoning_content field
    pending = ""
    usage: dict | None = None
    first_token = True
    is_tool_call = False

    for chunk in stream:
        if chunk.usage:
            usage = {
                "prompt_tokens":     chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens":      chunk.usage.total_tokens,
            }

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason

        # --- Tool-call delta accumulation ---
        if delta.tool_calls:
            is_tool_call = True
            for tc_delta in delta.tool_calls:
                i = tc_delta.index
                if i not in tool_acc:
                    tool_acc[i] = {
                        "id":        tc_delta.id or "",
                        "name":      (tc_delta.function.name or "") if tc_delta.function else "",
                        "arguments": "",
                    }
                if tc_delta.function and tc_delta.function.arguments:
                    tool_acc[i]["arguments"] += tc_delta.function.arguments
                # Fill in id/name if they arrive in later chunks
                if tc_delta.id and not tool_acc[i]["id"]:
                    tool_acc[i]["id"] = tc_delta.id
                if tc_delta.function and tc_delta.function.name and not tool_acc[i]["name"]:
                    tool_acc[i]["name"] = tc_delta.function.name
            continue  # don't process as text

        # --- Text delta streaming ---
        has_content = (delta.content or getattr(delta, "reasoning_content", None))

        if first_token and has_content:
            stop_spinner.set()
            spinner.join()
            first_token = False

        if has_content:
            token_counter[0] += 1
            _set_title(f"⟨{token_counter[0]} tok⟩")

        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            if not in_think_tag:
                _think_open()
                in_think_tag = True
                using_reasoning_field = True
            print(f"{_THINK_CONTENT}{reasoning}{_RESET}", end="", flush=True)

        token = delta.content or ""
        if not token:
            continue

        # For reasoning_content-based models the </think> tag never appears in
        # delta.content — close the thinking block as soon as answer tokens arrive.
        if in_think_tag and using_reasoning_field:
            _think_close()
            in_think_tag = False
            using_reasoning_field = False
            # Some models (e.g. Gemma4) emit a thinking open-tag marker at the
            # start of delta.content right after reasoning_content ends.
            # Strip it so we don't re-enter thinking mode for the answer.
            for _ot, _ in _THINK_TAG_PAIRS:
                if token.startswith(_ot):
                    token = token[len(_ot):]
                    break

        pending += token
        while pending:
            if in_think_tag:
                end = pending.find(think_close_tag)
                if end == -1:
                    print(f"{_THINK_CONTENT}{pending}{_RESET}", end="", flush=True)
                    pending = ""
                else:
                    print(f"{_THINK_CONTENT}{pending[:end]}{_RESET}", flush=True)
                    _think_close()
                    in_think_tag = False
                    pending = pending[end + len(think_close_tag):]
            else:
                match = _find_think_open(pending)
                if match is None:
                    print(f"{ASSISTANT_COLOR}{pending}{_RESET}", end="", flush=True)
                    answer_chunks.append(pending)
                    pending = ""
                else:
                    start, open_tag, close_tag = match
                    before = pending[:start]
                    if before:
                        print(f"{ASSISTANT_COLOR}{before}{_RESET}", end="", flush=True)
                        answer_chunks.append(before)
                    _think_open()
                    in_think_tag = True
                    think_close_tag = close_tag
                    pending = pending[start + len(open_tag):]

    stop_spinner.set()
    spinner.join()
    _set_title("harness")

    # --- Tool call response: return accumulated tool calls ---
    if is_tool_call:
        # Build simple namespace objects compatible with the rest of the call site
        tool_calls = [_ToolCall(d) for d in (tool_acc[k] for k in sorted(tool_acc))]
        return "", tool_calls, usage

    # --- Text response: finalise and print stats ---
    elapsed = time.monotonic() - t_start

    if in_think_tag:
        _think_close()

    print()

    completion_tok = usage["completion_tokens"] if usage else token_counter[0]
    prompt_tok = usage["prompt_tokens"] if usage else "?"
    tok_per_sec = completion_tok / elapsed if elapsed > 0 else 0
    print(
        f"{_DIM}  ↳ {completion_tok} tokens out · {prompt_tok} in · "
        f"{elapsed:.1f}s · {tok_per_sec:.1f} tok/s{_RESET}",
        flush=True,
    )

    return "".join(answer_chunks), None, usage


class _ToolCall:
    """Lightweight stand-in for the OpenAI SDK ChoiceDeltaToolCall object."""

    class _Fn:
        def __init__(self, name: str, arguments: str) -> None:
            self.name = name
            self.arguments = arguments

    def __init__(self, d: dict) -> None:
        self.id = d["id"]
        self.function = self._Fn(d["name"], d["arguments"])


def _execute_tool_with_retry(
    fn_name: str,
    fn_args: dict,
    tool_call_id: str,
    verbose: bool,
    state: dict,
) -> str:
    """
    Execute a tool with:
      - User confirmation if the tool is marked as requiring it
      - Automatic retry on error (up to TOOL_RETRY_MAX times)
      - Optional per-retry confirmation prompt (TOOL_RETRY_CONFIRM)

    Returns the final result string.
    """
    # Confirmation before first execution
    if tool_registry.requires_confirmation(fn_name) and not state.get("skip_confirm"):
        print(f"\n  [confirm] '{fn_name}' is a destructive tool.")
        print(f"  Args: {json.dumps(fn_args, ensure_ascii=False)}")
        import ui as _ui
        answer = _ui.prompt("  Proceed? [y/N] ").strip().lower()
        if answer != "y":
            return (
                "CANCELLED: The user explicitly declined to run this tool. "
                "The action was NOT performed and NO changes were made. "
                "Inform the user that the action was cancelled and do not "
                "claim or imply that it succeeded."
            )

    result = tool_registry.dispatch(fn_name, fn_args)
    retries_left = min(TOOL_RETRY_MAX, 5)  # hard cap at 5

    while result.startswith("Error:") and retries_left > 0:
        attempt = TOOL_RETRY_MAX - retries_left + 1
        if verbose:
            print(f"  [retry {attempt}/{TOOL_RETRY_MAX}] {fn_name}: {result}")
        if TOOL_RETRY_CONFIRM:
            import ui as _ui
            answer = _ui.prompt(f"  Retry '{fn_name}'? [y/N] ").strip().lower()
            if answer != "y":
                break
        retries_left -= 1
        result = tool_registry.dispatch(fn_name, fn_args)

    return result


def _get_role(m) -> str:
    if isinstance(m, dict):
        return (m.get("role") or "").lower()
    return (getattr(m, "role", "") or "").lower()


def _get_tool_calls(m):
    if isinstance(m, dict):
        return m.get("tool_calls")
    return getattr(m, "tool_calls", None)


def _safe_compress_boundary(messages: list, sys_end: int, keep_from: int) -> int:
    """
    Adjust keep_from so it does not split a tool-call/result group.

    A group is: one assistant message with tool_calls + all following tool messages.
    We push keep_from forward if it would land on an orphaned tool-result, or pull
    it back if the message just before it is an assistant message with tool_calls.
    """
    total = len(messages)
    i = keep_from
    # Iterate until stable
    changed = True
    while changed and sys_end < i < total:
        changed = False
        # If the message at i is a tool-result, it must be kept with its pair — push forward
        if _get_role(messages[i]) == "tool":
            i += 1
            changed = True
            continue
        # If the message just before i is an assistant-with-tool-calls,
        # the tool results that follow it are still inside the compressible slice —
        # pull back to exclude the whole group
        if i > sys_end:
            prev = messages[i - 1]
            if _get_role(prev) == "assistant" and _get_tool_calls(prev):
                i -= 1
                changed = True
    return i


def _maybe_compress(
    client: OpenAI,
    model: str,
    messages: list[dict],
    usage: dict,
    context_length: int | None,
    gen_params: dict | None = None,
) -> bool:
    """
    If the context is above CONTEXT_PRESSURE_THRESHOLD, summarise the oldest
    non-system, non-recent turns into a single compressed message.
    Returns True if compression happened.
    """
    if not context_length or not usage:
        return False

    ratio = usage.get("total_tokens", 0) / context_length
    if ratio < CONTEXT_PRESSURE_THRESHOLD:
        return False

    # Find system message (always index 0 if present)
    sys_end = 1 if messages and _get_role(messages[0]) == "system" else 0

    total = len(messages)
    # Keep the last CONTEXT_SUMMARY_KEEP_RECENT user+assistant turn pairs
    keep_from = total
    kept = 0
    for i in range(total - 1, sys_end - 1, -1):
        role = _get_role(messages[i])
        if role in ("user", "assistant"):
            kept += 1
            if kept >= CONTEXT_SUMMARY_KEEP_RECENT * 2:
                keep_from = i
                break

    # Ensure we don't split a tool-call/result group at the boundary
    keep_from = _safe_compress_boundary(messages, sys_end, keep_from)

    compressible = messages[sys_end:keep_from]
    if len(compressible) < 2:
        return False

    # Build a readable summary prompt from the compressible slice
    lines = []
    for m in compressible:
        role = _get_role(m)
        if isinstance(m, dict):
            content = m.get("content") or ""
        else:
            content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if content:
            lines.append(f"{role.upper()}: {content[:500]}")

    if not lines:
        return False

    summary_prompt = (
        "Summarise the following conversation segment concisely, "
        "preserving key facts and decisions:\n\n" + "\n".join(lines)
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": summary_prompt}],
            **(gen_params or {}),
        )
        summary = resp.choices[0].message.content or "(summary unavailable)"
    except Exception as e:
        print(f"{_DIM}  [context] Compression failed: {e}{_RESET}")
        return False

    # Replace compressible slice with a single summary system message
    compressed = {"role": "system", "content": f"[SUMMARY OF EARLIER CONVERSATION]: {summary}"}
    del messages[sys_end:keep_from]
    messages.insert(sys_end, compressed)

    print(
        f"{_DIM}  [context] Compressed {len(compressible)} messages into summary "
        f"(context was {ratio:.0%} full){_RESET}",
        flush=True,
    )
    return True


def chat(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    verbose: bool = True,
    usage_out: dict | None = None,
    gen_params: dict | None = None,
    context_length: int | None = None,
    state: dict | None = None,
) -> str:
    """
    Send the current message history to the model and handle the full
    tool-call loop until the model produces a plain text response.

    Uses a single streaming call per round (_stream_or_tools) that either
    streams text directly or accumulates tool-call deltas silently — no
    double API call.

    Args:
        client:         OpenAI-compatible client.
        model:          Model identifier string.
        messages:       Mutable message list (modified in-place, always plain dicts).
        verbose:        Print tool call / result info to stdout.
        usage_out:      Updated in-place with {prompt_tokens, completion_tokens, total_tokens}.
        gen_params:     Extra kwargs forwarded to every create() call (temperature, etc.).
        context_length: Model's max context size; used for auto-compression.
        state:          Full session state dict (needed for tool confirmation).

    Returns:
        The final assistant text response.
    """
    if state is None:
        state = {}

    schemas = tool_registry.get_schemas()
    _compressed_this_call = False  # only compress once per chat() call

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            text, tool_calls, usage = _stream_or_tools(
                client, model, messages, schemas or None, gen_params
            )
        except Exception as e:
            raise RuntimeError(f"API call failed: {e}") from e

        if tool_calls is None:
            # Plain text response — already printed by _stream_or_tools
            messages.append({"role": "assistant", "content": text})
            if usage_out is not None and usage:
                usage_out.update(usage)
                if not _compressed_this_call:
                    _compressed_this_call = _maybe_compress(
                        client, model, messages, usage, context_length, gen_params
                    )
            return text

        # Model wants to call one or more tools
        if verbose:
            names = [tc.function.name for tc in tool_calls]
            print(f"  [tool] {', '.join(names)}")

        # Append assistant message as a plain dict (Bug 3 fix: no SDK objects)
        messages.append({
            "role":       "assistant",
            "content":    None,
            "tool_calls": [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                fn_args = {}
                result = f"Error: could not parse tool arguments: {e}"
            else:
                result = _execute_tool_with_retry(fn_name, fn_args, tc.id, verbose, state)

            if verbose:
                print(f"  [{fn_name}] -> {result}")

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })
        # Loop back: let the model decide whether to call more tools or respond

    # Safety valve — MAX_TOOL_ROUNDS exceeded
    if verbose:
        print(f"  [agent] reached max tool rounds ({MAX_TOOL_ROUNDS}), forcing final answer")
    try:
        text, _, usage = _stream_or_tools(client, model, messages, None, gen_params)
    except Exception as e:
        raise RuntimeError(f"API call failed: {e}") from e
    messages.append({"role": "assistant", "content": text})
    if usage_out is not None and usage:
        usage_out.update(usage)
    return text


def new_conversation(system_prompt: str = SYSTEM_PROMPT) -> list[dict]:
    """Return a fresh message list with the system prompt pre-loaded."""
    return [{"role": "system", "content": system_prompt}]


# ---------------------------------------------------------------------------
# Subagent support
# ---------------------------------------------------------------------------

def run_subagent(
    client,
    model: str,
    task: str,
    *,
    system_prompt: str | None = None,
    verbose: bool = True,
    gen_params: dict | None = None,
    state: dict | None = None,
) -> str:
    """
    Spawn an isolated subagent conversation for *task*.

    Streams output normally (bracketed by the caller's header/footer).
    Returns the final assistant answer string.
    Does NOT modify the caller's message history.
    """
    sys_msg = system_prompt or (
        "You are a focused subagent. Complete the given task thoroughly and concisely."
    )
    messages = new_conversation(sys_msg)
    messages.append({"role": "user", "content": task})

    usage_out: dict = {}

    return chat(
        client,
        model,
        messages,
        verbose=verbose,
        usage_out=usage_out,
        gen_params=gen_params,
        context_length=None,
        state=state,
    )
