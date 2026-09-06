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

Seit 2026-09-06 (M1/M2, docs/dossier_measurement_2026-09-06.md) zusätzlich:

  * **Rückfallkaskade statt stillem Ausfall.** `query_gate` verlangt Patent-
    Volltexte mit ALLEN Wörtern der Auftragsphrase; „GLP-1 and incretin
    technology" trifft dadurch 0 Patente und schaltete die gesamte Messkette
    ab (dossiers.id=13: quant = {"off_topic": true}), während „GLP-1 receptor
    agonist" ≥2.000 trifft. `measure_topic()` normalisiert die Phrase (Füll-
    wörter wie and/technology/market/sector raus), probiert dann Kernbegriffe,
    dann die CPC-Auswahl eines mehrdeutigen Gates und zuletzt die CPC-Klassen
    aus den eigenen Korpustreffern (`signal_cpc` → `analyze_codes`).
  * **Sichtbarer Fehlschlag.** Fällt die Messung trotzdem aus, steht das mit
    jedem Versuch im Dossier (codegenerierter Anhang) — nie mehr stumm.
  * **Messanhang.** `measurement_appendix()` erzeugt aus den bereits
    gerechneten, aber bisher verworfenen Jahresreihen (leadtime tiers
    `series`, trajectory `points`/`x_by_year`) einen codegenerierten Abschnitt:
    Zeitreihe je Ebene, Take-off-Jahre, Patent→Markt-Vorlauf, Zykluszeit,
    Zentralitäts-Peak — jeweils mit n und Zeitraum. Der Anhang ist Beleg, dass
    gemessen und nicht erzählt wurde; er ist codegeneriert und wird deshalb in
    pipeline/dossier_check.py wie der Coverage-Anhang abgetrennt.

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
import re
from datetime import date
from urllib.parse import quote

logger = logging.getLogger("dossier_quant")

TECH_TOOL_BASE = "https://catandary.de/trends/foresight/technology"
MAX_HUB_PATENTS = 5

# Überschriften des codegenerierten Messanhangs. MÜSSEN textgleich zu den
# Schnittmarken in pipeline/dossier_check.py bleiben (dort abgetrennt, damit
# die Endkontrolle die Mess-Tabellen nicht als Modell-Prosa zählt).
MEASURE_HEADINGS = (
    "## Measured development (auto-generated)",
    "## Gemessene Entwicklung (automatisch erzeugt)",
)

# Muss textgleich zu idx_trends_fts / scripts.corpus_research.FTS_VECTOR sein,
# sonst seq-scannt die Korpus-Rückfallebene 1,7 Mio Zeilen
# (tests/test_dossier_quant.py hält beide Fassungen aneinander).
FTS_VECTOR = ("to_tsvector('english', coalesce(title_en,'') || ' ' || "
              "coalesce(summary_en,'') || ' ' || coalesce(tags::text,''))")

# Ehrlichkeitsgrenzen — wörtlich in jeden Messblock übernommen.
_CAVEATS = (
    "Honesty limits for every figure above: absolute improvement rates are "
    "calibrated only to ~2019 — read later years as direction, not magnitude. "
    "A patent documents a claimed invention, never a working product. All "
    "counts are Catandary corpus measurements (data window from 1990), not "
    "market statistics."
)

# Füllwörter, die eine Auftragsphrase unmessbar machen: sie stehen in keinem
# Patenttitel neben dem Fachbegriff, das AND-Gate von query_gate fällt damit
# auf 0 Treffer. Reine Vorverarbeitung — die Gate-Logik bleibt unangetastet.
_FILLER = frozenset("""
a an the and or of for in on at to with without from into about across
technology technologies tech market markets industry industries sector sectors
segment segments trend trends trending landscape space field fields domain
domains innovation innovations solution solutions application applications
development developments product products area areas ecosystem overview
outlook state status today current modern advanced next generation general
""".split())

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*")


def normalize_topic(topic: str) -> str:
    """Auftragsphrase ohne Füllwörter — die Form, die das Patent-Titelgate
    passieren kann. „GLP-1 and incretin technology" → „GLP-1 incretin"."""
    words = [w for w in _WORD_RE.findall(topic or "")
             if w.lower().strip(".-/") not in _FILLER]
    return " ".join(words)


