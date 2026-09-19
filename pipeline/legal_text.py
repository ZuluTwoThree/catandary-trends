"""Rechtstexte artikelweise lesen — Stufe 3 des Plans
docs/plan_dossier_agent_2026-09-18.md, Lehre 6/7 des Handdurchgangs
(`docs/dossier_manual_run_2026-09-19.md`): der EUR-Lex-Volltext des Data Act
war beim Abruf vor Kapitel VI abgeschnitten, und die entscheidende Ausnahme
(Art. 31) tauchte in keiner Dossierversion auf, weil niemand den Artikel je
gelesen hatte.

Für die Hosts in `LEGAL_HOSTS` holt der Rechercheur die Seite mit einer sehr
viel größeren Kappe (`LEGAL_FETCH_CHARS`) und behält als Seitentext nur

  (a) den Definitionsartikel und
  (b) die Artikel/Paragraphen, deren Überschrift oder Text die Begriffe der
      Lücke trifft,

samt ihren Titeln, gedeckelt auf `LEGAL_KEEP_CHARS` (12.000 — die normale
Speicherkappe des Fetchers). Welche Artikel behalten wurden, steht im
Rückgabewert (`kept`) und beim Aufrufer an der Quelle (`legal_articles`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

LEGAL_HOSTS = ("eur-lex.europa.eu", "gesetze-im-internet.de", "legislation.gov.uk",
               "ecfr.gov", "federalregister.gov")
LEGAL_FETCH_CHARS = 1_500_000      # eine Verordnung mit Anhängen passt hinein
LEGAL_KEEP_CHARS = 12_000          # = article_fetcher.MAX_TEXT_CHARS
MAX_ARTICLE_CHARS = 4_000          # ein einzelner Artikel wird darüber gekürzt
MIN_TERM_LEN = 4

# Artikel-/Paragraphenkopf am Zeilenanfang: "Article 23", "Art. 23", "Artikel 23",
# "§ 12", "Section 4", "Sec. 4", "Rule 12", "Regulation 5" — optional mit Titel
# in derselben Zeile ("Article 2 Definitions", "§ 3 Begriffsbestimmungen").
_HEAD = re.compile(
    r"^[ \t]*(?P<label>(?:Article|Art\.|Artikel|§|Section|Sec\.|Rule|Regulation)"
    r"[ \t]*(?P<num>\d{1,4}[a-z]?))(?P<rest>[^\n]{0,120})$",
    re.IGNORECASE | re.MULTILINE)
_DEF_RE = re.compile(r"\b(definitions?|begriffsbestimmungen|interpretation)\b", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ0-9'-]{2,}")


def is_legal_host(url: str) -> bool:
    try:
        host = urlparse(str(url or "")).netloc.lower().removeprefix("www.")
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in LEGAL_HOSTS)


@dataclass
class Article:
    label: str          # "Article 23"
    title: str          # Überschrift der Folgezeile oder Rest der Kopfzeile
    body: str
    start: int
    is_definitions: bool = False
    hits: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        head = self.label + (f" — {self.title}" if self.title else "")
        body = self.body.strip()
        if len(body) > MAX_ARTICLE_CHARS:
            body = body[:MAX_ARTICLE_CHARS].rstrip() + " […]"
        return f"{head}\n{body}".strip()


def _stems(terms) -> list[str]:
    out: list[str] = []
    for t in terms or ():
        for w in _WORD.findall(str(t or "").lower()):
            w = w.strip("'-")
            if len(w) >= MIN_TERM_LEN:
                st = w[:-1] if (len(w) > 5 and w.endswith("s")) else w
                if st not in out:
                    out.append(st)
    return out


def split_articles(text: str) -> list[Article]:
    """Artikel in Dokumentreihenfolge; leer, wenn der Text keine
    Artikelstruktur trägt (dann bleibt der Anfang wie bisher)."""
    heads = [m for m in _HEAD.finditer(text or "")]
    # Ein einzelner Treffer ist keine Struktur — Inhaltsverzeichnisse tragen
    # zudem viele Köpfe ohne Körper; die Kopfzeilen mit leerem Körper fallen.
    arts: list[Article] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        rest = " ".join((m.group("rest") or "").strip(" -–—:.").split())
        title = rest
        lines = [ln.strip() for ln in body.strip("\n").split("\n")]
        if not title and lines and lines[0] and len(lines[0]) <= 120 and not lines[0].endswith("."):
            title = lines[0]
            body = "\n".join(lines[1:])
        label = " ".join(m.group("label").split())
        label = re.sub(r"^art\.", "Art.", label, flags=re.IGNORECASE)
        if len(body.strip()) < 40:
            continue
        arts.append(Article(label=label, title=title, body=body, start=m.start(),
                            is_definitions=bool(_DEF_RE.search(title) or _DEF_RE.search(body[:200]))))
    if len(arts) < 2:
        return []
    # Doppelte Labels (Inhaltsverzeichnis + Text): den längeren Körper behalten
    best: dict[str, Article] = {}
    for a in arts:
        key = a.label.lower()
        if key not in best or len(a.body) > len(best[key].body):
            best[key] = a
    return sorted(best.values(), key=lambda a: a.start)


def slice_articles(text: str, terms, limit: int = LEGAL_KEEP_CHARS) -> tuple[str, list[str]]:
    """(Seitentext, behaltene Artikel). Definitionsartikel zuerst, dann die
    Artikel mit Begriffstreffer in Dokumentreihenfolge, bis `limit` voll ist.
    Ohne Artikelstruktur: der Anfang des Textes, keine Labels."""
    text = str(text or "")
    arts = split_articles(text)
    if not arts:
        return text[:limit], []
    stems = _stems(terms)
    chosen: list[Article] = []
    for a in arts:
        if a.is_definitions:
            chosen.append(a)
    for a in arts:
        if a in chosen:
            continue
        hay = f"{a.title}\n{a.body}".lower()
        hits = [st for st in stems if st in hay]
        if hits:
            a.hits = hits
            chosen.append(a)
    if not chosen:
        chosen = arts[:3]
    # Artikel mit mehr Treffern zuerst innerhalb der Kappe, Ausgabe aber in
    # Dokumentreihenfolge — der Definitionsartikel steht ohnehin vorn.
    ranked = sorted(chosen, key=lambda a: (not a.is_definitions, -len(a.hits), a.start))
    kept: list[Article] = []
    used = 0
    for a in ranked:
        t = a.text
        if used + len(t) + 2 > limit:
            if not kept:
                kept.append(a)
            continue
        kept.append(a)
        used += len(t) + 2
    kept.sort(key=lambda a: a.start)
    out = "\n\n".join(a.text for a in kept)[:limit]
    labels = [a.label + (" (Definitions)" if a.is_definitions else "") for a in kept]
    return out, labels


# --------------------------------------------------------------------------
# Runde 28 (2026-09-19): Nachschlag im vollen Rechtstext
# --------------------------------------------------------------------------
# Die Zahlenpruefung (`dossier_structure.verify_cited_figures`) sieht nur den
# gespeicherten Ausschnitt (<= LEGAL_KEEP_CHARS). Der volle Text liegt aber im
# Web-Cache unter dem Schluessel "page-legal" — steht die Zahl in einem Artikel,
# den die Lueckenbegriffe beim Abruf nicht getroffen haben, wird hier um die
# Begriffe des SATZES neu geschnitten und darin nachgeschlagen. Kein Netz.

def cached_full_text(url: str) -> str | None:
    """Der beim Abruf gecachte volle Rechtstext (oder None)."""
    if not is_legal_host(url):
        return None
    try:
        from pipeline import web_cache
        hit = web_cache.cache_get("page", web_cache.make_key("page-legal", url))
    except Exception:                                               # noqa: BLE001
        return None
    if isinstance(hit, dict) and hit.get("text"):
        return str(hit["text"])
    return None


def reslice_for(url: str, terms, full_text: str | None = None,
                limit: int = LEGAL_KEEP_CHARS) -> tuple[str, list[str]]:
    """Artikelschnitt um `terms` (die Woerter des zu pruefenden Satzes) aus dem
    vollen Text — `full_text` oder der Cache. ("", []) wenn nichts vorliegt."""
    full = full_text if full_text is not None else cached_full_text(url)
    if not full:
        return "", []
    return slice_articles(full, list(terms or []), limit=limit)
