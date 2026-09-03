"""Quant-Vorstufe für Scouting-Dossiers: die gemessene Innovationskette.

Der agentische Rechercheur (scripts/corpus_research.py) liest nur Text. Die
quantitative Kette existiert aber längst: scripts/tech_analyze.py rechnet zu
einem Freitext-Technologiefeld die CPC-Auflösung, die TIR-Trajektorie
(SPNP-Methode auf dem Patent-Zitationsgraphen), die Cross-Tier-Lead-Time
(Forschung→Patent→Funding→Markt) und die meistzitierten Leitpatente.

Dieses Modul führt beide zusammen — bewusst DETERMINISTISCH, vor dem Plan-Hop,
nicht als Agent-Aktion: Messung ist kein Ermessen (dieselbe Begründung, aus der
der Paper-/Patent-Sweep im Rechercheur deterministisch läuft). Das Ergebnis
wird als zitierbarer Katalog-Eintrag (kind "measurement", verlinkt auf das
Technology-Tool) plus Evidenznotiz injiziert; die Leitpatente kommen als
eigene Patent-Quellen dazu.

Jede Zahl im Messblock trägt ihre Ehrlichkeitsgrenze im Klartext mit
(Kalibrierung bis ~2019, Patent ≠ Produkt, 1990er-Datenfenster) — die
Grenzen aus der Product-Truth-Matrix gelten auch owner-intern.

Braucht PostgreSQL (Patent-Tabellen) und den Embedding-Endpunkt (GPU-Handover
übernimmt tech_query.embed_query selbst). Ohne beides degradiert
build_quant_evidence() zu einem klaren Fehlgrund statt eines Absturzes —
das Dossier läuft dann ohne Messblock.
"""
from __future__ import annotations

import logging
from datetime import date
from urllib.parse import quote

logger = logging.getLogger("dossier_quant")

TECH_TOOL_BASE = "https://catandary.de/trends/foresight/technology"
MAX_HUB_PATENTS = 5

# Ehrlichkeitsgrenzen — wörtlich in jeden Messblock übernommen.
_CAVEATS = (
    "Honesty limits for every figure above: absolute improvement rates are "
    "calibrated only to ~2019 — read later years as direction, not magnitude. "
    "A patent documents a claimed invention, never a working product. All "
    "counts are Catandary corpus measurements (data window from 1990), not "
    "market statistics."
)


def _fmt_tier(name: str, tier: dict | None) -> str | None:
    if not tier or not tier.get("n"):
        return None
    bits = [f"{name}: {tier['n']} signals"]
    if tier.get("first"):
        bits.append(f"first {tier['first']}")
    if tier.get("takeoff"):
        bits.append(f"takeoff ~{tier['takeoff']}")
    if tier.get("median"):
        bits.append(f"median year {tier['median']}")
    return ", ".join(bits)