def topic_cascade(topic: str) -> list[str]:
    """Reihenfolge der Messversuche: volle Phrase → normalisiert → Kernbegriffe
    (die Inhaltswörter einzeln, längste zuerst — der spezifischste Begriff hat
    die besten Chancen auf ein `ok`-Gate)."""
    out: list[str] = []
    seen: set[str] = set()

    def add(phrase: str) -> None:
        p = " ".join((phrase or "").split())
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            out.append(p)

    add(topic)
    norm = normalize_topic(topic)
    add(norm)
    terms = [w for w in _WORD_RE.findall(norm) if len(w.strip(".-/")) >= 3]
    for w in sorted(terms, key=lambda x: (-len(x), x)):
        add(w)
    return out


def corpus_cpc_codes(topic: str, limit: int = 6, min_hits: int = 5) -> list[str]:
    """Letzte Rückfallebene: die CPC-Klassen, die der EIGENE Korpus dem Thema
    zuordnet. Die Distill-Tabelle `signal_cpc` (trend_id → cpc, dist) trägt die
    Zuordnung für Millionen Signale; sie kennt kein Patent-Titelgate und trifft
    deshalb auch Themen, an denen `query_gate` scheitert.

    Rein lesend, mit statement_timeout — schlägt die Query fehl, gibt es eben
    keine Codes (und der Fehlschlag steht sichtbar im Dossier)."""
    terms = [w.lower() for w in _WORD_RE.findall(normalize_topic(topic))
             if len(w.strip(".-/")) >= 3][:8]
    if not terms:
        return []
    tsq = " | ".join(terms)
    sql = (
        "WITH hit AS (SELECT id FROM trends "
        f"             WHERE {FTS_VECTOR} @@ to_tsquery('english', ?) LIMIT 4000) "
        "SELECT sc.cpc AS cpc, count(*) AS n FROM hit "
        "  JOIN signal_cpc sc ON sc.trend_id = hit.id "
        " GROUP BY sc.cpc ORDER BY n DESC LIMIT ?")
    from pipeline.db import get_connection
    try:
        with get_connection() as conn:
            conn.execute("SET statement_timeout = '60s'")
            rows = conn.execute(sql, (tsq, limit * 3)).fetchall()
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("corpus CPC fallback failed for %r: %r", topic, exc)
        return []
    codes = [(dict(r)["cpc"], int(dict(r)["n"])) for r in rows]
    return [c for c, n in codes if n >= min_hits][:limit]


def _measurable(analysis: dict | None) -> bool:
    """Eine Messung liegt vor, wenn eine Trajektorie gerechnet wurde. Ein
    `ambiguous`-Gate liefert nur Kandidaten — das ist KEINE Messung (der alte
    Code druckte in dem Fall trotzdem den TIR-Default-Snippet)."""
    return bool(analysis and analysis.get("trajectory"))


def measure_topic(topic: str) -> dict:
    """Messung mit Rückfallkaskade. Gibt IMMER ein Dict zurück:
    {"analysis": dict|None, "phrase": str|None, "resolved_via": str|None,
     "attempts": [{"phrase", "verdict", "reason"}...]}

    `analysis` ist None, wenn keine Stufe eine Trajektorie erzeugt hat —
    dann trägt `attempts` die vollständige Begründung in den Bericht."""
    from scripts.tech_analyze import analyze_query

    attempts: list[dict] = []
    ambiguous: tuple[str, list[str]] | None = None

    def _record(phrase: str, res: dict | None, err: str | None = None) -> None:
        gate = (res or {}).get("gate") or {}
        attempts.append({
            "phrase": phrase,
            "verdict": ("error" if err else
                        ("off_topic" if (res or {}).get("off_topic")
                         else gate.get("verdict") or
                         ("ok" if _measurable(res) else "no_trajectory"))),
            "reason": err or gate.get("reason") or "",
        })

    for phrase in topic_cascade(topic)[:8]:
        try:
            res = analyze_query(phrase)
        except SystemExit:
            raise                                    # Embedding tot → Fehlgrund
        except Exception as exc:                                    # noqa: BLE001
            _record(phrase, None, f"{type(exc).__name__}: {exc}")
            continue
        _record(phrase, res)
        if _measurable(res):
            return {"analysis": res, "phrase": phrase,
                    "resolved_via": ("topic phrase" if phrase == topic
                                     else f"normalized phrase {phrase!r}"),
                    "attempts": attempts}
        if ambiguous is None and res.get("selection"):
            ambiguous = (phrase, list(res["selection"]))

    # Stufe 2: das mehrdeutige Gate hat Kandidaten benannt — der Pfad für die
    # explizite Auswahl existiert (analyze_query(..., codes=...)), wurde bisher
    # aber nie benutzt. Der Vektor kommt aus dem Cache, kein zweiter Handover.
    if ambiguous:
        phrase, codes = ambiguous
        try:
            res = analyze_query(phrase, codes=codes)
            if _measurable(res):
                return {"analysis": res, "phrase": phrase,
                        "resolved_via": f"gate candidates for {phrase!r} "
                                        f"({', '.join(codes[:4])})",
                        "attempts": attempts}
            _record(f"{phrase} [gate candidates]", res)
        except Exception as exc:                                    # noqa: BLE001
            _record(f"{phrase} [gate candidates]", None,
                    f"{type(exc).__name__}: {exc}")

    # Stufe 3: die CPC-Klassen aus den eigenen Korpustreffern.
    codes = corpus_cpc_codes(topic)
    if codes:
        phrase = normalize_topic(topic) or topic
        try:
            res = analyze_query(phrase, codes=codes)
            if _measurable(res):
                return {"analysis": res, "phrase": phrase,
                        "resolved_via": f"corpus CPC classes "
                                        f"({', '.join(codes[:4])})",
                        "attempts": attempts}
            _record(f"corpus CPC {', '.join(codes[:4])}", res)
        except Exception as exc:                                    # noqa: BLE001
            _record(f"corpus CPC {', '.join(codes[:4])}", None,
                    f"{type(exc).__name__}: {exc}")
        try:                                     # ohne Embedding, reines SQL
            from scripts.tech_analyze import analyze_codes
            res = analyze_codes(codes)
            if _measurable(res):
                res = {**res, "off_topic": False, "candidates": [],
                       "leadtime": None, "query": topic}
                return {"analysis": res, "phrase": topic,
                        "resolved_via": f"corpus CPC classes, trajectory only "
                                        f"({', '.join(codes[:4])})",
                        "attempts": attempts}
            _record(f"corpus CPC {', '.join(codes[:4])} [SQL only]", res)
        except Exception as exc:                                    # noqa: BLE001
            _record("corpus CPC [SQL only]", None,
                    f"{type(exc).__name__}: {exc}")

    return {"analysis": None, "phrase": None, "resolved_via": None,
            "attempts": attempts}


