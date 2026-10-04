"""Entwürfe für Trajectory Sheet und Field Watch (Owner 2026-10-04).

Owner-Festlegung 04.10.: Modelltext darf **als Entwurf** ins Blatt; jedes Entwurfsblatt
wird vor der Auslieferung von einem Menschen umgeschrieben. Für die mitgespeicherten
Quelltexte gilt die 1825-Tage-Regel.

Ablage je Kunde und Feld (Main-venv schreibt, der Renderer liest):

    data/field_watch/<kunde>/drafts/<feld>/<abschnitt>[-<woche>]-<datum>[-n].md    Text + Kopf
    data/field_watch/<kunde>/drafts/<feld>/<…>.json                                 Quellen, Modell,
                                                                                    Maschinentext, Quelltexte
    data/field_watch/_owner/drafts/<abschnitt>/<…>                                  setup / prospect

Kopf der .md-Datei (YAML zwischen `---`):

    status: draft        # draft = maschinell, nur im Entwurfsblatt (--draft)
                         # rewritten = vom Analysten umgeschrieben, darf ins Kundenblatt
    section: regulatory  # reading | regulatory | movers | setup | prospect
    …

Der Weg zur Auslieferung: Datei öffnen, Text umschreiben, `status: rewritten` setzen,
Blatt neu bauen. Ein `rewritten`, dessen Text noch fast wörtlich der Maschinentext ist
(Ähnlichkeit >= REWRITE_MAX_SIMILARITY), wird abgelehnt — die Zusage „ein Mensch hat
umgeschrieben" soll nicht an einer vergessenen Kopfzeile hängen.
"""
from __future__ import annotations

import difflib
import html as _html
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from pipeline.field_watch import OUT_DIR, slugify

SECTIONS = ("reading", "regulatory", "movers", "setup", "prospect")
CUSTOMER_SECTIONS = ("reading", "regulatory", "movers")
STATUSES = ("draft", "rewritten")
REWRITE_MAX_SIMILARITY = 0.85
RETENTION_DAYS = 1825
SECTION_LABELS = {"reading": "Einordnung", "regulatory": "Rechtsrahmen", "movers": "Was hinter der Bewegung steckt",
                  "setup": "Feld-Einrichtung", "prospect": "Interessenten-Briefing"}


class DraftNotRewritten(ValueError):
    """`status: rewritten`, aber der Text ist im Kern noch der Maschinenentwurf."""


def draft_dir(customer: str | None, field: str | None, section: str) -> Path:
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}")
    if customer:
        return OUT_DIR / slugify(customer) / "drafts" / slugify(field or "_all")
    return OUT_DIR / "_owner" / "drafts" / section


