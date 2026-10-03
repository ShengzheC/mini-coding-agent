import os
from pathlib import Path

import pytest

from mini_agent.tasks import builtin_tasks, quixbugs_tasks
from mini_agent.workspace import Workspace, WorkspaceError

# Reference fixes for the built-in tasks, as (old, new) replacements. They live here, not in
# tasks/, so the agent never sees them.
FIXES = {
    "binary_search": ("lo, hi = 0, len(items) - 1", "lo, hi = 0, len(items)"),
    "bitfield": ("(reg & mask)", "(reg & ~mask)"),
    "crc8": ("    return crc\n", "    return crc & 0xFF\n"),
    "lru_cache": ("        return self._items[key]\n", "        self._items.move_to_end(key)\n        return self._items[key]\n"),
    "ring_buffer": ("self._head = self._head + 1", "self._head = (self._head + 1) % len(self._buf)"),
    "wear_leveling": ("-block))", "block))"),
}


@pytest.mark.parametrize("task", builtin_tasks(), ids=lambda t: t.name)
def test_builtin_bug_is_real_and_fixable(task):
    with Workspace(task) as ws:
        assert not ws.run_tests().passed, "the buggy version should fail its tests"
        (path,) = task.editable
        old, new = FIXES[task.name]
        source = ws.read(path)
        assert source.count(old) == 1
        ws.write(path, source.replace(old, new))
        result = ws.run_tests()
        assert result.passed, result.output
        assert ws.diff().startswith(f"--- a/{path}")


def test_every_builtin_task_has_a_reference_fix():
    assert sorted(t.name for t in builtin_tasks()) == sorted(FIXES)


@pytest.fixture
def ws():
    with Workspace(builtin_tasks(["ring_buffer"])[0]) as workspace:
        yield workspace


def test_tests_are_read_only(ws):
    with pytest.raises(WorkspaceError, match="read-only"):
        ws.write("test_ring_buffer.py", "def test_nothing(): pass\n")


def test_new_files_cannot_be_created(ws):
    with pytest.raises(WorkspaceError, match="read-only"):
        ws.write("conftest.py", "collect_ignore = ['test_ring_buffer.py']\n")


def test_paths_cannot_escape_the_workspace(ws):
    with pytest.raises(WorkspaceError, match="outside"):
        ws.read("../outside.txt")
    with pytest.raises(WorkspaceError, match="outside"):
        ws.write("../ring_buffer.py", "")


def test_infinite_loops_time_out():
    task = builtin_tasks(["crc8"])[0]
    with Workspace(task, timeout=3) as ws:
        ws.write("crc8.py", "def crc8(data, poly=7, init=0):\n    while True:\n        pass\n")
        result = ws.run_tests()
    assert result.timed_out and not result.passed


def test_workspace_is_deleted_on_exit():
    with Workspace(builtin_tasks(["crc8"])[0]) as ws:
        root = ws.root
        assert root.exists()
    assert not root.exists()


QUIXBUGS = Path(os.environ.get("QUIXBUGS_DIR", "data/QuixBugs"))


@pytest.mark.skipif(not (QUIXBUGS / "python_testcases").is_dir(), reason="QuixBugs not downloaded")
@pytest.mark.parametrize("name", ["gcd", "quicksort", "shortest_paths", "wrap"])
def test_quixbugs_tasks_fail_buggy_and_pass_with_reference(name):
    (task,) = quixbugs_tasks(QUIXBUGS, [name])
    assert len(quixbugs_tasks(QUIXBUGS)) == 40
    assert not any("correct_python_programs" in f for f in task.files)
    with Workspace(task, timeout=30) as ws:
        assert not ws.run_tests().passed
        ws.write(task.editable[0], (QUIXBUGS / "correct_python_programs" / f"{name}.py").read_text(encoding="utf-8"))
        assert ws.run_tests().passed
