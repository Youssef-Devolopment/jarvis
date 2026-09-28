"""Synthesize council results into one final answer + confidence."""

from __future__ import annotations
import re
from logger import get_logger

log = get_logger(__name__)


def _build_evidence(council_result: dict) -> str:
    """Format all model answers into one block."""
    lines = []
    for i, r in enumerate(council_result.get("results", []), 1):
        if not r.get("ok"):
            continue
        lines.append(
            f"[Model {i}: {r['model']}]\n{r['answer']}\n"
        )
    return "\n---\n".join(lines)


def synthesize(question: str, council_result: dict) -> dict:
    """Ask the moderator to merge the answers."""
    evidence = _build_evidence(council_result)
    if not evidence:
        return {
            "ok": False,
            "answer": "All council models failed. I cannot answer reliably.",
            "confidence": 0,
        }

    model_count = council_result.get("ok_count", 0)
    spec_name = council_result.get("level", "council")

    system = (
        f"You are the moderator of a {model_count}-model council. "
        "Read every model's answer below and produce ONE unified answer. "
        "Rules:\n"
        "- 3-5 spoken sentences. No markdown, no lists.\n"
        "- Where models agree, state the answer confidently.\n"
        "- Where models disagree, note the disagreement and pick the "
        "answer supported by the strongest reasoning.\n"
        "- If answers are contradictory or all uncertain, say so plainly.\n"
        "- End with: 'CONFIDENCE: <0-100>' on its own line."
    )

    user = f"Question: {question}\n\nCouncil answers:\n{evidence}"

    try:
        from ai.client import get_client
        c = get_client()
        r = c._client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        raw = (r.choices[0].message.content or "").strip()

        # Extract confidence line
        confidence = 70
        m = re.search(r"CONFIDENCE:\s*(\d{1,3})", raw)
        if m:
            confidence = max(0, min(100, int(m.group(1))))
            raw = re.sub(r"\n?CONFIDENCE:\s*\d{1,3}\s*$", "", raw).strip()

        return {
            "ok": True,
            "answer": raw,
            "confidence": confidence,
            "models_used": model_count,
            "level": spec_name,
        }
    except Exception as exc:
        log.exception("Moderator failed")
        return {
            "ok": False,
            "answer": "Council ran but moderator failed to synthesize.",
            "confidence": 0,
            "error": str(exc)[:200],
        }


def self_critique(answer: str, question: str) -> dict:
    """Quick self-check: is the answer good enough?"""
    system = (
        "Review this draft answer. Score it 0-100 on how well it answers "
        "the question. Reply with EXACTLY: '<score>|<one-line reason>'. "
        "No other text."
    )
    user = f"Question: {question}\n\nDraft answer:\n{answer}"

    try:
        from ai.client import get_client
        c = get_client()
        r = c._client.chat.completions.create(
            model="deepseek-v4.1-flash:free",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        raw = (r.choices[0].message.content or "").strip()
        parts = raw.split("|", 1)
        score = 50
        try:
            score = max(0, min(100, int(parts[0].strip())))
        except Exception:
            pass
        reason = parts[1].strip() if len(parts) > 1 else ""
        return {"score": score, "reason": reason}
    except Exception:
        return {"score": 50, "reason": "critique unavailable"}
