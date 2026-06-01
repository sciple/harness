import os
import pytest


def _write(tmp_workspace, rel_path, content):
    p = tmp_workspace / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------

def test_basic_match(tmp_workspace):
    _write(tmp_workspace, "hello.txt", "hello world\ngoodbye world\n")
    from tools.grep import grep
    result = grep("hello")
    assert "hello.txt:1: hello world" in result
    assert "goodbye" not in result


def test_no_match(tmp_workspace):
    _write(tmp_workspace, "hello.txt", "hello world\n")
    from tools.grep import grep
    assert grep("zzznomatch") == "No matches found."


def test_multiple_matches_in_file(tmp_workspace):
    _write(tmp_workspace, "a.txt", "foo bar\nbaz foo\nqux\n")
    from tools.grep import grep
    result = grep("foo")
    assert "a.txt:1:" in result
    assert "a.txt:2:" in result
    assert "a.txt:3:" not in result


# ---------------------------------------------------------------------------
# Recursive vs non-recursive
# ---------------------------------------------------------------------------

def test_recursive_searches_subdirs(tmp_workspace):
    _write(tmp_workspace, "sub/deep.txt", "needle here\n")
    _write(tmp_workspace, "top.txt", "nothing useful\n")
    from tools.grep import grep
    result = grep("needle")
    assert "deep.txt" in result
    assert "top.txt" not in result


def test_non_recursive_ignores_subdirs(tmp_workspace):
    _write(tmp_workspace, "sub/deep.txt", "needle here\n")
    _write(tmp_workspace, "top.txt", "needle here too\n")
    from tools.grep import grep
    result = grep("needle", recursive=False)
    assert "top.txt" in result
    assert "deep.txt" not in result


# ---------------------------------------------------------------------------
# Scoping to a specific file or subdirectory
# ---------------------------------------------------------------------------

def test_search_specific_file(tmp_workspace):
    _write(tmp_workspace, "a.txt", "match line\n")
    _write(tmp_workspace, "b.txt", "match line\n")
    from tools.grep import grep
    result = grep("match", path="a.txt")
    assert "a.txt" in result
    assert "b.txt" not in result


def test_search_subdirectory(tmp_workspace):
    _write(tmp_workspace, "sub/in.txt", "target\n")
    _write(tmp_workspace, "out.txt", "target\n")
    from tools.grep import grep
    result = grep("target", path="sub")
    assert "in.txt" in result
    assert "out.txt" not in result


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_invalid_regex(tmp_workspace):
    from tools.grep import grep
    result = grep("[unclosed")
    assert result.startswith("Error: invalid pattern:")


def test_path_not_found(tmp_workspace):
    from tools.grep import grep
    result = grep("anything", path="nonexistent_dir")
    assert result.startswith("Error: path does not exist:")


def test_path_outside_workspace(tmp_workspace):
    from tools.grep import grep
    result = grep("anything", path=os.path.abspath(os.path.join(str(tmp_workspace), "..", "..", "..")))
    assert result.startswith("Error: path is outside the workspace")


# ---------------------------------------------------------------------------
# Binary / undecodable files
# ---------------------------------------------------------------------------

def test_binary_file_skipped(tmp_workspace):
    binary_path = tmp_workspace / "binary.bin"
    binary_path.write_bytes(bytes(range(256)))
    _write(tmp_workspace, "text.txt", "findme\n")
    from tools.grep import grep
    result = grep("findme")
    assert "text.txt" in result  # text file still searched
    # no crash; binary file silently skipped
