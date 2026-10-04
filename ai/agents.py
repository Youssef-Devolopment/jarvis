"""Autonomous multi-agent orchestration."""

from __future__ import annotations
import re
import time
from logger import get_logger

log = get_logger(__name__)

_MAX_AGENTS = 5
_TASK_TIMEOUT = 45


def _plan_split(question: str) -> list:
    """Ask the LLM to split a question into independent sub-tasks."""
    system = (
        "You break complex questions into 2-5 INDEPENDENT sub-tasks that "
        "can run in parallel. Each sub-task must be self-contained and "
        "answerable on its own. "
        "Reply ONLY with a JSON array of strings, each a short sub-task. "
        "If the question is simple and does not need splitting, "
        "reply exactly: SINGLE"
    )
    try:
        from ai.client import get_client
        c = get_client()
        model = getattr(c, "model", None) or c.default_model
        r = c._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            max_tokens=200,
            temperature=0.2,
            timeout=30,
        )
        raw = (r.choices[0].message.content or "").strip()
        if raw.upper() == "SINGLE" or len(raw) < 5:
            return []
        import json
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not m:
            return []
        arr = json.loads(m.group(0))
        tasks = [str(x).strip() for x in arr if str(x).strip()]
        return tasks[:_MAX_AGENTS]
    except Exception as exc:
        log.debug("Plan split failed: %s", exc)
        return []


def _run_one(task: str) -> dict:
    """Run a single sub-task through the LLM."""
    t0 = time.time()
    try:
        from ai.client import get_client
        c = get_client()
        r = c._client.chat.completions.create(
            model=c.default_model,
            messages=[
                {"role": "system",
                 "content": "Answer in 2-3 short sentences. Be specific. "
                            "No markdown, no lists."},
                {"role": "user", "content": task},
            ],
            max_tokens=300,
            temperature=0.3,
            timeout=_TASK_TIMEOUT,
        )
        answer = (r.choices[0].message.content or "").strip()
        return {
            "ok": True,
            "task": task,
            "answer": answer,
            "elapsed": round(time.time() - t0, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "task": task,
            "error": str(exc)[:150],
            "elapsed": round(time.time() - t0, 2),
        }


def _merge(question: str, results: list) -> str:
    """Ask the LLM to combine all sub-agent answers into one."""
    ok_results = [r for r in results if r.get("ok")]
    if not ok_results:
        return "All sub-agents failed. I cannot answer, sir."

    parts = []
    for i, r in enumerate(ok_results, 1):
        parts.append(f"[Sub-task {i}] {r['task']}\n{r['answer']}")
    evidence = "\n---\n".join(parts)

    system = (
        "You combine parallel sub-agent answers into ONE unified answer. "
        "3-5 short spoken sentences. No markdown, no lists. "
        "Address the original question directly."
    )
    user = (f"Original question: {question}\n\n"
            f"Sub-agent answers:\n{evidence}")

    try:
        from ai.client import get_client
        c = get_client()
        model = getattr(c, "model", None) or c.default_model
        r = c._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=400,
            temperature=0.2,
            timeout=45,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as exc:
        log.exception("Merge failed")
        return ok_results[0]["answer"]


def should_use_agents(question: str) -> bool:
    """Decide if a question warrants parallel agents."""
    if not question or len(question) < 20:
        return False
    low = question.lower()
    triggers = [
        "compare", "analyze", "research", "investigate",
        "list all", "find all", "pros and cons", "advantages",
        "multiple", "several", "each of", "for each",
    ]
    return any(t in low for t in triggers)


def run(question: str, show_progress: bool = True) -> dict:
    """Run an autonomous multi-agent session."""
    log.info("Agents: starting for %r", question[:80])
    t0 = time.time()

    tasks = _plan_split(question)
    if not tasks:
        # Too simple — single agent
        r = _run_one(question)
        return {
            "ok": r.get("ok", False),
            "mode": "single",
            "answer": r.get("answer") or r.get("error", ""),
            "tasks": 1,
            "ok_tasks": 1 if r.get("ok") else 0,
            "elapsed": round(time.time() - t0, 2),
        }

    log.info("Agents: %d sub-tasks", len(tasks))

    from ai.agent_pool import run_parallel
    results = run_parallel(tasks, _run_one, timeout_per_task=_TASK_TIMEOUT)

    final = _merge(question, results)
    ok_count = sum(1 for r in results if r.get("ok"))

    return {
        "ok": ok_count > 0,
        "mode": "parallel",
        "answer": final,
        "tasks": len(tasks),
        "ok_tasks": ok_count,
        "sub_results": results,
        "elapsed": round(time.time() - t0, 2),
    }