# ---------------------------------------------------------------------------
# Domänen-Dynamik: Zykluszeit (die zweite TIR-Zutat) — reines SQL, gedeckelt.
# ---------------------------------------------------------------------------

def cycle_time(codes: list[str], since: str = "2015-01-01",
               timeout: str = "60s") -> dict:
    """Median-Rückwärts-Zitationsalter der Patente in den gewählten Klassen —
    die „Zykluszeit" des Feldes (Singh/Triulzi/Magee: kurze Zykluszeit ⇒ höhere
    erwartete Verbesserungsrate). Läuft über patent_links + raw_entries.

    Gibt {"years": float|None, "edges": int, "reason": str|None} zurück; eine
    zu teure Query endet im Timeout und wird als „nicht gemessen" berichtet,
    nie als Zahl geraten."""
    if not codes:
        return {"years": None, "edges": 0, "reason": "no CPC selection"}
    like = " OR ".join("pc.cpc LIKE %s" for _ in codes)
    sql = (
        "WITH dom AS (SELECT DISTINCT pc.pub_number FROM patent_cpc pc "
        "             WHERE (" + like + ")), "
        "src AS (SELECT d.pub_number, r.published_date FROM dom d "
        "        JOIN raw_entries r ON r.pub_number = d.pub_number "
        "        WHERE r.published_date >= %s), "
        "ages AS (SELECT EXTRACT(year FROM s.published_date) "
        "                - EXTRACT(year FROM r2.published_date) AS age "
        "         FROM src s "
        "         JOIN patent_links l ON l.src_pub = s.pub_number "
        "                            AND l.link_type = 'cites' "
        "         JOIN raw_entries r2 ON r2.pub_number = l.dst_pub "
        "         WHERE r2.published_date IS NOT NULL) "
        "SELECT count(*) AS n, "
        "       percentile_cont(0.5) WITHIN GROUP (ORDER BY age) AS med "
        "  FROM ages WHERE age BETWEEN 0 AND 60")
    from pipeline.db import get_connection
    try:
        with get_connection() as conn:
            conn.execute(f"SET statement_timeout = '{timeout}'")
            cur = conn._conn.cursor()
            cur.execute(sql, tuple(c + "%" for c in codes) + (since,))
            n, med = cur.fetchone()
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("cycle time not measured for %r: %r", codes, exc)
        return {"years": None, "edges": 0,
                "reason": f"not measured ({type(exc).__name__})"}
    n = int(n or 0)
    if n < 200:
        return {"years": None, "edges": n,
                "reason": f"only {n} dated citation edges — too thin to report"}
    return {"years": round(float(med), 1), "edges": n, "reason": None,
            "since": since[:4]}


