"""Parallel multi-model deliberation."""

from __future__ import annotations
import concurrent.futures
import time
from typing import Optional
from moods.levels import Level, LEVEL_SPECS
from logger import get_logger

log = get_logger(__name__)


def _call_model(model_id: str, question: str, timeout: int) -> dict:
    """Call one model and return its answer + metadata."""
    t0 = time.time()
    try:
        from ai.client import get_client
        c = get_client()
        r = c._client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system",
                 "content": (
                     "Answer the user's question in 3-5 sentences. "
                     "Be direct and specific. "
                     "If you are uncertain, say so plainly. "
                     "No markdown, no bullet lists.")},
                {"role": "user", "content": question},
            ],
            max_tokens=400,
            temperature=0.3,
            timeout=timeout,
        )
        answer = (r.choices[0].message.content or "").strip()
        elapsed = time.time() - t0
        return {
            "model": model_id,
            "ok": True,
            "answer": answer,
            "elapsed": round(elapsed, 2),
        }
    except Exception as exc:
        log.warning("Council model %s failed: %s", model_id, exc)
        return {
            "model": model_id,
            "ok": False,
            "error": str(exc)[:200],
            "elapsed": round(time.time() - t0, 2),
        }


def run_council(question: str, level: Level) -> dict:
    """Run parallel calls across all models for a given level."""
    spec = LEVEL_SPECS[level]
    models = list(spec.models)
    if not models:
        return {"ok": False, "error": "no models for level"}

    log.info("Council %s: %d models, timeout %ds",
             spec.name, len(models), spec.timeout_sec)

    t0 = time.time()
    results = []

    # Parallel via ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as ex:
        futures = {
            ex.submit(_call_model, m, question, spec.timeout_sec): m
            for m in models
        }
        for fut in concurrent.futures.as_completed(
                futures, timeout=spec.timeout_sec + 5):
            try:
                results.append(fut.result())
            except concurrent.futures.TimeoutError:
                m = futures[fut]
                results.append({
                    "model": m, "ok": False,
                    "error": "timeout", "elapsed": spec.timeout_sec,
                })

    total_time = round(time.time() - t0, 2)
    ok_results = [r for r in results if r.get("ok")]

    log.info("Council %s done: %d/%d ok in %.1fs",
             spec.name, len(ok_results), len(models), total_time)

    return {
        "ok": len(ok_results) > 0,
        "level": spec.name,
        "question": question,
        "results": results,
        "ok_count": len(ok_results),
        "total_count": len(models),
        "elapsed": total_time,
    }
