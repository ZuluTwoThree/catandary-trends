/** Autorenlisten aus research_authors_flat für die Anzeige aufbereiten (#83).
 *
 *  OpenAlex' `author.display_name` ist nicht durchweg ein Personenname: bei
 *  schlecht geparsten Quellen steht dort die Affiliation ("Dept. of Animal
 *  Bioscience (Insti. of Agric. & Life Sci.), Gyeongsang National Univ.,
 *  Jinju 660-701, Korea" — real im Korpus, 2026-08-16). Solche Einträge als
 *  klickbaren Autor zu zeigen führt zu Suchen, die nichts finden; sie werden
 *  deshalb aus der Anzeige gefiltert (nicht als "+N more" mitgezählt).
 *  Rein textuelle Heuristik, bewusst konservativ.
 */

const ORG_WORDS =
  /\b(univ|university|universit[äa]t|dept|department|institut|institute|instituto|laborator|college|hospital|academy|faculty|school of|center for|centre for|ministry|gmbh|ltd|inc)\b/i;

/** Sieht der Eintrag nach Einrichtung statt Person aus? */
export function looksLikeAffiliation(name: string): boolean {
  if (name.length > 60) return true;          // Personennamen sind kürzer
  if (/\d{3,}/.test(name)) return true;       // Postleitzahlen, Gebäudenummern
  if (ORG_WORDS.test(name)) return true;
  if ((name.match(/,/g) ?? []).length >= 2) return true; // Adress-Kaskade
  return false;
}

/** Erste `limit` Autoren plus Zähler für den Rest. `authors` ist der
 *  "; "-getrennte String aus research_authors_flat (max. 30 Namen — "+N
 *  more" ist bei Großkollaborationen also eine Untergrenze). */
export function splitAuthors(
  authors: string | null | undefined, limit = 3,
): { shown: string[]; more: number } {
  if (!authors) return { shown: [], more: 0 };
  const all = authors
    .split(";")
    .map((a) => a.trim())
    .filter((a) => a.length > 1 && !looksLikeAffiliation(a));
  return { shown: all.slice(0, limit), more: Math.max(0, all.length - limit) };
}
