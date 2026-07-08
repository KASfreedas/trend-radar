"""
Briefing renderer — briefing/render.py

Builds the one-page HTML briefing from scored candidates + gap analysis.
Follows 02_DESIGN_SYSTEM.md: Fraunces / Newsreader / Courier Prime,
Coffee & Cream palette, max-width 760px (browser) / 600px (email).
"""

from __future__ import annotations
import html
import json
from datetime import datetime, timezone

from tenancy import data_path

_esc = html.escape  # escape externally-sourced text (competitor captions, names) before embedding

HISTORY_DIR = data_path("history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# ── Design tokens (hardcoded for email compatibility) ──────────────────────
PAPER    = "#F4EBDD"
CREAM    = "#FBF5EA"
OAT      = "#EFE3D0"
ESPRESSO = "#2A1A10"
COCOA    = "#4B3422"
MOCHA    = "#6F4E37"
LATTE    = "#A9805B"
KRAFT    = "#D9C2A3"
CINNAMON = "#B5532A"
LINE     = "#E0CFB4"
LINE_STRONG = "#C9AE85"

RISING_TINT  = "#E7EAD7"; RISING_INK  = "#5E6A3E"
PEAKING_TINT = "#F3E4C7"; PEAKING_INK = "#B07D2A"
FADING_TINT  = "#E9E0D3"; FADING_INK  = "#6E5F4F"

FONTS = "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,600;0,9..144,900;1,9..144,900&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Courier+Prime:wght@400;700&display=swap"


def _badge_html(direction: str, confidence: str) -> str:
    tint = {
        "rising":  (RISING_TINT,  RISING_INK,  "▲ Rising"),
        "peaking": (PEAKING_TINT, PEAKING_INK, "► Peaking"),
        "fading":  (FADING_TINT,  FADING_INK,  "▼ Fading"),
    }.get(direction, (OAT, LATTE, "— Flat"))
    bg, ink, label = tint

    conf_color = {
        "high": RISING_INK, "medium": PEAKING_INK, "low": LATTE
    }.get(confidence, LATTE)

    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;">'
        f'<span style="background:{bg};color:{ink};font-family:\'Courier Prime\',monospace;'
        f'font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;'
        f'padding:3px 9px;border-radius:999px;">{label}</span>'
        f'<span style="background:{KRAFT};color:{COCOA};font-family:\'Courier Prime\',monospace;'
        f'font-size:9px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
        f'padding:2px 7px;border-radius:999px;">Confidence: {confidence}</span>'
        f'</span>'
    )


def _candidate_card(c: dict, is_gap: bool = False, why: str | None = None) -> str:
    term = c.get("term", "").title()
    category = c.get("category", "").capitalize()
    direction = c.get("direction", "flat")
    confidence = c.get("confidence", "low")
    evidence = c.get("evidence", [])
    current = c.get("current_interest", 0)
    delta = c.get("delta", 0)
    delta_str = f"+{round(delta*100)}%" if delta >= 0 else f"{round(delta*100)}%"
    why = why if why is not None else c.get("why")

    gap_note = (
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;'
        f'color:{CINNAMON};font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
        f'margin:0 0 10px;">'
        f'⚑ NOT ON MENU — opportunity gap</p>'
    ) if is_gap else ""

    evidence_html = ""
    if evidence:
        items = "".join(
            f'<li style="margin-bottom:4px;color:{MOCHA};">{e}</li>'
            for e in evidence
        )
        evidence_html = (
            f'<ul style="font-family:\'Courier Prime\',monospace;font-size:11px;'
            f'color:{MOCHA};letter-spacing:0.03em;padding-left:16px;margin:10px 0 0;">'
            f'{items}</ul>'
        )

    # Lead with momentum + confidence, not raw search interest: a genuinely
    # rising niche term can have near-zero *absolute* interest (cohort-
    # normalized), and "Score: 0/100" badly undersells a real +66% mover. Show
    # the absolute interest only when it's meaningful (>0).
    interest_bit = f' &nbsp;·&nbsp; {current}/100 search interest' if (current or 0) > 0 else ''
    stat_line = (
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:13px;font-weight:700;'
        f'color:{MOCHA};margin:10px 0 0;letter-spacing:0.04em;">'
        f'{delta_str} momentum vs prior period &nbsp;·&nbsp; {confidence} confidence{interest_bit}'
        f'</p>'
    )

    why_html = ""
    if why:
        why_html = (
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;'
            f'color:{COCOA};margin:12px 0 0;line-height:1.5;">{why}</p>'
        )

    return (
        f'<div style="background:{CREAM};border:1px solid {LINE};border-radius:20px;'
        f'box-shadow:0 2px 8px rgba(42,26,16,0.08);padding:24px;margin-bottom:16px;">'
        f'{gap_note}'
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        f'gap:12px;flex-wrap:wrap;margin-bottom:10px;">'
        f'<h3 style="font-family:\'Fraunces\',Georgia,serif;font-size:20px;font-weight:600;'
        f'color:{ESPRESSO};margin:0;">{term}</h3>'
        f'<span style="font-family:\'Courier Prime\',monospace;font-size:10px;color:{LATTE};'
        f'font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
        f'padding:3px 8px;background:{OAT};border-radius:999px;">{category}</span>'
        f'</div>'
        f'{_badge_html(direction, confidence)}'
        f'{why_html}'
        f'{stat_line}'
        f'{evidence_html}'
        f'</div>'
    )


