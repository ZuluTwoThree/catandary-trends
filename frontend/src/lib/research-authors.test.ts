import { describe, it, expect } from "vitest";
import { splitAuthors, looksLikeAffiliation } from "./research-authors";

describe("looksLikeAffiliation", () => {
  it("erkennt Affiliations-Strings, die OpenAlex als Autor liefert", () => {
    expect(looksLikeAffiliation(
      "Dept. of Animal Bioscience (Insti. of Agric. & Life Sci.), Gyeongsang National Univ., Jinju 660-701, Korea"
    )).toBe(true);
    expect(looksLikeAffiliation("Max Planck Institute for Polymer Research")).toBe(true);
    expect(looksLikeAffiliation("University of Cambridge")).toBe(true);
  });
  it("laesst echte Personennamen durch — auch mit Initialen und Partikeln", () => {
    expect(looksLikeAffiliation("Jennifer A. Doudna")).toBe(false);
    expect(looksLikeAffiliation("A.G. Mohamed")).toBe(false);
    expect(looksLikeAffiliation("Ludwig van Beethoven")).toBe(false);
    expect(looksLikeAffiliation("José Ramón Martínez-Sánchez")).toBe(false);
  });
});

describe("splitAuthors", () => {
  it("zeigt die ersten drei Namen und zaehlt den Rest", () => {
    const r = splitAuthors("Ada Lovelace; Alan Turing; Grace Hopper; Ken Thompson; Barbara Liskov");
    expect(r.shown).toEqual(["Ada Lovelace", "Alan Turing", "Grace Hopper"]);
    expect(r.more).toBe(2);
  });
  it("zaehlt gefilterte Affiliationen NICHT als weitere Autoren", () => {
    const r = splitAuthors("Jennifer A. Doudna; University of Cambridge; Emmanuelle Charpentier");
    expect(r.shown).toEqual(["Jennifer A. Doudna", "Emmanuelle Charpentier"]);
    expect(r.more).toBe(0);
  });
  it("vertraegt null, Leerstrings und Semikolon-Rauschen", () => {
    expect(splitAuthors(null)).toEqual({ shown: [], more: 0 });
    expect(splitAuthors("")).toEqual({ shown: [], more: 0 });
    expect(splitAuthors("; ; Alan Turing; ")).toEqual({ shown: ["Alan Turing"], more: 0 });
  });
  it("verwirft Ein-Zeichen-Fragmente (Parser-Rauschen, nie ein Name)", () => {
    expect(splitAuthors("A; Alan Turing")).toEqual({ shown: ["Alan Turing"], more: 0 });
  });
});
