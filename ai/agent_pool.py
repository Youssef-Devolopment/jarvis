"""Parallel execution pool for sub-agents."""

from __future__ import annotations
import concurrent.futures
import time
from typing import Callable
from logger import get_logger

log = get_logger(__name__)

MAX_WORKERS = 5


def run_parallel(tasks: list, worker: Callable,
                 timeout_per_task: int = 60) -> list:
    """Run tasks in parallel. Returns list of results in original order.

    Each task is passed as-is to worker(task). Worker must be
    picklable/thread-safe (we use threads, not processes).
    """
    if not tasks:
        return []

    results = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS, len(tasks))) as ex:
        futures = {
            ex.submit(worker, task): i
            for i, task in enumerate(tasks)
        }
        for fut in concurrent.futures.as_completed(
                futures, timeout=timeout_per_task * len(tasks) + 10):
            idx = futures[fut]
            try:
                results[idx] = fut.result(timeout=timeout_per_task)
            except concurrent.futures.TimeoutError:
                results[idx] = {
                    "ok": False,
                    "error": "timeout",
                    "elapsed": timeout_per_task,
                }
            except Exception as exc:
                log.warning("Agent task %d failed: %s", idx, exc)
                results[idx] = {
                    "ok": False,
                    "error": str(exc)[:150],
                    "elapsed": 0,
                }

    return results