def _section_header(eyebrow: str, title: str) -> str:
    return (
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
        f'color:{MOCHA};letter-spacing:0.14em;text-transform:uppercase;margin:32px 0 4px;">'
        f'{eyebrow}</p>'
        f'<h2 style="font-family:\'Fraunces\',Georgia,serif;font-size:28px;font-weight:900;'
        f'color:{ESPRESSO};margin:0 0 8px;letter-spacing:-0.01em;">{title}</h2>'
        f'<div style="border-top:1px solid {LINE};border-bottom:1px solid {LINE};'
        f'height:3px;margin-bottom:20px;"></div>'
    )


def _gap_item(g: dict) -> str:
    term = g.get("term", "").title()
    conf = g.get("confidence", "low")
    direction = g.get("direction", "flat")
    badge_tint = RISING_TINT if direction == "rising" else PEAKING_TINT
    badge_ink  = RISING_INK  if direction == "rising" else PEAKING_INK
    dir_label  = "▲ Rising" if direction == "rising" else "► Peaking"
    return (
        f'<li style="padding:10px 0;border-bottom:1px solid {LINE};display:flex;'
        f'align-items:center;justify-content:space-between;gap:12px;">'
        f'<span style="font-family:\'Fraunces\',Georgia,serif;font-size:17px;'
        f'font-weight:600;color:{ESPRESSO};">{term}</span>'
        f'<span style="display:flex;gap:6px;align-items:center;">'
        f'<span style="background:{badge_tint};color:{badge_ink};font-family:\'Courier Prime\','
        f'monospace;font-size:9px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
        f'padding:2px 8px;border-radius:999px;">{dir_label}</span>'
        f'<span style="background:{KRAFT};color:{COCOA};font-family:\'Courier Prime\','
        f'monospace;font-size:9px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
        f'padding:2px 8px;border-radius:999px;">{conf}</span>'
        f'</span></li>'
    )


def _retire_item(r: dict) -> str:
    term = r.get("term", "").title()
    delta = r.get("delta", 0)
    delta_str = f"{round(delta*100)}%"
    return (
        f'<li style="padding:8px 0;border-bottom:1px solid {LINE};display:flex;'
        f'align-items:center;justify-content:space-between;gap:12px;">'
        f'<span style="font-family:\'Fraunces\',Georgia,serif;font-size:16px;'
        f'font-weight:500;color:{MOCHA};text-decoration:line-through;">{term}</span>'
        f'<span style="background:{FADING_TINT};color:{FADING_INK};font-family:\'Courier Prime\','
        f'monospace;font-size:9px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
        f'padding:2px 8px;border-radius:999px;">▼ Fading {delta_str}</span>'
        f'</li>'
    )


_SOURCE_KEYS = ("google", "reddit", "food_media", "instagram", "tiktok", "pinterest")


