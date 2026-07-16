#!/usr/bin/env python3
"""Forward-citation snowball for the TIR literature (Singh/Triulzi/Magee lineage).

Starts from the seed papers and walks the CITED-BY graph via the Semantic Scholar
Graph API: papers that cite the seeds, then papers citing those, etc. (transitive
forward-citation closure) up to --depth. Collects metadata + open-access PDF URLs.

Outputs (versioned in the repo):
  docs/tir_literature/bibliography.json  — full records (dedup by paperId)
  docs/tir_literature/index.md           — readable table, grouped by depth
  docs/tir_literature/pdf_manifest.csv    — paperId,title,oa_pdf_url,status

Open-access PDFs are downloaded (with --download) to OUTSIDE the repo — the HDD at
--pdf-dir — because they are bulky and copyright-bound; the repo keeps only links.
Paywalled full texts cannot be fetched; they are marked 'paywalled' in the manifest.

Resumable: re-running reuses bibliography.json (visited set), so --depth can be
raised incrementally without refetching. Gentle on the shared S2 rate limit
(unauthenticated ~1 req/s): sleeps between calls, exponential backoff on HTTP 429.

    python scripts/tir_lit_snowball.py --depth 2
    python scripts/tir_lit_snowball.py --depth 3 --download   # extend + fetch OA PDFs
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import deque
from pathlib import Path

import httpx

API = "https://api.semanticscholar.org/graph/v1"
SEEDS = {  # name -> S2 paperId (resolved from DOI)
    "Singh/Triulzi/Magee 2021 (Research Policy)": "79752afdbc33278ce4a36f138e3a39b11fbf4cc6",
    "Triulzi/Alstott/Magee 2020 (TFSC)":          "1b42db697ee2fc966f3a80f826d6d89a19cdd714",
}
CIT_FIELDS = ("citingPaper.paperId,citingPaper.title,citingPaper.year,"
              "citingPaper.venue,citingPaper.citationCount,"
              "citingPaper.influentialCitationCount,citingPaper.externalIds,"
              "citingPaper.openAccessPdf,citingPaper.authors")
REPO = Path(__file__).parent.parent
OUTDIR = REPO / "docs" / "tir_literature"


def log(m: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def _get(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    for attempt in range(6):
        r = client.get(url, params=params)
        if r.status_code == 429:
            wait = 3 * (attempt + 1)
            log(f"  429 rate-limited, wait {wait}s")
            time.sleep(wait)
            continue
        return r
    return r


def fetch_citations(client: httpx.Client, paper_id: str) -> list[dict]:
    """All papers citing paper_id (paged)."""
    out, offset = [], 0
    while True:
        r = _get(client, f"{API}/paper/{paper_id}/citations",
                 {"fields": CIT_FIELDS, "limit": 1000, "offset": offset})
        if r.status_code != 200:
            log(f"  citations {paper_id[:8]} HTTP {r.status_code}")
            break
        data = r.json().get("data", [])
        out.extend(cp["citingPaper"] for cp in data if cp.get("citingPaper"))
        if len(data) < 1000:
            break
        offset += 1000
        time.sleep(1.2)
    return out


def rec_from(p: dict, depth: int) -> dict:
    ext = p.get("externalIds") or {}
    oa = p.get("openAccessPdf") or {}
    return {
        "paperId": p.get("paperId"),
        "title": (p.get("title") or "").strip(),
        "year": p.get("year"),
        "venue": p.get("venue") or "",
        "authors": [a.get("name") for a in (p.get("authors") or [])][:8],
        "doi": ext.get("DOI"),
        "arxiv": ext.get("ArXiv"),
        "pmid": ext.get("PubMed"),
        "pmcid": ext.get("PubMedCentral"),
        "citationCount": p.get("citationCount"),
        "influential": p.get("influentialCitationCount"),
        "oa_pdf": oa.get("url"),
        "url": f"https://www.semanticscholar.org/paper/{p.get('paperId')}",
        "depth": depth,
    }


def snowball(depth_max: int, max_papers: int) -> dict[str, dict]:
    records: dict[str, dict] = {}
    bib = OUTDIR / "bibliography.json"
    if bib.exists():
        for r in json.loads(bib.read_text()):
            records[r["paperId"]] = r
        log(f"resuming from {len(records)} known records")
    q: deque[tuple[str, int]] = deque()
    visited_expanded: set[str] = set()
    for name, pid in SEEDS.items():
        records.setdefault(pid, {"paperId": pid, "title": name, "depth": 0,
                                 "url": f"https://www.semanticscholar.org/paper/{pid}"})
        q.append((pid, 0))
    with httpx.Client(timeout=60, headers={"User-Agent": "catandary-tir-research"}) as c:
        while q and len(records) < max_papers:
            pid, d = q.popleft()
            if d >= depth_max or pid in visited_expanded:
                continue
            visited_expanded.add(pid)
            cits = fetch_citations(c, pid)
            log(f"depth {d}→{d+1}: {pid[:8]} cited by {len(cits)}  (total {len(records)})")
            for p in cits:
                cid = p.get("paperId")
                if not cid:
                    continue
                if cid not in records:
                    records[cid] = rec_from(p, d + 1)
                if cid not in visited_expanded and d + 1 < depth_max:
                    q.append((cid, d + 1))
            time.sleep(1.2)
            # checkpoint
            OUTDIR.mkdir(parents=True, exist_ok=True)
            bib.write_text(json.dumps(list(records.values()), indent=1, ensure_ascii=False))
    return records


def write_index(records: dict[str, dict]) -> None:
    rows = sorted(records.values(),
                  key=lambda r: (r.get("depth", 9), -(r.get("year") or 0),
                                 -(r.get("citationCount") or 0)))
    oa = sum(1 for r in rows if r.get("oa_pdf") or r.get("arxiv") or r.get("pmcid"))
    lines = ["# TIR-Literatur — Zitations-Hülle (Singh/Triulzi/Magee-Linie)\n",
             f"Automatisch erzeugt via `scripts/tir_lit_snowball.py` (Semantic Scholar "
             f"Graph API). **{len(rows)} Arbeiten**, davon **{oa} Open-Access** "
             f"(Volltext ziehbar). Seeds = die zwei MIT-Grundlagenpaper (depth 0).\n",
             "| d | Jahr | Titel | Autoren | Venue | Zit. | OA-PDF | DOI/Link |",
             "|--|--|--|--|--|--|--|--|"]
    for r in rows:
        au = ", ".join((r.get("authors") or [])[:3])
        if r.get("authors") and len(r["authors"]) > 3:
            au += " et al."
        oa_l = f"[PDF]({r['oa_pdf']})" if r.get("oa_pdf") else (
            f"[arXiv](https://arxiv.org/abs/{r['arxiv']})" if r.get("arxiv") else (
            f"[PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/{r['pmcid']}/)" if r.get("pmcid") else "—"))
        link = f"[{r['doi']}](https://doi.org/{r['doi']})" if r.get("doi") else \
               f"[S2]({r.get('url','')})"
        title = (r.get("title") or "").replace("|", "\\|")[:90]
        lines.append(f"| {r.get('depth','')} | {r.get('year') or ''} | {title} | {au} "
                     f"| {(r.get('venue') or '')[:28]} | {r.get('citationCount') or ''} "
                     f"| {oa_l} | {link} |")
    (OUTDIR / "index.md").write_text("\n".join(lines))
    with (OUTDIR / "pdf_manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["paperId", "title", "year", "oa_pdf_url", "arxiv", "pmcid", "status"])
        for r in rows:
            url = r.get("oa_pdf") or (f"https://arxiv.org/pdf/{r['arxiv']}" if r.get("arxiv")
                  else (f"https://www.ncbi.nlm.nih.gov/pmc/articles/{r['pmcid']}/pdf/" if r.get("pmcid") else ""))
            w.writerow([r["paperId"], (r.get("title") or "")[:120], r.get("year") or "",
                        url, r.get("arxiv") or "", r.get("pmcid") or "",
                        "open_access" if url else "paywalled"])
    log(f"wrote index.md ({len(rows)} papers, {oa} OA) + pdf_manifest.csv")


def download_pdfs(records: dict[str, dict], pdf_dir: Path) -> None:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    got = skip = fail = 0
    with httpx.Client(timeout=90, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 catandary-research"}) as c:
        for r in records.values():
            url = r.get("oa_pdf") or (f"https://arxiv.org/pdf/{r['arxiv']}.pdf" if r.get("arxiv") else None)
            if not url:
                continue
            dest = pdf_dir / f"{r['paperId']}.pdf"
            if dest.exists() and dest.stat().st_size > 1000:
                skip += 1; continue
            try:
                resp = c.get(url)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                    dest.write_bytes(resp.content); got += 1
                    if got % 10 == 0:
                        log(f"  downloaded {got} PDFs …")
                else:
                    fail += 1
            except Exception:
                fail += 1
            time.sleep(0.5)
    log(f"PDFs: {got} new, {skip} present, {fail} failed → {pdf_dir}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--depth", type=int, default=2,
                    help="forward-citation depth (1=direct citers, 2=+their citers)")
    ap.add_argument("--max-papers", type=int, default=1500)
    ap.add_argument("--download", action="store_true", help="fetch OA PDFs to --pdf-dir")
    ap.add_argument("--pdf-dir", default="/mnt/data-hdd/tir_literature/pdfs")
    args = ap.parse_args()
    t0 = time.time()
    records = snowball(args.depth, args.max_papers)
    write_index(records)
    if args.download:
        download_pdfs(records, Path(args.pdf_dir))
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {len(records)} works in the closure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