def centrality_peak(traj: dict | None) -> dict | None:
    """Jahr der höchsten mittleren SPNP-Zentralität der Domänen-Patente —
    „wann wurden die Anmeldungen geschrieben, auf die sich das Feld beruft".
    Kommt aus der Trajektorie selbst (scripts/tir_trajectory.trajectory()
    liefert x_by_year), kostet also keine zweite Query."""
    xs = (traj or {}).get("x_by_year") or {}
    pts = [(int(y), float(v[0]), int(v[1])) for y, v in xs.items()
           if isinstance(v, (list, tuple)) and len(v) == 2 and int(v[1]) >= 100]
    if not pts:
        return None
    y, x, n = max(pts, key=lambda p: p[1])
    span = (min(p[0] for p in pts), max(p[0] for p in pts))
    return {"year": y, "percentile": round(x, 3), "n": n,
            "from": span[0], "to": span[1]}


# ---------------------------------------------------------------------------
# Formatierung
# ---------------------------------------------------------------------------

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


def _series_rows(tiers: dict) -> list[tuple[int, dict]]:
    """Jahresachse über alle Reifegrade, ohne führende Leerjahre."""
    years: set[int] = set()
    for t in ("science", "patent", "funding", "market"):
        for y in ((tiers.get(t) or {}).get("series") or {}):
            try:
                years.add(int(y))
            except (TypeError, ValueError):
                continue
    if not years:
        return []
    rows: list[tuple[int, dict]] = []
    for y in sorted(years):
        vals = {}
        for t in ("science", "patent", "funding", "market"):
            v = ((tiers.get(t) or {}).get("series") or {}).get(str(y))
            vals[t] = v
        rows.append((y, vals))
    # führende Jahre, in denen nichts als 0 steht, wegschneiden
    while rows and not any(v for v in rows[0][1].values()):
        rows.pop(0)
    return rows[-40:]


