"""Die Volltext-Anreicherung muss GENAU die Zeilen treffen, die der Lauf verarbeitet.

Anlass (2026-09-26): Zwei Stellen entschieden unabhängig voneinander, welche Einträge
wichtig sind, und zählten von entgegengesetzten Enden der Warteschlange:

  article_fetcher.fetch_batch     ORDER BY re.id DESC          (die NEUESTEN)
  db.get_unprocessed_entries      ORDER BY re.fetched_at ASC   (die ÄLTESTEN)

Solange der Rückstand kleiner ist als der Batch, nehmen beide alles und es fällt nicht
auf. Ist er größer — nach einem ausgefallenen Lauf, einem langen Wochenende, bei einem
Teillauf — verfehlen sich die Mengen: gemessen 0 von 250 Überschneidung, und im Lauf vom
25.09. trugen nur 13 von 331 verarbeiteten Einträgen Volltext, obwohl der Fetcher 226
geholt hatte. Die Artikel entstanden dann aus zwei Sätzen Teaser, 27 davon verwarf der
Garbage-Guard als zu kurz.

Dieser Test prüft die Kopplung, nicht die Sortierung: `enrich_fulltext` muss die
Auswahl des Laufs nehmen und als ID-Liste weitergeben.
"""
from __future__ import annotations

import pipeline.article_fetcher as af
import pipeline.db as db
from pipeline import run_full_cycle as rfc


def _capture(monkeypatch, selection_ids: list[int], *, limit: int, min_id: int = 0):
    """enrich_fulltext ausführen und festhalten, was bei fetch_batch ankommt."""
    seen: dict = {}

    def selection(lim=50, mid=0, **kw):
        seen["selection_args"] = (lim, mid)
        return [{"id": i} for i in selection_ids]

    monkeypatch.setattr(db, "get_unprocessed_entries", selection)
    monkeypatch.setattr(af, "fetch_batch",
                        lambda limit=100, ids=None: seen.setdefault("ids", ids) is None or 0)
    rfc.enrich_fulltext(limit, min_id=min_id)
    return seen


def test_enrichment_receives_exactly_the_selected_ids(monkeypatch):
    ids = [25494865, 25494900, 25495341]
    seen = _capture(monkeypatch, ids, limit=3)
    assert seen["ids"] == ids, "der Fetcher muss die Auswahl des Laufs bekommen, keine eigene"


def test_enrichment_uses_the_same_limit_and_window_as_the_run(monkeypatch):
    """Sonst reichert die Anreicherung ein anderes Fenster an als der Lauf verarbeitet."""
    seen = _capture(monkeypatch, [1, 2], limit=250, min_id=25490000)
    assert seen["selection_args"] == (250, 25490000)


def test_enrichment_passes_a_list_not_a_batch_size(monkeypatch):
    """Regression: `fetch_batch(limit=...)` ohne ids würde wieder selbst auswählen."""
    seen = _capture(monkeypatch, [7, 8, 9], limit=3)
    assert seen["ids"] is not None


def test_fetch_batch_with_ids_keeps_the_opt_in_and_no_text_conditions():
    """Die ID-Liste darf die bestehenden Filter nicht aushebeln: nur Opt-in-Quellen,
    nur unverarbeitet, nur ohne Text. Geprüft am SQL, das die Variante baut."""
    import inspect
    src = inspect.getsource(af.fetch_batch)
    ids_branch = src.split("if ids is not None:", 1)[1].split("else:", 1)[0]
    assert "re.id IN" in ids_branch
    assert "s.name IN" in ids_branch, "Opt-in-Quellen-Filter fehlt im ids-Zweig"
    assert "re.processed = FALSE" in ids_branch
    assert "re.raw_content IS NULL" in ids_branch


def test_fetch_batch_with_empty_list_is_a_noop(monkeypatch):
    """Ein leerer Lauf darf kein SQL mit leerer IN-Klausel bauen."""
    monkeypatch.setattr(af, "fulltext_source_names", lambda: ["X"])
    called = {"db": False}

    class Boom:
        def __enter__(self):
            called["db"] = True
            raise AssertionError("keine DB-Abfrage bei leerer ID-Liste")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(af, "get_connection", Boom)
    assert af.fetch_batch(ids=[]) == 0
    assert called["db"] is False
