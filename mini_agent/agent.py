"""A minimal coding agent: read code, run tests, edit, repeat, then finish.

The tool-use loop is written by hand so each step is visible. The agent can only touch the
workspace through the tools below; the benchmark decides success by running the tests
itself afterwards, not by trusting the agent's own claim.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass, field

from .llm import USAGE_FIELDS
from .workspace import MAX_READ_LINES, Workspace, WorkspaceError

SYSTEM_PROMPT = """You are a careful software engineer. Fix the bug described by the user in a small Python project, working only through the tools.

How to work:
- Read the code and run the tests first, so you know what fails and why.
- Make the smallest change that fixes the underlying logic. Do not special-case test inputs. The tests are read-only.
- Run the tests again after each change. When they pass, call finish with one or two sentences on what the bug was and how you fixed it.
- If you cannot make the tests pass within your budget, call finish anyway and say what still fails.
- You have at most {max_tool_calls} tool calls. Independent calls (for example reading two files) can go in the same turn."""

ONESHOT_PROMPT = """You are a careful software engineer. The user message contains a small Python project with a bug, its tests, and the current test output. Reply by calling submit_fix once with the complete corrected file. Make the smallest change that fixes the underlying logic, and do not special-case test inputs."""

_PATH = {"type": "string", "description": "path relative to the workspace root"}

TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List the files in the workspace and mark the ones you may edit.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_file",
        "description": f"Read a file with line numbers (at most {MAX_READ_LINES} lines per call). Optionally pass a 1-based line range.",
        "input_schema": {
            "type": "object",
            "properties": {"path": _PATH, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "replace_in_file",
        "description": (
            "Replace one exact occurrence of old_text with new_text in an editable file. old_text must match "
            "the file exactly, including indentation, and occur exactly once; include neighboring lines if needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": _PATH, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Overwrite an editable file with new content. Prefer replace_in_file for small fixes.",
        "input_schema": {
            "type": "object",
            "properties": {"path": _PATH, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_tests",
        "description": "Run the task's tests with pytest and return the summary plus failure details.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "finish",
        "description": "End the task. Call this after the tests pass, or when you cannot make further progress.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "what the bug was and how you fixed it"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]

SUBMIT_FIX_SCHEMA = {
    "name": "submit_fix",
    "description": "Submit the complete corrected content of the editable file.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"path": _PATH, "content": {"type": "string"}},
        "required": ["path", "content"],
        "additionalProperties": False,
    },
}

REMINDER = "Continue with the tools, or call finish if you are done."
BUDGET_NOTE = "You have used your tool budget. Call finish now."


@dataclass
class Attempt:
    task: str
    finished: bool = False
    summary: str = ""
    stop: str = "no_finish"  # finished | no_finish | tool_budget | refusal | max_tokens
    tool_calls: list[str] = field(default_factory=list)
    requests: int = 0
    usage: Counter = field(default_factory=Counter)
    transcript: list[dict] = field(default_factory=list)


def solve(llm, ws: Workspace, max_tool_calls: int = 15) -> Attempt:
    """Let the model work on the task with tools until it calls finish or runs out of budget."""
    task = ws.task
    message = (
        f"{task.description}\n\nEditable files: {', '.join(task.editable)}\n"
        f"Tests: pytest {' '.join(task.tests)}"
    )
    attempt = Attempt(task.name)
    messages: list[dict] = [{"role": "user", "content": message}]
    attempt.transcript.append({"role": "user", "text": message})
    system = SYSTEM_PROMPT.format(max_tool_calls=max_tool_calls)
    reminded = False

    while attempt.requests < max_tool_calls + 3:
        response = _call(llm, attempt, system, TOOL_SCHEMAS, messages)
        if response.stop_reason in ("refusal", "max_tokens"):
            attempt.stop = response.stop_reason
            return attempt

        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            if reminded:
                return attempt
            reminded = True
            messages.append({"role": "user", "content": REMINDER})
            attempt.transcript.append({"role": "user", "text": REMINDER})
            continue

        results = []
        for call in calls:
            if call.name == "finish":
                attempt.finished, attempt.summary, attempt.stop = True, str(call.input.get("summary", "")), "finished"
                return attempt
            if len(attempt.tool_calls) >= max_tool_calls:
                output, is_error = f"Error: {BUDGET_NOTE}", True
            else:
                attempt.tool_calls.append(call.name)
                output, is_error = run_tool(ws, call.name, dict(call.input))
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": output, "is_error": is_error})
            attempt.transcript.append({"role": "tool", "name": call.name, "output": output, "is_error": is_error})
        if len(attempt.tool_calls) >= max_tool_calls:
            results.append({"type": "text", "text": BUDGET_NOTE})
        messages.append({"role": "user", "content": results})

    attempt.stop = "tool_budget"
    return attempt


def solve_oneshot(llm, ws: Workspace) -> Attempt:
    """Ablation without an agent loop: show the code, tests and failures once, take one full-file fix."""
    task = ws.task
    test_run = ws.run_tests()
    parts = [task.description]
    parts += [f"=== {rel} (editable) ===\n{ws.read(rel)}" for rel in task.editable]
    parts += [f"=== {rel} (tests) ===\n{ws.read(rel)}" for rel in task.tests]
    parts.append(f"=== current test output ===\n{test_run.output}")
    message = "\n\n".join(parts)
    attempt = Attempt(task.name)
    attempt.transcript.append({"role": "user", "text": message})
    messages = [{"role": "user", "content": message}]

    for _ in range(2):  # one answer, plus one retry if the submission is invalid
        response = _call(llm, attempt, ONESHOT_PROMPT, [SUBMIT_FIX_SCHEMA], messages)
        if response.stop_reason in ("refusal", "max_tokens"):
            attempt.stop = response.stop_reason
            return attempt
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            messages.append({"role": "user", "content": "Call submit_fix with the complete corrected file."})
            continue
        try:
            ws.write(calls[0].input["path"], calls[0].input["content"])
        except (WorkspaceError, KeyError) as e:
            # Every tool_use needs a tool_result; only the first submission is considered.
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                 "content": f"Error: {e}" if i == 0 else "Error: submit one fix at a time."}
                for i, c in enumerate(calls)
            ]})
            continue
        attempt.finished, attempt.stop = True, "finished"
        return attempt
    return attempt


def run_tool(ws: Workspace, name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool call against the workspace. Returns (output text, is_error)."""
    try:
        if name == "list_files":
            return "\n".join(f"{p}{'  (editable)' if p in ws.task.editable else ''}" for p in ws.list_files()), False
        if name == "read_file":
            return _read(ws, args["path"], args.get("start_line"), args.get("end_line")), False
        if name == "replace_in_file":
            text = ws.read(args["path"])
            count = text.count(args["old_text"])
            if count != 1:
                raise WorkspaceError(f"old_text occurs {count} times in {args['path']}; it must occur exactly once")
            return _write(ws, args["path"], text.replace(args["old_text"], args["new_text"])), False
        if name == "write_file":
            return _write(ws, args["path"], args["content"]), False
        if name == "run_tests":
            result = ws.run_tests()
            return f"{'PASSED' if result.passed else 'FAILED'}: {result.summary}\n\n{result.output}", False
        return f"Error: unknown tool {name!r}", True
    except (WorkspaceError, KeyError, TypeError) as e:
        return f"Error: {e}", True


