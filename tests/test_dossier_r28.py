"""Runde 28 (2026-09-19, datacenter-virtualization v7): die Zahlenpruefung
strich Saetze wegen FORMATVARIANTEN ("2023-12-13" gegen "13 December 2023",
"29 September 2020" gegen "29.09.2020"), wegen BEZEICHNERN ("Regulation (EU)
2023/2854") und wegen Zahlen aus dem EIGENEN Korpus-Block (Anteile je 10k);
der Pruefnachweis nannte "23 von 27" als "Zahl nicht auf der Seite", weil er
das Gesamt minus die Zaehler des LETZTEN Durchgangs rechnete (real: 2).

Alles hier laeuft ohne DB, ohne Netz und ohne GPU."""
from pipeline import dossier_structure as ds
from pipeline import legal_text
from pipeline.dossier_check import check_result


class TestFormatVariants:
    def test_iso_date_against_a_written_month(self):
        page = "REGULATION (EU) 2023/2854 OF THE EUROPEAN PARLIAMENT of 13 December 2023"
        assert ds.unverified_tokens("| 2023-12-13 | regulation | Adopted the Data Act |", page) == []

    def test_written_date_against_a_dotted_date(self):
        assert ds.unverified_tokens("Published on 29 September 2020 by BSI",
                                    "Version 1.0 | Datum 29.09.2020 zum Schutz") == []
        assert ds.unverified_tokens("applies from 12 September 2025", "shall apply from 12.9.2025") == []
        assert ds.unverified_tokens("applies from 12 September 2025",
                                    "shall apply from September 12, 2025") == []

    def test_a_different_date_is_not_rescued(self):
        assert ds.unverified_tokens("Published on 29 September 2020", "Datum 30.09.2020") == ["29"]
        assert ds.unverified_tokens("| 2023-12-13 | adopted |", "of 13 November 2023") == ["12"]

    def test_a_date_component_never_grounds_a_stray_number(self):
        """batteries v1: die Monatskomponente "02" aus "2027-02-18" belegte
        die "2" aus ">2 kWh"."""
        assert ds.unverified_tokens("industrial batteries (>2 kWh) from February 18, 2027",
                                    "mandatory from 18.02.2027 for batteries above 3 kWh") == ["2"]

    def test_grouped_digits_and_zero_decimals(self):
        assert ds.unverified_tokens("The graph has 10,605 patents", "we count 10 605 patents") == []
        assert ds.unverified_tokens("The graph has 10,605 patents", "we count 10 605 patents") == []
        assert ds.unverified_tokens("a median cycle time of 6.0 years", "cycle time 6 years") == []
        assert ds.unverified_tokens("a median cycle time of 6 years", "cycle time 6.0 years") == []
        assert ds.unverified_tokens("a median cycle time of 6.0 years", "cycle time 7 years") == ["6.0"]

    def test_a_thousands_group_implies_no_bare_integer(self):
        """Iron-Air v3: "8+ hour storage" gegen "8,000 cycle warranties"."""
        assert ds.unverified_tokens("relevant only for 8+ hour storage", "publish 4,000 to 8,000 cycle warranties") == ["8"]

    def test_quarters_and_halves(self):
        assert ds.unverified_tokens("Adoption in Q2 2026 of the scheme", "adopted in the second quarter of 2026") == []
        assert ds.unverified_tokens("Adoption in 2026-Q2 of the scheme", "adopted in Q2/2026") == []
        assert ds.unverified_tokens("Adoption in H1 2027", "in the first half of 2027") == []
        # das Quartalszeichen selbst ("Q2") gilt in grounding.py als angehaengter
        # Bezeichner; geprueft wird das Jahr der Angabe
        assert ds.unverified_tokens("Adoption in Q2 2026 of the scheme", "adopted in the third quarter of 2027") == ["2026"]
        assert ds._periods_in("second quarter of 2026, Q3 2027, 2028-H1") == {(2026, "Q2"), (2027, "Q3"), (2028, "H1")}

    def test_the_grouped_variant_is_exact_not_substring(self):
        """"12 900" darf keine "12.9" belegen (Teilstring-Toleranz umgangen)."""
        assert ds.unverified_tokens("Mordor projects 12.9 billion", "the total is 12 900 units") == ["12.9"]