def _stats_bar_html(scored: list[dict], gap_result: dict, data: dict | None) -> str:
    """'This Month at a Glance' — every number here is a real count already
    computed by score_all()/compute_gaps(), never a new measurement. Always
    shows something, even in a quiet month, so the email isn't just prose."""
    total = len(scored)
    rising = sum(1 for c in scored if c.get("direction") == "rising")
    peaking = sum(1 for c in scored if c.get("direction") == "peaking")
    fading = sum(1 for c in scored if c.get("direction") == "fading")
    gaps_n = len(gap_result.get("gaps", []))
    retire_n = len(gap_result.get("retire", []))

    stats = []
    if data:
        ok = sum(1 for k in _SOURCE_KEYS if data.get(k) and not data[k].get("error"))
        stats.append((f"{ok}/{len(_SOURCE_KEYS)}", "sources scanned"))
    stats += [
        (str(total), "terms scored"),
        (str(rising), "rising"),
        (str(peaking), "peaking"),
        (str(fading), "fading"),
        (str(gaps_n), "menu gaps"),
        (str(retire_n), "retire candidates"),
    ]

    cells = "".join(
        f'<div style="flex:1;min-width:88px;text-align:center;padding:12px 6px;">'
        f'<div style="font-family:\'Fraunces\',Georgia,serif;font-size:26px;font-weight:900;'
        f'color:{ESPRESSO};line-height:1;">{val}</div>'
        f'<div style="font-family:\'Courier Prime\',monospace;font-size:9px;font-weight:700;'
        f'color:{MOCHA};letter-spacing:0.08em;text-transform:uppercase;margin-top:4px;">{label}</div>'
        f'</div>'
        for val, label in stats
    )
    return (
        f'<div style="background:{CREAM};border:1px solid {LINE};border-radius:16px;'
        f'padding:4px;margin-bottom:24px;display:flex;flex-wrap:wrap;">{cells}</div>'
    )


def _trust_tier_html() -> str:
    """Plain-language trust hierarchy — static, no data, so it can't fabricate
    anything. Exists because nothing in the product explained which numbers
    are safe to act on vs. just worth watching."""
    tiers = [
        ("Most trustworthy", "Sales Tracker suggestions, once logged — your own real numbers, not a scraped guess."),
        ("Solid", "High-confidence picks — Google search data backed by 3+ independent sources."),
        ("Concrete but narrow", "Competitor Watch — a specific real post that really happened, worth a look either way."),
        ("Worth watching, not betting on", "Medium/low-confidence gaps and “On The Radar” discoveries — early signal, not proof yet."),
    ]
    rows = "".join(
        f'<div style="padding:7px 0;border-bottom:1px solid {LINE};">'
        f'<span style="font-family:\'Courier Prime\',monospace;font-size:10px;font-weight:700;'
        f'color:{CINNAMON};letter-spacing:0.06em;text-transform:uppercase;">{label}</span>'
        f'<span style="font-family:\'Newsreader\',Georgia,serif;font-size:14px;color:{COCOA};"> &mdash; {desc}</span>'
        f'</div>'
        for label, desc in tiers
    )
    return (
        f'<div style="background:{CREAM};border:1px dashed {LINE_STRONG};border-radius:14px;'
        f'padding:18px 22px;margin-bottom:24px;">'
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
        f'color:{MOCHA};letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px;">How To Read This</p>'
        f'{rows}'
        f'</div>'
    )


def _emerging_html(discoveries: list[dict]) -> str:
    """Compact 'on the radar' section from auto-discovered rising Google queries."""
    if not discoveries:
        return ""
    items = ""
    for d in discoveries[:8]:
        q = (d.get("query") or "").title()
        badge = "Breakout" if d.get("breakout") else f"+{d.get('value', 0)}%"
        bg, ink = (CINNAMON, "#FBF5EA") if d.get("breakout") else (RISING_TINT, RISING_INK)
        items += (
            f'<li style="padding:9px 0;border-bottom:1px solid {LINE};display:flex;'
            f'align-items:center;justify-content:space-between;gap:12px;">'
            f'<span style="font-family:\'Fraunces\',Georgia,serif;font-size:16px;'
            f'font-weight:500;color:{COCOA};">{q}</span>'
            f'<span style="background:{bg};color:{ink};font-family:\'Courier Prime\',monospace;'
            f'font-size:9px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;'
            f'padding:2px 8px;border-radius:999px;">{badge}</span></li>'
        )
    return (
        _section_header("Discovery", "On The Radar") +
        f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;color:{COCOA};'
        f'margin-bottom:16px;">Searches Google sees accelerating around your categories — '
        f'not yet tracked, worth watching for next cycle.</p>'
        f'<ul style="list-style:none;padding:0;margin:0;">{items}</ul>'
    )


