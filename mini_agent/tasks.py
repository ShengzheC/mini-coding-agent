"""Task sources: the small built-in tasks in tasks/, and the QuixBugs Python benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from .workspace import Task

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "tasks"


def builtin_tasks(names: list[str] | None = None) -> list[Task]:
    """Each task directory holds a task.json plus the files it names."""
    tasks = []
    for task_dir in sorted(p for p in BUILTIN_DIR.iterdir() if (p / "task.json").is_file()):
        if names and task_dir.name not in names:
            continue
        spec = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        tasks.append(
            Task(
                name=task_dir.name,
                source=task_dir,
                files=tuple(spec["editable"] + spec["tests"] + spec.get("support", [])),
                editable=tuple(spec["editable"]),
                tests=tuple(spec["tests"]),
                description=spec["description"],
            )
        )
    return tasks


def quixbugs_tasks(root: Path, names: list[str] | None = None) -> list[Task]:
    """One task per QuixBugs Python program: fix python_programs/<name>.py so its tests pass.

    Expects a clone of https://github.com/jkoppel/QuixBugs at `root`. The reference fixes
    in correct_python_programs/ are never copied into the workspace.
    """
    root = Path(root)
    tests_dir = root / "python_testcases"
    if not tests_dir.is_dir():
        raise FileNotFoundError(f"{tests_dir} not found; clone QuixBugs first (see README)")
    tasks = []
    for test_file in sorted(tests_dir.glob("test_*.py")):
        name = test_file.stem.removeprefix("test_")
        if names and name not in names:
            continue
        program = f"python_programs/{name}.py"
        support = ["conftest.py", "python_testcases/load_testdata.py", "python_testcases/node.py", "python_programs/node.py"]
        support += [f"json_testcases/{name}.json"] if (root / f"json_testcases/{name}.json").is_file() else []
        tasks.append(
            Task(
                name=name,
                source=root,
                files=(program, f"python_testcases/test_{name}.py", *support),
                editable=(program,),
                tests=(f"python_testcases/test_{name}.py",),
                description=(
                    f"The function in {program} has a bug (QuixBugs benchmark). "
                    f"Fix it so the tests in python_testcases/test_{name}.py pass."
                ),
            )
        )
    return tasks
