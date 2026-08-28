"""Regression tests for #79 (5.9M patent_cpc rows with subclass NULL).

Root cause: EPO's BDDS DOCDB exchange XML bundles multiple national
classification schemes under the same <patent-classification> tag. For
JP-origin documents that includes real CPC (scheme="CPCI") *and* Japan's own
"FI" and "FTERM" (F-term) schemes. FI's classification-symbol embeds a stray
leading digit (historically the IPC edition, e.g. "4F21S43/237" instead of
"F21S43/237") and FTERM's ("3E068/AA40") isn't CPC-shaped at all. The old
ingest read every classification-symbol regardless of scheme, so both landed
in `patent_cpc` looking like malformed CPC codes.

Two independent fixes, both covered here:
  1. scripts/ingest_patents.py::parse_docdb_document — only extracts
     scheme="CPCI" going forward, so FI/FTERM never reach patent_cpc again.
  2. pipeline/db.py::cpc_subclass — repairs the ~1.49M pre-existing rows
     whose FI-derived code happens to look CPC-shaped once the leading digit
     is stripped, while still returning None for genuine F-term codes.
"""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# --- pipeline.db.cpc_subclass ---------------------------------------------------

def test_cpc_subclass_normal_codes():
    from pipeline.db import cpc_subclass

    assert cpc_subclass("F21S43/237") == "F21S"
    assert cpc_subclass("G06N10/40") == "G06N"
    assert cpc_subclass("A61K9/00") == "A61K"


def test_cpc_subclass_strips_stray_leading_digit():
    """The #79 bug pattern: a JP 'FI' code stored as if it were CPC."""
    from pipeline.db import cpc_subclass

    assert cpc_subclass("4F21S43/237") == "F21S"
    assert cpc_subclass("5G06N10/40") == "G06N"
    assert cpc_subclass("2A61K9/00") == "A61K"
    assert cpc_subclass("3A61K9/00") == "A61K"


def test_cpc_subclass_fterm_stays_none():
    """F-term codes ('3E068/AA40') are digit + theme-code, never CPC-shaped —
    must NOT be coerced into a fake subclass by the stray-digit fix."""
    from pipeline.db import cpc_subclass

    assert cpc_subclass("3E068/AA40") is None
    assert cpc_subclass("2C005/CA04") is None
    assert cpc_subclass("4B42D15/10") is not None  # sanity: this IS CPC-shaped


def test_cpc_subclass_handles_spaces():
    from pipeline.db import cpc_subclass

    assert cpc_subclass("F21S 43/237") == "F21S"
    assert cpc_subclass("4F21S43 /237") == "F21S"
    assert cpc_subclass("C07C 319/24        ") == "C07C"


def test_cpc_subclass_edge_cases():
    from pipeline.db import cpc_subclass

    assert cpc_subclass("") is None
    assert cpc_subclass(None) is None
    assert cpc_subclass("garbage") is None
    assert cpc_subclass("12345") is None
    assert cpc_subclass("99F21S43/237") is None  # two stray digits — not the observed pattern


# --- scripts.ingest_patents.parse_docdb_document ---------------------------------

_EXCH = "{http://www.epo.org/exchange}"

# Minimal DOCDB exchange-document snippet modeled on real EPO BDDS backfile
# XML (verified against /mnt/data-hdd/bdds_backfile, JP delivery batch): one
# real CPC classification (scheme="CPCI") plus one JP "FI" entry with the
# stray leading digit and one JP "FTERM" entry, all under the same
# <exch:patent-classifications> the way the raw feed actually nests them.
_DOCDB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<exch:exchange-documents xmlns:exch="http://www.epo.org/exchange">
  <exch:exchange-document country="JP" doc-number="1234567" kind="A1" date-publ="20240515">
    <exch:bibliographic-data>
      <exch:publication-reference data-format="docdb">
        <document-id>
          <country>JP</country>
          <doc-number>1234567</doc-number>
          <kind>A1</kind>
          <date>20240515</date>
        </document-id>
      </exch:publication-reference>
      <exch:invention-title lang="en">Fermented plant protein composition</exch:invention-title>
      <exch:patent-classifications>
        <patent-classification sequence="1">
          <classification-scheme office="EP" scheme="CPCI"/>
          <classification-symbol>A61K   9/00        </classification-symbol>
          <classification-value>I</classification-value>
        </patent-classification>
        <patent-classification sequence="2">
          <classification-scheme office="JP" scheme="FI"/>
          <classification-symbol>4F21S43  /237      </classification-symbol>
        </patent-classification>
        <patent-classification sequence="3">
          <classification-scheme office="JP" scheme="FTERM"/>
          <classification-symbol>3E068/AA40</classification-symbol>
        </patent-classification>
      </exch:patent-classifications>
    </exch:bibliographic-data>
    <exch:abstract lang="en"><exch:p>A test abstract about fermentation.</exch:p></exch:abstract>
  </exch:exchange-document>
</exch:exchange-documents>"""


def _parse_first_doc(xml_text: str):
    from scripts.ingest_patents import parse_docdb_document

    root = ET.fromstring(xml_text)
    doc = root.find(f"{_EXCH}exchange-document")
    return parse_docdb_document(doc, require_en=True, require_vertical=True)


def test_parse_docdb_document_keeps_only_cpci_scheme():
    rec = _parse_first_doc(_DOCDB_XML)
    assert rec is not None
    assert rec["pub_number"] == "JP-1234567-A1"
    # only the real CPC entry survives — FI and FTERM are dropped entirely
    assert rec["cpc"] == ["A61K9/00"]
    assert rec["cpc_struct"] == [("A61K9/00", True)]
    assert rec["vertical"] == "HEALTH"


def test_parse_docdb_document_no_cpci_yields_empty_cpc():
    """A document with only FI/FTERM classifications (no CPCI block at all,
    as seen for some older JP grants in the real backfile) must not leak
    those into cpc/cpc_struct — and, with require_vertical, is dropped."""
    xml = _DOCDB_XML.replace(
        '<classification-scheme office="EP" scheme="CPCI"/>\n'
        '          <classification-symbol>A61K   9/00        </classification-symbol>\n'
        '          <classification-value>I</classification-value>',
        '<classification-scheme office="JP" scheme="FI"/>\n'
        '          <classification-symbol>4A61K9   /00       </classification-symbol>')
    root = ET.fromstring(xml)
    doc = root.find(f"{_EXCH}exchange-document")
    from scripts.ingest_patents import parse_docdb_document

    rec = parse_docdb_document(doc, require_en=True, require_vertical=False)
    assert rec is not None
    assert rec["cpc"] == []
    assert rec["cpc_struct"] == []
    assert rec["vertical"] == "CROSS"  # no CPC → out-of-vertical fallback


def test_parse_docdb_document_missing_scheme_element_is_skipped():
    """Defensive: a <patent-classification> without a classification-scheme
    child at all must not crash and must not be treated as CPC."""
    xml = _DOCDB_XML.replace(
        '<patent-classification sequence="2">\n'
        '          <classification-scheme office="JP" scheme="FI"/>\n'
        '          <classification-symbol>4F21S43  /237      </classification-symbol>\n'
        '        </patent-classification>',
        '<patent-classification sequence="2">\n'
        '          <classification-symbol>4F21S43  /237      </classification-symbol>\n'
        '        </patent-classification>')
    rec = _parse_first_doc(xml)
    assert rec is not None
    assert rec["cpc"] == ["A61K9/00"]