def _competitor_move_html(move: dict | None) -> str:
    """The 'I couldn't get this myself' competitor callout (§C). Real post,
    real link, real multiple — never shown unless the data backs it up."""
    if not move:
        return ""
    item = _esc((move.get("item") or "").strip() or "a recent post")
    name = _esc(move.get("competitor") or move.get("username") or "A competitor")
    url = move.get("url") or ""
    link_html = (
        f'<p style="margin:10px 0 0;"><a href="{_esc(url)}" target="_blank" '
        f'style="font-family:\'Courier Prime\',monospace;font-size:12px;font-weight:700;'
        f'color:{CINNAMON};text-decoration:none;">View post &#8599;</a></p>'
    ) if url else ""
    return (
        _section_header("Competitor Watch", "Worth A Look") +
        f'<div style="background:{CREAM};border:1px solid {CINNAMON};border-radius:20px;'
        f'box-shadow:0 2px 8px rgba(42,26,16,0.08);padding:24px;margin-bottom:24px;">'
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
        f'color:{CINNAMON};letter-spacing:0.10em;text-transform:uppercase;margin:0 0 10px;">'
        f'{name} is overperforming their own baseline</p>'
        f'<p style="font-family:\'Fraunces\',Georgia,serif;font-size:19px;font-weight:600;'
        f'color:{ESPRESSO};margin:0 0 10px;">&ldquo;{item}&rdquo;</p>'
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:13px;font-weight:700;'
        f'color:{MOCHA};margin:0;">{move.get("multiple", 0)}&times; their typical engagement'
        f'&nbsp;&middot;&nbsp;{move.get("likes", 0)} likes &middot; {move.get("comments", 0)} comments</p>'
        f'{link_html}'
        f'</div>'
    )


def _events_html(scored: list[dict], data: dict | None = None) -> str:
    """'Coming Up' — calendar moments inside the planning window, with any
    matching trending terms attached, plus live occasion-demand buzz read from
    the social feeds. Dates are facts; tie-in stats and mention counts come from
    real data. Empty window AND no buzz = section omitted entirely."""
    try:
        from briefing.events import upcoming_events, event_tie_ins, occasion_buzz
        from scrapers._config import get_value
        try:
            occ_min = max(1, min(int(float(get_value("discovery", "occasion_min_mentions", "3"))), 10))
        except (TypeError, ValueError):
            occ_min = 3
        events = event_tie_ins(upcoming_events(), scored)
        buzz = occasion_buzz((data or {}).get("instagram"), (data or {}).get("tiktok"), min_mentions=occ_min)
    except Exception:
        return ""
    if not events and not buzz:
        return ""

    # Live occasion-demand block — which cake-order occasions are heating up now.
    buzz_html = ""
    if buzz:
        brows = []
        for b in buzz[:4]:
            season = ("&#9679; peak season now" if b.get("in_season") else "")
            season_txt = (f'<span style="font-family:\'Courier Prime\',monospace;font-size:10px;'
                          f'font-weight:700;color:{CINNAMON};float:right;">{season}</span>' if season else "")
            brows.append(
                f'<div style="padding:9px 0;border-bottom:1px solid {LINE};">'
                f'<span style="font-family:\'Fraunces\',Georgia,serif;font-size:15px;font-weight:600;'
                f'color:{ESPRESSO};">{_esc(b["occasion"])}</span>'
                f'<span style="font-family:\'Courier Prime\',monospace;font-size:11px;color:{MOCHA};'
                f'margin-left:10px;">{b["mentions"]} mentions</span>{season_txt}'
                f'<div style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;color:{MOCHA};'
                f'font-style:italic;margin-top:2px;">{_esc(b["note"])}</div></div>'
            )
        buzz_html = (
            f'<div style="font-family:\'Courier Prime\',monospace;font-size:10px;font-weight:700;'
            f'letter-spacing:0.14em;text-transform:uppercase;color:{MOCHA};margin:4px 0 2px;">'
            f'Occasion demand &middot; live from social</div>{"".join(brows)}'
        )

    if not events:
        return (
            _section_header("Plan Ahead", "Coming Up") +
            f'<div style="background:{CREAM};border:1px solid {LINE};border-radius:16px;'
            f'padding:8px 20px 4px;margin-bottom:24px;">{buzz_html}</div>'
        )

    rows = []
    for ev in events[:5]:
        d = datetime.fromisoformat(ev["date"]).strftime("%b %d")
        urgency = ("&#9888; decide by " + datetime.fromisoformat(ev["decide_by"]).strftime("%b %d")
                   if ev["status"] == "act_now" else f'{ev["days_until"]} days out')
        tie_txt = ""
        if ev.get("tie_ins"):
            names = ", ".join(_esc(t["term"]) for t in ev["tie_ins"][:2])
            tie_txt = (f'<div style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;'
                       f'color:{MOCHA};font-style:italic;margin-top:3px;">Trending now: {names}</div>')
        color = CINNAMON if ev["status"] == "act_now" else MOCHA
        rows.append(
            f'<div style="padding:10px 0;border-bottom:1px solid {LINE};">'
            f'<span style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
            f'color:{color};letter-spacing:0.06em;text-transform:uppercase;">{d}</span>'
            f'<span style="font-family:\'Fraunces\',Georgia,serif;font-size:16px;font-weight:600;'
            f'color:{ESPRESSO};margin-left:12px;">{_esc(ev["name"])}</span>'
            f'<span style="font-family:\'Courier Prime\',monospace;font-size:11px;'
            f'color:{color};float:right;">{urgency}</span>'
            f'{tie_txt}</div>'
        )
    cal_label = (f'<div style="font-family:\'Courier Prime\',monospace;font-size:10px;font-weight:700;'
                 f'letter-spacing:0.14em;text-transform:uppercase;color:{MOCHA};margin:14px 0 2px;">'
                 f'Calendar &middot; dated moments</div>' if buzz_html else "")
    return (
        _section_header("Plan Ahead", "Coming Up") +
        f'<div style="background:{CREAM};border:1px solid {LINE};border-radius:16px;'
        f'padding:8px 20px 4px;margin-bottom:24px;">{buzz_html}{cal_label}{"".join(rows)}</div>'
    )


