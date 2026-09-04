"""Research Pulse (#73 Teil 1): wöchentliche Synthese je Mega-Signal-Theme aus
dem frischen Forschungskorpus.

Datenbasis ist `research_signals` (Research-Explorer-Index, materialisiert
vom Samstags-Ingester) mit den 1024-dim-Embeddings aus `trends.embedding_1024`
— der Fresh-Korpus ist vollständig embedded (Distill-Pfad des Samstagslaufs),
deshalb KMeans auf Embeddings statt Konzept-Gruppen (docs/research_pulse.md).

Je Theme und ISO-Woche:
  volume    Papers der Woche vs. Median der vier Vorwochen (Verhältnis)
  clusters  KMeans (k≈5, fester Seed) auf L2-normierten Embeddings; Label =
            c-TF-IDF-Terme der Cluster-Titel/-Abstracts + dominantes Konzept;
            Wachstum = Wochenzahl gegen den Wochen-Mittelwert der Vorwochen,
            zugeordnet per Nächster-Zentroid in SQL (pgvector <=>)
  papers    die zentroid-nächsten Papers je Cluster (Titel, Quelle, Datum,
            Link, OA-Badge — Preprint-Server sind per Definition Open Access;
            für OpenAlex-Fresh-Werke liegt kein OA-Status vor)
  text      100–150 Wörter Gemma-4-26B, T=0.2, fester Seed, nur Zahlen aus
            dem Messblock, keine Prognosen (Prompt unten)

Alles unterhalb von `compute_theme` ist deterministisch: gleiche Daten →
gleiche Cluster, gleiche Labels, gleiche Top-Papers. Der LLM-Text ist per
Seed reproduzierbar, soweit llama.cpp das hergibt (Batch-Komposition).

Reine Helfer (Wochenlogik, Verhältnis, k-Regel, Labels, Prompt, Wortwächter)
haben keine DB-Abhängigkeit — tests/test_research_pulse.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
from collections import Counter
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Content-Engine wie Newsletter/Stage 6 (CLAUDE.md). Bewusst NICHT
# config.STAGE5_MODEL: dessen Default ist noch das 35B; Gemma wird im Cycle
# nur per Env gesetzt. Hier explizit, damit der Knopf im Frontend ohne Env
# dasselbe Modell nimmt wie der Cron-Wrapper.
PULSE_MODEL = os.getenv("RESEARCH_PULSE_MODEL",
                        "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")
PULSE_SEED = int(os.getenv("RESEARCH_PULSE_SEED", "73"))
PULSE_TEMPERATURE = float(os.getenv("RESEARCH_PULSE_TEMPERATURE", "0.2"))
KMEANS_SEED = 73
MAX_K = 5
# Unter dieser Wochenmenge gibt es keinen Text — ein Absatz über drei
# Papers wäre erfundene Bedeutung.
MIN_PAPERS_FOR_TEXT = 5
TOP_PAPERS_PER_CLUSTER = 4
PRIOR_WEEKS = 4
WORDS_MIN, WORDS_MAX = 80, 190

PREPRINT_SOURCES = ("arXiv Preprints", "biorxiv Preprints", "medrxiv Preprints")
SOURCE_LABELS = {"preprints": "preprint servers", "openalex": "OpenAlex journal works",
                 "journals": "journal and press feeds"}


# ---------------------------------------------------------------------------
# Wochenlogik
# ---------------------------------------------------------------------------

def iso_week_bounds(year: int, week: int) -> tuple[date, date]:
    """Montag und Sonntag der ISO-Woche (beide inklusiv)."""
    monday = date.fromisocalendar(year, week, 1)
    return monday, monday + timedelta(days=6)


def default_week(today: date | None = None) -> tuple[int, int]:
    """Die letzte ABGESCHLOSSENE ISO-Woche — dieselbe Regel wie der
    Newsletter-Cron (%G/%V von vor 7 Tagen): am Samstag des Pulse-Laufs ist die
    laufende Woche halb leer und der 14-Tage-Ingest hat die Vorwoche voll."""
    today = today or date.today()
    y, w, _ = (today - timedelta(days=7)).isocalendar()
    return y, w


def parse_week(text: str) -> tuple[int, int]:
    """'2026-W35' / '2026-w35' / '2026-35' → (2026, 35). ValueError sonst."""
    m = re.fullmatch(r"\s*(\d{4})-?[Ww]?(\d{1,2})\s*", text or "")
    if not m:
        raise ValueError(f"week must look like 2026-W35, got {text!r}")
    year, week = int(m.group(1)), int(m.group(2))
    date.fromisocalendar(year, week, 1)  # validates the week number
    return year, week


def prior_weeks(year: int, week: int, n: int = PRIOR_WEEKS) -> list[tuple[int, int]]:
    """Die n Wochen vor (year, week), älteste zuerst."""
    monday, _ = iso_week_bounds(year, week)
    out = []
    for i in range(n, 0, -1):
        y, w, _ = (monday - timedelta(days=7 * i)).isocalendar()
        out.append((y, w))
    return out


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def volume_ratio(current: int, prior: list[int]) -> float | None:
    """Wochenvolumen geteilt durch den Median der Vorwochen. None, wenn es
    keine Vergleichsbasis gibt (kein Vorwochen-Volumen) — die Seite zeigt dann
    „no baseline" statt eines unendlichen Anstiegs."""
    if not prior:
        return None
    med = statistics.median(prior)
    if med <= 0:
        return None
    return round(current / med, 3)


