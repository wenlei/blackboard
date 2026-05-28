import os
import subprocess
from pathlib import Path


class Sandbox:
    def __init__(self, session_id: str, base_dir: str = "/tmp/blackboard-sandbox"):
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        self.sandbox_dir = self.base_dir / session_id
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str) -> Path:
        resolved = (self.sandbox_dir / path).resolve()
        sandbox_root = str(self.sandbox_dir.resolve())
        if not str(resolved).startswith(sandbox_root + os.sep) and str(resolved) != sandbox_root:
            raise ValueError(f"Path traversal denied: {path}")
        return resolved

    def read_file(self, path: str) -> str:
        filepath = self.resolve_path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return filepath.read_text()

    def write_file(self, path: str, content: str) -> str:
        filepath = self.resolve_path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        return f"Written {len(content)} bytes to {path}"

    def delete_file(self, path: str) -> str:
        filepath = self.resolve_path(path)
        if filepath.exists():
            filepath.unlink()
            return f"Deleted: {path}"
        return f"File not found: {path}"

    def list_dir(self, path: str = ".") -> list[str]:
        dirpath = self.resolve_path(path)
        if not dirpath.exists():
            return []
        base = str(self.sandbox_dir.resolve())
        return sorted([str(p.resolve()).replace(base, "").lstrip("/") for p in dirpath.iterdir()])

    def execute_python(self, code: str, timeout: int = 30) -> tuple[str, str, int]:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=timeout, cwd=str(self.sandbox_dir),
        )
        return result.stdout, result.stderr, result.returncode

    def execute_shell(self, command: str, timeout: int = 30) -> tuple[str, str, int]:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True, text=True, timeout=timeout, cwd=str(self.sandbox_dir),
        )
        return result.stdout, result.stderr, result.returncode

    def cleanup(self):
        import shutil
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir)
