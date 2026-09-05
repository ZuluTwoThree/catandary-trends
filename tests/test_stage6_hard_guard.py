"""Stage-6 HARD guard (#11, 2026-09-05): garbage is never accepted.

Root cause of the incident: llamacpp_client.chat_structured accepted the LAST
result once the soft validate budget was spent ("a flagged body beats None"),
so 22 token-soup bodies became drafts. The hard guard re-rolls with a fresh,
uncached request and raises GarbledOutputError instead of returning soup.
No network: POST /v1/chat/completions is mocked.
"""
import json

import pytest

import pipeline.llamacpp_client as lc
from pipeline.content_guard import GarbledOutputError, garbage_reasons
from pipeline.models import GeneratedContent

PROSE = ("The company reported a measurable shift in procurement behaviour, with "
         "buyers favouring suppliers that publish verified emissions data. Analysts "
         "attribute the change to new disclosure rules and to pressure from lenders, "
         "who increasingly price climate risk into credit terms. The report notes "
         "that smaller manufacturers struggle to produce the required documentation "
         "and may lose contracts as a result, while larger groups absorb the cost.")
SOUP = ": writing writing市/address : writing M M M M M       仪器("


def _content(body: str) -> str:
    return json.dumps({"title": "T", "summary": "S", "body": body,
                       "source_attribution": "src"})


def _client(monkeypatch, bodies: list[str], posts: list):
    """Each POST answers with the next body from `bodies`."""
    queue = list(bodies)

    class Resp:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": _content(self.body)}}]}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None):
            posts.append(dict(json))   # snapshot: the client mutates one payload
            return Resp(queue.pop(0))
    monkeypatch.setattr(lc.httpx, "Client", Client)
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)


def _hard(c: GeneratedContent) -> list[str]:
    return garbage_reasons(c.body)


def test_garbage_is_rerolled_uncached_and_clean_result_returned(monkeypatch):
    posts = []
    _client(monkeypatch, [SOUP, SOUP, PROSE], posts)
    r = lc.chat_structured("m", "p", GeneratedContent, hard_validate=_hard)
    assert r is not None and r.body == PROSE
    assert len(posts) == 3
    # the first request is normal; every hard re-roll disables prompt-cache reuse
    assert "cache_prompt" not in posts[0]
    assert posts[1]["cache_prompt"] is False and posts[2]["cache_prompt"] is False


def test_all_garbage_raises_instead_of_returning_soup(monkeypatch):
    posts = []
    _client(monkeypatch, [SOUP, SOUP, SOUP], posts)
    with pytest.raises(GarbledOutputError) as ei:
        lc.chat_structured("m", "p", GeneratedContent, hard_validate=_hard)
    assert len(posts) == 3
    assert "non_latin_script" in str(ei.value) or "too_short" in str(ei.value)


def test_soft_guard_still_accepts_last_result(monkeypatch):
    """Regression: the soft validate (cliché/brevity/grounding) keeps its
    'accept after budget' semantics — only the HARD guard refuses."""
    posts = []
    _client(monkeypatch, [PROSE, PROSE, PROSE], posts)
    r = lc.chat_structured("m", "p", GeneratedContent,
                           validate=lambda c: False, max_validate_retries=3,
                           hard_validate=_hard)
    assert r is not None and r.body == PROSE
    assert len(posts) == 3


def test_hard_guard_default_off_keeps_old_behaviour(monkeypatch):
    posts = []
    _client(monkeypatch, [SOUP], posts)
    r = lc.chat_structured("m", "p", GeneratedContent)
    assert r is not None and r.body == SOUP        # callers must opt in


def test_make_garbage_guard_uses_the_source():
    from pipeline.llm_processor import make_garbage_guard
    body = PROSE + " " + PROSE + " Nintendo (任天堂) raised prices."
    c = GeneratedContent(title="T", summary="S", body=body, source_attribution="s")
    assert make_garbage_guard("Nintendo raised prices.")(c)          # leak → reasons
    assert make_garbage_guard("任天堂 raised prices.")(c) == []       # in source → fine
    assert make_garbage_guard("x")(GeneratedContent(
        title="T", summary="S", body=PROSE, source_attribution="s")) == []