def _read(ws: Workspace, path: str, start: int | None, end: int | None) -> str:
    lines = ws.read(path).splitlines()
    start = max(1, int(start or 1))
    end = min(len(lines), int(end or len(lines)), start + MAX_READ_LINES - 1)
    numbered = "\n".join(f"{i:>4}  {lines[i - 1]}" for i in range(start, end + 1))
    more = f"\n... ({len(lines) - end} more lines)" if end < len(lines) else ""
    return f"{path} (lines {start}-{end} of {len(lines)}):\n{numbered}{more}"


def _write(ws: Workspace, path: str, new_text: str) -> str:
    old_text = ws.read(path)
    ws.write(path, new_text)
    diff = "".join(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True), n=1))
    return f"Updated {path}:\n{diff}" if diff else f"{path} unchanged (new content is identical)."


def _call(llm, attempt: Attempt, system: str, tools: list[dict], messages: list[dict]):
    response = llm.create(system=system, tools=tools, messages=messages)
    attempt.requests += 1
    for f in USAGE_FIELDS:
        attempt.usage[f] += getattr(response.usage, f, 0) or 0
    # Append the full content (thinking blocks included) so the history stays valid.
    messages.append({"role": "assistant", "content": response.content})
    for block in response.content:
        if block.type == "thinking" and getattr(block, "thinking", ""):
            attempt.transcript.append({"role": "assistant", "thinking": block.thinking})
        elif block.type == "text" and block.text.strip():
            attempt.transcript.append({"role": "assistant", "text": block.text})
        elif block.type == "tool_use":
            attempt.transcript.append({"role": "assistant", "tool_call": block.name, "input": dict(block.input)})
    return response
