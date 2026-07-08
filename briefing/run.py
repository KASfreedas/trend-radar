"""
Briefing orchestrator — briefing/run.py

Usage:
    python -m briefing.run

Loads the latest cached scraper data from the running Flask app (or falls
back to a direct scraper run if the server is not up), then:
  1. Scores all trend candidates
  2. Computes menu gaps
  3. Renders the HTML briefing
  4. Saves it to data/history/
  5. Prints the output path

Phase 1: no email send, no LLM synthesis (can be added in Phase 2).
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python -m briefing.run` from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from briefing.score import score_all
from briefing.gaps import compute_gaps
from briefing.synthesize import synthesize
from briefing.render import build_html, save_briefing
from briefing.send import send_briefing
from briefing.competitors import load_competitors, compute_competitor_move
from briefing.outcomes import record_picks, hit_rate_sentence
from scrapers.competitor_accounts import load_cached_scan


def _load_data_from_server(base_url: str = "http://localhost:5050") -> dict | None:
    """Try fetching cached data from the running Flask app."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{base_url}/api/data", timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[briefing] Server not reachable ({e}), falling back to direct scrape.")
        return None


def _load_data_direct() -> dict:
    """Run all scrapers directly (slower, ~2-3 min for Apify sources)."""
    import threading
    from datetime import datetime

    print("[briefing] Running scrapers directly — this takes ~2 minutes…")
    from scrapers import google_trends, reddit, food_media, instagram, tiktok, pinterest

    scrapers = {
        "google":     google_trends.run_full_scan,
        "reddit":     reddit.run_full_scan,
        "food_media": food_media.run_full_scan,
        "instagram":  instagram.run_full_scan,
        "tiktok":     tiktok.run_full_scan,
        "pinterest":  pinterest.run_full_scan,
    }
    results: dict = {}

    def _run(name: str):
        try:
            results[name] = scrapers[name]()
        except Exception as e:
            results[name] = {"source": name, "error": str(e),
                             "scanned_at": datetime.utcnow().isoformat()}

    threads = [threading.Thread(target=_run, args=(n,)) for n in scrapers]
    for t in threads: t.start()
    for t in threads: t.join()
    return results


def run(base_url: str = "http://localhost:5050", send: bool = False) -> Path:
    print("[briefing] Loading data...")
    data = _load_data_from_server(base_url) or _load_data_direct()

    print("[briefing] Scoring candidates...")
    scored = score_all(data)
    print(f"[briefing] {len(scored)} candidates scored.")
    for c in scored[:5]:
        print(f"  {c['direction']:8s} | {c['confidence']:6s} | {c['term']}")

    print("[briefing] Computing menu gaps...")
    gap_result = compute_gaps(scored)
    print(f"  {len(gap_result['gaps'])} gaps  |  "
          f"{len(gap_result['covered'])} covered  |  "
          f"{len(gap_result['retire'])} retire candidates")

    print("[briefing] Synthesizing recommendations...")
    synthesis = synthesize(scored, gap_result)
    print(f"  source={synthesis['source']}  quiet_month={synthesis['quiet_month']}")
    print(f"  headline: {synthesis['headline']}")

    # Competitor move: reuses the last EXPLICIT scan cache — never re-scrapes
    # here (that costs Apify credits and is its own opt-in action, see
    # POST /api/competitors/scan or scrapers/competitor_accounts.run_full_scan).
    scan = load_cached_scan()
    competitor_move = compute_competitor_move(scan, load_competitors()) if scan else None
    if competitor_move:
        print(f"[briefing] Competitor move: {competitor_move['competitor']} "
              f"{competitor_move['multiple']}x baseline")

    from briefing.cycle import cycle_label, cycle_id
    month_label = cycle_label()  # e.g. "Early July 2026" — bi-weekly cycle
    cid = cycle_id()
    hit_rate = hit_rate_sentence(month_label)
    if hit_rate:
        print(f"[briefing] Proof loop: {hit_rate}")

    print("[briefing] Rendering HTML briefing...")
    discoveries = (data.get("google") or {}).get("rising_queries") or []
    html = build_html(scored, gap_result, month_label=month_label, synthesis=synthesis,
                      discoveries=discoveries, competitor_move=competitor_move, hit_rate=hit_rate,
                      data=data)

    path = save_briefing(html)
    record_picks(synthesis, month_label)
    from briefing.dataset import record_observations
    n_obs = record_observations(scored, gap_result, synthesis, cid, month_label)
    print(f"[briefing] Recorded {n_obs} observations for future training data.")
    print(f"[briefing] Saved to {path}")
    print(f"[briefing] Preview at: {base_url}/briefing/latest")

    if send:
        print("[briefing] Sending email...")
        result = send_briefing(html)
        if result["status"] == "sent":
            print(f"[briefing] Sent to {result['to']} (id={result.get('id')})")
        else:
            print(f"[briefing] Not sent ({result['status']}): {result.get('reason')}")
            if result.get("saved_to"):
                print(f"[briefing] Email copy saved to {result['saved_to']}")

    return path


if __name__ == "__main__":
    send = "--send" in sys.argv
    run(send=send)