class TestDesignators:
    CATALOG = "Regulation - EU - 2023/2854 - EN - Data Act - EUR-Lex https://eur-lex.europa.eu/eli/reg/2023/2854/oj"

    def test_an_act_number_carried_by_the_catalog_is_a_name(self):
        assert ds.unverified_tokens("The EU Data Act (Regulation (EU) 2023/2854) applies",
                                    "The Data Act applies from 12 September 2025", catalog=self.CATALOG) == []

    def test_an_act_number_unknown_to_the_catalog_stays_unverified(self):
        """datacenter v3 nannte "Regulation 2024/1028" — die falsche Nummer."""
        out = ds.unverified_tokens("The EU Data Act (Regulation (EU) 2024/1028) applies",
                                   "The Data Act applies", catalog=self.CATALOG)
        assert set(out) == {"2024", "1028"}
        assert ds.unverified_tokens("Regulation (EC) 1924/2006 governs claims", "claims are regulated") != []

    def test_article_lists(self):
        assert ds.unverified_tokens("GDPR Article 28/32 and Articles 5 and 6 apply", "GDPR applies") == []
        assert ds.unverified_tokens("Art. 28, 32 GDPR apply", "GDPR applies") == []

    def test_version_numbers_after_a_name_but_not_currency_or_units(self):
        assert ds.unverified_tokens("PDM 1.0 reached stable release", "PDM stable release") == []
        assert ds.unverified_tokens("Proxmox Datacenter Manager 1.0 reached stable release", "release") == []
        assert ds.unverified_tokens("Mordor projects USD 12.9 billion", "no figure") == ["12.9"]
        assert ds.unverified_tokens("Arla spent EUR 0.5 million", "no figure") == ["0.5"]
        assert ds.unverified_tokens("Broadcom expects 1.5 GW of capacity", "no figure") == ["1.5"]


class TestMeasuredBlock:
    MEASURED = ("Corpus signals matching ALL of datacenter, virtualization since 2024-09-01: 31 — 26 in the "
                "last 12 months. Per tier and quarter: count, and share per 10,000 signals\n"
                "| market | 12 (3.62/10k) | 5 (1.27/10k) |\n| patent | 5 (4.15/10k) | 1 (0.15/10k) |\n"
                "improvement rate median 33.1 %/yr (n=10,605, 2006–2026), cycle time 6.0 years")

    def test_figures_from_the_corpus_block_are_grounded_when_the_sentence_speaks_of_the_measurement(self):
        s = "The market tier carries 12 signals in 2026-Q2 (3.62 per 10,000) and 5 in 2026-Q3 (1.27 per 10,000)."
        assert ds.unverified_tokens(s, "a page about hypervisors", measured=self.MEASURED) == []
        s2 = "The patent citation graph contains 10,605 patents with a median cycle time of 6.0 years."
        assert ds.unverified_tokens(s2, "a page about hypervisors", measured=self.MEASURED) == []

    def test_without_a_measurement_cue_the_block_grounds_nothing(self):
        """"the next 12 months" wird nicht dadurch belegt, dass die Zykluszeit 12.0 Jahre betraegt."""
        assert ds.unverified_tokens("the next 12 months present an opportunity", "nothing numeric",
                                    measured="cycle time 12.0 years, median 3.3 %/yr") == ["12"]
        assert ds.unverified_tokens("GLP-1 therapy causes up to 40% lean mass loss", "no figure",
                                    measured="share 40% of signals") == ["40%"]

    def test_verify_takes_the_measured_block(self):
        src = [{"id": "W1", "kind": "web", "url": "https://x.example/a", "title": "t",
                "text": "a page about hypervisors", "snippet": "", "date": ""}]
        rep = ("# D\n\n## Maturity and position in the cycle\n\nThe market tier carries 12 signals in "
               "2026-Q2 (3.62 per 10,000) [[W1]].\n")
        assert ds.verify_cited_figures(rep, src)["unverified"]
        assert ds.verify_cited_figures(rep, src, self.MEASURED)["unverified"] == []

    def test_sourceless_figures_read_the_corpus_block(self):
        rep = "# D\n\n## Maturity and position in the cycle\n\nFunding signals: 1 signal in 2025-Q3 (0.74 per 10,000).\n"
        assert ds.sourceless_figures(rep, [], "") != []
        assert ds.sourceless_figures(rep, [], "| funding | 1 (0.74/10k) |") == []


