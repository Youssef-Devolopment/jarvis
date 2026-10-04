"""Reality Check — verify answers against a second source before speaking."""

from __future__ import annotations
import re
from logger import get_logger

log = get_logger(__name__)

# Facts that don't need verification
_TRIVIAL = [
    r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay)\b",
    r"\b(?:what time|what day|what'?s the date|today'?s date)\b",
    r"^\s*[\d\s\+\-\*/\(\)\.]+\s*$",
    r"\b(?:translate|convert)\b",
    r"\b(?:open|launch|run|start)\b",
]

# Facts that MUST be verified
_NEEDS_CHECK = [
    r"\b(?:who|what|when|where|which)\s+(?:is|was|are|were)\b",
    r"\b(?:capital|population|founded|born|died)\b",
    r"\b(?:current|latest|recent|today'?s|this year)\b",
    r"\b(?:price|cost|how much)\b",
    r"\b(?:president|prime minister|ceo|leader)\b",
]

_TRIVIAL_RE = [re.compile(p, re.IGNORECASE) for p in _TRIVIAL]
_NEEDS_RE = [re.compile(p, re.IGNORECASE) for p in _NEEDS_CHECK]


def should_verify(question: str) -> bool:
    """Should we cross-check this question?"""
    if not question:
        return False
    q = question.strip()
    # Too short = probably not factual
    if len(q) < 10:
        return False
    # Trivial skip
    for pat in _TRIVIAL_RE:
        if pat.search(q):
            return False
    # Explicit factual
    for pat in _NEEDS_RE:
        if pat.search(q):
            return True
    # Long factual-sounding
    if len(q.split()) >= 5 and "?" in q:
        return True
    return False


def _extract_key_facts(text: str, max_facts: int = 3) -> list:
    """Pull candidate facts from an answer."""
    if not text:
        return []
    # Split sentences
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    facts = []
    for s in sentences[:5]:
        s = s.strip()
        if 5 < len(s) < 200:
            facts.append(s)
        if len(facts) >= max_facts:
            break
    return facts


def _quick_search(query: str) -> str:
    """Use web_search to get a second source."""
    try:
        from skills.web_search import _search_ddg_html
        results = _search_ddg_html(query)
        if not results:
            return ""
        parts = []
        for r in results[:3]:
            title = (r.get("title") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            if title or snippet:
                parts.append(f"{title}: {snippet}"[:300])
        return "\n".join(parts)
    except Exception as exc:
        log.debug("Reality check search failed: %s", exc)
        return ""


def _ask_judge(question: str, primary: str, second: str) -> dict:
    """Ask a small model: do these agree?"""
    system = (
        "You compare two answers to the same question. "
        "Reply EXACTLY in this format: "
        "AGREE: yes|no|partial | CONFIDENCE: 0-100 | NOTE: <one line>. "
        "No other text."
    )
    user = (
        f"Question: {question}\n\n"
        f"Answer A: {primary[:800]}\n\n"
        f"Second source: {second[:800]}"
    )
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
            max_tokens=80,
            temperature=0.0,
        )
        raw = (r.choices[0].message.content or "").strip()
        agree = "partial"
        confidence = 50
        note = ""
        m = re.search(r"AGREE:\s*(yes|no|partial)", raw, re.IGNORECASE)
        if m:
            agree = m.group(1).lower()
        m = re.search(r"CONFIDENCE:\s*(\d{1,3})", raw)
        if m:
            confidence = max(0, min(100, int(m.group(1))))
        m = re.search(r"NOTE:\s*(.+)", raw, re.IGNORECASE)
        if m:
            note = m.group(1).strip()[:200]
        return {"agree": agree, "confidence": confidence, "note": note}
    except Exception as exc:
        log.debug("Judge failed: %s", exc)
        return {"agree": "partial", "confidence": 50, "note": ""}


def verify(question: str, primary_answer: str) -> dict:
    """Full reality check flow."""
    if not should_verify(question):
        return {"checked": False, "confidence": 75, "agree": "skip",
                "note": "trivial"}

    second = _quick_search(question)
    if not second:
        return {"checked": False, "confidence": 60, "agree": "no_source",
                "note": "could not reach second source"}

    judge = _ask_judge(question, primary_answer, second)
    log.info("Reality check: agree=%s conf=%d",
             judge["agree"], judge["confidence"])

    result = {
        "checked": True,
        "confidence": judge["confidence"],
        "agree": judge["agree"],
        "note": judge["note"],
    }

    # If disagree → recommend Council
    if judge["agree"] == "no" or judge["confidence"] < 50:
        result["escalate_to_council"] = True
        result["council_reason"] = judge["note"] or "sources disagree"

    return result