def _clusters_html(data: dict | None, scored: list[dict] | None = None) -> str:
    """'By Market' — the multi-location breakdown for a chain. National trends
    are shared (shown above); this routes them to each market by fit (a
    trend-forward market takes early bets; a classic market only proven ones),
    plus each market's own local buzz and local events. Omitted for a
    single-market business. All numbers are real; empty is honest."""
    try:
        from clusters import load_clusters, group_by_cluster
        clusters = load_clusters()
    except Exception:
        return ""
    if not clusters or len(clusters) <= 1:
        return ""  # single market — no per-cluster breakdown needed
    grouped = group_by_cluster((data or {}).get("instagram"), (data or {}).get("tiktok"))
    rows = []
    for c in clusters:
        g = grouped.get(c.get("key", ""), {})
        locals_ = (g.get("local_ig") or []) + (g.get("local_tt") or [])
        locals_.sort(key=lambda t: -(t.get("posts_per_day") or t.get("videos_per_day") or 0))
        if locals_[:3]:
            buzz = ", ".join(f"#{_esc(t.get('hashtag',''))}" for t in locals_[:3])
            buzz_html = (f'<span style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;'
                         f'color:{RISING_INK};">Local buzz: {buzz}</span>')
        else:
            buzz_html = (f'<span style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;'
                         f'color:{LATTE};font-style:italic;">No distinct local signal this cycle</span>')
        locs = ", ".join(_esc(l) for l in (c.get("locations") or []))
        # Launch routing: which national trends fit THIS market, by confidence.
        launch_html = ""
        try:
            from clusters import launch_picks_for_cluster, profile_rationale
            picks = launch_picks_for_cluster(c, scored or [])
        except Exception:
            picks = []
        if picks:
            names = ", ".join(
                f"{_esc(p.get('term',''))} (+{round((p.get('delta') or 0)*100)}%)" for p in picks
            )
            launch_html = (
                f'<div style="font-family:\'Newsreader\',Georgia,serif;font-size:14px;'
                f'color:{ESPRESSO};margin-top:6px;">&#9654; <strong>Launch here:</strong> {names}'
                f'<span style="color:{LATTE};font-size:12px;"> &mdash; {profile_rationale(c)}</span></div>'
            )
        elif scored:
            launch_html = (
                f'<div style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;'
                f'color:{LATTE};font-style:italic;margin-top:6px;">No new trend cleared this '
                f'market\'s bar &mdash; hold proven classics + seasonal.</div>'
            )
        # Local events coming to this market (top 2, with planning lead time).
        events_html = ""
        try:
            from briefing.events import upcoming_events
            cev = upcoming_events(cluster=c.get("key"))[:2]
        except Exception:
            cev = []
        if cev:
            bits = "; ".join(
                f"{_esc(e['name'])} ({datetime.fromisoformat(e['date']).strftime('%b %d')}"
                + (f", decide by {datetime.fromisoformat(e['decide_by']).strftime('%b %d')})"
                   if e.get("status") == "act_now" else ")")
                for e in cev
            )
            events_html = (
                f'<div style="font-family:\'Newsreader\',Georgia,serif;font-size:13px;'
                f'color:{CINNAMON};margin-top:4px;">&#128197; Coming to this market: {bits}</div>'
            )
        rows.append(
            f'<div style="padding:12px 0;border-bottom:1px solid {LINE};">'
            f'<div style="font-family:\'Fraunces\',Georgia,serif;font-size:17px;font-weight:600;'
            f'color:{ESPRESSO};">{_esc(c.get("name",""))}</div>'
            f'<div style="font-family:\'Courier Prime\',monospace;font-size:11px;color:{MOCHA};'
            f'margin:2px 0 5px;">{locs}</div>'
            f'{launch_html}{buzz_html}{events_html}</div>'
        )
    return (
        _section_header("Multi-Location", "By Market") +
        f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:15px;color:{COCOA};'
        f'margin-bottom:14px;">National trends move the same everywhere &mdash; the difference is '
        f'<strong>where to launch them</strong>. Each market\'s own local buzz:</p>'
        f'<div style="background:{CREAM};border:1px solid {LINE};border-radius:16px;'
        f'padding:8px 20px 4px;margin-bottom:24px;">{"".join(rows)}</div>'
    )


