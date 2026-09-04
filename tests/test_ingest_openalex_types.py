"""Work-type gate in the OpenAlex concept sweep (#73): `admit_work` on mocked
works, and `ingest_concept` end-to-end with the network + DB monkeypatched —
only papers are inserted, skips are counted per type, the admitted type is
stored in openalex_meta via the raw_entries.openalex_id node key."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from scripts import ingest_openalex as oa


def _work(wid: str, wtype: str | None, url: str, title: str = "T", doi: str | None = None):
    return {
        "id": f"https://openalex.org/{wid}", "type": wtype, "title": title,
        "doi": doi or url, "publication_date": "2026-08-25",
        "primary_location": {"landing_page_url": url},
        "abstract_inverted_index": {"Deep": [0], "learning": [1]},
        "cited_by_count": 0, "counts_by_year": [], "is_retracted": False,
    }


ZENODO = _work("W1", "article", "https://doi.org/10.5281/zenodo.22080387",
               "sc26-submission/ad-artifacts: BatchFlow — SC26 Artifact v1.0.1")
PAPER = _work("W2", "article", "https://doi.org/10.1038/s41586-026-1")
PREPRINT = _work("W3", "preprint", "https://doi.org/10.1101/2026.08.25.1")
REVIEW = _work("W4", "review", "https://doi.org/10.1016/j.x.2026.1")
CHAPTER = _work("W5", "book-chapter", "https://link.springer.com/chapter/1")
DATASET = _work("W6", "dataset", "https://doi.org/10.1234/data.1")
SOFTWARE = _work("W7", "software", "https://doi.org/10.1234/sw.1")
GITHUB = _work("W8", "article", "https://github.com/org/repo")
EDITORIAL = _work("W9", "editorial", "https://doi.org/10.1234/ed.1")
UNTYPED = _work("W10", None, "https://doi.org/10.1234/x.1")
PARATEXT = _work("W11", "paratext", "https://doi.org/10.1234/p.1")


@pytest.mark.parametrize("work,expected", [
    (PAPER, (True, "article")), (PREPRINT, (True, "preprint")),
    (REVIEW, (True, "review")), (CHAPTER, (True, "book-chapter")),
    (ZENODO, (False, "repository")), (GITHUB, (False, "repository")),
    (DATASET, (False, "type:dataset")), (SOFTWARE, (False, "type:software")),
    (EDITORIAL, (False, "type:editorial")), (PARATEXT, (False, "type:paratext")),
    (UNTYPED, (False, "type:none")),
])
def test_admit_work(work, expected):
    assert oa.admit_work(work) == expected


def test_admit_work_checks_the_doi_too():
    # landing page on a publisher, DOI on Zenodo → still a repository deposit
    w = _work("W12", "article", "https://example.org/landing", doi="https://doi.org/10.5281/zenodo.9")
    assert oa.admit_work(w) == (False, "repository")


class _NoClient:
    """httpx.Client stand-in — the sweep must not touch the network."""
    def __init__(self, *a, **k): ...
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _run_sweep(monkeypatch, works, dry_run=False, cap=3000):
    inserted: list[dict] = []
    meta: list[tuple] = []
    monkeypatch.setattr(oa.httpx, "Client", _NoClient)
    monkeypatch.setattr(oa, "resolve_concept_id",
                        lambda client, name: ("https://openalex.org/C154945302", "Artificial intelligence"))
    monkeypatch.setattr(oa, "iter_works_fresh", lambda client, cid, after, before: iter(works))
    monkeypatch.setattr(oa.db, "upsert_source", lambda **kw: 42)

    def _insert(source_id, url, title, excerpt, published_date=None, **kw):
        if any(r["url"] == url for r in inserted):
            return None
        inserted.append({"source_id": source_id, "url": url, "title": title,
                         "excerpt": excerpt, "openalex_id": kw.get("openalex_id")})
        return len(inserted)

    monkeypatch.setattr(oa.db, "insert_raw_entry", _insert)
    monkeypatch.setattr(oa.db, "insert_openalex_meta", lambda rows: meta.extend(rows) or len(rows))
    stats = oa.ingest_concept("artificial intelligence", "TECH", "2026-08-22", "2026-09-05",
                              min_citations=0, cap=cap, dry_run=dry_run, fresh=True)
    return stats, inserted, meta


def test_fresh_sweep_keeps_papers_and_skips_artifacts(monkeypatch):
    works = [ZENODO, PAPER, PREPRINT, DATASET, REVIEW, SOFTWARE, GITHUB, CHAPTER,
             EDITORIAL, UNTYPED, PARATEXT]
    stats, inserted, meta = _run_sweep(monkeypatch, works)

    assert stats["works"] == 11
    assert stats["inserted"] == 4
    assert stats["duplicates"] == 0
    assert stats["skipped_repo"] == 2                      # Zenodo + GitHub
    assert stats["skipped_type"] == {"dataset": 1, "software": 1, "editorial": 1,
                                     "none": 1, "paratext": 1}
    assert [r["url"] for r in inserted] == [PAPER["primary_location"]["landing_page_url"],
                                            PREPRINT["primary_location"]["landing_page_url"],
                                            REVIEW["primary_location"]["landing_page_url"],
                                            CHAPTER["primary_location"]["landing_page_url"]]
    # the Zenodo artifact never reaches raw_entries
    assert not any("BatchFlow" in r["title"] for r in inserted)
    # concept prefix carries the tier into the embedding as before
    assert all(r["excerpt"].startswith("[Science · Artificial intelligence] ") for r in inserted)
    # node key + type stored for every admitted work (kind source for the index)
    assert [r["openalex_id"] for r in inserted] == ["W2", "W3", "W4", "W5"]
    assert {(m[0], m[3]) for m in meta} == {("W2", "article"), ("W3", "preprint"),
                                            ("W4", "review"), ("W5", "book-chapter")}


def test_fresh_sweep_duplicate_still_counts_and_stores_type(monkeypatch):
    stats, inserted, meta = _run_sweep(monkeypatch, [PAPER, PAPER])
    assert stats["inserted"] == 1 and stats["duplicates"] == 1
    # meta rows are de-duplicated by insert_openalex_meta (work_id upsert);
    # here both rows reach the buffer, the DB layer keeps one
    assert [m[0] for m in meta] == ["W2", "W2"]


def test_fresh_sweep_dry_run_writes_nothing(monkeypatch):
    stats, inserted, meta = _run_sweep(monkeypatch, [PAPER, ZENODO, DATASET], dry_run=True)
    assert stats["inserted"] == 1 and stats["skipped_repo"] == 1
    assert stats["skipped_type"] == {"dataset": 1}
    assert inserted == [] and meta == []


def test_cap_counts_admitted_works_only(monkeypatch):
    works = [DATASET, PAPER, ZENODO, PREPRINT, REVIEW]
    stats, inserted, _ = _run_sweep(monkeypatch, works, cap=2)
    assert stats["inserted"] == 2
    assert [r["openalex_id"] for r in inserted] == ["W2", "W3"]