def choose_k(n: int, max_k: int = MAX_K) -> int:
    """k≈5 ab 40 Papers, darunter ein Cluster je ~8 Papers, unter 8 ein
    einziger Block (kein Clustering, nur Liste)."""
    if n < 8:
        return 1
    return max(1, min(max_k, n // 8))


def is_open_access(source: str | None) -> bool:
    return (source or "") in PREPRINT_SOURCES


def source_group(source: str | None) -> str:
    s = source or ""
    if s in PREPRINT_SOURCES:
        return "preprints"
    if s.startswith("OpenAlex"):
        return "openalex"
    return "journals"


# ---------------------------------------------------------------------------
# Clustering (numpy/sklearn — Import erst hier, Tests der reinen Helfer
# brauchen sie nicht)
# ---------------------------------------------------------------------------

def parse_vector(text: str):
    import numpy as np
    return np.asarray(json.loads(text), dtype=np.float32)


def _normalize(mat):
    import numpy as np
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def kmeans_labels(mat, k: int):
    """Labels + Zentroide (L2-normiert) — fester Seed, n_init=10."""
    import numpy as np
    if k <= 1 or mat.shape[0] <= 1:
        centroid = _normalize(mat.mean(axis=0, keepdims=True))
        return np.zeros(mat.shape[0], dtype=int), centroid
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, random_state=KMEANS_SEED, n_init=10)
    labels = km.fit_predict(mat)
    return labels, _normalize(km.cluster_centers_)


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
_TAG_RE = re.compile(r"<[^>]+>")
# Elsevier-RSS-„Abstracts" sind Boilerplate (Publication date / Source / Author(s))
_BOILER_RE = re.compile(r"(publication date|available online|source|author\(s\)|volume|issue)\s*:?[^.]*",
                        re.I)
# Generische Wissenschaftssprache, die sonst jedes Label füllt („study · results")
_GENERIC = frozenset("""
study studies research researchers results result based using used use approach approaches
analysis analyses novel paper papers review reviews findings finding data method methods
model models proposed propose present presented new via effect effects role
performance evaluation framework system systems application applications abstract
background conclusion conclusions objective objectives introduction significance
implications high low different various potential recent current available
et al ieee mdpi elsevier springer wiley journal article preprint
""".split())


def _doc_text(title: str | None, abstract: str | None) -> str:
    """Titel doppelt (Gewicht), Abstract ohne HTML/Boilerplate, gekappt."""
    t = (title or "").strip()
    a = _TAG_RE.sub(" ", abstract or "")
    a = _BOILER_RE.sub(" ", a)[:400]
    return f"{t}. {t}. {a}"


def cluster_terms(docs: list[str], labels, k: int, top: int = 4) -> list[list[str]]:
    """c-TF-IDF-Label: TF-IDF über alle Dokumente des Themes, je Cluster der
    Mittelwert, die top-Terme. Ein Cluster heißt dann „perovskite solar ·
    tandem cells · stability" statt „Cluster 2"."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    if not docs:
        return [[] for _ in range(k)]
    try:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        vec = TfidfVectorizer(stop_words=list(ENGLISH_STOP_WORDS | _GENERIC),
                              ngram_range=(1, 2),
                              min_df=2 if len(docs) >= 8 else 1, max_df=0.6,
                              sublinear_tf=True, token_pattern=_TOKEN_RE.pattern)
        X = vec.fit_transform(docs)
    except ValueError:  # nur Stoppwörter / leere Vokabel
        return [[] for _ in range(k)]
    vocab = np.asarray(vec.get_feature_names_out())
    out: list[list[str]] = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if idx.size == 0:
            out.append([])
            continue
        mean = np.asarray(X[idx].mean(axis=0)).ravel()
        order = np.argsort(-mean)
        terms: list[str] = []
        for j in order:
            if mean[j] <= 0:
                break
            t = str(vocab[j])
            # Bigram schlägt seine eigenen Unigramme (kein „solar · solar cell")
            if any(t in seen or seen in t for seen in terms):
                continue
            terms.append(t)
            if len(terms) >= top:
                break
        out.append(terms)
    return out


def cluster_label(terms: list[str], concepts: list[tuple[str, int]]) -> str:
    if terms:
        return " · ".join(terms[:3])
    if concepts:
        return concepts[0][0]
    return "unlabelled"


# ---------------------------------------------------------------------------
# Cluster-Bau (reine Funktion über geladene Zeilen)
# ---------------------------------------------------------------------------

def build_clusters(rows: list[dict], prior_counts: dict[int, int] | None = None,
                   prior_weeks_n: int = PRIOR_WEEKS) -> tuple[list[dict], list]:
    """rows: dicts mit trend_id,title,abstract,url,source,concept,published,vec.
    Gibt (clusters, centroids) zurück; prior_counts (idx→Anzahl der Vorwochen-
    Papers, die diesem Zentroid am nächsten liegen) kann in einem zweiten
    Schritt nachgereicht werden (apply_prior_counts)."""
    import numpy as np
    n = len(rows)
    if n == 0:
        return [], []
    rows = sorted(rows, key=lambda r: r["trend_id"])
    mat = _normalize(np.stack([r["vec"] for r in rows]))
    k = choose_k(n)
    labels, centroids = kmeans_labels(mat, k)
    docs = [_doc_text(r["title"], r["abstract"]) for r in rows]
    terms = cluster_terms(docs, labels, k)
    clusters: list[dict] = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if idx.size == 0:
            continue
        sims = mat[idx] @ centroids[c]
        order = idx[np.argsort(-sims, kind="stable")]
        concepts = Counter((rows[i]["concept"] or "").strip() for i in idx
                           if (rows[i]["concept"] or "").strip()).most_common(3)
        papers = [{
            "trend_id": rows[i]["trend_id"],
            "title": rows[i]["title"],
            "source": rows[i]["source"],
            "published": rows[i]["published"],
            "url": rows[i]["url"],
            "oa": is_open_access(rows[i]["source"]),
            "sim": round(float(mat[i] @ centroids[c]), 4),
        } for i in order[:TOP_PAPERS_PER_CLUSTER]]
        clusters.append({
            "idx": int(c),
            "n": int(idx.size),
            "share": round(idx.size / n, 3),
            "terms": terms[c],
            "concepts": [[name, int(cnt)] for name, cnt in concepts],
            "label": cluster_label(terms[c], concepts),
            "prior_n": None,
            "prior_weekly_mean": None,
            "growth": None,
            "emerging": False,
            "papers": papers,
        })
    # größte Cluster zuerst, stabil über idx
    clusters.sort(key=lambda c: (-c["n"], c["idx"]))
    if prior_counts is not None:
        apply_prior_counts(clusters, prior_counts, prior_weeks_n)
    return clusters, centroids


def apply_prior_counts(clusters: list[dict], prior_counts: dict[int, int],
                       prior_weeks_n: int = PRIOR_WEEKS) -> None:
    """Wachstum je Cluster: Wochenzahl gegen den Wochen-Mittelwert der Vorwochen
    (Nächster-Zentroid-Zuordnung). „emerging" = mindestens 5 Papers UND das
    1,5-fache des Vorwochen-Mittels — ein Cluster, der letzte Woche kaum da war."""
    for c in clusters:
        prior_n = int(prior_counts.get(c["idx"], 0))
        mean = prior_n / prior_weeks_n if prior_weeks_n else 0.0
        c["prior_n"] = prior_n
        c["prior_weekly_mean"] = round(mean, 2)
        c["growth"] = round(c["n"] / mean, 2) if mean > 0 else None
        c["emerging"] = c["n"] >= 5 and (mean == 0 or c["n"] / mean >= 1.5)


def week_stats(rows: list[dict], week_n: int, prior: list[dict],
               window: tuple[date, date], embedded_n: int) -> dict:
    """Der Messblock, der in die Tabelle (stats JSON) und in den Prompt geht."""
    sources = Counter(source_group(r["source"]) for r in rows)
    top_sources = Counter((r["source"] or "") for r in rows).most_common(5)
    concepts = Counter((r["concept"] or "").strip() for r in rows
                       if (r["concept"] or "").strip()).most_common(6)
    prior_ns = [p["n"] for p in prior]
    return {
        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
        "week_n": week_n,
        "embedded_n": embedded_n,
        "prior_weeks": prior,
        "prior_median": statistics.median(prior_ns) if prior_ns else None,
        "ratio": volume_ratio(week_n, prior_ns),
        "sources": {k: int(v) for k, v in sorted(sources.items())},
        "top_sources": [[s, int(n)] for s, n in top_sources],
        "top_concepts": [[c, int(n)] for c, n in concepts],
        "oa_n": sum(1 for r in rows if is_open_access(r["source"])),
        "k": choose_k(len(rows)) if rows else 0,
    }


# ---------------------------------------------------------------------------
# Prompt + Wortwächter
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the research desk of a foresight service. You write short, sober, "
    "factual English for analysts. Use only the numbers and titles given in the "
    "data block; never invent papers, institutions, figures or causes. No "
    "forecasts, no promises, no recommendations, no hype adjectives. Plain prose: "
    "no headings, no bullet points, no markdown."
)


def ratio_phrase(ratio: float | None) -> str:
    if ratio is None:
        return "no comparable prior weeks"
    pct = round((ratio - 1) * 100)
    if abs(pct) < 5:
        return "about level with the prior four-week median"
    return f"{'+' if pct > 0 else ''}{pct}% versus the prior four-week median"


def build_prompt(theme: dict, stats: dict, clusters: list[dict]) -> str:
    name = theme.get("name_en") or theme.get("key")
    desc = (theme.get("description") or "").strip()
    w = stats["window"]
    lines = [
        f"Theme: {name}",
        f"Theme scope: {desc}" if desc else "",
        f"Week: {w['start']} to {w['end']}",
        f"Papers this week: {stats['week_n']}",
        f"Prior four weeks: {', '.join(str(p['n']) for p in stats['prior_weeks'])} "
        f"(median {round(stats['prior_median']) if stats['prior_median'] is not None else 'n/a'})",
        f"Volume: {ratio_phrase(stats['ratio'])}",
        "Source mix: " + ", ".join(f"{SOURCE_LABELS.get(k, k)} {v}"
                                   for k, v in stats["sources"].items()),
        "",
        "Clusters (embedding clusters of this week's papers; growth = this week's "
        "count divided by the mean weekly count of the prior four weeks assigned to "
        "the same cluster):",
    ]
    for c in clusters:
        growth = f"growth ×{c['growth']}" if c.get("growth") is not None else "no prior baseline"
        top = "; ".join(f"\"{p['title']}\"" for p in c["papers"][:2])
        lines.append(f"- {c['label']}: {c['n']} papers ({round(c['share'] * 100)}%), "
                     f"prior weekly mean {c['prior_weekly_mean']}, {growth}"
                     f"{' [emerging]' if c.get('emerging') else ''}. Examples: {top}")
    lines += [
        "",
        "Write ONE paragraph of 100 to 150 words: (1) this week's volume against "
        "the prior four-week median, with the numbers; (2) the two or three most "
        "notable clusters — say what they are about in your own words, drawing on "
        "the term labels and one or two of the example titles, with their counts; "
        "(3) which cluster grew most against the prior weeks, with its growth "
        "figure, or state that none stands out. Describe what was published; do "
        "not say what it means for the future.",
    ]
    return "\n".join(ln for ln in lines if ln is not None)


def word_count(text: str) -> int:
    return len((text or "").split())


def text_ok(text: str) -> bool:
    n = word_count(text)
    if n < WORDS_MIN or n > WORDS_MAX:
        return False
    t = text.strip()
    if t.startswith(("#", "-", "*", "•")) or "\n-" in t or "\n*" in t:
        return False
    return True


def clean_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^\s*(?:\*\*)?(?:Research )?Pulse[^\n]*\n", "", t, flags=re.I)
    t = t.replace("**", "").strip()
    return re.sub(r"\s*\n\s*", " ", t)


def generate_text(theme: dict, stats: dict, clusters: list[dict],
                  chat=None, model: str = PULSE_MODEL) -> tuple[str | None, str | None]:
    """Gemma-Absatz. Zwei Versuche (Seed, Seed+1), der Wortwächter entscheidet;
    fällt beides durch, wird der letzte Text trotzdem genommen und die Notiz
    im Rückgabewert vermerkt. chat=None → pipeline.llamacpp_client.chat."""
    if chat is None:
        from pipeline.llamacpp_client import chat as _chat
        chat = _chat
    prompt = build_prompt(theme, stats, clusters)
    last, note = None, None
    for attempt in range(2):
        raw = chat(model=model, prompt=prompt, system=SYSTEM_PROMPT,
                   temperature=PULSE_TEMPERATURE, seed=PULSE_SEED + attempt,
                   max_tokens=420)
        text = clean_text(raw)
        if text_ok(text):
            return text, None
        last = text or last
        note = f"word guard: {word_count(text)} words on attempt {attempt + 1}"
        logger.warning("%s — %s", theme.get("key"), note)
    return last, note


# ---------------------------------------------------------------------------
# DB (PostgreSQL + pgvector; Tests fassen das nicht an)
# ---------------------------------------------------------------------------

def ensure_schema(conn) -> None:
    """Additiv + idempotent; Spiegel von scripts/migrate_research_pulse.py."""
    from pipeline import db as db_mod
    if db_mod.USE_POSTGRES:
        conn.execute("""CREATE TABLE IF NOT EXISTS research_pulse (
            id SERIAL PRIMARY KEY,
            theme TEXT NOT NULL,
            year INTEGER NOT NULL,
            week INTEGER NOT NULL,
            week_start DATE NOT NULL,
            computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            stats JSONB NOT NULL,
            clusters JSONB NOT NULL,
            text TEXT,
            model TEXT,
            seconds REAL,
            note TEXT)""")
    else:
        conn.execute("""CREATE TABLE IF NOT EXISTS research_pulse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            year INTEGER NOT NULL,
            week INTEGER NOT NULL,
            week_start DATE NOT NULL,
            computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            stats TEXT NOT NULL,
            clusters TEXT NOT NULL,
            text TEXT,
            model TEXT,
            seconds REAL,
            note TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_pulse_theme_week "
                 "ON research_pulse (theme, year, week, computed_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_pulse_week "
                 "ON research_pulse (year, week, computed_at DESC)")


