import os
import re
import uuid
import tools
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _event_filename(summary: str, date: str) -> str:
    """Build a filesystem-safe filename from the event summary and date."""
    slug = summary.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)       # drop punctuation
    slug = re.sub(r"[\s_]+", "_", slug)         # spaces -> underscores
    slug = re.sub(r"-+", "-", slug).strip("-_") # collapse dashes
    slug = slug[:40]                             # cap length
    return f"{date}_{slug}.ics"


def _local_tz():
    """Return the local timezone as a zoneinfo object, falling back to UTC."""
    import time as _time
    name = _time.tzname[0] if not _time.daylight else _time.tzname[1]
    # Use the IANA name via the stdlib localtime approach
    try:
        # Python 3.9+ — ZoneInfo.local() is not available, but we can read
        # the local zone name from the system
        from zoneinfo import ZoneInfo
        # Prefer the IANA key embedded in the local timezone if available
        import sys
        if sys.platform == "win32":
            # On Windows, use tzlocal if installed, else fall back to UTC offset
            try:
                from zoneinfo import ZoneInfo
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation") as k:
                    win_tz = winreg.QueryValueEx(k, "TimeZoneKeyName")[0]
                # Map common Windows timezone names to IANA
                _WIN_TO_IANA = {
                    "Romance Standard Time": "Europe/Paris",
                    "W. Europe Standard Time": "Europe/Berlin",
                    "Central Europe Standard Time": "Europe/Budapest",
                    "GMT Standard Time": "Europe/London",
                    "Eastern Standard Time": "America/New_York",
                    "Central Standard Time": "America/Chicago",
                    "Mountain Standard Time": "America/Denver",
                    "Pacific Standard Time": "America/Los_Angeles",
                    "UTC": "UTC",
                }
                iana = _WIN_TO_IANA.get(win_tz)
                if iana:
                    return ZoneInfo(iana)
            except Exception:
                pass
        return ZoneInfo("localtime")
    except Exception:
        return timezone.utc


def create_calendar_event(
    summary: str,
    date: str,
    time: str,
    duration_hours: float = 1.0,
    timezone_name: str = "",
    output_path: str = "",
) -> str:
    """
    Create an ICS calendar event file using the local timezone.

    Parses `date` (YYYY-MM-DD) and `time` (HH:MM, 24h) as local time,
    builds a VCALENDAR/VEVENT block, and writes it to `output_path` inside
    the workspace. Returns the path written or an error string.
    """
    # --- Resolve timezone ---
    tz = None
    if timezone_name.strip():
        try:
            tz = ZoneInfo(timezone_name.strip())
        except (ZoneInfoNotFoundError, KeyError):
            return f"Error: unknown timezone '{timezone_name}'. Use an IANA name like 'Europe/Zurich'."
    if tz is None:
        tz = _local_tz()

    tz_id = getattr(tz, "key", str(tz))

    # --- Resolve output path ---
    if not output_path.strip():
        output_path = os.path.join("events", _event_filename(summary, date))

    # --- Parse date and time as local time ---
    try:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError as e:
        return f"Error: could not parse date/time '{date} {time}': {e}"

    end_dt = start_dt + timedelta(hours=float(duration_hours))

    # --- Build ICS content ---
    # Use local-time format (no Z suffix) with TZID so calendar apps show
    # the event at the correct local wall-clock time.
    fmt_local = "%Y%m%dT%H%M%S"
    fmt_utc   = "%Y%m%dT%H%M%SZ"
    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//LocalLLMHarness//CalendarTool//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DTSTAMP:{datetime.now(timezone.utc).strftime(fmt_utc)}\r\n"
        f"DTSTART;TZID={tz_id}:{start_dt.strftime(fmt_local)}\r\n"
        f"DTEND;TZID={tz_id}:{end_dt.strftime(fmt_local)}\r\n"
        f"UID:{uuid.uuid4()}@localllm.harness\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    # --- Write file (confined to workspace root) ---
    import config
    root = config.WORKSPACE_ROOT
    target = os.path.realpath(os.path.join(root, output_path))
    if not (target.startswith(root + os.sep) or target == root):
        return f"Error: output path '{output_path}' resolves outside the workspace root."

    from tools import is_protected_path
    protected, reason = is_protected_path(target)
    if protected:
        return f"Error: write refused. {reason}"

    try:
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(ics_content)
    except Exception as e:
        return f"Error writing '{target}': {e}"

    return (
        f"Calendar event '{summary}' written to {target}\n"
        f"Start: {start_dt.strftime('%Y-%m-%d %H:%M')} UTC  "
        f"End: {end_dt.strftime('%Y-%m-%d %H:%M')} UTC"
    )


TOOL_SCHEMA = {
    "type": "function",
    "confirm": True,
    "function": {
        "name": "create_calendar_event",
        "description": (
            "Create an Outlook-compatible .ics calendar event file and save it to disk. "
            "Events are created in the local system timezone by default. "
            "Only call this tool when the user explicitly asks to schedule, book, or "
            "create a calendar event or appointment with a specific date and time. "
            "Do NOT call this for general planning, to-do items, or any request that "
            "does not include a concrete date and time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Event title / subject line.",
                },
                "date": {
                    "type": "string",
                    "description": "Event date in YYYY-MM-DD format, e.g. '2026-04-15'.",
                },
                "time": {
                    "type": "string",
                    "description": "Start time in HH:MM 24-hour format, e.g. '10:30'.",
                },
                "duration_hours": {
                    "type": "number",
                    "description": "Duration of the event in hours. Defaults to 1.0.",
                },
                "timezone_name": {
                    "type": "string",
                    "description": (
                        "IANA timezone name, e.g. 'Europe/Zurich' or 'America/New_York'. "
                        "If omitted, the local system timezone is used."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Relative path where the .ics file will be saved. "
                        "If omitted, saved to 'events/<date>_<summary>.ics'."
                    ),
                },
            },
            "required": ["summary", "date", "time"],
        },
    },
}

tools.register(TOOL_SCHEMA, create_calendar_event)
