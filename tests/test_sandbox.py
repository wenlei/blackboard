import tempfile

import pytest

from blackboard.sandbox.sandbox import Sandbox


@pytest.fixture
def sandbox():
    with tempfile.TemporaryDirectory() as tmpdir:
        sb = Sandbox("test-session", base_dir=tmpdir)
        yield sb


class TestSandbox:
    def test_write_read_file(self, sandbox):
        sandbox.write_file("test.txt", "hello world")
        content = sandbox.read_file("test.txt")
        assert content == "hello world"

    def test_write_nested_directory(self, sandbox):
        sandbox.write_file("sub/dir/file.txt", "nested")
        content = sandbox.read_file("sub/dir/file.txt")
        assert content == "nested"

    def test_path_traversal_blocked(self, sandbox):
        with pytest.raises(ValueError, match="traversal"):
            sandbox.resolve_path("../../../etc/passwd")

    def test_execute_python(self, sandbox):
        stdout, stderr, rc = sandbox.execute_python("print(1+1)")
        assert "2" in stdout
        assert rc == 0

    def test_execute_python_error(self, sandbox):
        stdout, stderr, rc = sandbox.execute_python("x = 1/0")
        assert rc != 0

    def test_execute_shell(self, sandbox):
        stdout, stderr, rc = sandbox.execute_shell("echo 'ok'")
        assert "ok" in stdout
        assert rc == 0

    def test_list_dir(self, sandbox):
        sandbox.write_file("a.txt", "a")
        sandbox.write_file("b.txt", "b")
        files = sandbox.list_dir()
        assert "a.txt" in files
        assert "b.txt" in files

    def test_delete_file(self, sandbox):
        sandbox.write_file("tmp.txt", "tmp")
        sandbox.delete_file("tmp.txt")
        with pytest.raises(FileNotFoundError):
            sandbox.read_file("tmp.txt")

    def test_read_nonexistent(self, sandbox):
        with pytest.raises(FileNotFoundError):
            sandbox.read_file("ghost.txt")

    def test_cleanup(self, sandbox):
        sandbox.write_file("x.txt", "x")
        assert sandbox.sandbox_dir.exists()
        sandbox.cleanup()
        assert not sandbox.sandbox_dir.exists()

    def test_cleanup_idempotent(self, sandbox):
        sandbox.cleanup()
        sandbox.cleanup()

    def test_delete_nonexistent_file(self, sandbox):
        result = sandbox.delete_file("nonexistent.txt")
        assert "not found" in result.lower()

    def test_list_dir_empty(self, sandbox):
        files = sandbox.list_dir()
        assert files == []

    def test_list_dir_nonexistent(self, sandbox):
        files = sandbox.list_dir("subdir")
        assert files == []

    def test_write_read_large_content(self, sandbox):
        content = "x" * 10000
        sandbox.write_file("large.txt", content)
        result = sandbox.read_file("large.txt")
        assert result == content

    def test_execute_python_with_output(self, sandbox):
        stdout, stderr, rc = sandbox.execute_python("import sys; print('hello', file=sys.stderr); print('world')")
        assert "world" in stdout
        assert "hello" in stderr
        assert rc == 0

    def test_execute_shell_nonzero_exit(self, sandbox):
        stdout, stderr, rc = sandbox.execute_shell("exit 1")
        assert rc == 1

    def test_resolve_normal_path(self, sandbox):
        resolved = sandbox.resolve_path("file.txt")
        assert resolved.name == "file.txt"
        assert str(sandbox.sandbox_dir) in str(resolved)

    def test_resolve_path_with_dots(self, sandbox):
        resolved = sandbox.resolve_path("./subdir/../file.txt")
        assert "subdir" not in str(resolved)

    def test_write_file_return_value(self, sandbox):
        result = sandbox.write_file("test.txt", "hello")
        assert "hello" in result or "5" in result

    def test_write_file_overwrite(self, sandbox):
        sandbox.write_file("data.txt", "first")
        sandbox.write_file("data.txt", "second")
        assert sandbox.read_file("data.txt") == "second"

    def test_path_traversal_with_absolute(self, sandbox):
        with pytest.raises(ValueError, match="traversal"):
            sandbox.resolve_path("/etc/passwd")

    def test_path_traversal_with_symlink_like(self, sandbox):
        with pytest.raises(ValueError, match="traversal"):
            sandbox.resolve_path("../.." * 10 + "etc/passwd")
