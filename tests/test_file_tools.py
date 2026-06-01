"""Tests for file-manipulating tools: write_file, append_to_file, patch_file,
read_file_content, make_dir."""

import os
import pytest


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_happy_path(self, tmp_workspace):
        from tools.write_file import write_file
        result = write_file("hello.txt", "world")
        assert "File written" in result
        assert (tmp_workspace / "hello.txt").read_text(encoding="utf-8") == "world"

    def test_creates_parent_dirs(self, tmp_workspace):
        from tools.write_file import write_file
        result = write_file("a/b/c/deep.txt", "content")
        assert "File written" in result
        assert (tmp_workspace / "a" / "b" / "c" / "deep.txt").exists()

    def test_path_traversal_refused(self, tmp_workspace):
        from tools.write_file import write_file
        result = write_file("../../escape.txt", "evil")
        assert result.startswith("Error")

    def test_protected_file_refused(self, tmp_workspace):
        from tools.write_file import write_file
        import config as cfg_mod
        real_config = os.path.realpath(cfg_mod.__file__)
        result = write_file(real_config, "malicious")
        assert result.startswith("Error")

    def test_overwrites_existing(self, tmp_workspace):
        from tools.write_file import write_file
        write_file("overwrite.txt", "original")
        write_file("overwrite.txt", "updated")
        assert (tmp_workspace / "overwrite.txt").read_text(encoding="utf-8") == "updated"


# ---------------------------------------------------------------------------
# append_to_file
# ---------------------------------------------------------------------------

class TestAppendToFile:
    def test_creates_file_if_missing(self, tmp_workspace):
        from tools.append_to_file import append_to_file
        result = append_to_file("new.txt", "first line")
        assert "Appended" in result
        assert (tmp_workspace / "new.txt").read_text(encoding="utf-8") == "first line"

    def test_appends_to_existing(self, tmp_workspace):
        from tools.append_to_file import append_to_file
        (tmp_workspace / "existing.txt").write_text("line1", encoding="utf-8")
        append_to_file("existing.txt", "line2", newline=False)
        content = (tmp_workspace / "existing.txt").read_text(encoding="utf-8")
        assert "line1" in content
        assert "line2" in content

    def test_newline_separator_inserted(self, tmp_workspace):
        from tools.append_to_file import append_to_file
        append_to_file("sep.txt", "first")
        append_to_file("sep.txt", "second", newline=True)
        content = (tmp_workspace / "sep.txt").read_text(encoding="utf-8")
        assert "\n" in content
        assert "first" in content
        assert "second" in content

    def test_no_separator_when_newline_false(self, tmp_workspace):
        from tools.append_to_file import append_to_file
        append_to_file("nosep.txt", "A")
        append_to_file("nosep.txt", "B", newline=False)
        content = (tmp_workspace / "nosep.txt").read_text(encoding="utf-8")
        assert content == "AB"

    def test_path_traversal_refused(self, tmp_workspace):
        from tools.append_to_file import append_to_file
        result = append_to_file("../../escape.txt", "evil")
        assert result.startswith("Error")


# ---------------------------------------------------------------------------
# patch_file
# ---------------------------------------------------------------------------

