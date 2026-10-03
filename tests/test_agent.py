"""The agent loop, driven by a scripted model so no API key is needed."""

import pytest

from mini_agent.agent import BUDGET_NOTE, SUBMIT_FIX_SCHEMA, run_tool, solve, solve_oneshot
from mini_agent.llm import ScriptedLLM
from mini_agent.tasks import builtin_tasks
from mini_agent.workspace import Workspace

BUGGY = "self._head = self._head + 1"
FIXED = "self._head = (self._head + 1) % len(self._buf)"


@pytest.fixture
def ws():
    with Workspace(builtin_tasks(["ring_buffer"])[0]) as workspace:
        yield workspace


def test_agent_fixes_the_bug_and_finishes(ws):
    llm = ScriptedLLM([
        [("run_tests", {}), ("read_file", {"path": "ring_buffer.py"})],
        [("replace_in_file", {"path": "ring_buffer.py", "old_text": BUGGY, "new_text": FIXED})],
        [("run_tests", {})],
        [("finish", {"summary": "pop() did not wrap the head index."})],
    ])
    attempt = solve(llm, ws)
    assert attempt.finished and attempt.stop == "finished"
    assert attempt.tool_calls == ["run_tests", "read_file", "replace_in_file", "run_tests"]
    assert ws.run_tests().passed
    # The model saw the failing run first and the passing run after its edit.
    first_results = llm.requests[1]["messages"][-1]["content"]
    assert first_results[0]["content"].startswith("FAILED")
    assert llm.requests[3]["messages"][-1]["content"][0]["content"].startswith("PASSED")


def test_editing_the_tests_is_refused(ws):
    output, is_error = run_tool(ws, "write_file", {"path": "test_ring_buffer.py", "content": ""})
    assert is_error and "read-only" in output


def test_ambiguous_replacement_is_refused(ws):
    output, is_error = run_tool(ws, "replace_in_file", {"path": "ring_buffer.py", "old_text": "self._size", "new_text": "x"})
    assert is_error and "exactly once" in output


def test_read_file_numbers_lines(ws):
    output, is_error = run_tool(ws, "read_file", {"path": "ring_buffer.py", "start_line": 4, "end_line": 5})
    assert not is_error
    assert "   4  class RingBuffer:" in output


def test_tool_budget_is_enforced(ws):
    call = [("run_tests", {})]
    llm = ScriptedLLM([call, call, call, [("finish", {"summary": "gave up"})]])
    attempt = solve(llm, ws, max_tool_calls=2)
    assert attempt.tool_calls == ["run_tests", "run_tests"]
    over_budget = llm.requests[3]["messages"][-1]["content"]
    assert over_budget[0]["is_error"] and over_budget[-1] == {"type": "text", "text": BUDGET_NOTE}


def test_prose_reply_gets_one_reminder_then_stops(ws):
    attempt = solve(ScriptedLLM(["I think it is fixed.", "Done."]), ws)
    assert not attempt.finished and attempt.stop == "no_finish"


def test_oneshot_writes_the_submitted_file(ws):
    fixed = ws.read("ring_buffer.py").replace(BUGGY, FIXED)
    llm = ScriptedLLM([[("submit_fix", {"path": "ring_buffer.py", "content": fixed})]])
    attempt = solve_oneshot(llm, ws)
    assert attempt.finished and ws.run_tests().passed
    assert llm.requests[0]["tools"] == [SUBMIT_FIX_SCHEMA]
    assert "current test output" in llm.requests[0]["messages"][0]["content"]


def test_oneshot_cannot_overwrite_tests(ws):
    llm = ScriptedLLM([
        [("submit_fix", {"path": "test_ring_buffer.py", "content": ""})],
        "no second answer",
    ])
    attempt = solve_oneshot(llm, ws)
    assert not attempt.finished
    error = llm.requests[1]["messages"][-1]["content"][0]
    assert error["is_error"] and "read-only" in error["content"]
