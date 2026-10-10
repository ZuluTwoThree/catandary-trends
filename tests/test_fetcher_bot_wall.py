"""Sperrseiten sind kein Volltext (2026-10-10).

Die Radware-Seite der Förderdatenbank wurde bei 50 Einträgen als raw_content
gespeichert; Stage 6 schrieb daraus Artikel über „Bot Detection Protocols“."""
import pytest

from pipeline import article_fetcher as af

RADWARE = ("We apologize for the inconvenience...\n...but your activity and behavior on this site "
           "made us think that you are a bot.\nNote: A number of things could be going on here.\n"
           "- If you are attempting to access this site using an anonymous Private/Proxy network, "
           "please disable that and try accessing site again.\n- Due to previously detected "
           "malicious behavior which originated from the network you're using, please request "
           "unblock to site.")
DIGITIMES = ("Access denied\nSorry, unusual traffic from your computer network.\nYour IP has been "
             "blocked temporarily.\nTo provide quality services to our members, DIGITIMES blocks "
             "IPs if large volume of traffic is detected. " * 2)


def test_known_walls_detected():
    assert af.looks_like_bot_wall(RADWARE)
    assert af.looks_like_bot_wall(DIGITIMES)


def test_long_article_about_captchas_is_kept():
    text = ("Wer beim Öffnen von Webseiten auf Captchas stößt, sollte vorsichtig sein: "
            "Angreifer bitten darum, zu bestätigen, dass man kein Roboter ist – „verify you are human“. "
            * 20)
    assert len(text) > af.BOT_WALL_MAX_CHARS
    assert not af.looks_like_bot_wall(text)


def test_plain_article_and_empty():
    assert not af.looks_like_bot_wall("Das Land Nordrhein-Westfalen unterstützt Gründer. " * 10)
    assert not af.looks_like_bot_wall(None)
    assert not af.looks_like_bot_wall("")


class _Resp:
    status_code = 200
    headers = {"content-type": "text/html"}

    def __init__(self, url, html):
        self.url = url
        self.text = html
        self.content = html.encode()


class _Client:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url):
        return self.resp

    def close(self):
        pass


def test_fetch_returns_bot_wall_and_stores_nothing(monkeypatch):
    monkeypatch.setattr(af, "_robots_ok", lambda url: True)
    monkeypatch.setattr(af, "tdmrep_rules", lambda host, client: {})
    monkeypatch.setattr(af, "_throttle", lambda host: None)
    monkeypatch.setattr(af.trafilatura, "extract", lambda *a, **k: RADWARE)
    url = "https://www.foerderdatenbank.de/FDB/Content/DE/Foerderprogramm/x.html"
    res = af.fetch_fulltext_result(url, client=_Client(_Resp(url, "<html>wall</html>")))
    assert res.text is None
    assert res.reason == "bot_wall"