def _feedback_html(cycle_label: str) -> str:
    """A 'Was this useful?' widget — a 1-5 rating plus a details box. Posts to
    /api/feedback when viewed in a browser (the JS is inert in email, so the
    note tells email readers to open it in-browser). This is the client's
    channel for real signal + improvement ideas."""
    ink = CREAM  # text on the cinnamon accent (light)
    stars = "".join(
        f'<button type="button" onclick="trRate({n})" data-tr="{n}" '
        f'style="font-family:\'Courier Prime\',monospace;font-size:14px;font-weight:700;'
        f'width:38px;height:38px;margin-right:6px;cursor:pointer;border:1px solid {LINE_STRONG};'
        f'border-radius:10px;background:{OAT};color:{ESPRESSO};">{n}</button>'
        for n in range(1, 6)
    )
    js = (
        "var trR=null;"
        "function trRate(n){trR=n;var b=document.querySelectorAll('#tr-fb [data-tr]');"
        f"for(var i=0;i<b.length;i++){{b[i].style.background=(i<n)?'{CINNAMON}':'{OAT}';"
        f"b[i].style.color=(i<n)?'{ink}':'{ESPRESSO}';}}}}"
        "function trSend(){var n=document.getElementById('tr-note').value;"
        "if(!trR&&!n){return;}"
        "fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},"
        f"body:JSON.stringify({{rating:trR,note:n,cycle:{json.dumps(cycle_label)}}})}})"
        ".then(function(){document.getElementById('tr-thanks').style.display='block';"
        "document.getElementById('tr-form').style.display='none';});}"
    )
    return (
        f'<div id="tr-fb" style="background:{CREAM};border:1px solid {LINE};border-radius:16px;'
        f'padding:20px 24px;margin-top:28px;">'
        f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
        f'color:{MOCHA};letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px;">Your feedback</p>'
        f'<div id="tr-form">'
        f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;color:{COCOA};margin:0 0 12px;">'
        f'How useful was this briefing? '
        f'<span style="font-size:12px;color:{LATTE};">(1 = not useful, 5 = very — open in your browser to submit)</span></p>'
        f'<div style="margin-bottom:10px;">{stars}</div>'
        f'<textarea id="tr-note" rows="2" placeholder="What would make this more useful?" '
        f'style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid {LINE};'
        f'border-radius:10px;font-family:\'Newsreader\',Georgia,serif;font-size:14px;color:{ESPRESSO};'
        f'background:#ffffff;"></textarea>'
        f'<button type="button" onclick="trSend()" style="margin-top:10px;font-family:\'Courier Prime\',monospace;'
        f'font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:10px 18px;'
        f'border:none;border-radius:10px;background:{CINNAMON};color:{ink};cursor:pointer;">Send feedback</button>'
        f'</div>'
        f'<p id="tr-thanks" style="display:none;font-family:\'Newsreader\',Georgia,serif;font-size:15px;'
        f'color:{RISING_INK};margin:0;">Thank you — your feedback was recorded.</p>'
        f'<script>{js}</script>'
        f'</div>'
    )


