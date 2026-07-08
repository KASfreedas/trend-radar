"""
Recommendation engine — briefing/synthesize.py  (03_BRIEFING_LAYER.md §D)

Turns scored candidates + menu gaps (+ optional competitor move) into the
written briefing: Launch Next / Hold-Watch / Skip buckets, each with ONE
plain "why" sentence that restates only figures already present in the
candidate's `evidence`.

Design rules (non-negotiable, from CLAUDE.md + §D):
  - No invented data. The model may only cite numbers that exist in the
    scraped evidence. We enforce this after the call: any number in a "why"
    that is not present in that item's evidence causes the sentence to be
    replaced with the deterministic, evidence-only version.
  - Every recommendation references at least one evidence item.
  - If confidence is low across all candidates, return a short "quiet month".

The module works with OR without an LLM:
  - LLM_API_KEY set   -> one Anthropic Messages API call, then validated.
  - LLM_API_KEY unset -> deterministic synthesis (restates evidence only).
Either way the output schema is identical, so render.py / run.py don't care.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6").strip()
LLM_URL = "https://api.anthropic.com/v1/messages"

# Verbatim system-prompt guardrails (03_BRIEFING_LAYER.md §D).
GUARDRAILS = (
    "Only cite numbers present in the provided data. Do not estimate, round "
    "into new figures, or invent statistics.\n"
    "Every recommendation must reference at least one evidence item.\n"
    "If confidence is low across all candidates, return a short 'quiet month' "
    "briefing."
)

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


# ── Bucketing (shared by deterministic + LLM paths) ─────────────────────────
def _bucket(scored: list[dict], gap_result: dict) -> dict:
    """Split scored candidates into launch / watch / skip lists."""
    launch = [c for c in scored
              if c["direction"] == "rising" and c["confidence"] in ("high", "medium")][:3]
    watch = [c for c in scored if c["direction"] == "peaking"][:3]
    skip = [c for c in scored if c["direction"] == "fading" and c["confidence"] == "high"][:2]
    gaps = gap_result.get("gaps", [])[:5]
    retire = gap_result.get("retire", [])[:4]
    return {"launch": launch, "watch": watch, "skip": skip, "gaps": gaps, "retire": retire}


def _is_quiet(buckets: dict) -> bool:
    """Quiet month: nothing strong to launch and no menu gaps worth naming."""
    return not buckets["launch"] and not buckets["gaps"]


# ── Deterministic "why" (evidence-only, no invention) ───────────────────────
def _deterministic_why(c: dict, *, is_gap: bool = False) -> str:
    direction = c.get("direction", "flat")
    confidence = c.get("confidence", "low")
    evidence = c.get("evidence", []) or []
    frame = {
        "rising": "Rising momentum", "peaking": "At or near its peak",
        "fading": "Cooling off", "flat": "Holding steady",
    }.get(direction, "Holding steady")
    lead = f"{frame} with {confidence} confidence"
    if is_gap:
        lead = f"Not on the menu and {direction} ({confidence} confidence)"
    if evidence:
        return f"{lead} — " + "; ".join(evidence[:2]) + "."
    return f"{lead}; limited signal — worth a closer look before committing."


def _deterministic_synthesis(scored: list[dict], gap_result: dict, competitor: dict | None) -> dict:
    buckets = _bucket(scored, gap_result)
    quiet = _is_quiet(buckets)

    def pack(items, is_gap_fn=lambda c: False):
        out = []
        for c in items:
            is_gap = is_gap_fn(c)
            out.append({
                "term": c.get("term", ""),
                "category": c.get("category", ""),
                "direction": c.get("direction", "flat"),
                "confidence": c.get("confidence", "low"),
                "current_interest": c.get("current_interest", 0),
                "delta": c.get("delta", 0),
                "on_menu": c.get("on_menu", True),
                "evidence": c.get("evidence", []) or [],
                "why": _deterministic_why(c, is_gap=is_gap),
            })
        return out

    if quiet:
        headline = "Quiet month — no strong moves detected across sources. Hold the current menu and revisit next cycle."
    else:
        n_launch, n_gaps = len(buckets["launch"]), len(buckets["gaps"])
        bits = []
        if n_launch:
            bits.append(f"{n_launch} flavor{'s' if n_launch != 1 else ''} ready to launch")
        if n_gaps:
            bits.append(f"{n_gaps} menu gap{'s' if n_gaps != 1 else ''} worth a limited special")
        headline = " and ".join(bits).capitalize() + " this month." if bits else "Signals are mixed this month."

    return {
        "quiet_month": quiet,
        "headline": headline,
        "launch": pack(buckets["launch"], is_gap_fn=lambda c: not c.get("on_menu", True)),
        "watch": pack(buckets["watch"]),
        "skip": pack(buckets["skip"]),
        "gaps": pack(buckets["gaps"], is_gap_fn=lambda c: True),
        "retire": pack(buckets["retire"]),
        "competitor": competitor,
        "texture_tip": None,
        "source": "deterministic",
    }


# ── Guardrail enforcement ───────────────────────────────────────────────────
def _numbers_in(text: str) -> set[str]:
    return {m.group(0).rstrip(".") for m in _NUM_RE.finditer(text or "")}


def _why_is_grounded(why: str, evidence: list[str]) -> bool:
    """A 'why' is grounded iff every number it cites appears in the evidence."""
    haystack = " ".join(evidence or [])
    hay_nums = _numbers_in(haystack)
    for n in _numbers_in(why):
        if n not in hay_nums and n not in haystack:
            return False
    return True


def _enforce_guardrails(synth: dict, deterministic: dict) -> dict:
    """For each item, drop any LLM 'why' that cites a number not in its evidence,
    replacing it with the deterministic evidence-only sentence."""
    det_index = {}
    for bucket in ("launch", "watch", "skip", "gaps", "retire"):
        for item in deterministic.get(bucket, []):
            det_index[(bucket, item["term"])] = item["why"]

    for bucket in ("launch", "watch", "skip", "gaps", "retire"):
        for item in synth.get(bucket, []):
            ev = item.get("evidence", [])
            why = (item.get("why") or "").strip()
            if not why or not ev or not _why_is_grounded(why, ev):
                item["why"] = det_index.get((bucket, item.get("term", "")),
                                            _deterministic_why(item))
    # Texture tip: qualitative only — strip if it smuggles in numbers.
    tip = synth.get("texture_tip")
    if tip and _numbers_in(tip):
        synth["texture_tip"] = None
    return synth


# ── LLM path ────────────────────────────────────────────────────────────────
def _llm_payload(scored: list[dict], gap_result: dict, competitor: dict | None) -> dict:
    buckets = _bucket(scored, gap_result)
    return {
        "launch": buckets["launch"], "watch": buckets["watch"], "skip": buckets["skip"],
        "gaps": buckets["gaps"], "retire": buckets["retire"], "competitor": competitor,
    }


def _call_llm(payload: dict, voice: str = "") -> dict | None:
    """One Anthropic Messages API call. Returns parsed JSON synthesis or None on any failure."""
    import requests

    brand_context = (
        f"\nBrand context from the owner — use this to judge fit and tone, "
        f"but the guardrails above still apply (never invent numbers, never "
        f"cite a figure not in the evidence):\n\"{voice}\"\n"
        if voice else ""
    )

    instructions = (
        "You are the recommendation engine for a bakery's monthly "
        "'Specials Board Briefing'. Convert the scored trend data below into a "
        "decision for a busy bakery owner.\n\n"
        "Rank candidates by momentum x confidence x gap-status x feasibility. "
        "Bucket into Launch Next / Hold-Watch / Skip. Write ONE plain sentence "
        "of 'why' per item, restating only figures present in that item's "
        "`evidence`. Name the menu gaps explicitly. If signals are weak, say "
        "'quiet month, no strong moves' rather than padding to five items.\n"
        f"{brand_context}\n"
        "Return ONLY a JSON object with this exact shape (no prose, no markdown):\n"
        '{"quiet_month": bool, "headline": str, '
        '"launch":[{"term":str,"why":str}], "watch":[{"term":str,"why":str}], '
        '"skip":[{"term":str,"why":str}], "gaps":[{"term":str,"why":str}], '
        '"texture_tip": str|null}\n\n'
        f"DATA:\n{json.dumps(payload, default=str)}"
    )

    body = {
        "model": LLM_MODEL,
        "max_tokens": 1500,
        "system": GUARDRAILS,
        "messages": [{"role": "user", "content": instructions}],
    }
    headers = {
        "x-api-key": LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = requests.post(LLM_URL, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = text.strip()
    # Tolerate accidental code fences.
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text.strip("`")
        text = text.lstrip("json").strip()
    return json.loads(text)


def _merge_llm_into_deterministic(llm: dict, deterministic: dict) -> dict:
    """Take LLM headline + per-item 'why' strings, but keep deterministic's
    real numbers/evidence/structure. The LLM only contributes phrasing."""
    why_map = {}
    for bucket in ("launch", "watch", "skip", "gaps"):
        for item in llm.get(bucket, []):
            t = (item.get("term") or "").lower()
            if t:
                why_map[(bucket, t)] = item.get("why", "")

    merged = json.loads(json.dumps(deterministic))  # deep copy
    for bucket in ("launch", "watch", "skip", "gaps"):
        for item in merged.get(bucket, []):
            key = (bucket, item.get("term", "").lower())
            if key in why_map and why_map[key].strip():
                item["why"] = why_map[key].strip()

    if isinstance(llm.get("headline"), str) and llm["headline"].strip():
        merged["headline"] = llm["headline"].strip()
    if isinstance(llm.get("quiet_month"), bool):
        merged["quiet_month"] = llm["quiet_month"]
    if isinstance(llm.get("texture_tip"), str) and llm["texture_tip"].strip():
        merged["texture_tip"] = llm["texture_tip"].strip()
    merged["source"] = "llm"
    return merged


# ── Public entry point ──────────────────────────────────────────────────────
def synthesize(scored: list[dict], gap_result: dict, competitor: dict | None = None) -> dict:
    """
    Convert scored data into a structured briefing synthesis.
    Always returns the same schema; falls back to deterministic synthesis when
    no LLM key is configured, the call fails, or the result is empty/quiet.
    """
    deterministic = _deterministic_synthesis(scored, gap_result, competitor)

    # Empty / quiet data: never spend an API call, never risk fabrication.
    if deterministic["quiet_month"] or not LLM_API_KEY:
        return deterministic

    try:
        from briefing.dna import load_dna
        voice = load_dna().get("voice", "").strip()
        llm = _call_llm(_llm_payload(scored, gap_result, competitor), voice=voice)
        if not isinstance(llm, dict):
            return deterministic
        merged = _merge_llm_into_deterministic(llm, deterministic)
        return _enforce_guardrails(merged, deterministic)
    except Exception as e:
        # Reliability: a flaky LLM must never block the briefing.
        print(f"[synthesize] LLM call failed ({e!r}); using deterministic synthesis.")
        return deterministic
