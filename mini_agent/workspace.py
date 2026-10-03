"""A throwaway copy of a task that the agent can read, edit, and test.

Only the files a task marks as editable can be written; tests and helpers are read-only,
so the agent cannot make the tests pass by changing them. Paths are resolved inside the
workspace root, and every test run has a timeout because buggy code may loop forever.

The code under test still runs on your machine with your permissions. That is fine for
small benchmark programs; use a container or VM for anything you do not trust.
"""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_READ_LINES = 400
MAX_TEST_OUTPUT_LINES = 60


@dataclass(frozen=True)
class Task:
    name: str
    source: Path  # directory the files are copied from
    files: tuple[str, ...]  # paths relative to `source`, copied into the workspace
    editable: tuple[str, ...]  # the only files the agent may change
    tests: tuple[str, ...]  # pytest targets
    description: str


@dataclass(frozen=True)
class TestRun:
    passed: bool
    timed_out: bool
    summary: str  # pytest's final line, e.g. "2 failed, 5 passed in 0.10s"
    output: str  # truncated pytest output for the model


class WorkspaceError(ValueError):
    """A request the workspace refuses. The message goes back to the model."""


class Workspace:
    def __init__(self, task: Task, timeout: float = 60.0):
        self.task, self.timeout = task, timeout
        self.root = Path(tempfile.mkdtemp(prefix=f"mini-agent-{task.name}-")).resolve()
        for rel in task.files:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(task.source / rel, target)
        self.original = {rel: self.read(rel) for rel in task.editable}

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def list_files(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())

    def read(self, rel: str) -> str:
        path = self._resolve(rel)
        if not path.is_file():
            raise WorkspaceError(f"no such file: {rel}")
        return path.read_text(encoding="utf-8")

    def write(self, rel: str, content: str) -> None:
        rel = self._relative(rel)
        if rel not in self.task.editable:
            raise WorkspaceError(f"{rel} is read-only; editable files: {', '.join(self.task.editable)}")
        self._resolve(rel).write_text(content, encoding="utf-8")

    def run_tests(self) -> TestRun:
        command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", *self.task.tests]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            proc = subprocess.run(
                command, cwd=self.root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            message = f"tests did not finish within {self.timeout:g} s (the code may loop forever)"
            return TestRun(passed=False, timed_out=True, summary="timeout", output=message)
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        summary = lines[-1].strip("= ") if lines else f"pytest exited with code {proc.returncode}"
        if len(lines) > MAX_TEST_OUTPUT_LINES:
            lines = lines[: MAX_TEST_OUTPUT_LINES - 1] + [f"... ({len(lines) - MAX_TEST_OUTPUT_LINES + 1} more lines)", lines[-1]]
        return TestRun(passed=proc.returncode == 0, timed_out=False, summary=summary, output="\n".join(lines))

    def diff(self) -> str:
        """Unified diff of every editable file against its original content."""
        chunks = []
        for rel, before in self.original.items():
            after = self.read(rel)
            chunks += difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True), f"a/{rel}", f"b/{rel}"
            )
        return "".join(chunks)

    def _relative(self, rel: str) -> str:
        return self._resolve(rel).relative_to(self.root).as_posix()

    def _resolve(self, rel: str) -> Path:
        path = (self.root / str(rel)).resolve()
        if not path.is_relative_to(self.root):
            raise WorkspaceError(f"{rel} is outside the workspace")
        return path
