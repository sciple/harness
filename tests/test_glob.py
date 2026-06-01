import os


def _write(tmp_workspace, rel_path, content=""):
    p = tmp_workspace / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_flat_pattern(tmp_workspace):
    _write(tmp_workspace, "a.py")
    _write(tmp_workspace, "b.py")
    _write(tmp_workspace, "c.txt")
    from tools.glob import glob
    result = glob("*.py")
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


def test_recursive_pattern(tmp_workspace):
    _write(tmp_workspace, "top.py")
    _write(tmp_workspace, "sub/nested.py")
    _write(tmp_workspace, "sub/deeper/very_deep.py")
    from tools.glob import glob
    result = glob("**/*.py")
    assert "top.py" in result
    assert os.path.join("sub", "nested.py") in result
    assert os.path.join("sub", "deeper", "very_deep.py") in result


def test_flat_pattern_skips_subdirs(tmp_workspace):
    _write(tmp_workspace, "a.py")
    _write(tmp_workspace, "sub/b.py")
    from tools.glob import glob
    result = glob("*.py")
    assert "a.py" in result
    assert "b.py" not in result


def test_no_match(tmp_workspace):
    _write(tmp_workspace, "a.txt")
    from tools.glob import glob
    assert glob("*.py") == "No matches found."


def test_path_scopes_search(tmp_workspace):
    _write(tmp_workspace, "sub1/x.py")
    _write(tmp_workspace, "sub2/y.py")
    from tools.glob import glob
    result = glob("*.py", path="sub1")
    assert "x.py" in result
    assert "y.py" not in result


def test_path_not_found(tmp_workspace):
    from tools.glob import glob
    result = glob("*.py", path="nonexistent")
    assert result.startswith("Error: path does not exist:")


def test_path_not_a_directory(tmp_workspace):
    _write(tmp_workspace, "file.txt", "hi")
    from tools.glob import glob
    result = glob("*.py", path="file.txt")
    assert result.startswith("Error: path is not a directory:")


def test_path_outside_workspace(tmp_workspace):
    from tools.glob import glob
    outside = os.path.abspath(os.path.join(str(tmp_workspace), "..", "..", ".."))
    result = glob("*.py", path=outside)
    assert result.startswith("Error: path is outside the workspace")


def test_results_are_sorted(tmp_workspace):
    _write(tmp_workspace, "c.py")
    _write(tmp_workspace, "a.py")
    _write(tmp_workspace, "b.py")
    from tools.glob import glob
    result = glob("*.py")
    lines = result.split("\n")
    assert lines == sorted(lines)
