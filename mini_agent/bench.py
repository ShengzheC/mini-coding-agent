"""Benchmark the coding agent (or the one-shot ablation) on built-in tasks or QuixBugs.

    python -m mini_agent.bench --suite builtin
    python -m mini_agent.bench --suite quixbugs --quixbugs data/QuixBugs --limit 5
    python -m mini_agent.bench --suite quixbugs --quixbugs data/QuixBugs --method oneshot
    python -m mini_agent.bench --suite builtin --task ring_buffer --verbose

A task counts as solved only if the benchmark's own test run passes after the attempt.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .agent import Attempt, solve, solve_oneshot
from .llm import DEFAULT_MODEL, USAGE_FIELDS, ClaudeLLM, estimate_cost
from .tasks import builtin_tasks, quixbugs_tasks
from .workspace import Workspace


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(errors="replace")  # consoles with legacy code pages cannot print every character
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suite", choices=["builtin", "quixbugs"], default="builtin")
    p.add_argument("--quixbugs", default="data/QuixBugs", help="path to a QuixBugs clone")
    p.add_argument("--method", choices=["agent", "oneshot"], default="agent")
    p.add_argument("--task", action="append", help="only run this task (repeatable)")
    p.add_argument("--limit", type=int, default=None, help="only run the first N tasks")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--max-tool-calls", type=int, default=15)
    p.add_argument("--timeout", type=float, default=30.0, help="seconds per test run")
    p.add_argument("--verbose", action="store_true", help="print each step of every attempt")
    p.add_argument("--out", default="runs")
    args = p.parse_args(argv)

    tasks = builtin_tasks(args.task) if args.suite == "builtin" else quixbugs_tasks(Path(args.quixbugs), args.task)
    tasks = tasks[: args.limit]
    if not tasks:
        p.error("no tasks selected")
    llm = ClaudeLLM(args.model, args.effort)
    tag = f"{args.suite}-{args.method}-{args.model}-{args.effort}"
    out_dir = Path(args.out) / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, task in enumerate(tasks, 1):
        start = time.time()
        with Workspace(task, timeout=args.timeout) as ws:
            attempt = solve(llm, ws, args.max_tool_calls) if args.method == "agent" else solve_oneshot(llm, ws)
            final = ws.run_tests()  # the verdict comes from this run, not from the agent
            diff = ws.diff()
        row = _row(task.name, attempt, final.passed, final.summary, args.model, time.time() - start)
        rows.append(row)
        record = {**row, "agent_summary": attempt.summary, "diff": diff, "transcript": attempt.transcript}
        (out_dir / f"{task.name}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if args.verbose:
            _print_attempt(attempt, diff)
        mark = "solved" if row["solved"] else "FAILED"
        print(
            f"[{i:>2}/{len(tasks)}] {mark}  {task.name:<28} tools={row['n_tool_calls']:>2} "
            f"tests={row['n_test_runs']:>2}  ${row['cost_usd'] or 0:.3f}  ({final.summary})"
        )

    report = _report(rows, tag)
    print("\n" + report)
    (out_dir / "results.json").write_text(json.dumps({"args": vars(args), "rows": rows}, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"\nSaved to {out_dir}")


def _row(name: str, attempt: Attempt, passed: bool, summary: str, model: str, seconds: float) -> dict:
    usage = {f: attempt.usage[f] for f in USAGE_FIELDS}
    return {
        "task": name,
        "solved": passed,
        "claimed_done": attempt.finished,
        "stop": attempt.stop,
        "final_tests": summary,
        "n_tool_calls": len(attempt.tool_calls),
        "n_test_runs": attempt.tool_calls.count("run_tests"),
        "n_requests": attempt.requests,
        "usage": usage,
        "cost_usd": estimate_cost(model, usage),
        "seconds": round(seconds, 1),
    }


def _report(rows: list[dict], tag: str) -> str:
    n = len(rows)
    solved = sum(r["solved"] for r in rows)
    false_claims = [r["task"] for r in rows if r["claimed_done"] and not r["solved"]]
    cost = sum(r["cost_usd"] or 0 for r in rows)
    lines = [
        f"## {tag}",
        "",
        f"Solved: {solved}/{n} = {solved / n:.0%}",
        f"Mean tool calls: {sum(r['n_tool_calls'] for r in rows) / n:.1f}; "
        f"mean test runs: {sum(r['n_test_runs'] for r in rows) / n:.1f}; "
        f"mean requests: {sum(r['n_requests'] for r in rows) / n:.1f}",
        f"Output tokens: {sum(r['usage']['output_tokens'] for r in rows):,}; approx. cost: ${cost:.2f}",
        f"Said done but tests fail: {len(false_claims)}" + (f" ({', '.join(false_claims)})" if false_claims else ""),
    ]
    unsolved = [r["task"] for r in rows if not r["solved"]]
    if unsolved:
        lines.append(f"Unsolved: {', '.join(unsolved)}")
    return "\n".join(lines)


def _print_attempt(attempt: Attempt, diff: str) -> None:
    for entry in attempt.transcript:
        if "thinking" in entry:
            print(f"  [thinking] {entry['thinking'].strip()}")
        elif "text" in entry:
            text = entry["text"].strip()
            print(f"  [{entry['role']}] {text[:1500]}{' ...' if len(text) > 1500 else ''}")
        elif "tool_call" in entry:
            shown = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v) for k, v in entry["input"].items()}
            print(f"  [call] {entry['tool_call']}({json.dumps(shown)})")
        else:
            body = entry["output"].splitlines()
            shown = "\n    ".join(body[:20] + ([f"... ({len(body) - 20} more lines)"] if len(body) > 20 else []))
            print(f"  [result{' ERROR' if entry['is_error'] else ''}]\n    {shown}")
    print(f"  [final diff]\n{diff or '  (no changes)'}")


if __name__ == "__main__":
    main()
