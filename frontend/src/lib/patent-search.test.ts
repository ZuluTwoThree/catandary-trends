import { describe, it, expect } from "vitest";
import { parsePatentQuery } from "./patent-search";

describe("parsePatentQuery — Publikationsnummern", () => {
  it("erkennt die gängigen Schreibweisen und normalisiert sie", () => {
    for (const q of ["US11734097B2", "US 11734097 B2", "us-11734097-b2", "US 11734097B2"]) {
      expect(parsePatentQuery(q).pubExact, q).toContain("US-11734097-B2");
    }
  });

  it("liefert ein Präfix, wenn der Kind-Code fehlt", () => {
    const p = parsePatentQuery("EP 3866123");
    expect(p.pubPrefix).toContain("EP-3866123-");
    expect(p.pubExact).toBeUndefined();
  });

  it("erkennt das EPO-Format mit Schrägstrich", () => {
    expect(parsePatentQuery("US 2023/120329 A1").pubExact).toContain("US-2023120329-A1");
  });

  it("findet US-Offenlegungen in beiden Schreibweisen (führende Null der Seriennummer)", () => {
    // amtlich US20230397640A1, im DOCDB-Korpus US-2023397640-A1
    const p = parsePatentQuery("US20230397640A1");
    expect(p.pubExact).toEqual(["US-20230397640-A1", "US-2023397640-A1"]);
    // und andersherum, wenn jemand die DOCDB-Form kopiert
    expect(parsePatentQuery("US2023397640A1").pubExact).toContain("US-20230397640-A1");
  });

  it("ignoriert unbekannte Länderkürzel (kein Fehlalarm auf Produktnamen)", () => {
    const p = parsePatentQuery("XY123456 battery");
    expect(p.pubExact).toBeUndefined();
    expect(p.pubPrefix).toBeUndefined();
    expect(p.text).toBe("XY123456 battery");
  });

  it("hält vierstellige Zahlen ohne Kind-Code für ein Jahr, nicht für eine Nummer", () => {
    const p = parsePatentQuery("US 2024");
    expect(p.pubPrefix).toBeUndefined();
    expect(p.yearFrom).toBe(2024);
  });
});

describe("parsePatentQuery — CPC", () => {
  it("erkennt Subclass und volle Gruppe", () => {
    expect(parsePatentQuery("G06N").cpc).toBe("G06N");
    const g = parsePatentQuery("G06N10/40");
    expect(g.cpc).toBe("G06N");
    expect(g.cpcGroup).toBe("G06N10/40");
    expect(g.chips[0].label).toBe("G06N (from G06N10/40)"); // filtert real auf Subclass
  });

  it("verträgt Leerzeichen und Kleinschreibung", () => {
    const p = parsePatentQuery("h01m 10/0525");
    expect(p.cpc).toBe("H01M");
    expect(p.cpcGroup).toBe("H01M10/0525");
  });
});

describe("parsePatentQuery — Jahre", () => {
  it("erkennt Einzeljahr und Bereich", () => {
    expect(parsePatentQuery("battery 2024").yearFrom).toBe(2024);
    const r = parsePatentQuery("solar 2019-2024");
    expect([r.yearFrom, r.yearTo]).toEqual([2019, 2024]);
  });

  it("ignoriert Zahlen außerhalb des Korpus-Zeitraums", () => {
    const p = parsePatentQuery("model 1873");
    expect(p.yearFrom).toBeUndefined();
    expect(p.text).toBe("model 1873");
  });

  it("dreht verkehrt herum eingegebene Bereiche um", () => {
    const p = parsePatentQuery("2024-2019");
    expect([p.yearFrom, p.yearTo]).toEqual([2019, 2024]);
  });
});

describe("parsePatentQuery — Kombination und Freitext", () => {
  it("trennt Thema, CPC und Jahr sauber", () => {
    const p = parsePatentQuery("solid state battery H01M 2022");
    expect(p.text).toBe("solid state battery");
    expect(p.cpc).toBe("H01M");
    expect(p.yearFrom).toBe(2022);
    expect(p.chips.map((c) => c.kind)).toEqual(["cpc", "year"]);
  });

  it("lässt reinen Freitext unangetastet", () => {
    const p = parsePatentQuery("perovskite tandem solar cell");
    expect(p.text).toBe("perovskite tandem solar cell");
    expect(p.chips).toHaveLength(0);
  });

  it("verkraftet leere Eingabe", () => {
    expect(parsePatentQuery("").text).toBe("");
    expect(parsePatentQuery("   ").chips).toHaveLength(0);
  });
});

describe("parsePatentQuery — Firmen-Operator", () => {
  it("erkennt company:, firma: und assignee:", () => {
    for (const op of ["company", "firma", "assignee"]) {
      expect(parsePatentQuery(`${op}:samsung`).company, op).toBe("samsung");
    }
  });

  it("hält mehrteilige Namen in Anführungszeichen zusammen", () => {
    const p = parsePatentQuery('company:"Toyota Motor" battery');
    expect(p.company).toBe("Toyota Motor");
    expect(p.text).toBe("battery");
  });

  it("kombiniert Firma mit Thema, Klasse und Jahr", () => {
    const p = parsePatentQuery("company:toyota solid state H01M 2023");
    expect(p.company).toBe("toyota");
    expect(p.cpc).toBe("H01M");
    expect(p.yearFrom).toBe(2023);
    expect(p.text).toBe("solid state");
  });

  it("verträgt ein Leerzeichen nach dem Doppelpunkt", () => {
    expect(parsePatentQuery("company: battery").company).toBe("battery");
  });

  it("greift nicht ohne Wert und nicht ohne Operator", () => {
    expect(parsePatentQuery("company:").company).toBeUndefined();
    expect(parsePatentQuery("battery").company).toBeUndefined();
  });
});