class TestNoWeakeningForAbsentFigures:
    def test_truly_absent_figures_still_fall(self):
        page = "The Data Act applies from 12 September 2025 and was adopted on 13 December 2023."
        assert ds.unverified_tokens("The web sweep admitted 66 sources", page) == ["66"]
        assert ds.unverified_tokens("the market is worth $200 billion", page) == ["$200"]
        assert ds.unverified_tokens("12–18 months to develop", page) == ["18"]   # "12" steht auf der Seite


FULL_ACT = ("REGULATION (EU) 2023/2854\n\nArticle 1\nSubject matter\nThis Regulation lays down harmonised "
            "rules on data access and use, cloud switching and interoperability for data processing services.\n\n"
            "Article 2\nDefinitions\nFor the purposes of this Regulation, 'data' means any digital representation "
            "of acts, facts or information; 'data processing service' means a digital service that enables "
            "ubiquitous and on-demand network access to a shared pool of configurable computing resources.\n\n"
            "Article 25\nContractual terms concerning switching\nThe rights of the customer and the obligations "
            "of the provider of data processing services in relation to switching between providers shall be "
            "set out in a written contract with a maximum notice period of two months.\n\n"
            "Article 50\nEntry into force and application\nThis Regulation shall enter into force on the twentieth "
            "day following that of its publication. It shall apply from 12 September 2025. Article 3(1) shall "
            "apply to connected products placed on the market after 12 September 2026.\n")


class TestLegalReslice:
    SRC = [{"id": "L1", "kind": "legal", "url": "https://eur-lex.europa.eu/eli/reg/2023/2854/oj/eng",
            "title": "Regulation - EU - 2023/2854", "snippet": "", "date": "",
            # gespeicherter Ausschnitt: Definitionen + Artikel 25 (die Lueckenbegriffe
            # trafen "switching"), Artikel 50 fehlt
            "text": "Article 2\nDefinitions\n'data processing service' means a digital service.\n\n"
                    "Article 25\nContractual terms concerning switching\nmaximum notice period of two months."}]
    REPORT = ("# D\n\n## Regulatory and IP status\n\nThe Data Act applies from 12 September 2025 and its "
              "switching rules apply to data processing services [[L1]].\n")

    def test_the_full_text_is_resliced_around_the_sentence(self):
        out = ds.verify_cited_figures(self.REPORT, self.SRC, legal_full=lambda url: FULL_ACT)
        assert out["unverified"] == []
        assert len(out["legal_rescued"]) == 1
        r = out["legal_rescued"][0]
        assert set(r["tokens"]) == {"12", "2025"} and any(a.startswith("Article 50") for a in r["articles"])

    def test_without_the_full_text_the_figure_stays_unverified(self):
        out = ds.verify_cited_figures(self.REPORT, self.SRC, legal_full=lambda url: None)
        assert out["unverified"] and set(out["unverified"][0]["tokens"]) == {"12", "2025"}
        assert out["legal_rescued"] == []

    def test_a_figure_absent_from_the_whole_act_is_not_rescued(self):
        rep = "# D\n\n## Regulatory and IP status\n\nThe Data Act applies from 12 September 2028 [[L1]].\n"
        out = ds.verify_cited_figures(rep, self.SRC, legal_full=lambda url: FULL_ACT)
        assert out["unverified"] and set(out["unverified"][0]["tokens"]) == {"2028"}

    def test_only_legal_hosts_are_resliced(self):
        src = [dict(self.SRC[0], kind="web", url="https://blog.example/data-act")]
        rep = self.REPORT.replace("[[L1]]", "[[L1]]")
        out = ds.verify_cited_figures(rep, src, legal_full=lambda url: FULL_ACT)
        assert out["unverified"] and out["legal_rescued"] == []

    def test_reslice_helpers(self):
        kept, labels = legal_text.reslice_for("https://eur-lex.europa.eu/x", ["apply", "September"],
                                              full_text=FULL_ACT)
        assert "12 September 2025" in kept and any(lab.startswith("Article 50") for lab in labels)
        assert legal_text.reslice_for("https://eur-lex.europa.eu/x", ["apply"], full_text="") == ("", [])
        assert legal_text.cached_full_text("https://blog.example/") is None


