"""ML-ready observation log — briefing/dataset.py

The one thing you cannot reconstruct later. Every cycle, the moment a briefing
is built, this snapshots the FEATURE VECTOR of every scored term exactly as it
looked when the system made its call, plus what the system decided. If you don't
record the features at decision time, they're gone forever — you can't go back
and ask "what was TikTok showing for this term three cycles ago."

Outcomes (did it sell — from the proof loop) and feedback (was it useful — from
client ratings) are captured separately as they resolve, and JOINED back in at
export time by (cycle, term). The result is a clean, longitudinal, labeled
training table: for every (cycle, term), the exact inputs a model would see plus
the label it should learn to predict.

Nothing here trains a model. It exists so that when there's finally enough real
data (many cycles × many terms × ideally many bakeries), it's already perfectly
organized to train on — no reconstruction, no gaps, consistent features.
"""

from __future__ import annotations
import csv
import io
import json
from datetime import datetime, timezone

from tenancy import data_path

OBSERVATIONS_PATH = data_path("history", "observations.json")

# Features captured from score_all() output — the real inputs the system uses to
# decide. Keep this list STABLE across cycles so the time-series stays clean
# (appending a new feature later is fine; renaming/removing breaks history).
FEATURE_FIELDS = ("direction", "delta", "current_interest", "confidence",
                  "sources_agreeing")


def _load() -> list[dict]:
    if OBSERVATIONS_PATH.exists():
        try:
            return json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
    return []


def _save(rows: list[dict]) -> None:
    OBSERVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OBSERVATIONS_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                                 encoding="utf-8")


def _decision_map(synthesis: dict | None) -> dict:
    """term(lower) -> the bucket the briefing actually put it in."""
    out: dict = {}
    if not synthesis:
        return out
    # Ordered by strength: a term that's both a "launch" pick and a "gap" is
    # labeled by the stronger, more-actionable bucket (first write wins).
    for bucket in ("launch", "watch", "skip", "retire", "gaps"):
        for item in synthesis.get(bucket, []) or []:
            t = (item.get("term") or "").lower()
            if t and t not in out:
                out[t] = "gap" if bucket == "gaps" else bucket
    return out


def _menu_status_map(gap_result: dict | None) -> dict:
    out: dict = {}
    if not gap_result:
        return out
    for c in gap_result.get("gaps", []) or []:
        out[(c.get("term") or "").lower()] = "off_menu"
    for key in ("covered", "retire"):
        for c in gap_result.get(key, []) or []:
            out[(c.get("term") or "").lower()] = "on_menu"
    return out


def record_observations(scored, gap_result, synthesis, cycle_id, cycle_label) -> int:
    """Snapshot every scored term's features + decision for this cycle.
    Idempotent per (cycle_id, term): re-generating a cycle replaces its rows
    rather than duplicating them. Returns the number of observations written."""
    rows = [r for r in _load() if r.get("cycle_id") != cycle_id]
    decisions = _decision_map(synthesis)
    menu = _menu_status_map(gap_result)
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    for c in scored or []:
        term = c.get("term", "")
        if not term:
            continue
        rows.append({
            "cycle_id": cycle_id,
            "cycle_label": cycle_label,
            "observed_at": now,
            "term": term,
            "category": c.get("category", ""),
            "features": {f: c.get(f) for f in FEATURE_FIELDS},
            "menu_status": menu.get(term.lower(), "unclassified"),
            "decision": decisions.get(term.lower(), "none"),
            # Labels — backfilled at export time (build_training_table):
            "outcome": None,
            "feedback": None,
        })
        written += 1
    _save(rows)
    return written


def list_observations() -> list[dict]:
    return _load()


def build_training_table() -> list[dict]:
    """Join observations with resolved outcomes + feedback into labeled rows.
    The outcome label comes from the proof loop (did it sell); feedback from the
    client's term-level ratings. Rows whose label hasn't resolved yet keep a
    null outcome — they're still valid feature snapshots, just not yet
    trainable."""
    from briefing.outcomes import list_outcomes
    try:
        from briefing.feedback import feedback_by_term
        fb = feedback_by_term()
    except Exception:
        fb = {}
    outcome_map = {(o.get("month"), (o.get("term") or "").lower()): o.get("status")
                   for o in list_outcomes()}
    rows = []
    for r in _load():
        term_l = (r.get("term") or "").lower()
        status = outcome_map.get((r.get("cycle_label"), term_l))
        # "not_yet" means the owner hasn't resolved it — it carries no training
        # signal, so it's not a label. Only resolved statuses count.
        outcome = status if status and status != "not_yet" else None
        rows.append({**r, "outcome": outcome, "feedback": fb.get(term_l)})
    return rows


def to_csv(rows: list[dict] | None = None) -> str:
    """Flatten the training table to CSV — the format an ML pipeline expects."""
    rows = rows if rows is not None else build_training_table()
    cols = (["cycle_id", "cycle_label", "observed_at", "term", "category"]
            + [f"feat_{f}" for f in FEATURE_FIELDS]
            + ["menu_status", "decision", "outcome"])
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        flat = {k: r.get(k) for k in
                ("cycle_id", "cycle_label", "observed_at", "term", "category",
                 "menu_status", "decision", "outcome")}
        feats = r.get("features") or {}
        for f in FEATURE_FIELDS:
            flat[f"feat_{f}"] = feats.get(f)
        w.writerow(flat)
    return buf.getvalue()


def coverage() -> dict:
    """Quick stats for the operator: how much training data exists yet, and how
    much of it is actually labeled (the bottleneck for ML)."""
    rows = build_training_table()
    labeled = sum(1 for r in rows if r.get("outcome"))
    cycles = {r.get("cycle_id") for r in rows}
    return {
        "observations": len(rows),
        "labeled_outcomes": labeled,
        "cycles_recorded": len(cycles),
        "note": "A real predictive model realistically needs hundreds of "
                "labeled rows across many cycles/bakeries. This is the raw "
                "material accumulating toward that.",
    }
