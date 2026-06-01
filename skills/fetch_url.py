import re
import tools

SKILL_META = {
    "name":        "fetch_url",
    "description": "Fetches and retrieves the content from a given URL.",
    "version":     "1.0",
}

def run(args: str, state: dict, client) -> str:
    """
    Takes a URL from args, calls the web fetching tool, and returns the content summary.
    """
    if not args or not re.match(r'https?://', args):
        return "Usage: /skill fetch_url <full_url> (e.g., https://www.example.com)"

    target_url = args.strip()
    print(f"\nAttempting to fetch content from: {target_url}...")

    try:
        result = tools.dispatch("fetch_url", {"url": target_url})

        if result:
            return f"Successfully fetched content from {target_url}.\n{result}"
        else:
            return f"The tool executed for {target_url}, but returned no visible content."

    except Exception as e:
        return f"An unexpected error occurred while fetching the URL: {e}"