def format_quant_evidence(analysis: dict, topic: str) -> dict:
    """Reine Formatierung (testbar ohne DB/GPU): analyze_query()-Ergebnis →
    {sources, note, summary}. sources[0] ist der zitierbare Mess-Eintrag,
    danach bis zu MAX_HUB_PATENTS Leitpatente."""
    url = f"{TECH_TOOL_BASE}?q={quote(topic)}"
    today = date.today().isoformat()

    if analysis.get("off_topic"):
        note = (
            f"Measured innovation-chain profile for {topic!r}: the phrase did "
            f"not resolve to any patent technology class (nearest CPC distance "
            f"{analysis.get('nearest_dist')}). No improvement rate and no "
            f"patent-tier lead-time can be measured for it — treat any such "
            f"figure in outside sources with corresponding skepticism.")
        return {"sources": [], "note": note,
                "summary": {"off_topic": True,
                            "nearest_dist": analysis.get("nearest_dist")}}

    lines: list[str] = [
        f"Measured innovation-chain profile for {topic!r} "
        f"(Catandary Foresight engine, deterministic, measured {today}):"]

    verdict = analysis.get("verdict")
    if verdict:
        lines.append(f"* Verdict: {verdict}")

    sel = analysis.get("selection") or []
    cands = {c["symbol"]: c for c in (analysis.get("candidates") or [])}
    if sel:
        parts = []
        for code in sel:
            c = cands.get(code, {})
            title = (c.get("title") or "").strip()
            n = c.get("n")
            parts.append(f"{code}" + (f" ({title}" + (f", {n:,} patents)" if n else ")")
                                      if title or n else ""))
        lines.append("* Patent technology classes (CPC) measured: "
                     + "; ".join(parts))

    traj = analysis.get("trajectory") or {}
    direction = traj.get("direction")
    if traj.get("calibrated") and traj.get("K_median") is not None:
        lines.append(
            f"* Technology Improvement Rate (peer-reviewed SPNP method, patent "
            f"citation graph): median ~{traj['K_median']}%/yr over the measured "
            f"history; S-curve reading: {direction or 'n/a'}.")
    elif direction:
        reason = traj.get("reason")
        lines.append(f"* Improvement-rate trajectory: {direction}"
                     + (f" ({reason})" if reason else "") + ".")

    lead = analysis.get("leadtime") or {}
    tiers = lead.get("tiers") or {}
    tier_bits = [b for b in (
        _fmt_tier("research", tiers.get("science")),
        _fmt_tier("patents", tiers.get("patent")),
        _fmt_tier("funding", tiers.get("funding")),
        _fmt_tier("market", tiers.get("market"))) if b]
    if tier_bits:
        lines.append("* Signal history per maturity tier — " + " | ".join(tier_bits))
    if lead.get("established"):
        lines.append(
            "* Lead-time: established field — research and patents predate the "
            "1990 data window, so no research→market lead can honestly be "
            "claimed from these series.")
    else:
        if lead.get("lead_science_market"):
            lines.append(f"* Measured research→market lead: "
                         f"~{lead['lead_science_market']} years.")
        if lead.get("lead_patent_market"):
            lines.append(f"* Measured patent→market lead: "
                         f"~{lead['lead_patent_market']} years.")
        if lead.get("concurrent"):
            lines.append("* Research and market activity move closely together "
                         "(no measurable lead).")

    hubs = (analysis.get("top_patents") or [])[:MAX_HUB_PATENTS]
    if hubs:
        lines.append("* Most forward-cited patents in the measured classes "
                     "(landmark filings): "
                     + "; ".join(f"{h.get('pub')} ({h.get('year') or '?'}, "
                                 f"{h.get('cites')} citations) {h.get('title')}"
                                 for h in hubs))

    lines.append("* " + _CAVEATS)
    note = "\n".join(lines)

    sources = [{
        "id": "Q1", "trend_id": None, "kind": "measurement",
        "title": f"Measured innovation-chain profile: {topic}",
        "url": url, "origin": url,
        "outlet": "Catandary Foresight engine", "vertical": "",
        "date": today,
        "snippet": (verdict or "Deterministic measurement: CPC resolution, "
                    "TIR trajectory, cross-tier lead-time.")[:420],
        "fetched": True,
    }]
    for i, h in enumerate(hubs, start=2):
        if not h.get("url"):
            continue
        sources.append({
            "id": f"Q{i}", "trend_id": None, "kind": "patent",
            "title": (h.get("title") or h.get("pub") or "patent")[:200],
            "url": h["url"], "origin": "",
            "outlet": "patent filing (hub)", "vertical": "",
            "date": str(h.get("year") or ""),
            "snippet": (f"One of the domain's most forward-cited patents "
                        f"({h.get('cites')} citations). A patent documents a "
                        f"claimed invention, never a working product.")[:420],
            "fetched": True,
        })

    summary = {
        "off_topic": False,
        "selection": sel,
        "verdict": verdict,
        "direction": direction,
        "K_median": traj.get("K_median") if traj.get("calibrated") else None,
        "lead_science_market": lead.get("lead_science_market"),
        "lead_patent_market": lead.get("lead_patent_market"),
        "established": bool(lead.get("established")),
    }
    return {"sources": sources, "note": note, "summary": summary}


def build_quant_evidence(topic: str) -> dict:
    """Messung + Formatierung. Gibt IMMER ein Dict zurück:
    {"ok": bool, "reason": str|None, "sources": [...], "note": str|None,
     "summary": dict|None}. Fehler (kein Postgres, kein Embedding-Endpunkt,
    fehlende Patent-Tabellen) werden zum Fehlgrund, nie zum Absturz — das
    Dossier läuft dann ohne Messblock, und die Review-Ansicht zeigt warum."""
    try:
        from scripts.tech_analyze import analyze_query
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "reason": f"tech_analyze unavailable: {exc}",
                "sources": [], "note": None, "summary": None}
    try:
        analysis = analyze_query(topic)
    except SystemExit as exc:  # embed_query raises SystemExit on embed failure
        return {"ok": False, "reason": f"embedding failed: {exc}",
                "sources": [], "note": None, "summary": None}
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("quant measurement failed for %r: %r", topic, exc)
        return {"ok": False, "reason": f"measurement failed: {exc}",
                "sources": [], "note": None, "summary": None}
    out = format_quant_evidence(analysis, topic)
    return {"ok": True, "reason": None, **out}
