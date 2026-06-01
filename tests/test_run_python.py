"""Tests for tools/run_python.py — subprocess execution, timeout, stdin handling."""

import pytest
from tools.run_python import run_python


def test_stdout_captured():
    result = run_python('print("hello harness")')
    assert "hello harness" in result


def test_stderr_labeled():
    result = run_python('import sys; sys.stderr.write("err msg")')
    assert "err msg" in result
    assert "[stderr]" in result


def test_exit_code_nonzero():
    result = run_python('import sys; sys.exit(42)')
    assert "42" in result


def test_no_output():
    result = run_python('x = 1 + 1')
    assert "(no output)" in result


def test_timeout_enforced():
    result = run_python('while True: pass', timeout=1)
    assert "timed out" in result.lower() or "timeout" in result.lower()


def test_timeout_clamp_upper():
    # timeout=999 should be clamped to 120 and not crash
    # (we don't want to actually wait 120s — just verify it doesn't raise)
    # Use a short-running script even with high timeout arg
    result = run_python('print("ok")', timeout=999)
    assert "ok" in result


def test_timeout_clamp_lower():
    # timeout=0 should be clamped to 1
    result = run_python('print("ok")', timeout=0)
    assert "ok" in result


def test_stdin_no_hang():
    """input() should not hang forever — subprocess stdin is DEVNULL."""
    result = run_python('x = input("prompt: ")', timeout=2)
    # Should either time out or produce an EOF error, not hang
    assert result  # non-empty — either timeout msg or EOFError


def test_stdout_and_stderr_combined():
    code = 'import sys; print("out"); sys.stderr.write("err")'
    result = run_python(code)
    assert "out" in result
    assert "err" in result


def test_multiline_code():
    code = 'total = 0\nfor i in range(5):\n    total += i\nprint(total)'
    result = run_python(code)
    assert "10" in result