def _thin(points: list, cap: int = 24) -> list:
    """Gleichmäßig ausgedünnte Reihe, letzter Punkt bleibt immer erhalten."""
    if len(points) <= cap:
        return list(points)
    step = (len(points) + cap - 1) // cap
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def _num(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"
    return f"{v:,}"


def measurement_appendix(analysis: dict | None, topic: str, meta: dict | None = None,
                         lang: str = "en", dynamics: dict | None = None) -> str:
    """Der codegenerierte Messanhang. Nicht vom Modell geschrieben — deshalb
    exakt, deshalb der Beleg gegenüber einem Web-Rechercheur, und deshalb in
    dossier_check als Schnittmarke registriert."""
    de = lang == "de"
    head = MEASURE_HEADINGS[1] if de else MEASURE_HEADINGS[0]
    L: list[str] = ["", "---", "", head, ""]
    meta = meta or {}
    today = date.today().isoformat()

    if not _measurable(analysis):
        # SICHTBARER Fehlschlag: bisher verschwand eine gescheiterte Messung
        # spurlos (dossiers.id=13). Jeder Versuch steht jetzt im Dokument.
        L.append(
            f"Die deterministische Messung der Innovationskette für "
            f"*{topic}* ist am {today} **ausgefallen** — für dieses Dossier "
            f"gibt es keine eigene Patent-/Zeitreihenmessung."
            if de else
            f"The deterministic innovation-chain measurement for *{topic}* "
            f"**failed** on {today} — this dossier carries no measurement of "
            f"its own patent and time-series layer.")
        L.append("")
        L.append("Versuche (Phrase → Befund des Query-Gates):" if de
                 else "Attempts (phrase → query-gate verdict):")
        for a in (meta.get("attempts") or [])[:12]:
            L.append(f"* `{a.get('phrase')}` → **{a.get('verdict')}**"
                     + (f" — {str(a.get('reason'))[:180]}" if a.get("reason") else ""))
        if not (meta.get("attempts") or []):
            L.append("* " + (str(meta.get("reason") or "keine Messung ausgeführt")
                             if de else str(meta.get("reason") or "no measurement run")))
        L.append("")
        L.append("Jede Aussage dieses Dossiers zu Tempo, Vorlaufzeit oder "
                 "Patentaktivität stammt daher aus Texten, nicht aus einer Messung."
                 if de else
                 "Every statement in this dossier about pace, lead time or patent "
                 "activity therefore comes from text, not from a measurement.")
        return "\n".join(L) + "\n"

    sel = analysis.get("selection") or []
    cands = {c["symbol"]: c for c in (analysis.get("candidates") or [])}
    traj = analysis.get("trajectory") or {}
    lead = analysis.get("leadtime") or {}
    tiers = lead.get("tiers") or {}

    L.append(
        f"Deterministisch gemessen am {today} über das Catandary-Patent- und "
        f"Signalarchiv; aufgelöst über {meta.get('resolved_via') or 'die Auftragsphrase'}. "
        f"Jede Zahl unten ist ein Query-Ergebnis, keine Modellaussage."
        if de else
        f"Measured deterministically on {today} over the Catandary patent and "
        f"signal archive; resolved via {meta.get('resolved_via') or 'the topic phrase'}. "
        f"Every figure below is a query result, not a model statement.")
    L.append("")

    if sel:
        parts = []
        for code in sel:
            c = cands.get(code, {})
            t = (c.get("title") or "").strip()
            n = c.get("n")
            parts.append(f"`{code}`" + (f" {t}" if t else "")
                         + (f" ({n:,} patents)" if n else ""))
        L.append(("**Gemessene Patentklassen (CPC):** " if de
                  else "**Patent technology classes measured (CPC):** ")
                 + "; ".join(parts))
        L.append("")
    if traj.get("n_total"):
        L.append((f"**Messbasis:** {traj['n_total']:,} Patente im "
                  f"Zitationsgraphen der gewählten Klassen"
                  if de else
                  f"**Measurement base:** {traj['n_total']:,} patents in the "
                  f"citation graph of the selected classes")
                 + (f", {traj.get('earliest_dense_year')}–"
                    f"{(traj.get('points') or [{}])[-1].get('year')}."
                    if traj.get("points") else "."))
        L.append("")

    rows = _series_rows(tiers)
    if rows:
        L.append("### " + ("Zeitreihe je Reifegrad" if de
                           else "Signal history per maturity tier"))
        L.append("")
        L.append("Research/funding/market sind Anteilswerte (pro 10.000 Signale "
                 "des jeweiligen Jahres, entfernt den Erhebungs-Sprung der "
                 "eigenen Pipeline); Patente sind Rohzahlen."
                 if de else
                 "Research/funding/market are share values (per 10,000 signals of "
                 "that year, which removes our own collection ramp); patents are "
                 "raw counts.")
        L.append("")
        L.append("| " + ("Jahr" if de else "year")
                 + " | research | patents | funding | market |")
        L.append("|---|---|---|---|---|")
        for y, v in _thin(rows, 30):
            L.append(f"| {y} | {_num(v['science'])} | {_num(v['patent'])} | "
                     f"{_num(v['funding'])} | {_num(v['market'])} |")
        L.append("")
        bits = []
        for key, label in (("science", "research"), ("patent", "patents"),
                           ("funding", "funding"), ("market", "market")):
            t = tiers.get(key) or {}
            if t.get("n"):
                bits.append(f"{label}: n={t['n']:,}, "
                            + (f"{t.get('first')}–" if t.get("first") else "")
                            + (str(max(int(y) for y in (t.get('series') or {'0': 0}))
                                   ) if t.get("series") else "?")
                            + (f", take-off {t['takeoff']}" if t.get("takeoff")
                               else ", " + ("kein Take-off messbar" if de
                                            else "no measurable take-off")))
        if bits:
            L.append(("**Umfang und Take-off je Ebene:** " if de
                      else "**Volume and take-off per tier:** ") + " · ".join(bits))
            L.append("")
        pat_to = (tiers.get("patent") or {}).get("takeoff")
        mkt_to = (tiers.get("market") or {}).get("takeoff")
        if lead.get("lead_patent_market"):
            L.append((f"**Vorlauf Patente → Markt: ~{lead['lead_patent_market']} Jahre** "
                      f"(Patent-Take-off {pat_to} → Markt-Take-off {mkt_to})."
                      if de else
                      f"**Lead time patents → market: ~{lead['lead_patent_market']} years** "
                      f"(patent take-off {pat_to} → market take-off {mkt_to})."))
        elif pat_to and mkt_to:
            L.append((f"Patent-Take-off {pat_to}, Markt-Take-off {mkt_to} — als "
                      f"Vorlaufzeit nicht belastbar (Randlage im Datenfenster)."
                      if de else
                      f"Patent take-off {pat_to}, market take-off {mkt_to} — not "
                      f"reportable as a lead time (boundary of the data window)."))
        elif lead.get("established"):
            L.append("Etabliertes Feld: Forschung und Patente liegen vor dem "
                     "1990er-Datenfenster — eine Vorlaufzeit wäre ein Artefakt."
                     if de else
                     "Established field: research and patents predate the 1990 data "
                     "window — a lead time here would be an artifact.")
        else:
            L.append("Keine belastbare Vorlaufzeit messbar." if de
                     else "No reportable lead time could be measured.")
        L.append("")

    pts = traj.get("points") or []
    if pts:
        L.append("### " + ("Verbesserungsrate K(t)" if de
                           else "Improvement-rate curve K(t)"))
        L.append("")
        L.append("SPNP-Methode auf dem Patent-Zitationsgraphen (5-Jahres-Fenster); "
                 "n = Patente im Fenster."
                 if de else
                 "SPNP method on the patent citation graph (5-year windows); "
                 "n = patents inside the window.")
        L.append("")
        L.append("| " + ("Jahr" if de else "year") + " | K (%/yr) | n |")
        L.append("|---|---|---|")
        for p in _thin(pts, 20):
            mark = "" if p.get("complete") else " *"
            L.append(f"| {p['year']}{mark} | {p['K']} | {p['n']:,} |")
        L.append("")
        L.append("\\* " + ("Fenster noch unvollständig (Zitations-Nachlauf)."
                           if de else "window still incomplete (citation lag)."))
        if traj.get("K_median") is not None and traj.get("calibrated"):
            L.append("")
            L.append((f"**Median über die gemessene Historie: {traj['K_median']} %/yr**; "
                      f"Richtung: {traj.get('direction_de') or traj.get('direction')}."
                      if de else
                      f"**Median over the measured history: {traj['K_median']} %/yr**; "
                      f"direction: {traj.get('direction')}."))
        elif traj.get("direction"):
            L.append("")
            L.append((f"Absolutwert außerhalb des kalibrierten Bereichs — nur die "
                      f"Richtung wird berichtet: {traj.get('direction_de') or traj['direction']}"
                      if de else
                      f"Absolute value outside the calibrated range — direction only: "
                      f"{traj['direction']}")
                     + (f" ({traj['reason']})" if traj.get("reason") else "") + ".")
        L.append("")

    peak = centrality_peak(traj)
    cyc = (dynamics or {}).get("cycle_time") or {}
    if peak or cyc:
        L.append("### " + ("Zykluszeit und Zentralität" if de
                           else "Cycle time and centrality"))
        L.append("")
        if cyc.get("years"):
            L.append((f"**Zykluszeit: {cyc['years']} Jahre** (Median-Alter der "
                      f"rückwärts zitierten Patente, {cyc['edges']:,} datierte "
                      f"Zitationskanten, Anmeldungen ab {cyc.get('since')}). "
                      f"Kurze Zykluszeit ⇒ höhere erwartete Verbesserungsrate."
                      if de else
                      f"**Cycle time: {cyc['years']} years** (median age of the "
                      f"patents cited backwards, {cyc['edges']:,} dated citation "
                      f"edges, filings from {cyc.get('since')}). A short cycle time "
                      f"implies a higher expected improvement rate."))
        elif cyc.get("reason"):
            L.append(("Zykluszeit: " if de else "Cycle time: ") + str(cyc["reason"]) + ".")
        if peak:
            L.append("")
            L.append((f"**Zentralitäts-Peak: {peak['year']}** (mittleres "
                      f"SPNP-Perzentil {peak['percentile']}, n={peak['n']:,} Patente "
                      f"dieses Jahrgangs; gemessen über {peak['from']}–{peak['to']}). "
                      f"Danach fallende Zentralität heißt: die Anmeldungen, auf die "
                      f"sich das Feld beruft, sind älter als die aktuelle Welle."
                      if de else
                      f"**Centrality peak: {peak['year']}** (mean SPNP percentile "
                      f"{peak['percentile']}, n={peak['n']:,} filings of that cohort; "
                      f"measured across {peak['from']}–{peak['to']}). Falling centrality "
                      f"afterwards means the filings the field builds on are older "
                      f"than the current wave."))
        L.append("")

    hubs = (analysis.get("top_patents") or [])[:MAX_HUB_PATENTS]
    if hubs:
        L.append("### " + ("Meistzitierte Patente der gemessenen Klassen" if de
                           else "Most forward-cited patents in the measured classes"))
        L.append("")
        for h in hubs:
            L.append(f"* {h.get('pub')} ({h.get('year') or '?'}, "
                     f"{h.get('cites'):,} " + ("Zitationen" if de else "citations")
                     + f") — {h.get('title')}")
        L.append("")
        L.append("Sortiert nach Vorwärtszitationen in der CPC-Domäne; das bevorzugt "
                 "alte, breite Anmeldungen und ist kein Themenranking."
                 if de else
                 "Ranked by forward citations inside the CPC domain; this favours old, "
                 "broad filings and is not a topical ranking.")
        L.append("")

    L.append("*" + _CAVEATS + "*")
    return "\n".join(L) + "\n"


def format_quant_evidence(analysis: dict, topic: str, meta: dict | None = None,
                          lang: str = "en", dynamics: dict | None = None) -> dict:
    """Reine Formatierung (testbar ohne DB/GPU): analyze_query()-Ergebnis →
    {sources, note, summary, appendix}. sources[0] ist der zitierbare
    Mess-Eintrag, danach bis zu MAX_HUB_PATENTS Leitpatente."""
    url = f"{TECH_TOOL_BASE}?q={quote(topic)}"
    today = date.today().isoformat()
    meta = meta or {}

    if analysis.get("off_topic"):
        note = (
            f"Measured innovation-chain profile for {topic!r}: the phrase did "
            f"not resolve to any patent technology class (nearest CPC distance "
            f"{analysis.get('nearest_dist')}). No improvement rate and no "
            f"patent-tier lead-time can be measured for it — treat any such "
            f"figure in outside sources with corresponding skepticism.")
        return {"sources": [], "note": note,
                "summary": {"off_topic": True,
                            "nearest_dist": analysis.get("nearest_dist")},
                "appendix": measurement_appendix(None, topic, meta, lang)}

    lines: list[str] = [
        f"Measured innovation-chain profile for {topic!r} "
        f"(Catandary Foresight engine, deterministic, measured {today}):"]
    if meta.get("resolved_via") and meta["resolved_via"] != "topic phrase":
        lines.append(f"* Measured field resolved via {meta['resolved_via']} — "
                     f"the literal order phrase did not resolve to a patent class.")

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
    if traj.get("n_total"):
        lines.append(f"* Measurement base: {traj['n_total']:,} patents in the "
                     f"citation graph of those classes.")

    lead = analysis.get("leadtime") or {}
    tiers = lead.get("tiers") or {}
    tier_bits = [b for b in (
        _fmt_tier("research", tiers.get("science")),
        _fmt_tier("patents", tiers.get("patent")),
        _fmt_tier("funding", tiers.get("funding")),
        _fmt_tier("market", tiers.get("market"))) if b]
    if tier_bits:
        lines.append("* Signal history per maturity tier — " + " | ".join(tier_bits))
    # Die gerechneten Jahresreihen selbst (bis 2026-09-06 berechnet und
    # weggeworfen): kompakt als Jahr:Wert, damit der Schreiber sie zitieren
    # kann statt nur die Skalare zu sehen.
    for key, label in (("science", "research"), ("patent", "patents"),
                       ("funding", "funding"), ("market", "market")):
        ser = (tiers.get(key) or {}).get("series") or {}
        pairs = [(int(y), v) for y, v in ser.items() if v]
        if len(pairs) >= 4:
            pairs.sort()
            shown = _thin(pairs, 18)
            unit = ("filings/yr" if key == "patent" else "share per 10k signals")
            lines.append(f"  - {label} by year ({unit}): "
                         + ", ".join(f"{y}:{_num(v)}" for y, v in shown))
    pts = traj.get("points") or []
    if pts:
        lines.append("  - improvement rate K(t) by year (%/yr, n = patents in the "
                     "5-year window): "
                     + ", ".join(f"{p['year']}:{p['K']}(n={p['n']:,})"
                                 for p in _thin(pts, 14)))
    peak = centrality_peak(traj)
    if peak:
        lines.append(f"* Patent centrality (SPNP percentile) peaks in the "
                     f"{peak['year']} cohort at {peak['percentile']} "
                     f"(n={peak['n']:,}), measured {peak['from']}–{peak['to']}.")
    cyc = (dynamics or {}).get("cycle_time") or {}
    if cyc.get("years"):
        lines.append(f"* Cycle time (median age of the patents cited backwards): "
                     f"{cyc['years']} years over {cyc['edges']:,} dated citation "
                     f"edges — a short cycle time implies a higher expected "
                     f"improvement rate.")
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

    # Der Q1-Snippet trägt jetzt die eigentlichen Messgrößen (bis zu den
    # erlaubten 420 Zeichen) statt eines 60-Zeichen-Verdikts — der Katalog
    # steht garantiert im Report-Prompt, die Evidenznotiz nicht immer.
    snip_bits = [verdict] if verdict else []
    if sel:
        snip_bits.append("CPC " + ", ".join(sel[:3]))
    if traj.get("K_median") is not None and traj.get("calibrated"):
        snip_bits.append(f"median {traj['K_median']}%/yr")
    if lead.get("lead_patent_market"):
        snip_bits.append(f"patent→market lead ~{lead['lead_patent_market']} yr")
    if cyc.get("years"):
        snip_bits.append(f"cycle time {cyc['years']} yr")
    if peak:
        snip_bits.append(f"centrality peak {peak['year']}")
    if traj.get("n_total"):
        snip_bits.append(f"{traj['n_total']:,} patents measured")
    snippet = " · ".join(b for b in snip_bits if b) or (
        "Deterministic measurement: CPC resolution, TIR trajectory, "
        "cross-tier lead-time.")

    sources = [{
        "id": "Q1", "trend_id": None, "kind": "measurement",
        "title": f"Measured innovation-chain profile: {topic}",
        "url": url, "origin": url,
        "outlet": "Catandary Foresight engine", "vertical": "",
        "date": today,
        "snippet": snippet[:420],
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
        "resolved_via": meta.get("resolved_via"),
        "measured_phrase": meta.get("phrase"),
        "n_patents": traj.get("n_total"),
        "cycle_time_years": cyc.get("years"),
        "centrality_peak_year": (peak or {}).get("year"),
        "takeoffs": {k: (tiers.get(k) or {}).get("takeoff")
                     for k in ("science", "patent", "funding", "market")},
    }
    return {"sources": sources, "note": note, "summary": summary,
            "appendix": measurement_appendix(analysis, topic, meta, lang, dynamics)}


def build_quant_evidence(topic: str, lang: str = "en",
                         measure: bool = True) -> dict:
    """Messung + Formatierung. Gibt IMMER ein Dict zurück:
    {"ok": bool, "reason": str|None, "sources": [...], "note": str|None,
     "summary": dict|None, "appendix": str|None}. Fehler (kein Postgres, kein
    Embedding-Endpunkt, fehlende Patent-Tabellen) werden zum Fehlgrund, nie zum
    Absturz — das Dossier läuft dann ohne Messblock, und die Review-Ansicht
    zeigt warum.

    `measure=False` reproduziert den Pfad vor 2026-09-06: ein einziger
    analyze_query(topic)-Versuch, keine Kaskade, kein Anhang."""
    try:
        from scripts.tech_analyze import analyze_query                # noqa: F401
    except Exception as exc:                                        # noqa: BLE001
        return {"ok": False, "reason": f"tech_analyze unavailable: {exc}",
                "sources": [], "note": None, "summary": None, "appendix": None}

    if not measure:
        try:
            analysis = analyze_query(topic)
        except SystemExit as exc:
            return {"ok": False, "reason": f"embedding failed: {exc}",
                    "sources": [], "note": None, "summary": None, "appendix": None}
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("quant measurement failed for %r: %r", topic, exc)
            return {"ok": False, "reason": f"measurement failed: {exc}",
                    "sources": [], "note": None, "summary": None, "appendix": None}
        out = format_quant_evidence(analysis, topic)
        out.pop("appendix", None)
        return {"ok": True, "reason": None, "appendix": None, **out}

    try:
        found = measure_topic(topic)
    except SystemExit as exc:  # embed_query raises SystemExit on embed failure
        return {"ok": False, "reason": f"embedding failed: {exc}",
                "sources": [], "note": None, "summary": None,
                "appendix": measurement_appendix(
                    None, topic, {"reason": f"embedding failed: {exc}"}, lang)}
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("quant measurement failed for %r: %r", topic, exc)
        return {"ok": False, "reason": f"measurement failed: {exc}",
                "sources": [], "note": None, "summary": None,
                "appendix": measurement_appendix(
                    None, topic, {"reason": f"measurement failed: {exc}"}, lang)}

    analysis = found.get("analysis")
    if not _measurable(analysis):
        tried = "; ".join(
            f"{a['phrase']}→{a['verdict']}"
            + (f" ({str(a['reason'])[:120]})" if a.get("reason") else "")
            for a in (found.get("attempts") or [])[:6])
        reason = f"no measurable patent field for {topic!r} (tried: {tried})"
        logger.warning("quant: %s", reason)
        return {"ok": False, "reason": reason, "sources": [], "note": None,
                "summary": {"off_topic": True, "attempts": found.get("attempts")},
                "appendix": measurement_appendix(None, topic, found, lang)}

    dynamics = {"cycle_time": cycle_time(analysis.get("selection") or [])}
    logger.info("quant: measured via %s (%d attempt(s))",
                found.get("resolved_via"), len(found.get("attempts") or []))
    out = format_quant_evidence(analysis, topic, found, lang, dynamics)
    return {"ok": True, "reason": None, **out}
