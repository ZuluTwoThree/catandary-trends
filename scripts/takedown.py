#!/usr/bin/env python3
"""Takedown / removal requests from rights holders (compliance review 2026-09-02).

Public commitment: docs/compliance/takedown_notice.md — a request to
trends@catandary.de is acted on within 72 hours. This is the tool that acts:

  Article level (--url / --trend-id):
    trends.status → 'rejected', reviewed_at stamped (a human decision — the
    dedup window then no longer suppresses another outlet's coverage of the
    same story, see db.get_recent_embeddings), and the stored full-text copy of
    the underlying raw entry is deleted (raw_content → NULL). A rejected trend
    is never rendered, exported or listed in the sitemap; it is not added to
    dead_links (that table drives the archive-link badge, which withdrawn
    content must not get).

  Source level (--source):
    sources.llm_pipeline → FALSE (the source can never again become article
    material; signals via the distill path are unaffected). --deactivate also
    sets sources.active = FALSE. --purge-raw deletes every stored full text of
    that source. --reject-all rejects every draft/published trend of it.
    sources.yaml is NOT edited here — the poller reads the yaml, so set
    `active: false` / drop `fulltext: true` there too (the tool reminds you).

  --url accepts the publisher's article URL (matched against trends.source_url
  and raw_entries.url) or our own https://catandary.de/trends/<slug> URL.

Dry run is the default; --apply writes and appends a record to
data/takedown_log.jsonl (the audit trail for the 72-hour promise).

    python scripts/takedown.py --url https://publisher.example/story
    python scripts/takedown.py --url https://catandary.de/trends/some-slug --apply --note "mail 2026-09-02"
    python scripts/takedown.py --trend-id 1678403 --apply
    python scripts/takedown.py --source "Publisher Name" --purge-raw --apply
    python scripts/takedown.py --source publisher.example --deactivate --reject-all --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import DATA_DIR  # noqa: E402
from pipeline.db import _now_iso, get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    stream=sys.stderr)
logger = logging.getLogger("takedown")

OWN_HOSTS = ("catandary.de", "www.catandary.de")
LOG_PATH = DATA_DIR / "takedown_log.jsonl"


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _url_variants(url: str) -> list[str]:
    u = url.strip()
    out = {u, u.rstrip("/"), u.rstrip("/") + "/"}
    if u.startswith("http://"):
        out.add("https://" + u[len("http://"):])
    return sorted(out)


def find_trends(conn, url: str | None = None, trend_id: int | None = None) -> list[dict]:
    """Trends affected by a request: by id, by our own /trends/<slug> URL, or by
    the publisher's article URL (trends.source_url or raw_entries.url)."""
    cols = ("t.id, t.slug, t.title_en, t.status, t.source_name, t.source_url, "
            "t.raw_entry_id, t.reviewed_at")
    if trend_id is not None:
        return _rows(conn.execute(f"SELECT {cols} FROM trends t WHERE t.id = ?", (trend_id,)))
    if not url:
        return []
    p = urlparse(url.strip())
    if p.netloc.lower() in OWN_HOSTS and p.path.startswith("/trends/"):
        slug = p.path[len("/trends/"):].strip("/").split("/")[0]
        return _rows(conn.execute(f"SELECT {cols} FROM trends t WHERE t.slug = ?", (slug,)))
    variants = _url_variants(url)
    ph = ",".join("?" * len(variants))
    return _rows(conn.execute(
        f"SELECT DISTINCT {cols} FROM trends t "
        f"LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
        f"WHERE t.source_url IN ({ph}) OR re.url IN ({ph}) ORDER BY t.id",
        [*variants, *variants]))


def find_source(conn, ident: str) -> dict | None:
    """sources row by exact name (case-insensitive) or by feed host."""
    ident = ident.strip()
    rows = _rows(conn.execute(
        "SELECT id, name, feed_url, active, llm_pipeline FROM sources WHERE LOWER(name) = LOWER(?)",
        (ident,)))
    if rows:
        return rows[0]
    host = urlparse(ident if "://" in ident else "https://" + ident).netloc.lower()
    if not host:
        return None
    host = host[4:] if host.startswith("www.") else host
    rows = _rows(conn.execute(
        "SELECT id, name, feed_url, active, llm_pipeline FROM sources "
        "WHERE feed_url LIKE ? OR feed_url LIKE ? ORDER BY id",
        (f"%://{host}/%", f"%://www.{host}/%")))
    return rows[0] if rows else None


def source_footprint(conn, source: dict) -> dict:
    """What a source block would touch: stored full texts, drafts, published."""
    raw = conn.execute(
        "SELECT COUNT(*) AS n FROM raw_entries WHERE source_id = ? AND raw_content IS NOT NULL",
        (source["id"],)).fetchone()
    trends = _rows(conn.execute(
        "SELECT status, COUNT(*) AS n FROM trends WHERE source_name = ? GROUP BY status",
        (source["name"],)))
    return {"raw_with_text": int(raw["n"] if isinstance(raw, dict) else raw[0]),
            "trends_by_status": {r["status"]: int(r["n"]) for r in trends}}


