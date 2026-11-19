"""The only place a language model touches an answer - and it can only re-phrase verified text."""
from __future__ import annotations

from . import guard
from . import ollama_client

PROMPT = """You are an editor, not an analyst. Rewrite the VERIFIED ANSWER below as clear, concise executive prose (at most {limit} words).
Hard rules:
- Do not add, remove or change any fact, number, date, name or identifier. Do not do any arithmetic.
- Keep every caveat and uncertainty exactly as strong as written.
- Do not add recommendations or opinions that are not already present.
{persona}
VERIFIED ANSWER:
{verified}
"""


def safe_rewrite(verified: str, evidence: str = "", require_uncertainty: bool = False, persona: str = "", generate=None, limit: int = 220) -> dict:
    """Return {'text','used_llm','guard_ok','reasons'}. Falls back to `verified` unless the rewrite passes the guard."""
    gen = generate or ollama_client.generate
    candidate = None
    try:
        candidate = gen(PROMPT.format(verified=verified, persona=persona, limit=limit))
    except Exception:
        candidate = None
    if not candidate:
        return {"text": verified, "used_llm": False, "guard_ok": True, "reasons": ["no model output"]}
    res = guard.check(candidate, verified, evidence, require_uncertainty=require_uncertainty)
    if res.ok:
        return {"text": candidate, "used_llm": True, "guard_ok": True, "reasons": []}
    return {"text": verified, "used_llm": False, "guard_ok": False, "reasons": res.reasons}
