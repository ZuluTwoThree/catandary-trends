"""Förderung mit bloßem Titel wird Signal, nicht verworfen (Owner 2026-10-10).

Stufe 0b verwirft Einträge unter MIN_SOURCE_TEXT_CHARS, weil aus einem Titel nur
erfundener Text entsteht. Für öffentliche Förderung gilt seit 10.10. „nie
verwerfen“ — der Eintrag wird klassifiziert, eingebettet und als status='signal'
ohne Artikeltext gespeichert. Andere Quellen bleiben beim Verwerfen."""
from __future__ import annotations

import pipeline.llm_processor as lp
from pipeline.models import ClassificationResult, ExtractionResult, RelevanceResult


TITLES = {1: "Förderung von Verbundvorhaben MARE:N Küstenforschung",
          2: "Quarterly market outlook for snack bars",
          3: "Investitionszuschuss Elektrolyseure Niedersachsen",
          4: "Wohnraumförderung Hamburg Neubau"}


def _entry(i, source, excerpt):
    return {"id": i, "title": TITLES[i], "excerpt": excerpt,
            "raw_content": None, "url": f"https://example.org/{i}", "source_name": source,
            "source_vertical": "CROSS", "source_type": "press_wire"}


def test_title_only_public_funding_becomes_signal(monkeypatch):
    entries = [_entry(1, "Förderinfo Bund – Bekanntmachungen (alle)", ""),
               _entry(2, "Some Trade Journal", ""),
               _entry(4, "Förderdatenbank des Bundes",
                      "Sie erhalten zinsgünstige Darlehen und Zuschüsse für den Neubau von "
                      "Mietwohnungen in Hamburg, wenn die Förderbedingungen erfüllt sind."),
               _entry(3, "Förderinfo Bund – Bekanntmachungen (alle)",
                      "Sie erhalten einen Zuschuss für Investitionen in Elektrolyseure, wenn Sie "
                      "ein kleines oder mittleres Unternehmen in Niedersachsen sind.")]
    monkeypatch.setattr(lp, "init_db", lambda: None)
    monkeypatch.setattr(lp, "get_unprocessed_entries", lambda **k: [dict(e) for e in entries])
    monkeypatch.setattr(lp, "get_recent_titles", lambda days=30: [])
    monkeypatch.setattr(lp, "get_recent_embeddings", lambda days=30: [])
    monkeypatch.setattr(lp, "RSS_CLASSIFY_MODE", "hybrid")
    monkeypatch.setattr(lp, "EMBED_BACKEND", "ollama")
    monkeypatch.setattr(lp, "STAGE5_BACKEND", "ollama")
    monkeypatch.setattr(lp, "save_stage_result", lambda *a, **k: None)
    monkeypatch.setattr(lp, "publish_stages_needed", lambda created: False)

    def hybrid(survivors):
        for e in survivors:
            e["_relevance"] = RelevanceResult(is_relevant=True, confidence=0.5,
                                              primary_vertical="ECO", reason="distill")
            e["_extraction"] = ExtractionResult()
            e["_classification"] = ClassificationResult(
                verticals=["ECO"], pestel=["E"], tags=[], trend_signal_type="funding",
                mega_trend=None, regions=[])
        return survivors, 0, 0
    monkeypatch.setattr(lp, "hybrid_classify", hybrid)
    vec = [0.0] * 8
    monkeypatch.setattr(lp, "generate_embedding", lambda model, text: [1.0] + vec[1:] if "MARE" in text
                        else ([0.0, 0.0, 1.0] + vec[3:] if "Hamburg" in text
                              else [0.0, 1.0] + vec[2:]))

    generated = []

    def gen(title, excerpt, *a, **k):
        generated.append(title)
        return lp.GeneratedContent(title="Lower Saxony funds electrolysers", summary="s", source_attribution="Source: x",
                                   body="b " * 120)
    monkeypatch.setattr(lp, "step_generate_content_en", gen)
    filtered, inserted, processed = [], [], []
    monkeypatch.setattr(lp, "mark_filtered", lambda eid, reason, *a, **k: filtered.append((eid, reason)))
    monkeypatch.setattr(lp, "insert_trend", lambda eid, data: inserted.append((eid, data)))
    monkeypatch.setattr(lp, "mark_processed", lambda eid: processed.append(eid))

    out = lp.run_pipeline_batch(limit=10)

    assert filtered == [(2, "insufficient_source_text")]      # andere Quellen: wie bisher
    by_id = dict(inserted)
    assert by_id[1]["status"] == "signal"                      # Titel-only Förderung: Signal
    assert by_id[1]["body_en"] is None and by_id[1]["trend_signal_type"] == "funding"
    assert "status" not in by_id[3] and by_id[3]["body_en"]     # mit Text: normaler Artikel
    assert by_id[4]["status"] == "signal"                      # Förderdatenbank: nur Signal (1b)
    assert generated == [TITLES[3]]                            # kein Modelltext aus Titel/Förderdatenbank
    assert out["created"] == 1 and out["signals_only"] == 2


def test_foerderdatenbank_with_text_is_signal_only(monkeypatch):
    """Owner 10.10. (1b): Förderdatenbank nie Artikel, auch mit Text."""
    import inspect
    src = inspect.getsource(lp.run_pipeline_batch)
    assert "is_funding_signal_only" in src
