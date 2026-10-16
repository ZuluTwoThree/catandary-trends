"""Daily Digest (Stage 10b, Owner 2026-10-16): ein Tagesüberblick über die
Artikel, die ein Nachtlauf veröffentlicht hat — für die Morgen-Mail des Owners.

Zwei Stufen, damit das Modell nie 1.600 Meldungen auf einmal sieht:

  1. Zählen ohne Modell: je Vertikale Signaltypen, Mega-Trends, häufige Marken
     und die mehrfach berichteten Meldungen (Story-Regel #109, im Speicher
     gerechnet, nichts geschrieben). Rangfolge: Story-Größe, dann Confidence.
  2. Ein Aufruf je Vertikale (alle Titel + Kurzfassung der zwölf stärksten
     Artikel, einer je Story), danach ein Überblicksaufruf über die Abschnitte.

Jede Aussage muss Artikel-IDs in eckigen Klammern tragen. `check()` zählt nach:
zitierte IDs, die nicht im Material des Aufrufs stehen, und Zahlen, die dort
weder im englischen noch im deutschen Format vorkommen. Die Mail zeigt beides
an, statt es zu verstecken; die IDs verlinken auf den Artikel.

Modell: Qwen3.8-27B (der Richter). Im Nachtlauf ist es nach Stage 10 ohnehin
geladen, der Digest läuft deshalb im selben Block ohne eigenen Modellwechsel
(`scheduled_cycle.sh`, DAILY_DIGEST=0 schaltet ab). Versuch vom 15.10.
(1.638 Artikel): Qwen3.8 0 ungültige Belege in 155 s, Gemma-4-26B 15 in 38 s
und eine Falschaussage — daher Qwen3.8.

Ausgabe: data/daily_digest_last.json (liest scripts/review_notify.py) und eine
Kopie je Tag unter data/daily_digest/<datum>.json.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from pipeline.config import DATA_DIR

logger = logging.getLogger(__name__)

DIGEST_MODEL = "Qwen3.8-27B"            # = pipeline.draft_judge.JUDGE_MODEL
DIGEST_CTX = int(os.getenv("DIGEST_CTX", "16384"))      # -c des Richter-Starts (ctx16k)
DIGEST_MAX_TOKENS = int(os.getenv("DIGEST_MAX_TOKENS", "1100"))
# Rest für Chat-Template und Sicherheitsabstand. Am 15.10. brauchte TECH (506 Artikel)
# 13.799 Token Eingabe — an stärkeren Tagen werden die schwächsten Titel gestrichen.
PROMPT_BUDGET = DIGEST_CTX - DIGEST_MAX_TOKENS - 400
FEATURED = 12
MIN_ARTICLES = 3                        # kleinere Vertikalen bekommen keinen Abschnitt
TEMPERATURE = 0.4
SEED = 42
# Ziel der Links in der Mail. Default ist die Owner-Instanz: die Artikel eines Laufs
# erscheinen öffentlich erst mit dem Export der folgenden Nacht (02:00), auf
# catandary.de wären die Links den ganzen Tag 404. DIGEST_ARTICLE_BASE stellt um.
ARTICLE_BASE = os.getenv("DIGEST_ARTICLE_BASE",
                         "https://kiworkstation.tail678c6e.ts.net:3001/trends/")
LAST_PATH = DATA_DIR / "daily_digest_last.json"
ARCHIVE_DIR = DATA_DIR / "daily_digest"

VERTICALS = ("TECH", "BIZ", "ECO", "HEALTH", "FOOD", "LIFESTYLE", "FASHION", "DESIGN")
VLABEL = {"FOOD": "Food & Beverage", "TECH": "Technology & AI", "HEALTH": "Health & Wellness",
          "ECO": "Sustainability", "DESIGN": "Design & Architecture", "FASHION": "Fashion & Beauty",
          "BIZ": "Business & Retail", "LIFESTYLE": "Lifestyle & Culture"}
SIG_DE = {"market_shift": "Marktbewegung", "regulation": "Regulierung", "research": "Forschung",
          "product_launch": "Produktstart", "partnership": "Partnerschaft",
          "consumer_behavior": "Verbraucherverhalten", "funding": "Finanzierung", "patent": "Patent"}

DIGEST_SYSTEM = (
    "Du bist Analyst bei Catandary Trends und schreibst einen internen Tagesüberblick für den "
    "Inhaber. Du arbeitest ausschließlich mit dem Material im <data>-Block: Titel und "
    "Kurzfassungen von Artikeln, die die Pipeline heute Nacht veröffentlicht hat, und gezählte "
    "Kennzahlen. Du erfindest nichts dazu, triffst keine Vorhersagen und schreibst nüchtern, ohne "
    "Werbesprache. Jede inhaltliche Aussage belegst du mit den IDs der Artikel in eckigen Klammern, "
    "z. B. [2241873] oder [2241873, 2241901]. Eckige Klammern verwendest du nur für Artikel-IDs, "
    "nie für Anzahlen. Zahlen nennst du nur, wenn sie wörtlich im Material stehen. Firmen- und "
    "Produktnamen übernimmst du so, wie sie im Material stehen. Du schreibst auf Deutsch.")

CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
NUM_RE = re.compile(r"(?<![\w\[])\d[\d.,]*\d|(?<![\w\[,.])\d(?![\d\]])")
_ID_IN_PROMPT = re.compile(r"\b(\d{5,})\b")


# ------------------------------------------------------------------ Stufe 1: zählen
@dataclass
class RunData:
    articles: list[dict]
    size: dict[int, int] = field(default_factory=dict)       # Artikel → Quellen seiner Story
    story_of: dict[int, int] = field(default_factory=dict)   # Artikel → Lead-ID seiner Story
    groups: list[dict] = field(default_factory=list)         # {brand, n, today:[ids]}, größte zuerst
    mega_names: dict[str, str] = field(default_factory=dict)


def load_articles(conn, since: datetime, until: datetime) -> list[dict]:
    """Veröffentlichte Artikel, die im Fenster ANGELEGT wurden (= dieser Lauf)."""
    rows = conn.execute(
        "SELECT id, slug, title_en, summary_en, primary_vertical, mega_trend, trend_signal_type, "
        "source_name, confidence FROM trends "
        "WHERE status = 'published' AND created_at >= ? AND created_at < ? ORDER BY id",
        (since, until)).fetchall()
    return [dict(r) for r in rows]


def story_index(conn, articles: list[dict], since: datetime, until: datetime,
                ) -> tuple[dict[int, int], dict[int, int], list[dict]]:
    """Story-Regel #109 im Speicher über ein Fenster ab 48 h vor `since`, damit ein
    Folgebericht zu einer Meldung vom Vortag als solcher zählt. Schreibt nichts."""
    from pipeline.stories import STORY_WINDOW_HOURS, group_stories, load_window
    window = load_window(conn, since - timedelta(hours=STORY_WINDOW_HOURS), until)
    ours = {a["id"] for a in articles}
    size: dict[int, int] = {}
    story_of: dict[int, int] = {}
    groups = []
    for st in group_stories(window):
        inside = [m for m in st.member_ids if m in ours]
        if not inside:
            continue
        for m in inside:
            size[m] = len(st.member_ids)
            story_of[m] = st.lead_id
        groups.append({"brand": st.brand_key, "n": len(st.member_ids), "today": inside})
    groups.sort(key=lambda g: (-g["n"], g["today"][0]))
    return size, story_of, groups


def mega_names() -> dict[str, str]:
    from pipeline.config import load_mega_trends
    return {m["key"]: m.get("name_de") or m.get("name_en") or m["key"] for m in load_mega_trends()}


def _naive_local(d: datetime) -> datetime:
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def collect(since: datetime, until: datetime) -> RunData:
    from pipeline.db import get_connection
    # created_at/sort_date sind lokale Zeit ohne Zone: naiv-lokal übergeben.
    s, u = (_naive_local(since), _naive_local(until))
    with get_connection() as conn:
        arts = load_articles(conn, s, u)
        size, story_of, groups = story_index(conn, arts, s, u)
    return RunData(articles=arts, size=size, story_of=story_of, groups=groups,
                   mega_names=mega_names())


def ranked(arts: list[dict], data: RunData) -> list[dict]:
    return sorted(arts, key=lambda a: (-data.size.get(a["id"], 1), -(a.get("confidence") or 0), a["id"]))


def by_vertical(data: RunData) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for a in data.articles:
        out[a.get("primary_vertical") or ""].append(a)
    return {v: out[v] for v in VERTICALS if len(out.get(v, [])) >= MIN_ARTICLES}


# ------------------------------------------------------------------ Prompts
def _clip(t: str | None, n: int) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + " …"


def _sig(k: str | None) -> str:
    return SIG_DE.get(k or "", k or "-")


def vertical_prompt(v: str, arts: list[dict], data: RunData, drop: int = 0) -> str:
    """User-Prompt für einen Vertikal-Abschnitt. `drop` streicht die schwächsten Titel
    der Titelliste (nie die hervorgehobenen) und sagt das im Material."""
    order = ranked(arts, data)
    feat, seen = [], set()
    for a in order:                       # eine Story = ein hervorgehobener Artikel
        key = data.story_of.get(a["id"], -a["id"])
        if key in seen:
            continue
        seen.add(key)
        feat.append(a)
        if len(feat) == FEATURED:
            break
    fid = {a["id"] for a in feat}
    rest = [a for a in order if a["id"] not in fid]
    if drop:
        rest = rest[: max(0, len(rest) - drop)]
    sig = Counter(a.get("trend_signal_type") or "-" for a in arts)
    meg = Counter(a["mega_trend"] for a in arts if a.get("mega_trend"))
    ids_v = {a["id"] for a in arts}
    groups = [g for g in data.groups if any(i in ids_v for i in g["today"])][:8]

    lines = [f"Vertikale: {v} — {VLABEL.get(v, v)}", f"Veröffentlichte Artikel heute: {len(arts)}", "",
             "Signaltypen (gezählt): " + ", ".join(f"{_sig(k)} {c}" for k, c in sig.most_common()),
             "Mega-Trends (gezählt): "
             + (", ".join(f"{data.mega_names.get(k, k)} {c}" for k, c in meg.most_common(6)) or "keine")]
    if groups:
        lines.append("Mehrfach berichtete Meldungen (dieselbe Meldung von mehreren Quellen):")
        for g in groups:
            lines.append(f"- {g['brand']}: {g['n']} Quellen, heutige Artikel "
                         + ", ".join(f"[{i}]" for i in g["today"]))
    lines += ["", "Hervorgehobene Artikel (am häufigsten berichtet bzw. am sichersten, mit Kurzfassung):"]
    for a in feat:
        lines.append(f"[{a['id']}] {a['title_en']} — {a.get('source_name') or '?'} — "
                     f"{_sig(a.get('trend_signal_type'))}\n    {_clip(a.get('summary_en'), 320)}")
    note = f", {drop} weitere aus Platzgründen weggelassen" if drop else ""
    lines += ["", f"Alle übrigen Artikel dieser Vertikale (nur Titel{note}):"]
    lines += [f"[{a['id']}] {_clip(a['title_en'], 140)}" for a in rest]
    data_block = "\n".join(lines)
    return f"""<data>
{data_block}
</data>

