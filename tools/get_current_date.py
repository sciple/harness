from datetime import datetime
import tools

def get_current_date() -> str:
    """Returns today's current date with day of week using local time."""
    # Explicitly use timezone-aware local time to ensure consistency.
    # On Windows, this often defaults to the system's configured local time zone.
    return f"{datetime.now().strftime('%A')}, {datetime.now().strftime('%Y-%m-%d')}"

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_current_date",
        "description": "Gets the current system date with day of week using local time.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "required": []
    }
}

tools.register(TOOL_SCHEMA, get_current_date)