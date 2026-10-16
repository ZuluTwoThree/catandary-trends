"""Daily Digest (Stage 10b): Auswahl, Budget, Belegprüfung, Mail-Darstellung."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline import daily_digest as dd

ROOT = Path(__file__).resolve().parent.parent


def _art(i, v="TECH", title=None, conf=0.9, sig="market_shift"):
    return {"id": i, "slug": f"slug-{i}", "title_en": title or f"Title {i}",
            "summary_en": f"Summary of article {i} with 44.9 percent and 1,000 units.",
            "primary_vertical": v, "mega_trend": "artificial_intelligence_and_automation",
            "trend_signal_type": sig, "source_name": f"Source {i}", "confidence": conf}


def _data(n_tech=30, story=None):
    arts = [_art(1000000 + i) for i in range(n_tech)] + [_art(2000000 + i, v="FOOD") for i in range(4)]
    d = dd.RunData(articles=arts, mega_names={"artificial_intelligence_and_automation": "KI"})
    if story:
        for m in story:
            d.size[m] = len(story)
            d.story_of[m] = story[0]
        d.groups = [{"brand": "apple", "n": len(story), "today": list(story)}]
    return d


def test_featured_takes_one_article_per_story():
    story = [1000000, 1000001, 1000002, 1000003]
    data = _data(story=story)
    p = dd.vertical_prompt("TECH", [a for a in data.articles if a["primary_vertical"] == "TECH"], data)
    feat = p.split("Hervorgehobene Artikel")[1].split("Alle übrigen")[0]
    ids = [int(x) for x in re.findall(r"^\[(\d+)\]", feat, flags=re.M)]
    assert len(ids) == dd.FEATURED
    assert sum(1 for i in ids if i in story) == 1          # die Story nur einmal hervorgehoben
    assert ids[0] == 1000000                              # größte Story zuerst
    rest = p.split("Alle übrigen")[1]
    assert all(f"[{i}]" in rest for i in story[1:])       # Folgeberichte stehen in der Titelliste


def test_small_verticals_get_no_section():
    data = _data()
    data.articles += [_art(3000000, v="DESIGN"), _art(3000001, v="DESIGN")]
    assert "DESIGN" not in dd.by_vertical(data)
    assert set(dd.by_vertical(data)) == {"TECH", "FOOD"}


def test_fit_vertical_drops_weakest_titles_until_budget(monkeypatch):
    monkeypatch.setattr(dd, "PROMPT_BUDGET", 2000)
    data = _data(n_tech=200)
    arts = [a for a in data.articles if a["primary_vertical"] == "TECH"]
    for a in arts:
        a["title_en"] = f"A fairly long headline about development number {a['id']} in its field"
    assert len(dd.vertical_prompt("TECH", arts, data)) // 4 > 2000      # passt ungekürzt nicht
    counter = lambda t: len(t) // 4                                   # noqa: E731
    p, n, drop = dd.fit_vertical("TECH", arts, data, counter)
    assert drop > 0 and n <= 2000
    assert f"{drop} weitere aus Platzgründen weggelassen" in p
    assert "[1000000]" in p                                           # hervorgehobene bleiben


def test_check_flags_foreign_and_count_citations_and_tolerates_number_format():
    prompt = "[1000001] Lufthansa takes 44.9% of TAP\n[1000002] 1,000 jobs\nSignaltypen 263"
    ids = {1000001, 1000002, 1000003}
    text = ("Lufthansa hält 44,9 % [1000001]. 1.000 Stellen [1000002]. "
            "Marktbewegung dominiert [263]. Fremd [1000003]. Erfunden 77 % [1000002].")
    c = dd.check(text, prompt, ids)
    assert c["bad_ids"] == [263, 1000003]      # Anzahl in Klammern, ID aus anderem Material
    assert c["bad_numbers"] == ["77"]          # 44,9 und 1.000 sind Formatvarianten
    assert c["distinct_cited"] == 4


def test_generate_with_fake_model_writes_refs_and_checks():
    data = _data(story=[1000000, 1000001])
    calls = []

    def fake_chat(prompt):
        calls.append(prompt)
        return "### Kurzlage\nApple dominiert [1000000, 1000001]. Unsinn [999]."

    now = datetime.now(timezone.utc)
    res = dd.generate(data, now - timedelta(hours=4), now, chat=fake_chat, counter=lambda t: 100)
    assert len(calls) == 3                     # TECH, FOOD, Überblick
    assert set(res["sections"]) == {"TECH", "FOOD"}
    assert res["checks"]["TECH"]["bad_ids"] == [999]
    assert res["checks"]["FOOD"]["bad_ids"] == [999, 1000000, 1000001]   # TECH-IDs nicht im FOOD-Material
    assert res["refs"]["1000000"]["slug"] == "slug-1000000"
    assert "999" not in res["refs"]
    assert dd.totals(res)["bad_ids"] == 1 + 3 + 1  # TECH 999, FOOD 999 + zwei TECH-IDs, Überblick 999


def test_generate_empty_run_is_not_ok():
    now = datetime.now(timezone.utc)
    res = dd.generate(dd.RunData(articles=[]), now, now, chat=lambda p: pytest.fail("no call"))
    assert res["status"] == "empty"


def _result():
    now = datetime.now(timezone.utc)
    return {"date": now.isoformat(), "until": now.isoformat(), "status": "ok", "model": "Qwen3.8-27B",
            "articles": 2, "stories": 1, "total_seconds": 12,
            "overview": "### Schlagzeile\n**Apple** <b>x</b> [1000000, 999] mit 77 %.",
            "sections": {"TECH": "- Thema [1000000]"}, "per_vertical": {"TECH": 2}, "dropped": {},
            "checks": {"_overview": {"words": 5, "cited": 2, "distinct_cited": 2, "bad_ids": [999],
                                     "numbers": 1, "bad_numbers": ["77"]},
                       "TECH": {"words": 2, "cited": 1, "distinct_cited": 1, "bad_ids": [],
                                "numbers": 0, "bad_numbers": []}},
            "refs": {"1000000": {"slug": "apple-home", "title": "Apple <Home>", "source": "Verge"}}}


def test_mail_html_links_ids_to_article_and_escapes():
    h = dd.render_mail_html(_result(), base="https://example.test/trends/")
    assert 'href="https://example.test/trends/apple-home"' in h
    assert ">1000000</a>" in h
    assert "line-through" in h and ">999<" in h               # ungültiger Beleg sichtbar, ohne Link
    assert "&lt;b&gt;" in h and "<b>x" not in h              # Modelltext wird escaped
    assert "<strong>Apple</strong>" in h
    assert "Apple &lt;Home&gt;" in h                          # Titel im Tooltip escaped
    assert "Zahl steht nicht im Material" in h


def test_mail_text_numbers_citations_with_url_list():
    t = dd.render_mail_text(_result(), base="https://example.test/trends/")
    assert "[1, 999?]" in t
    assert "[1] https://example.test/trends/apple-home" in t


def test_load_last_ignores_stale_and_empty(tmp_path, monkeypatch):
    p = tmp_path / "daily_digest_last.json"
    monkeypatch.setattr(dd, "LAST_PATH", p)
    assert dd.load_last() is None
    r = _result()
    p.write_text(json.dumps(r))
    assert dd.load_last()["articles"] == 2
    r["date"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    p.write_text(json.dumps(r))
    assert dd.load_last() is None
    r = _result() | {"status": "empty"}
    p.write_text(json.dumps(r))
    assert dd.load_last() is None


def test_save_writes_last_and_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, "LAST_PATH", tmp_path / "last.json")
    monkeypatch.setattr(dd, "ARCHIVE_DIR", tmp_path / "arch")
    r = _result()
    dd.save(r)
    assert json.loads((tmp_path / "last.json").read_text())["model"] == "Qwen3.8-27B"
    assert (tmp_path / "arch" / f"{r['until'][:10]}.json").exists()


def test_morning_mail_opens_with_digest():
    import scripts.review_notify as rn
    subject, body, text = rn.build_mail(3, 5, "2026-10-10", [{"title_en": "Held", "source_name": "X"}],
                                        digest=_result())
    assert subject.startswith("Daily Digest ")
    assert body.index("Daily Digest") < body.index("held by the quality gate")
    assert text.startswith("DAILY DIGEST")
    s2, b2, _ = rn.build_mail(3, 5, None, [])
    assert "Daily Digest" not in s2 + b2


def test_cycle_runs_digest_inside_judge_block_and_reports_rc():
    sh = (ROOT / "scripts" / "scheduled_cycle.sh").read_text()
    judge = sh.index("python -m pipeline.draft_judge")
    digest = sh.index("python -m scripts.daily_digest --since \"$CYCLE_STARTED_AT\"")
    stop = sh.index("llama_unit_stop_owned scheduled_cycle-judge")
    assert judge < digest < stop                    # auf dem Richter-Server, vor dessen Stopp
    assert sh.index('CYCLE_STARTED_AT="$(date -Iseconds)"') < judge
    assert "digest=${RCD:--}" in sh
    from scripts import cycle_watchdog
    assert "digest" in cycle_watchdog.STAGE_LABEL