class TestPatchFile:
    def _make_file(self, tmp_workspace, name, content):
        p = tmp_workspace / name
        p.write_text(content, encoding="utf-8")
        return name

    def test_single_replacement(self, tmp_workspace):
        from tools.patch_file import patch_file
        self._make_file(tmp_workspace, "f.txt", "hello world")
        result = patch_file("f.txt", "world", "earth")
        assert "Patched" in result
        assert (tmp_workspace / "f.txt").read_text(encoding="utf-8") == "hello earth"

    def test_replaces_only_first_by_default(self, tmp_workspace):
        from tools.patch_file import patch_file
        self._make_file(tmp_workspace, "multi.txt", "foo foo foo")
        result = patch_file("multi.txt", "foo", "bar")
        content = (tmp_workspace / "multi.txt").read_text(encoding="utf-8")
        assert content == "bar foo foo"
        assert "left unchanged" in result

    def test_replace_all(self, tmp_workspace):
        from tools.patch_file import patch_file
        self._make_file(tmp_workspace, "all.txt", "foo foo foo")
        patch_file("all.txt", "foo", "bar", replace_all=True)
        assert (tmp_workspace / "all.txt").read_text(encoding="utf-8") == "bar bar bar"

    def test_text_not_found(self, tmp_workspace):
        from tools.patch_file import patch_file
        self._make_file(tmp_workspace, "nf.txt", "hello")
        result = patch_file("nf.txt", "xyz", "abc")
        assert result.startswith("Error")

    def test_file_not_found(self, tmp_workspace):
        from tools.patch_file import patch_file
        result = patch_file("nonexistent.txt", "x", "y")
        assert result.startswith("Error")

    def test_protected_file_refused(self, tmp_workspace):
        from tools.patch_file import patch_file
        import config as cfg_mod
        real_config = os.path.realpath(cfg_mod.__file__)
        result = patch_file(real_config, "x", "y")
        assert result.startswith("Error")


# ---------------------------------------------------------------------------
# read_file_content
# ---------------------------------------------------------------------------

class TestReadFileContent:
    def test_reads_txt(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "test.txt"
        p.write_text("hello", encoding="utf-8")
        result = read_file_content(str(p))
        assert result == "hello"

    def test_reads_py(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "code.py"
        p.write_text("print('hi')", encoding="utf-8")
        result = read_file_content(str(p))
        assert "print" in result

    def test_reads_md(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "doc.md"
        p.write_text("# Title", encoding="utf-8")
        assert "Title" in read_file_content(str(p))

    def test_unsupported_extension(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "binary.exe"
        p.write_text("MZ", encoding="utf-8")
        result = read_file_content(str(p))
        assert result.startswith("Error")

    def test_file_not_found(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        result = read_file_content(str(tmp_workspace / "missing.txt"))
        assert result.startswith("Error")


class TestReadYamlFile:
    def test_reads_yml(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "data.yml"
        p.write_text("key: value\n", encoding="utf-8")
        result = read_file_content(str(p))
        assert "key" in result
        assert not result.startswith("Error")

    def test_reads_yaml(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "data.yaml"
        p.write_text("name: test\n", encoding="utf-8")
        result = read_file_content(str(p))
        assert "name" in result
        assert not result.startswith("Error")

    def test_yaml_content_preserved(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "cfg.yml"
        p.write_text("alpha: 1\nbeta: hello\n", encoding="utf-8")
        result = read_file_content(str(p))
        assert "alpha" in result
        assert "beta" in result
        assert "hello" in result

    def test_malformed_yaml_returns_error(self, tmp_workspace):
        from tools.read_file_content import read_file_content
        p = tmp_workspace / "bad.yml"
        p.write_text("key: :\n  - broken: [\n", encoding="utf-8")
        result = read_file_content(str(p))
        assert result.startswith("Error")



# ---------------------------------------------------------------------------
# make_dir
# ---------------------------------------------------------------------------

class TestMakeDir:
    def test_creates_directory(self, tmp_workspace):
        from tools.make_dir import make_dir
        target = str(tmp_workspace / "newdir")
        result = make_dir(target)
        assert "created" in result.lower() or os.path.isdir(target)
        assert os.path.isdir(target)

    def test_creates_nested_directories(self, tmp_workspace):
        from tools.make_dir import make_dir
        target = str(tmp_workspace / "a" / "b" / "c")
        make_dir(target)
        assert os.path.isdir(target)

    def test_protected_dir_refused(self, tmp_workspace):
        from tools.make_dir import make_dir
        import config as cfg
        result = make_dir(cfg.SESSIONS_DIR)
        assert result.startswith("Error")
