import os


def _write(tmp_workspace, rel_path, content):
    p = tmp_workspace / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_basic_range(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\nthree\nfour\nfive\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 2, 4)
    assert result == "2: two\n3: three\n4: four"


def test_single_line(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\nthree\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 2, 2)
    assert result == "2: two"


def test_end_clamped_to_eof(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\nthree\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 2, 1000)
    assert result == "2: two\n3: three"


def test_file_without_trailing_newline(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\nthree")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 1, 3)
    assert result == "1: one\n2: two\n3: three"


def test_subdirectory_file(tmp_workspace):
    _write(tmp_workspace, "sub/nested.txt", "alpha\nbeta\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("sub/nested.txt", 1, 2)
    assert result == "1: alpha\n2: beta"


def test_start_zero_rejected(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 0, 1)
    assert result.startswith("Error: start must be >= 1")


def test_end_before_start_rejected(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 5, 2)
    assert result.startswith("Error: end must be >= start")


def test_start_past_eof(tmp_workspace):
    _write(tmp_workspace, "a.txt", "one\ntwo\n")
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("a.txt", 100, 200)
    assert result.startswith("Error: start (100) exceeds file length")


def test_file_not_found(tmp_workspace):
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("nonexistent.txt", 1, 5)
    assert result.startswith("Error: file does not exist:")


def test_path_is_directory(tmp_workspace):
    (tmp_workspace / "sub").mkdir()
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("sub", 1, 5)
    assert result.startswith("Error: path is not a file:")


def test_path_outside_workspace(tmp_workspace):
    from tools.read_file_lines import read_file_lines
    outside = os.path.abspath(os.path.join(str(tmp_workspace), "..", "..", "..", "etc"))
    result = read_file_lines(outside, 1, 5)
    assert result.startswith("Error: path is outside the workspace")


def test_binary_file(tmp_workspace):
    binary_path = tmp_workspace / "binary.bin"
    binary_path.write_bytes(bytes(range(256)))
    from tools.read_file_lines import read_file_lines
    result = read_file_lines("binary.bin", 1, 5)
    assert result.startswith("Error: file is not valid UTF-8:")
