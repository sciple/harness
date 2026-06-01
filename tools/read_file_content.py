from pathlib import Path
import tools
import config
import os
import yaml

def read_file_content(file_path: str) -> str:
    """Reads and returns the text content of a specified file if it has an allowed extension."""
    allowed_extensions = ('.txt', '.csv', '.py', '.md', '.ics', '.json', '.yml', '.yaml')
    p = Path(file_path)
    if not p.is_absolute():
        p = Path(config.WORKSPACE_ROOT) / p

    if not p.exists():
        # Fall back: search workspace recursively by basename
        basename = Path(file_path).name
        matches = [m for m in Path(config.WORKSPACE_ROOT).rglob(basename) if m.is_file()]
        if len(matches) == 1:
            p = matches[0]
        elif len(matches) > 1:
            listing = "\n".join(f"  {m}" for m in sorted(matches))
            return (
                f"Error: '{basename}' is ambiguous — found {len(matches)} matches. "
                f"Use a more specific path:\n{listing}"
            )
        else:
            return f"Error: The file path '{file_path}' does not exist."

    if p.suffix.lower() not in allowed_extensions:
        return f"Error: Unsupported file type. Only {', '.join(allowed_extensions)} files are supported for reading."

    try:
        content = p.read_text(encoding='utf-8')
        if p.suffix.lower() in ('.yml', '.yaml'):
            parsed = yaml.safe_load(content)
            return yaml.dump(parsed, allow_unicode=True, default_flow_style=False)
        return content
    except yaml.YAMLError as e:
        return f"Error: Failed to parse YAML file '{file_path}': {e}"
    except Exception as e:
        return f"An error occurred while reading the file '{file_path}': {e}"

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file_content",
        "description": "Reads and returns the text content of a local file. Supports .txt, .csv, .py, .md, .ics, .json, .yml, .yaml files.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file. Relative paths resolve from the workspace root. A bare filename (e.g. 'manifest.json') is searched recursively across the workspace if not found at the root."},
            },
            "required": ["file_path"],
        },
    },
}

tools.register(TOOL_SCHEMA, read_file_content)
