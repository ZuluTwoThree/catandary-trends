"""PDF-Volltext im Fetcher (2026-09-18): bis dahin lief jedes PDF durch
trafilatura und kam als "too_short" zurueck — die BSI-Grundschutz-Bausteine
(SYS.1.5 Virtualisierung) waren fuer den Rechercheur unlesbar."""
import io

import pytest

from pipeline import article_fetcher as af


def _pdf_bytes(text: str, pages: int = 1) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               NameObject, NumberObject)
    w = PdfWriter()
    for _ in range(pages):
        page = w.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 200 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = w._add_object(stream)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


class _Resp:
    def __init__(self, url, content, ctype):
        self.status_code = 200
        self.url = url
        self.content = content
        self.text = content.decode("latin-1", "replace")
        self.headers = {"content-type": ctype}


class _Client:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url):
        return self._resp

    def close(self):
        pass


@pytest.fixture
def quiet_fetcher(monkeypatch):
    monkeypatch.setattr(af, "_robots_ok", lambda url: True)
    monkeypatch.setattr(af, "tdmrep_rules", lambda host, client: {})
    monkeypatch.setattr(af, "_throttle", lambda host: None)


class TestPdfText:
    def test_extracts_text_and_caps_pages(self):
        data = _pdf_bytes("SYS.1.5 Virtualisierung Baustein", pages=3)
        assert "SYS.1.5 Virtualisierung Baustein" in af.pdf_text(data)
        assert af.pdf_text(data, max_pages=1).count("Virtualisierung") == 1

    def test_garbage_is_empty_not_an_error(self):
        assert af.pdf_text(b"%PDF-1.4 not really a pdf") == ""


class TestFetchDetectsPdf:
    URL = "https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/x/SYS_1_5.pdf?__blob=publicationFile&v=3"

    def test_pdf_by_content_type_is_read(self, quiet_fetcher, monkeypatch):
        body = ("Der Baustein SYS.1.5 Virtualisierung beschreibt Anforderungen an "
                "Virtualisierungsserver und virtuelle IT-Systeme. ") * 8
        resp = _Resp(self.URL, _pdf_bytes(body), "application/pdf")
        monkeypatch.setattr(af, "MIN_TEXT_CHARS", 100)
        res = af.fetch_fulltext_result(self.URL, client=_Client(resp))
        assert res.reason is None and res.text and "SYS.1.5" in res.text

    def test_pdf_by_magic_bytes_without_content_type(self, quiet_fetcher, monkeypatch):
        resp = _Resp("https://example.org/doc", _pdf_bytes("Hello world " * 20),
                     "application/octet-stream")
        monkeypatch.setattr(af, "MIN_TEXT_CHARS", 50)
        res = af.fetch_fulltext_result("https://example.org/doc", client=_Client(resp))
        assert res.text and "Hello world" in res.text

    def test_tdm_header_still_wins_on_pdf(self, quiet_fetcher):
        resp = _Resp(self.URL, _pdf_bytes("x" * 200), "application/pdf")
        resp.headers["tdm-reservation"] = "1"
        res = af.fetch_fulltext_result(self.URL, client=_Client(resp))
        assert res.text is None and res.reason.startswith("tdm:")

    def test_html_path_unchanged(self, quiet_fetcher, monkeypatch):
        html = "<html><body><article>" + "<p>Lorem ipsum dolor sit amet consectetur.</p>" * 30 + "</article></body></html>"
        resp = _Resp("https://example.org/a", html.encode(), "text/html; charset=utf-8")
        res = af.fetch_fulltext_result("https://example.org/a", client=_Client(resp))
        assert res.text and "Lorem ipsum" in res.text
