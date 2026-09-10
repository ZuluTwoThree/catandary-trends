#!/usr/bin/env python3
"""Zweiter Vektorraum ueber den QUELLTEXT (#102).

Warum ueberhaupt ein zweiter. Der bestehende `embedding`/`embedding_1024` wird
aus `title + excerpt[:500]` gerechnet — Median 588 Zeichen, also Ueberschrift und
Anriss. Dieser Ausschnitt ist fuer den DEDUP richtig gewaehlt und darf nicht
angefasst werden (1,7 Mio. Zeilen, geaenderte Semantik). Fuer Analyse und
Retrieval ist er zu duenn; gemessen am 2026-09-09 clusterte der Raum formelhafte
Meldungen nach ihrer SATZFORM ("X wins $600k SBIR Phase II award"), und die
Silhouette lag auf Mega-Trend-Hoehe bei ~0,02.

Was hier eingebettet wird: Titel + der volle verfuegbare Quelltext
(`raw_content`, sonst `excerpt`) nach HTML-Reinigung, OHNE die 500er-Kappe.
Das hilft auch den Signalen: 96 % von ihnen tragen einen Auszug mit Median
775 Zeichen — der Dedup-Vektor schneidet davon rund ein Drittel ab.

Warum ein eigener Lauf statt Stage 5: der Nachtlauf bleibt unangetastet. Der
Schritt laeuft auf der GPU ueber denselben Handover wie der Distill-Pfad
(scripts/embed_full_text_gpu.py) — der CPU-Embedder auf :8091 ist fuer die
kurzen Dossier-Anfragen gedacht und braucht fuer einen 6.400-Zeichen-Text rund
20 Sekunden, also 13 Stunden fuer eine Nacht Material (gemessen 10.09.). Seit
der Frist von 60 Monaten eilt es innerhalb einer Nacht ohnehin nicht mehr.

`full_embedded_at` wird bei JEDEM Ausgang gestempelt — auch wenn der Quelltext
zu duenn war. Sonst prueft der naechtliche Lauf dieselben Zeilen ewig neu.

    python scripts/embed_full_text.py --limit 200            # Dry-Run
    python scripts/embed_full_text.py --limit 2000 --apply
    python scripts/embed_full_text.py --status signal --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import EMBED_BACKEND, EMBED_MODEL
from pipeline.db import get_connection
from pipeline.llamacpp_client import served_model_id
from pipeline.text_clean import clean_source_text
# Derselbe belastbare Batch-Embedder wie der Distill-Pfad: ein Server-Fehler
# markiert NICHTS, derselbe Chunk wird wiederholt, nach EMBED_MAX_CONSECUTIVE_ERRORS
# Fehlern in Folge bricht der Lauf ab (#98 d).
from scripts.signal_batch import EmbeddingAbort, embed_chunk_resilient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

#: Unter dieser Laenge lohnt der zweite Vektor nicht — er waere fast identisch
#: mit dem Dedup-Vektor (Titel + 500 Zeichen). Die Zeile wird trotzdem
#: gestempelt, damit sie nicht wiederkehrt.
MIN_GAIN_CHARS = 600
#: Obergrenze je Text. Qwen3-Embedding laeuft mit -c 4096/8192; 8.000 Zeichen
#: sind grob 2.000 Tokens und passen sicher.
MAX_EMBED_CHARS = 8_000
DIM = 1024


def assert_embedding_model() -> None:
    """Sicherstellen, dass wirklich das Embedding-Modell antwortet (#98-Muster).

    llama-server ignoriert den `model`-Namen im Request und antwortet mit dem
    geladenen GGUF. Wird dieses Skript ohne den GPU-Handover gestartet, waehrend
    :8090 das 8B-Chatmodell haelt, liefert /v1/embeddings trotzdem einen Vektor —
    aus einem ANDEREN Raum. Die Zeilen waeren dann gestempelt und der Fehler
    unsichtbar. Also vorher fragen.

    Kontrollmessung 2026-09-10: Dedup- und Volltext-Vektor desselben Eintrags
    liegen bei cos 0,903, fremde Paare bei 0,201 — so sieht es aus, wenn beide
    aus demselben Modell stammen.
    """
    if EMBED_BACKEND != "llamacpp":
        return
    served = served_model_id() or ""
    if "mbed" not in served.lower():
        raise SystemExit(
            f"llama-server serviert {served!r}, kein Embedding-Modell. Ueber den "
            f"Handover starten: scripts/embed_full_text_gpu.py (erwartet {EMBED_MODEL})")
    logger.info("Embedding-Modell bestaetigt: %s", served)


def candidates(limit: int, status: str = "", min_id: int = 0) -> list[dict]:
    where = ["t.full_embedded_at IS NULL"]
    params: list = []
    if status:
        sts = [s.strip() for s in status.split(",") if s.strip()]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if min_id:
        where.append("t.id > ?")
        params.append(min_id)
    sql = ("SELECT t.id, t.title_en, re.raw_content, re.excerpt "
           "FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
           f"WHERE {' AND '.join(where)} ORDER BY t.id DESC")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def text_for(row: dict) -> str:
    """Titel + bester verfuegbarer Quelltext, HTML entfernt."""
    body = clean_source_text(row.get("raw_content") or row.get("excerpt") or "")
    title = (row.get("title_en") or "").strip()
    return f"{title}\n{body}"[:MAX_EMBED_CHARS]


def _stamp(conn, trend_id: int, vec: list[float] | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if vec is None:
        conn.execute("UPDATE trends SET full_embedded_at = ? WHERE id = ?", (now, trend_id))
        return
    lit = "[" + ",".join(f"{v:.6f}" for v in vec[:DIM]) + "]"
    conn.execute(
        "UPDATE trends SET embedding_full_1024 = ?::vector, full_embedded_at = ? WHERE id = ?",
        (lit, now, trend_id))


def run(rows: list[dict], apply: bool, chunk_size: int = 16) -> Counter:
    """Zu duenne Zeilen werden nur gestempelt, der Rest chunkweise eingebettet."""
    stat = Counter()
    todo: list[dict] = []
    for r in rows:
        stat["seen"] += 1
        raw = clean_source_text(r.get("raw_content") or r.get("excerpt") or "")
        if len(raw) < MIN_GAIN_CHARS:
            stat["too_thin"] += 1
            if apply:
                with get_connection() as conn:
                    _stamp(conn, r["id"], None)
            continue
        todo.append(r)

    state: dict = {}
    for i in range(0, len(todo), chunk_size):
        chunk = todo[i:i + chunk_size]
        texts = [text_for(r) for r in chunk]
        try:
            vecs = embed_chunk_resilient(texts, state)
        except EmbeddingAbort as exc:
            logger.error("ABORT: %s — %d Zeilen bleiben ungestempelt", exc, len(todo) - i)
            stat["aborted"] = 1
            break
        for r, text, vec in zip(chunk, texts, vecs):
            if not vec or len(vec) < DIM:
                stat["embed_failed"] += 1
                continue          # NICHT stempeln — beim naechsten Lauf erneut versuchen
            stat["embedded"] += 1
            stat["chars"] += len(text)
            if apply:
                with get_connection() as conn:
                    _stamp(conn, r["id"], vec)
                stat["written"] += 1
        logger.info("%d/%d eingebettet", min(i + chunk_size, len(todo)), len(todo))
    return stat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=500, help="0 = alle Kandidaten")
    ap.add_argument("--status", default="", help="nur diese Status (Komma-Liste)")
    ap.add_argument("--min-id", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=16, help="Texte je Embedding-Request")
    ap.add_argument("--apply", action="store_true", help="wirklich schreiben (Default: Dry-Run)")
    args = ap.parse_args(argv)

    rows = candidates(args.limit, args.status, args.min_id)
    logger.info("%d Kandidaten ohne Volltext-Vektor", len(rows))
    if not rows:
        return 0
    assert_embedding_model()
    stat = run(rows, args.apply, args.chunk)
    print()
    for k, v in sorted(stat.items()):
        print(f"  {k:14} {v}")
    if stat["embedded"]:
        print(f"  {'avg_chars':14} {stat['chars'] // stat['embedded']}")
    if not args.apply:
        print("\nDry-Run — nichts geschrieben. Mit --apply ausfuehren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