def weekly_counts(conn, theme: str, year: int, week: int) -> tuple[int, list[dict]]:
    """Wochenzahl + die vier Vorwochen (älteste zuerst) aus research_signals."""
    weeks = prior_weeks(year, week) + [(year, week)]
    start = iso_week_bounds(*weeks[0])[0]
    end = iso_week_bounds(year, week)[1]
    rows = conn.execute(
        "SELECT published AS d, count(*) AS n FROM research_signals "
        "WHERE mega_trend = ? AND published >= ? AND published <= ? "
        "GROUP BY published", (theme, start, end)).fetchall()
    by_week: Counter = Counter()
    for r in rows:
        d = r["d"] if not isinstance(r["d"], str) else date.fromisoformat(r["d"])
        y, w, _ = d.isocalendar()
        by_week[(y, w)] += int(r["n"])
    prior = [{"year": y, "week": w, "n": by_week.get((y, w), 0)} for y, w in weeks[:-1]]
    return by_week.get((year, week), 0), prior


def load_week_rows(conn, theme: str, year: int, week: int) -> list[dict]:
    start, end = iso_week_bounds(year, week)
    rows = conn.execute(
        "SELECT rs.trend_id, rs.title, rs.abstract, rs.url, rs.source, rs.concept, "
        "rs.published::text AS published, t.embedding_1024::text AS vec "
        "FROM research_signals rs JOIN trends t ON t.id = rs.trend_id "
        "WHERE rs.mega_trend = ? AND rs.published >= ? AND rs.published <= ? "
        "AND t.embedding_1024 IS NOT NULL ORDER BY rs.trend_id",
        (theme, start, end)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["vec"] = parse_vector(d.pop("vec"))
        out.append(d)
    return out


def prior_cluster_counts(conn, theme: str, year: int, week: int,
                         centroids) -> dict[int, int]:
    """Vorwochen-Papers per Nächster-Zentroid zuordnen — in SQL (pgvector <=>),
    damit die vier Vorwochen nicht als Vektoren durch die Leitung müssen."""
    if len(centroids) == 0:
        return {}
    pw = prior_weeks(year, week)
    start = iso_week_bounds(*pw[0])[0]
    end = iso_week_bounds(*pw[-1])[1]
    values = ", ".join(f"({i}, %s::vector)" for i in range(len(centroids)))
    params: list = [json.dumps([round(float(x), 6) for x in c]) for c in centroids]
    params += [theme, start, end]
    sql = (f"WITH c(idx, vec) AS (VALUES {values}) "
           "SELECT n.idx, count(*) AS n FROM research_signals rs "
           "JOIN trends t ON t.id = rs.trend_id "
           "CROSS JOIN LATERAL (SELECT c.idx FROM c ORDER BY t.embedding_1024 <=> c.vec LIMIT 1) n "
           "WHERE rs.mega_trend = %s AND rs.published >= %s AND rs.published <= %s "
           "AND t.embedding_1024 IS NOT NULL GROUP BY n.idx")
    rows = conn.execute(sql, params).fetchall()
    return {int(r["idx"]): int(r["n"]) for r in rows}


def compute_theme(conn, theme: dict, year: int, week: int) -> dict:
    """Messblock + Cluster für ein Theme (CPU + SQL, kein LLM)."""
    key = theme["key"]
    week_n, prior = weekly_counts(conn, key, year, week)
    rows = load_week_rows(conn, key, year, week)
    clusters, centroids = build_clusters(rows)
    if clusters:
        counts = prior_cluster_counts(conn, key, year, week, centroids)
        apply_prior_counts(clusters, counts)
    stats = week_stats(rows, week_n, prior, iso_week_bounds(year, week), len(rows))
    return {"theme": key, "year": year, "week": week,
            "week_start": iso_week_bounds(year, week)[0],
            "stats": stats, "clusters": clusters}


def save_pulse(conn, result: dict, text: str | None, model: str | None,
               seconds: float, note: str | None) -> int:
    from pipeline import db as db_mod
    stats = json.dumps(result["stats"], ensure_ascii=False)
    clusters = json.dumps(result["clusters"], ensure_ascii=False)
    if db_mod.USE_POSTGRES:
        row = conn.execute(
            "INSERT INTO research_pulse (theme, year, week, week_start, stats, clusters, "
            "text, model, seconds, note) VALUES (?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?, ?, ?) "
            "RETURNING id",
            (result["theme"], result["year"], result["week"], result["week_start"],
             stats, clusters, text, model, round(seconds, 1), note)).fetchone()
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO research_pulse (theme, year, week, week_start, stats, clusters, "
        "text, model, seconds, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (result["theme"], result["year"], result["week"], result["week_start"].isoformat(),
         stats, clusters, text, model, round(seconds, 1), note))
    return int(cur.lastrowid)