def _front(meta: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + body.strip() + "\n"


def parse(path: Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path}: Kopf (--- … ---) fehlt")
    meta = yaml.safe_load(m.group(1)) or {}
    if meta.get("status") not in STATUSES:
        raise ValueError(f"{path}: status muss draft oder rewritten sein, ist {meta.get('status')!r}")
    meta["body"] = m.group(2).strip()
    meta["path"] = str(path)
    side = Path(path).with_suffix(".json")
    meta["sidecar"] = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
    return meta


def save_draft(customer: str | None, field: str | None, section: str, body: str, meta: dict,
               payload: dict, week: str | None = None) -> Path:
    """Schreibt <abschnitt>[-<woche>]-<datum>[-n].md (+ .json). Nie überschreiben."""
    d = draft_dir(customer, field, section)
    d.mkdir(parents=True, exist_ok=True)
    stem0 = f"{section}{'-' + week if week else ''}-{datetime.now():%Y-%m-%d}"
    stem, n = stem0, 1
    while (d / f"{stem}.md").exists():
        n += 1
        stem = f"{stem0}-{n}"
    head = {"status": "draft", "section": section, "customer": customer, "field": field, "week": week,
            "created": datetime.now().isoformat(timespec="minutes"), **meta}
    (d / f"{stem}.md").write_text(_front(head, body), encoding="utf-8")
    side = dict(payload)
    side["machine_text"] = body
    side["review_hints"] = review_hints(body, payload.get("sources") or [], payload.get("measurement"))
    side["retention_until"] = (datetime.now() + timedelta(days=RETENTION_DAYS)).date().isoformat()
    (d / f"{stem}.json").write_text(json.dumps(side, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return d / f"{stem}.md"


_MD_LINK = re.compile(r"\[([^\]]{1,300})\]\((https?://[^\s)]{1,800})\)")
_CELEX_IN_URL = re.compile(r"CELEX(?::|%3A)(\d)(\d{4})([A-Z])(\d{4})", re.I)
_ACT_NO = re.compile(r"\b(\d{1,4})/(\d{4})\b|\b(\d{4})/(\d{1,4})\b")


_NUM = re.compile(r"(?<![\w/.,-])\d{1,3}(?:[.,\u202f\u00a0 ]\d{3})+(?![\d])|(?<![\w/.,-])\d+(?:[.,]\d+)?")


_FORECAST = re.compile(r"\b(wird erwartet|werden erwartet|prognostizier\w*|dürfte\w*|wird voraussichtlich|"
                       r"voraussichtlich|is expected to|are expected to|forecast\w*|projected to|will reach)\b", re.I)


def numbers(text: str) -> set[str]:
    """Zahlen eines Textes, normiert (Tausenderpunkte weg, Dezimalkomma → Punkt). URLs zählen nicht."""
    text = _MD_LINK.sub(lambda m: m.group(1), text or "")
    text = re.sub(r"https?://\S+", " ", text)
    out = set()
    for n in _NUM.findall(text):
        n = n.strip()
        if re.fullmatch(r"\d{1,3}(?:[.,\u202f\u00a0 ]\d{3})+", n):
            out.add(re.sub(r"\D", "", n))
        else:
            out.add(n.replace(",", "."))
    return out


def ungrounded_numbers(body: str, measurement: str) -> list[str]:
    """Zahlen im Text, die im Messblock nicht vorkommen (Einordnung: nur Messzahlen erlaubt)."""
    allowed = numbers(measurement)
    allowed |= {x.rstrip("0").rstrip(".") for x in allowed if "." in x}
    return sorted(n for n in numbers(body)
                  if n not in allowed and n.rstrip("0").rstrip(".") not in allowed and n not in {"1", "2", "3", "4", "5", "6", "7"})


def review_hints(body: str, sources: list[dict], measurement: str | None = None) -> list[str]:
    """Deterministische Prüfhinweise für den Analysten (kein Urteil, nur Auffälligkeiten):
    Links, die in keiner Quelle des Laufs stehen; Rechtsakt-Nummern, die nicht zur
    verlinkten CELEX-Nummer passen (Fund 04.10.: „1333/2008" verlinkt auf 32011R1130)."""
    known = {s.get("url") for s in sources or [] if s.get("url")}
    known |= {u.replace("%3A", ":") for u in known}
    hints: list[str] = []
    for line in (body or "").splitlines():
        for m in _MD_LINK.finditer(line):
            url = m.group(2)
            if url not in known and url.replace("%3A", ":") not in known:
                hints.append(f"Link ohne Quelle im Lauf: {url}")
            c = _CELEX_IN_URL.search(url)
            if not c:
                continue
            year, num = c.group(2), str(int(c.group(4)))
            nums = set()
            for a, b, y2, n2 in _ACT_NO.findall(line):
                if a and b:
                    nums.update({(b, str(int(a))), (a, str(int(b)))})
                if y2 and n2:
                    nums.update({(y2, str(int(n2))), (n2, str(int(y2)))})
            if nums and (year, num) not in nums:
                shown = ", ".join(sorted({f"{n_}/{y_}" for y_, n_ in nums if 1950 <= int(y_) <= 2100 and len(n_) <= 4}))
                celex = f"{c.group(1)}{year}{c.group(3).upper()}{c.group(4)}"
                hints.append(f"Rechtsakt-Nummer {shown} passt nicht zur verlinkten CELEX {celex}: {url}")
    for line in (body or "").splitlines():
        m = _FORECAST.search(line)
        if m:
            hints.append(f"Prognose-Formulierung „{m.group(0)}\" — das Blatt enthält keine Prognose: {line.strip()[:160]}")
    if measurement:
        bad = ungrounded_numbers(body, measurement)
        if bad:
            hints.append(f"Zahlen nicht aus der Messung (Einordnung darf nur Messzahlen nennen): {', '.join(bad)}")
    seen, out = set(), []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def similarity(a: str, b: str) -> float:
    norm = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())  # noqa: E731
    return difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


def check_rewritten(d: dict) -> None:
    machine = (d.get("sidecar") or {}).get("machine_text")
    if machine and similarity(machine, d["body"]) >= REWRITE_MAX_SIMILARITY:
        raise DraftNotRewritten(
            f"{d['path']}: status rewritten, aber {similarity(machine, d['body']):.0%} des Textes "
            f"stimmen mit dem Maschinenentwurf überein (Grenze {REWRITE_MAX_SIMILARITY:.0%}) — bitte umschreiben")


def load_section(customer: str, field: str, section: str, include_drafts: bool,
                 week: str | None = None) -> dict | None:
    """Neuester `rewritten` (geprüft) — sonst, nur mit include_drafts, neuester `draft`."""
    d = draft_dir(customer, field, section)
    if not d.exists():
        return None
    prefix = f"{section}-{week}-" if week else f"{section}-"
    files = sorted((p for p in d.glob(f"{prefix}*.md")
                    if week or not re.match(rf"{section}-\d{{4}}-W\d{{2}}-", p.name)),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    parsed = [parse(p) for p in files]
    for x in parsed:
        if x["status"] == "rewritten":
            check_rewritten(x)
            return x
    if include_drafts:
        return next((x for x in parsed if x["status"] == "draft"), None)
    return None


def purge(days: int = RETENTION_DAYS, now: float | None = None, apply: bool = False) -> list[str]:
    """Entwürfe (inkl. Quelltexten im .json) älter als `days` löschen (1825-Tage-Regel)."""
    cutoff = (now or time.time()) - days * 86400
    gone = []
    for p in OUT_DIR.glob("*/drafts/**/*"):
        if p.is_file() and p.suffix in (".md", ".json") and p.stat().st_mtime < cutoff:
            gone.append(str(p))
            if apply:
                p.unlink()
    return gone


# ---------------------------------------------------------------------------
# Sicheres Markdown → HTML (Modelltext kann fremden Inhalt tragen: erst escapen)
# ---------------------------------------------------------------------------
_LINK = re.compile(r"\[([^\]]{1,300})\]\((https?://[^\s)]{1,800})\)")
_BARE = re.compile(r"(?<![\"'>=])(https?://[^\s<)\]]{4,800})")
_BOLD = re.compile(r"\*\*([^*]{1,300})\*\*")
_EM = re.compile(r"(?<![*\w])\*([^*\n]{1,200})\*(?![*\w])")


_FAKE_LINK = re.compile(r"\[([^\]]{1,300})\]\((?!https?://)[^)]{0,300}\)")


def _inline(text: str) -> str:
    text = _FAKE_LINK.sub(r"\1", text)  # [Catandary-Messung](Catandary-Messung) → Text
    s = _html.escape(text, quote=True)
    links: list[str] = []

    def keep(url: str, label: str) -> str:
        links.append(f'<a href="{url}">{label}</a>')
        return f"\x00{len(links) - 1}\x00"

    s = _LINK.sub(lambda m: keep(m.group(2), m.group(1)), s)
    s = _BARE.sub(lambda m: keep(m.group(1), m.group(1)), s)
    s = _BOLD.sub(r"<b>\1</b>", s)
    s = _EM.sub(r"<i>\1</i>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], s)


def md_to_html(md: str) -> str:
    """Überschriften (#), Listen (-, *, 1.), Absätze, **fett**, *kursiv*, Links (nur http/https).
    Alles andere bleibt escapter Text — kein rohes HTML aus Modellausgaben."""
    out: list[str] = []
    para: list[str] = []
    lst: list[str] = []
    kind = None

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list():
        nonlocal kind
        if lst:
            out.append(f"<{kind}>" + "".join(f"<li>{_inline(x)}</li>" for x in lst) + f"</{kind}>")
            lst.clear()
        kind = None

    for line in (md or "").splitlines():
        s = line.rstrip()
        h = re.match(r"^(#{1,6})\s+(.*)$", s)
        b = re.match(r"^\s*[-*•]\s+(.*)$", s)
        n = re.match(r"^\s*\d+[.)]\s+(.*)$", s)
        if not s.strip():
            flush_para()
            flush_list()
        elif h:
            flush_para()
            flush_list()
            lvl = min(len(h.group(1)) + 2, 5)
            out.append(f"<h{lvl}>{_inline(h.group(2))}</h{lvl}>")
        elif b or n:
            flush_para()
            k = "ul" if b else "ol"
            if kind and kind != k:
                flush_list()
            kind = k
            lst.append((b or n).group(1))
        else:
            flush_list()
            para.append(s.strip())
    flush_para()
    flush_list()
    return "\n".join(out)