class TestDropAccounting:
    REPORT = ("# D\n\n## Decision summary\n\nA is true [[W1]]. B costs 12 units [[W1]]. C follows [[W1]].\n\n"
              "## Decision points and watch items\n\n- Watch D at 3.5% [[W1]].\n")

    def test_drop_unverified_counts_per_kind(self):
        counts: dict = {}
        out, n = ds.drop_unverified(self.REPORT, [
            {"sentence": "B costs 12 units [[W1]].", "tokens": ["12"], "kind": "figure", "url": "u"},
            {"sentence": "C follows [[W1]].", "tokens": ["x"], "kind": "subject", "url": "u"},
            {"sentence": "- Watch D at 3.5% [[W1]].", "tokens": ["3.5%"], "kind": "sourceless", "url": ""},
        ], "en", counts=counts)
        assert n >= 3
        assert counts["figure"] == 1 and counts["subject"] == 1 and counts["sourceless"] == 1
        assert "B costs" not in out and "C follows" not in out

    def test_the_check_names_every_drop_reason_from_the_cumulative_counts(self):
        r = {"report": "Fine.", "evidence": [], "sources": [], "cited": [], "stripped_citations": 0,
             "ledger": [], "question": "q",
             "structure": {"dropped_sentences": 27, "drops_by_kind": {
                 "figure": 2, "subject": 15, "contradicted": 1, "sourceless": 1, "measure": 1,
                 "marked_secondary": 4, "orphan": 3},
                 # die alten Zaehler des LETZTEN Durchgangs — ohne drops_by_kind
                 # ergaeben sie "23× enthielt die zitierte Web-Seite die Zahl nicht"
                 "off_topic_after": 2, "weakclaim_after": 2, "findings_after": []}}
        lines = [f for f in check_result(r)["findings"] if "gestrichen" in f]
        assert len(lines) == 1
        line = lines[0]
        assert line.startswith("27 Satz/Saetze gestrichen oder gekennzeichnet: ")
        assert "2× enthielt die zitierte Web-Seite die behauptete Zahl nicht" in line
        assert "15× zitierte die Seite ein anderes Thema" in line
        assert "4× ruhte eine Kernaussage nur auf Rang-2-Material" in line
        assert "3× blieb ein Anschluss-Absatz" in line
        assert "23×" not in line

    def test_old_runs_without_the_counts_keep_the_legacy_arithmetic(self):
        r = {"report": "Fine.", "evidence": [], "sources": [], "cited": [], "stripped_citations": 0,
             "ledger": [], "question": "q",
             "structure": {"dropped_sentences": 27, "off_topic_after": 2, "weakclaim_after": 2,
                           "findings_after": []}}
        line = next(f for f in check_result(r)["findings"] if "gestrichen" in f)
        assert "23× enthielt die zitierte Web-Seite" in line

    def test_the_check_reports_scope_exclusions_and_legal_rescues(self):
        r = {"report": "Fine.", "evidence": [], "sources": [], "cited": [], "stripped_citations": 0,
             "ledger": [], "question": "q",
             "structure": {"contradiction_scope_excluded": ["a", "b", "c"], "legal_rescued": 1,
                           "contradictions_after": [], "findings_after": []}}
        out = check_result(r)["findings"]
        assert any("Widerspruchs-Gate: 3 Kandidat(en) als Scope-Aussage" in f for f in out)
        assert any("Zahlenpruefung: 1× stand die Zahl nicht im gespeicherten Ausschnitt" in f for f in out)
        assert not any("noch offen" in f for f in out)