Schreibe den Abschnitt für {VLABEL.get(v, v)} im Tagesüberblick, genau in dieser Form:

### Kurzlage
2–3 Sätze: Was hat diese Vertikale heute geprägt? Stütze dich auf die gezählten Kennzahlen und die Artikel.

### Themen
3–5 Spiegelstriche. Jeder Strich ist ein Thema, das MEHRERE Artikel verbindet: ein fett gesetzter Themenname, dann ein Satz, dann die Belege, mindestens zwei IDs, z. B. [2241873, 2241901].

### Einzelstück
Höchstens ein Spiegelstrich: ein einzelnes, ungewöhnliches Signal, das sonst untergehen würde, mit [ID]. Lass den Abschnitt ganz weg, wenn nichts heraussticht.

Regeln: höchstens 230 Wörter. Jede Aussage mit Artikel-IDs in eckigen Klammern. Nur IDs aus dem Material. Zahlen nur, wenn sie im Material stehen. Keine Einleitung, kein Schlusssatz."""


def overview_prompt(sections: dict[str, str], data: RunData) -> str:
    arts = data.articles
    vc = Counter(a.get("primary_vertical") for a in arts)
    sig = Counter(a.get("trend_signal_type") or "-" for a in arts)
    meg = Counter(a["mega_trend"] for a in arts if a.get("mega_trend"))
    by_id = {a["id"]: a for a in arts}
    g_lines = "\n".join(
        f"- {g['brand']}: {g['n']} Quellen — "
        + "; ".join(f"[{i}] {by_id[i]['title_en']}" for i in g["today"][:2])
        for g in data.groups[:8]) or "- keine"
    secs = "\n\n".join(f"## {VLABEL.get(v, v)}\n{t}" for v, t in sections.items())
    return f"""<data>
