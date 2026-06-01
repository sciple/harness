"""Tests for tools/__init__.py — registry, dispatch, protection checks, truncation."""

import os
import pytest
import config
import tools as tr
from tools import is_protected_path, register, dispatch, get_schemas


# ---------------------------------------------------------------------------
# register / dispatch basics
# ---------------------------------------------------------------------------

def test_register_and_dispatch():
    def _fn(x: str) -> str:
        return f"got:{x}"

    schema = {"type": "function", "function": {"name": "_test_fn",
              "description": "test", "parameters": {"type": "object",
              "properties": {"x": {"type": "string"}}, "required": ["x"]}}}
    register(schema, _fn)
    result = dispatch("_test_fn", {"x": "hello"})
    assert result == "got:hello"


def test_dispatch_unknown_tool():
    result = dispatch("no_such_tool", {})
    assert "Error" in result
    assert "no_such_tool" in result


def test_dispatch_exception_returns_error_string():
    def _exploding():
        raise ValueError("boom")

    schema = {"type": "function", "function": {"name": "_exploding",
              "description": "x", "parameters": {"type": "object",
              "properties": {}, "required": []}}}
    register(schema, _exploding)
    result = dispatch("_exploding", {})
    assert result.startswith("Error")
    assert "boom" in result


def test_dispatch_dict_result_json_serialised():
    def _dict_fn() -> dict:
        return {"key": "value", "num": 42}

    schema = {"type": "function", "function": {"name": "_dict_fn",
              "description": "x", "parameters": {"type": "object",
              "properties": {}, "required": []}}}
    register(schema, _dict_fn)
    result = dispatch("_dict_fn", {})
    assert '"key"' in result
    assert '"value"' in result


# ---------------------------------------------------------------------------
# confirm / no_truncate flags
# ---------------------------------------------------------------------------

def test_confirm_flag_registers_tool_in_confirm_set():
    def _fn() -> str:
        return "ok"

    schema = {"type": "function", "confirm": True,
              "function": {"name": "_confirm_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    assert tr.requires_confirmation("_confirm_fn")


def test_no_confirm_flag_not_in_confirm_set():
    def _fn() -> str:
        return "ok"

    schema = {"type": "function", "confirm": False,
              "function": {"name": "_no_confirm_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    assert not tr.requires_confirmation("_no_confirm_fn")


def test_no_truncate_flag_bypasses_truncation(monkeypatch):
    monkeypatch.setattr(config, "TOOL_OUTPUT_MAX_CHARS", 10)
    monkeypatch.setattr(config, "TOOL_OUTPUT_STORE", True)

    long_output = "x" * 500

    def _fn() -> str:
        return long_output

    schema = {"type": "function", "no_truncate": True,
              "function": {"name": "_no_trunc_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    result = dispatch("_no_trunc_fn", {})
    assert len(result) == 500
    assert "truncated" not in result.lower()


def test_truncation_applied_for_normal_tool(monkeypatch):
    monkeypatch.setattr(config, "TOOL_OUTPUT_MAX_CHARS", 10)
    monkeypatch.setattr(config, "TOOL_OUTPUT_STORE", True)

    def _fn() -> str:
        return "x" * 500

    schema = {"type": "function",
              "function": {"name": "_trunc_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    result = dispatch("_trunc_fn", {})
    assert "truncated" in result.lower() or "Output truncated" in result


# ---------------------------------------------------------------------------
# Output store
# ---------------------------------------------------------------------------

def test_get_stored_output():
    def _fn() -> str:
        return "stored result"

    schema = {"type": "function",
              "function": {"name": "_stored_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    dispatch("_stored_fn", {})
    key = f"_stored_fn_{tr._call_counter[0]}"
    assert tr.get_stored_output(key) == "stored result"


def test_get_stored_output_missing_key():
    result = tr.get_stored_output("nonexistent_key_99")
    assert "Error" in result


def test_store_eviction_at_max():
    """When the store exceeds 50 entries, the oldest is evicted."""
    def _fn(n: int) -> str:
        return f"result_{n}"

    schema = {"type": "function",
              "function": {"name": "_evict_fn", "description": "x",
              "parameters": {"type": "object", "properties": {
                  "n": {"type": "integer"}}, "required": ["n"]}}}
    register(schema, _fn)

    # Fill past the 50-entry limit
    for i in range(55):
        dispatch("_evict_fn", {"n": i})

    assert len(tr._tool_output_store) <= 50


# ---------------------------------------------------------------------------
# get_schemas strips non-standard keys
# ---------------------------------------------------------------------------

def test_get_schemas_strips_confirm_key():
    def _fn() -> str:
        return "ok"

    schema = {"type": "function", "confirm": True,
              "function": {"name": "_schema_strip_fn", "description": "x",
              "parameters": {"type": "object", "properties": {}, "required": []}}}
    register(schema, _fn)
    schemas = get_schemas()
    matching = [s for s in schemas if s.get("function", {}).get("name") == "_schema_strip_fn"]
    assert len(matching) == 1
    assert "confirm" not in matching[0]


# ---------------------------------------------------------------------------
# is_protected_path
# ---------------------------------------------------------------------------

def test_is_protected_exact_file():
    # config.py absolute path must be protected
    path = os.path.join(os.path.dirname(config.__file__), "config.py")
    protected, reason = is_protected_path(path)
    assert protected
    assert reason


def test_is_protected_pattern_init():
    protected, reason = is_protected_path("/some/dir/__init__.py")
    assert protected


def test_is_protected_pattern_env():
    protected, reason = is_protected_path("/some/dir/.env")
    assert protected


def test_is_protected_pattern_requirements():
    protected, reason = is_protected_path("/some/dir/requirements.txt")
    assert protected


def test_is_protected_dir_sessions(tmp_path):
    # A file inside the sessions directory should be protected
    import config as cfg
    sessions_dir = os.path.realpath(cfg.SESSIONS_DIR)
    test_path = os.path.join(sessions_dir, "fake_session.jsonl")
    protected, reason = is_protected_path(test_path)
    assert protected


def test_is_protected_case_insensitive():
    # MAIN.PY (uppercase) should also be blocked
    harness_root = os.path.dirname(os.path.realpath(config.__file__))
    upper_path = os.path.join(harness_root, "MAIN.PY")
    protected, _ = is_protected_path(upper_path)
    assert protected


def test_not_protected_normal_file(tmp_path):
    normal = str(tmp_path / "my_output.txt")
    protected, reason = is_protected_path(normal)
    assert not protected
    assert reason == ""
