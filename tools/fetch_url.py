import re
import urllib.request
import urllib.error
import tools


def fetch_url(url: str, plain_text: bool = True, max_chars: int = 16000) -> str:
    """
    Fetch the content of a URL and return it as a string.

    Uses only the Python standard library (urllib) — no extra dependencies.
    When plain_text is True (default), HTML tags are stripped so the model
    receives readable prose instead of raw markup.
    Output is capped at max_chars to avoid flooding the context.
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LocalLLMHarness/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = "utf-8"
            content_type = resp.headers.get_content_type() or ""
            # Try to read charset from Content-Type header
            ct_full = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct_full, re.I)
            if m:
                charset = m.group(1).strip('"')
            raw = resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code} {e.reason} — {url}"
    except urllib.error.URLError as e:
        return f"Error: could not reach '{url}': {e.reason}"
    except Exception as e:
        return f"Error fetching '{url}': {e}"

    if plain_text:
        # Remove <script> and <style> blocks entirely
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
        # Strip remaining tags
        raw = re.sub(r"<[^>]+>", " ", raw)
        # Collapse whitespace
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = raw.strip()

    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n\n[Truncated — {len(raw) - max_chars} chars omitted]"

    return raw


TOOL_SCHEMA = {
    "type": "function",
    "confirm": True,
    "no_truncate": True,   # fetch_url manages its own max_chars cap
    "function": {
        "name": "fetch_url",
        "description": (
            "Fetch the content of a web page or URL and return it as text. "
            "HTML tags are stripped by default, returning readable prose. "
            "Useful for reading articles, documentation, or any public web page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch, e.g. 'https://example.com/page'.",
                },
                "plain_text": {
                    "type": "boolean",
                    "description": "Strip HTML tags and return plain text (default true).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 16000).",
                },
            },
            "required": ["url"],
        },
    },
}

tools.register(TOOL_SCHEMA, fetch_url)