Nachtlauf: {len(arts)} veröffentlichte Artikel.
Je Vertikale (gezählt): {", ".join(f"{v} {c}" for v, c in vc.most_common())}
Signaltypen (gezählt): {", ".join(f"{_sig(k)} {c}" for k, c in sig.most_common())}
Mega-Trends (gezählt): {", ".join(f"{data.mega_names.get(k, k)} {c}" for k, c in meg.most_common(8))}
Am häufigsten berichtete Meldungen:
{g_lines}

Abschnitte je Vertikale (bereits geschrieben):
{secs}
</data>

Schreibe den Kopf des Tagesüberblicks, genau in dieser Form:

### Schlagzeile
Ein Satz: das wichtigste Muster dieses Laufs.

### Was heute auffiel
4–6 Spiegelstriche über alle Vertikalen hinweg, jeweils ein Satz mit Belegen [ID].

### Querverbindungen
1–3 Spiegelstriche: dasselbe Thema in zwei oder mehr Vertikalen, mit Belegen [ID] aus beiden. Lass den Abschnitt weg, wenn das Material keine echte Verbindung zeigt.

Regeln: höchstens 220 Wörter. Nur IDs aus dem Material. Zahlen nur, wenn sie im Material stehen. Keine Einleitung, kein Schlusssatz."""


# ------------------------------------------------------------------ Prüfung
def _variants(n: str) -> set[str]:
    """Dieselbe Zahl im englischen und deutschen Format (44.9 / 44,9; 1,000 / 1.000 / 1000)."""
    v = {n, n.replace(",", "§").replace(".", ",").replace("§", ".")}
    v |= {x.replace(",", "").replace(".", "") for x in list(v) if re.fullmatch(r"\d{1,3}([.,]\d{3})+", x)}
    return v


def cited_ids(text: str) -> list[int]:
    return [int(x) for m in CITE_RE.findall(text) for x in re.split(r"\s*,\s*", m)]


def check(text: str, prompt: str, article_ids: set[int]) -> dict:
    """Belege und Zahlen gegen das Material DIESES Aufrufs. Gültig ist eine ID nur,
    wenn sie ein Artikel des Laufs ist UND im Prompt steht (eine Anzahl in Klammern,
    eine erfundene oder eine aus einer anderen Vertikale geratene ID fällt durch)."""
    valid = {int(x) for x in _ID_IN_PROMPT.findall(prompt)} & article_ids
    cited = cited_ids(text)
    plain = CITE_RE.sub("", text)
    nums = [n.rstrip(".,") for n in NUM_RE.findall(plain)]
    bad_nums = sorted({n for n in nums if n and not any(x in prompt for x in _variants(n))})
    return {"words": len(plain.split()), "cited": len(cited), "distinct_cited": len(set(cited)),
            "bad_ids": sorted({i for i in cited if i not in valid}),
            "numbers": len(nums), "bad_numbers": bad_nums}


# ------------------------------------------------------------------ Stufe 2: schreiben
def _llama_tokens(text: str) -> int:
    import httpx
    from pipeline import llamacpp_client
    r = httpx.post(f"{llamacpp_client.LLAMACPP_HOST}/tokenize", json={"content": text}, timeout=60)
    r.raise_for_status()
    return len(r.json()["tokens"])


def count_tokens(text: str) -> int:
    """Token laut Server; ist /tokenize nicht erreichbar, konservativ geschätzt."""
    try:
        return _llama_tokens(text)
    except Exception as e:                                      # noqa: BLE001
        logger.warning("tokenize failed (%s) — estimating", e)
        return int(len(text) / 3.0) + 1


def _llama_chat(prompt: str) -> str:
    from pipeline import llamacpp_client
    llamacpp_client.assert_served_model(DIGEST_MODEL, stage="daily-digest")
    return llamacpp_client.chat(model=DIGEST_MODEL, prompt=prompt, system=DIGEST_SYSTEM,
                                temperature=TEMPERATURE, seed=SEED, max_tokens=DIGEST_MAX_TOKENS,
                                enable_thinking=False).strip()


def fit_vertical(v: str, arts: list[dict], data: RunData,
                 counter: Callable[[str], int] = count_tokens) -> tuple[str, int, int]:
    """Prompt, der ins Budget passt: (prompt, token, gestrichene Titel)."""
    drop = 0
    prompt = vertical_prompt(v, arts, data)
    n = counter(DIGEST_SYSTEM + prompt)
    while n > PROMPT_BUDGET:
        rest = len(arts) - FEATURED
        if drop >= rest:
            break
        drop = min(rest, drop + max(10, (n - PROMPT_BUDGET) // 12))
        prompt = vertical_prompt(v, arts, data, drop=drop)
        n = counter(DIGEST_SYSTEM + prompt)
    return prompt, n, drop


def generate(data: RunData, since: datetime, until: datetime, *,
             chat: Callable[[str], str] = _llama_chat,
             counter: Callable[[str], int] = count_tokens) -> dict:
    """Schreibt die Abschnitte und den Überblick. Wirft nur bei Modellfehlern
    (ModelMismatchError, HTTP) — der Aufrufer entscheidet, ob der Lauf weiterläuft."""
    t_all = time.time()
    article_ids = {a["id"] for a in data.articles}
    res: dict = {"date": datetime.now(timezone.utc).isoformat(), "model": DIGEST_MODEL,
                 "since": since.isoformat(), "until": until.isoformat(),
                 "articles": len(data.articles), "stories": len(data.groups),
                 "per_vertical": {}, "sections": {}, "checks": {}, "seconds": {},
                 "prompt_tokens": {}, "dropped": {}, "status": "ok"}
    if not data.articles:
        res["status"] = "empty"
        return res
    for v, arts in by_vertical(data).items():
        prompt, n, drop = fit_vertical(v, arts, data, counter)
        t0 = time.time()
        text = chat(prompt)
        res["per_vertical"][v] = len(arts)
        res["sections"][v] = text
        res["seconds"][v] = round(time.time() - t0, 1)
        res["prompt_tokens"][v] = n
        if drop:
            res["dropped"][v] = drop
        res["checks"][v] = check(text, prompt, article_ids)
        logger.info("digest %s: %d articles, %d tokens, %.1fs, %s", v, len(arts), n,
                    res["seconds"][v], res["checks"][v])
    op = overview_prompt(res["sections"], data)
    t0 = time.time()
    res["overview"] = chat(op)
    res["seconds"]["_overview"] = round(time.time() - t0, 1)
    res["prompt_tokens"]["_overview"] = counter(DIGEST_SYSTEM + op)
    res["checks"]["_overview"] = check(res["overview"], op, article_ids)
    res["total_seconds"] = round(time.time() - t_all, 1)
    # Für die Links in der Mail: nur die zitierten Artikel (Slug, Titel, Quelle).
    by_id = {a["id"]: a for a in data.articles}
    cited = {i for t in [res["overview"], *res["sections"].values()] for i in cited_ids(t)}
    res["refs"] = {str(i): {"slug": by_id[i]["slug"], "title": by_id[i]["title_en"],
                            "source": by_id[i].get("source_name")}
                   for i in sorted(cited) if i in by_id}
    res["top_stories"] = [{"brand": g["brand"], "n": g["n"]} for g in data.groups[:6]]
    return res


def totals(res: dict) -> dict:
    c = res.get("checks", {}).values()
    return {"words": sum(x["words"] for x in c), "cited": sum(x["distinct_cited"] for x in c),
            "bad_ids": sum(len(x["bad_ids"]) for x in c),
            "bad_numbers": sum(len(x["bad_numbers"]) for x in c)}


def save(res: dict) -> None:
    LAST_PATH.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    ARCHIVE_DIR.mkdir(exist_ok=True)
    day = res["until"][:10]
    (ARCHIVE_DIR / f"{day}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                             encoding="utf-8")


def load_last(max_age_h: float = 24) -> dict | None:
    """Der Digest dieser Nacht, wenn er frisch ist — ein alter darf in der Mail nicht
    aussehen, als sei er von heute."""
    if not LAST_PATH.exists():
        return None
    try:
        d = json.loads(LAST_PATH.read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(d["date"])
        if age.total_seconds() > max_age_h * 3600 or d.get("status") != "ok":
            return None
        return d
    except (OSError, ValueError, KeyError):
        return None


# ------------------------------------------------------------------ Mail
def _bad_for(res: dict, key: str) -> tuple[set[int], set[str]]:
    c = res.get("checks", {}).get(key, {})
    return set(c.get("bad_ids", [])), set(c.get("bad_numbers", []))


def _cites_html(group: str, res: dict, bad: set[int], base: str) -> str:
    parts = []
    for x in re.split(r"\s*,\s*", group):
        i = int(x)
        ref = res.get("refs", {}).get(str(i))
        if ref and i not in bad:
            t = html.escape(f"{ref['title']} — {ref.get('source') or ''}", quote=True)
            parts.append(f'<a href="{html.escape(base + ref["slug"], quote=True)}" title="{t}" '
                         'style="color:#3d5a00;text-decoration:none;font-family:ui-monospace,Menlo,monospace;'
                         f'font-size:11px">{i}</a>')
        else:
            parts.append('<span title="nicht im Material" style="color:#9a2b00;text-decoration:line-through;'
                         f'font-family:ui-monospace,Menlo,monospace;font-size:11px">{i}</span>')
    return ('<span style="color:#888;font-size:11px">[</span>'
            + '<span style="color:#888;font-size:11px">, </span>'.join(parts)
            + '<span style="color:#888;font-size:11px">]</span>')


def _inline_html(s: str, res: dict, key: str, base: str) -> str:
    bad_ids, bad_nums = _bad_for(res, key)
    out, last = [], 0
    for m in CITE_RE.finditer(s):
        out.append(_text_html(s[last:m.start()], bad_nums))
        out.append(_cites_html(m.group(1), res, bad_ids, base))
        last = m.end()
    out.append(_text_html(s[last:], bad_nums))
    return "".join(out)


def _text_html(t: str, bad_nums: set[str]) -> str:
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    if bad_nums:
        t = NUM_RE.sub(lambda m: (f'<span title="Zahl steht nicht im Material" style="background:#ffe2d6;'
                                  f'color:#9a2b00">{m.group(0)}</span>'
                                  if m.group(0).rstrip(".,") in bad_nums else m.group(0)), t)
    return t


def _md_html(text: str, res: dict, key: str, base: str) -> str:
    out, in_ul = [], False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append('<p style="margin:12px 0 4px;font-size:11px;letter-spacing:.06em;'
                       f'text-transform:uppercase;color:#666">{_inline_html(s.lstrip("#").strip(), res, key, base)}</p>')
        elif re.match(r"^[-*•]\s+", s):
            if not in_ul:
                out.append('<ul style="margin:0 0 8px;padding-left:18px">'); in_ul = True
            out.append(f'<li style="margin-bottom:5px">{_inline_html(re.sub(r"^[-*•]\s+", "", s), res, key, base)}</li>')
        else:
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append(f'<p style="margin:0 0 8px">{_inline_html(s, res, key, base)}</p>')
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _quality_line(res: dict) -> str:
    t = totals(res)
    return (f"{res['articles']} Artikel, {res['stories']} mehrfach berichtete Meldungen · "
            f"{t['cited']} Belege, {t['bad_ids']} ungültig, {t['bad_numbers']} Zahlen ohne Beleg · "
            f"{res['model']}, {res.get('total_seconds', 0):.0f} s")


def day_label(res: dict) -> str:
    d = datetime.fromisoformat(res["until"]).astimezone()
    return d.strftime("%d.%m.")


def render_mail_html(res: dict, base: str | None = None) -> str:
    base = base or ARTICLE_BASE
    parts = ['<div style="border:1px solid #d6d9cf;padding:14px 16px;margin:0 0 20px">',
             f'<p style="margin:0 0 2px;font-size:18px;font-weight:600">Daily Digest {day_label(res)}</p>',
             f'<p style="margin:0 0 10px;color:#666;font-size:12px">{html.escape(_quality_line(res))}</p>',
             _md_html(res.get("overview", ""), res, "_overview", base)]
    for v, text in res.get("sections", {}).items():
        n = res.get("per_vertical", {}).get(v, 0)
        drop = res.get("dropped", {}).get(v)
        parts.append(f'<p style="margin:18px 0 2px;font-size:15px;font-weight:600;border-top:2px solid #0a0c0a;'
                     f'padding-top:8px">{html.escape(VLABEL.get(v, v))} '
                     f'<span style="font-weight:400;color:#888;font-size:12px">{n} Artikel'
                     + (f", {drop} Titel aus Platzgründen nicht gelesen" if drop else "") + "</span></p>")
        parts.append(_md_html(text, res, v, base))
    parts.append('<p style="margin:12px 0 0;color:#888;font-size:12px">Vom lokalen Modell geschrieben, nur aus '
                 'Titeln und Kurzfassungen des Laufs. Die Zahlen in den Kennzahlen sind gezählt; rot '
                 'markierte Belege oder Zahlen stehen nicht im Material.</p></div>')
    return '<div style="font-family:system-ui,sans-serif;font-size:14px;line-height:1.55">' + "".join(parts) + "</div>"


def render_mail_text(res: dict, base: str | None = None) -> str:
    base = base or ARTICLE_BASE
    used: list[int] = []

    def sub(text: str) -> str:
        def rep(m):
            nums = []
            for x in re.split(r"\s*,\s*", m.group(1)):
                i = int(x)
                if str(i) in res.get("refs", {}):
                    if i not in used:
                        used.append(i)
                    nums.append(str(used.index(i) + 1))
                else:
                    nums.append(f"{i}?")
            return "[" + ", ".join(nums) + "]"
        return CITE_RE.sub(rep, text).replace("**", "")

    lines = [f"DAILY DIGEST {day_label(res)}", _quality_line(res), "", sub(res.get("overview", "")), ""]
    for v, text in res.get("sections", {}).items():
        lines += [f"== {VLABEL.get(v, v)} ({res.get('per_vertical', {}).get(v, 0)} Artikel)", sub(text), ""]
    if used:
        lines.append("Belege:")
        lines += [f"  [{k + 1}] {base}{res['refs'][str(i)]['slug']}" for k, i in enumerate(used)]
    return "\n".join(lines)
