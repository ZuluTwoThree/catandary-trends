import { describe, it, expect } from "vitest";
import { parseResearchQuery } from "./research-search";

describe("parseResearchQuery — DOI", () => {
  it("erkennt nackte DOIs und doi.org-URLs, normalisiert auf Kleinschreibung", () => {
    expect(parseResearchQuery("10.1038/s41586-021-03819-2").doi)
      .toBe("10.1038/s41586-021-03819-2");
    expect(parseResearchQuery("https://doi.org/10.1074/JBC.M113.461533").doi)
      .toBe("10.1074/jbc.m113.461533");
  });

  it("schneidet Kopier-Artefakte am Ende ab", () => {
    expect(parseResearchQuery("siehe 10.1038/nature12373.").doi)
      .toBe("10.1038/nature12373");
  });

  it("lässt den Resttext für die Suche übrig", () => {
    const p = parseResearchQuery("perovskite 10.1038/nature12373");
    expect(p.doi).toBe("10.1038/nature12373");
    expect(p.text).toBe("perovskite");
  });
});

describe("parseResearchQuery — arXiv", () => {
  it("erkennt IDs mit und ohne Präfix, mit Version", () => {
    expect(parseResearchQuery("arXiv:2504.10470").arxiv).toBe("2504.10470");
    expect(parseResearchQuery("2504.10470v2").arxiv).toBe("2504.10470v2");
  });

  it("hält Jahreszahlen mit Dezimalstellen nicht für arXiv-IDs", () => {
    // 2024.1234: 'Monat' 24 existiert nicht → keine arXiv-ID
    const p = parseResearchQuery("growth 2024.1234");
    expect(p.arxiv).toBeUndefined();
  });
});

describe("parseResearchQuery — Jahre", () => {
  it("Einzeljahr und Bereich, verdreht wird getauscht", () => {
    expect(parseResearchQuery("battery 2024").yearFrom).toBe(2024);
    const r = parseResearchQuery("solar 2019-2024");
    expect([r.yearFrom, r.yearTo]).toEqual([2019, 2024]);
    const v = parseResearchQuery("2024-2019");
    expect([v.yearFrom, v.yearTo]).toEqual([2019, 2024]);
  });

  it("ignoriert Jahre außerhalb des Korpusfensters", () => {
    const p = parseResearchQuery("laser 1960");
    expect(p.yearFrom).toBeUndefined();
    expect(p.text).toBe("laser 1960");
  });
});

describe("parseResearchQuery — Kombination", () => {
  it("trennt Thema und Jahr sauber, Chips in Reihenfolge", () => {
    const p = parseResearchQuery("processed cheese 2020-2024");
    expect(p.text).toBe("processed cheese");
    expect(p.chips.map((c) => c.kind)).toEqual(["year"]);
  });

  it("Freitext bleibt unangetastet, leere Eingabe crasht nicht", () => {
    expect(parseResearchQuery("quantum error correction").text)
      .toBe("quantum error correction");
    expect(parseResearchQuery("").chips).toHaveLength(0);
  });
});

describe("parseResearchQuery — Operatoren", () => {
  it("erkennt author/institution/journal mit Anführungszeichen", () => {
    const p = parseResearchQuery('author:"Sandip Basak" institution:"Max Planck" battery');
    expect(p.author).toBe("Sandip Basak");
    expect(p.institution).toBe("Max Planck");
    expect(p.text).toBe("battery");
  });

  it("journal:-Kurzform ohne Anführungszeichen", () => {
    const p = parseResearchQuery("journal:Nature perovskite");
    expect(p.journal).toBe("Nature");
    expect(p.text).toBe("perovskite");
  });

  it("kombiniert Operator mit Jahr", () => {
    const p = parseResearchQuery("institution:ETH 2024");
    expect(p.institution).toBe("ETH");
    expect(p.yearFrom).toBe(2024);
    expect(p.chips.map((c) => c.kind)).toEqual(["institution", "year"]);
  });
});