def build_html(scored: list[dict], gap_result: dict, month_label: str | None = None,
               synthesis: dict | None = None, discoveries: list[dict] | None = None,
               competitor_move: dict | None = None, hit_rate: str | None = None,
               data: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    month_label = month_label or now.strftime("%B %Y")
    generated = now.strftime("%B %d, %Y at %H:%M UTC")
    # Brand the briefing with the configured business name (Settings-editable),
    # so one codebase serves any bakery — the demo default is a fictional shop.
    from scrapers._config import get_value
    bakery_name = get_value("business", "name", "Buttercup Bakery")

    # When synthesis is provided (Phase 2), use its bucketed items + 'why' lines.
    # Otherwise fall back to deterministic bucketing (Phase 1 behaviour).
    if synthesis:
        launch = synthesis.get("launch", [])
        watch  = synthesis.get("watch", [])
        skip   = synthesis.get("skip", [])
        gaps   = synthesis.get("gaps", [])
        retire = synthesis.get("retire", [])
    else:
        launch = [c for c in scored if c["direction"] == "rising" and c["confidence"] in ("high", "medium")][:3]
        watch  = [c for c in scored if c["direction"] == "peaking"][:3]
        skip   = [c for c in scored if c["direction"] == "fading" and c["confidence"] == "high"][:2]
        gaps   = gap_result.get("gaps", [])
        retire = gap_result.get("retire", [])

    # ── Sections ──────────────────────────────────────────────────────────────
    launch_html = (_section_header("Action", "Launch Next") +
        ("".join(_candidate_card(c, is_gap=not c.get("on_menu")) for c in launch)
         if launch else f'<p style="color:{LATTE};font-family:\'Newsreader\',Georgia,serif;'
                        f'font-size:16px;font-style:italic;">No strong launch candidates this month.</p>')
    )

    watch_html = (_section_header("Monitor", "Hold &amp; Watch") +
        ("".join(_candidate_card(c) for c in watch)
         if watch else f'<p style="color:{LATTE};font-family:\'Newsreader\',Georgia,serif;'
                       f'font-size:16px;font-style:italic;">Nothing at peak this month.</p>')
    )

    skip_html = ""
    if skip:
        skip_html = (
            _section_header("Avoid", "Skip This Month") +
            "".join(_candidate_card(c) for c in skip)
        )

    gaps_html = ""
    if gaps:
        gap_items = "".join(_gap_item(g) for g in gaps[:5])
        gaps_html = (
            _section_header("Opportunity", "Menu Gaps") +
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;color:{COCOA};'
            f'margin-bottom:16px;">These trends are gaining momentum but are <strong>not on your '
            f'current menu</strong>. Each one is a potential limited special.</p>'
            f'<ul style="list-style:none;padding:0;margin:0;">{gap_items}</ul>'
        )

    retire_html = ""
    if retire:
        retire_items = "".join(_retire_item(r) for r in retire[:4])
        retire_html = (
            _section_header("Wind Down", "Consider Retiring") +
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;color:{COCOA};'
            f'margin-bottom:16px;">These menu items are trending downward. Consider rotating them out.</p>'
            f'<ul style="list-style:none;padding:0;margin:0;">{retire_items}</ul>'
        )

    # Headline banner: prefer the synthesis headline; otherwise the quiet-month note.
    quiet = synthesis.get("quiet_month") if synthesis else (not launch and not gaps)
    headline = synthesis.get("headline") if synthesis else None
    quiet_note = ""
    if headline:
        quiet_note = (
            f'<div style="background:{OAT};border-left:3px solid {KRAFT};border-radius:14px;'
            f'padding:20px 24px;margin-bottom:24px;">'
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:17px;font-style:italic;'
            f'color:{COCOA};margin:0;">{headline}</p>'
            f'</div>'
        )
    elif quiet:
        quiet_note = (
            f'<div style="background:{OAT};border-left:3px solid {KRAFT};border-radius:14px;'
            f'padding:20px 24px;margin-bottom:24px;">'
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:17px;font-style:italic;'
            f'color:{COCOA};margin:0;">Quiet month — no strong moves detected across sources. '
            f'Hold current menu and revisit next cycle.</p>'
            f'</div>'
        )

    emerging_html = _emerging_html(discoveries or [])
    competitor_html = _competitor_move_html(competitor_move)
    stats_html = _stats_bar_html(scored, gap_result, data)
    trust_html = _trust_tier_html()
    events_html = _events_html(scored, data)
    clusters_html = _clusters_html(data, scored)
    feedback_html = _feedback_html(month_label)

    hit_rate_html = ""
    if hit_rate:
        hit_rate_html = (
            f'<p style="font-family:\'Courier Prime\',monospace;font-size:12px;font-weight:700;'
            f'color:{RISING_INK};background:{RISING_TINT};display:inline-block;'
            f'padding:5px 12px;border-radius:999px;margin:10px 0 0;">&#10003; {_esc(hit_rate)}</p>'
        )

    # Optional qualitative texture tip from synthesis.
    tip_html = ""
    tip = synthesis.get("texture_tip") if synthesis else None
    if tip:
        tip_html = (
            f'<div style="background:{CREAM};border:1px dashed {LINE_STRONG};border-radius:14px;'
            f'padding:16px 20px;margin-top:24px;">'
            f'<p style="font-family:\'Courier Prime\',monospace;font-size:11px;font-weight:700;'
            f'color:{MOCHA};letter-spacing:0.12em;text-transform:uppercase;margin:0 0 6px;">Texture tip</p>'
            f'<p style="font-family:\'Newsreader\',Georgia,serif;font-size:16px;color:{COCOA};margin:0;">{tip}</p>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{bakery_name} Trend Radar — {month_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>
  body{{margin:0;padding:0;background:{PAPER};font-family:"Newsreader",Georgia,serif;color:{ESPRESSO};}}
  *{{box-sizing:border-box;}}
  a{{color:{CINNAMON};}}
  @media print{{body{{background:{PAPER}!important;}}}}
</style>
</head>
<body>
<div style="max-width:760px;margin:0 auto;padding:40px 24px 80px;">

  <!-- Header -->
  <div style="background:{CREAM};border:1px solid {LINE};border-radius:20px;
    padding:32px 36px;margin-bottom:32px;box-shadow:0 2px 8px rgba(42,26,16,0.08);">
    <p style="font-family:'Courier Prime',monospace;font-size:11px;font-weight:700;
      color:{MOCHA};letter-spacing:0.14em;text-transform:uppercase;margin:0 0 4px;">
      {bakery_name} · Chicago</p>
    <h1 style="font-family:'Fraunces',Georgia,serif;font-size:34px;font-weight:900;
      font-style:italic;color:{ESPRESSO};margin:0 0 4px;letter-spacing:-0.02em;">
      Specials Board Briefing</h1>
    <p style="font-family:'Courier Prime',monospace;font-size:13px;font-weight:700;
      color:{CINNAMON};letter-spacing:0.08em;text-transform:uppercase;margin:0;">
      {month_label}</p>
    <div style="border-top:1px solid {LINE};border-bottom:1px solid {LINE};
      height:3px;margin:20px 0;"></div>
    <p style="font-family:'Newsreader',Georgia,serif;font-size:16px;color:{COCOA};margin:0;">
      Data sourced from Google Trends, Instagram, TikTok, Pinterest, Reddit, and food media.
      Recommendations cite only real, scraped numbers.
    </p>
    {hit_rate_html}
  </div>

  {stats_html}
  {trust_html}
  {quiet_note}
  {events_html}
  {clusters_html}
  {competitor_html}
  {launch_html}
  {watch_html}
  {skip_html}
  {gaps_html}
  {retire_html}
  {emerging_html}
  {tip_html}
  {feedback_html}

  <!-- Footer -->
  <div style="margin-top:48px;padding-top:20px;border-top:1px solid {LINE};">
    <p style="font-family:'Courier Prime',monospace;font-size:10px;color:{LATTE};
      letter-spacing:0.06em;text-transform:uppercase;margin:0;">
      Sources: Google Trends · Apify (Instagram, TikTok, Pinterest) · Reddit RSS · Food52 · Bon Appétit · More<br>
      Generated {generated} · {bakery_name} Trend Radar
    </p>
  </div>

</div>
</body>
</html>"""


def save_briefing(html: str, briefing_id: str | None = None) -> Path:
    """Persist a copy to data/history/ for the proof loop. `briefing_id`
    defaults to the current bi-weekly cycle id (e.g. '2026-07-b') so two
    sends in one month never overwrite each other."""
    if briefing_id is None:
        from briefing.cycle import cycle_id
        briefing_id = cycle_id()
    path = HISTORY_DIR / f"briefing_{briefing_id}.html"
    path.write_text(html, encoding="utf-8")
    return path