def reject_trends(conn, trends: list[dict], purge_raw: bool = True) -> dict:
    now = _now_iso()
    rejected = purged = 0
    for t in trends:
        if t["status"] != "rejected":
            conn.execute("UPDATE trends SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                         (now, t["id"]))
            rejected += 1
        if purge_raw and t.get("raw_entry_id"):
            cur = conn.execute(
                "UPDATE raw_entries SET raw_content = NULL WHERE id = ? AND raw_content IS NOT NULL",
                (t["raw_entry_id"],))
            purged += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return {"rejected": rejected, "raw_purged": purged}


def block_source(conn, source: dict, deactivate: bool = False, purge_raw: bool = False,
                 reject_all: bool = False) -> dict:
    conn.execute("UPDATE sources SET llm_pipeline = FALSE WHERE id = ?", (source["id"],))
    if deactivate:
        conn.execute("UPDATE sources SET active = FALSE WHERE id = ?", (source["id"],))
    out = {"llm_pipeline": False, "deactivated": deactivate, "raw_purged": 0, "rejected": 0}
    if purge_raw:
        cur = conn.execute(
            "UPDATE raw_entries SET raw_content = NULL WHERE source_id = ? AND raw_content IS NOT NULL",
            (source["id"],))
        out["raw_purged"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    if reject_all:
        cur = conn.execute(
            "UPDATE trends SET status = 'rejected', reviewed_at = ? "
            "WHERE source_name = ? AND status IN ('draft', 'review', 'published')",
            (_now_iso(), source["name"]))
        out["rejected"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return out


def append_log(record: dict, path: Path | None = None) -> None:
    path = path or LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("takedown log not written (%r) — record: %s", e, record)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Act on a takedown / removal request")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--url", help="publisher article URL or our /trends/<slug> URL")
    what.add_argument("--trend-id", type=int)
    what.add_argument("--source", help="source name (as in sources.yaml) or feed host")
    ap.add_argument("--keep-raw", action="store_true",
                    help="article mode: do not delete the stored full text")
    ap.add_argument("--purge-raw", action="store_true",
                    help="source mode: delete every stored full text of the source")
    ap.add_argument("--deactivate", action="store_true",
                    help="source mode: also set sources.active = FALSE")
    ap.add_argument("--reject-all", action="store_true",
                    help="source mode: reject every draft/published trend of the source")
    ap.add_argument("--note", default="", help="ticket / mail reference for the log")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="(default)")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record: dict = {"ts": stamp, "note": args.note, "applied": bool(args.apply)}

    with get_connection() as conn:
        if args.source:
            src = find_source(conn, args.source)
            if not src:
                print(f"no source matches {args.source!r}")
                return 1
            fp = source_footprint(conn, src)
            print(f"source #{src['id']} {src['name']!r} ({src['feed_url']}) "
                  f"active={src['active']} llm_pipeline={src['llm_pipeline']}")
            print(f"  stored full texts: {fp['raw_with_text']:,}; trends: {fp['trends_by_status']}")
            print(f"  plan: llm_pipeline=false"
                  f"{', active=false' if args.deactivate else ''}"
                  f"{', purge full texts' if args.purge_raw else ''}"
                  f"{', reject all drafts/published' if args.reject_all else ''}")
            record.update({"mode": "source", "source_id": src["id"], "source": src["name"]})
            if args.apply:
                res = block_source(conn, src, deactivate=args.deactivate,
                                   purge_raw=args.purge_raw, reject_all=args.reject_all)
                record.update(res)
                print(f"  applied: {res}")
            print("  next: sources.yaml → set `active: false` / remove `fulltext: true` for this "
                  "source (the poller and the fetcher read the yaml, not the DB flag);")
        else:
            trends = find_trends(conn, url=args.url, trend_id=args.trend_id)
            if not trends:
                print("no trend matches the request")
                return 1
            for t in trends:
                print(f"trend #{t['id']} [{t['status']}] {t['slug']} — {t['title_en'][:70]!r} "
                      f"(source: {t['source_name']}, raw_entry {t['raw_entry_id']})")
            print(f"  plan: status=rejected, reviewed_at=now"
                  f"{'' if args.keep_raw else ', raw_content=NULL'} for {len(trends)} trend(s)")
            record.update({"mode": "trend", "trend_ids": [t["id"] for t in trends],
                           "url": args.url})
            if args.apply:
                res = reject_trends(conn, trends, purge_raw=not args.keep_raw)
                record.update(res)
                print(f"  applied: {res}")

    if args.apply:
        append_log(record)
        print(f"  logged to {LOG_PATH}")
        print("  next: re-run the static export so the public site drops the article; "
              "reply to the requester within 72 hours.")
    else:
        print("dry run — nothing written (use --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
