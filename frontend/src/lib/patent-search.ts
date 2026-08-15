/** Smart-Query-Router für das Patent-Explorer-Suchfeld (#78, Stufe 1).
 *
 *  Nutzer tippen nicht nur Stichworte, sondern auch Publikationsnummern aus
 *  Artikeln ("US11734097B2"), CPC-Codes ("G06N10/40") und Jahreszahlen. Der
 *  Parser erkennt diese Muster VOR der Volltextsuche und übersetzt sie in
 *  echte Filter — sonst laufen sie als Suchwörter ins Leere.
 *
 *  Reine Funktion ohne DB-Zugriff, damit sie testbar bleibt. Was erkannt
 *  wurde, gibt `chips` zurück: die Seite zeigt es an, damit eine
 *  Fehlinterpretation sichtbar (und durch Umformulieren korrigierbar) ist.
 */

/** Ämter mit >= 100 Patenten im Korpus (gemessen 2026-08-12). Ohne diese
 *  Whitelist würde jedes "AB1234" als Publikationsnummer durchgehen. */
const AUTHORITIES = new Set([
  "CN", "US", "KR", "WO", "CA", "EP", "AU", "GB", "JP", "TW", "MX", "IL",
  "HU", "PL", "RU", "ZA", "NZ", "PT", "SG", "ES", "PH", "HK", "MY", "FR",
  "SK", "DE", "HR", "LT", "SI", "CZ", "GR", "FI", "IE", "SE", "UA", "SA",
  "SM", "NL", "AP", "BG", "DK", "BE", "NO", "ME", "EA", "CH", "SU", "OA",
  "AR", "LU", "CS", "IN", "RS", "MA", "TR", "MD", "ZW",
]);

const YEAR_MIN = 1990;
const YEAR_MAX = 2026;

export interface QueryChip {
  kind: "patent" | "cpc" | "year" | "company";
  label: string;
}

export interface ParsedPatentQuery {
  /** Restlicher Freitext für die Volltextsuche ("" wenn nichts übrig). */
  text: string;
  /** Exakte Publikationsnummern inkl. Kind-Code — mehrere, weil dieselbe
   *  Veröffentlichung je nach Quelle unterschiedlich geschrieben wird
   *  (siehe numberVariants). */
  pubExact?: string[];
  /** Präfixe ohne Kind-Code (US-11734097-) — treffen alle Kind-Codes. */
  pubPrefix?: string[];
  /** Anmelder-Filter aus `company:…` bzw. `firma:…`. */
  company?: string;
  /** CPC-Subclass (G06N). */
  cpc?: string;
  /** Volle CPC-Gruppe als Präfix (G06N10/40) — braucht Stufe 2. */
  cpcGroup?: string;
  yearFrom?: number;
  yearTo?: number;
  chips: QueryChip[];
}

// US 11734097 B2 | US-11734097-B2 | US11734097B2 | US 2023/120329 A1
// Der Schrägstrich im EPO-Format trennt Jahr und laufende Nummer INNERHALB
// der Nummer (nur "/" erlaubt, kein Leerzeichen — sonst würde "US 2024 2023"
// zu einer Fantasienummer verschmelzen).
const PUB_RE = /\b([A-Z]{2})[\s-]?(\d{4,12}(?:\/\d{4,8})?)[\s\-/]?([A-Z]\d?)?\b/gi;
// G06N | G06N10/40 | H01M 10/0525 | Y02E10/50 (Sektionen A–H und Y)
const CPC_RE = /\b([A-HY])(\d{2})([A-Z])[\s]?(\d{1,4}\/\d{1,6})?\b/gi;
const RANGE_RE = /\b(\d{4})\s*[-–—]\s*(\d{4})\b/g;
const YEAR_RE = /\b(\d{4})\b/g;

const inYearRange = (y: number) => y >= YEAR_MIN && y <= YEAR_MAX;

/** Schreibvarianten einer Publikationsnummer.
 *
 *  US-Offenlegungen werden amtlich als Jahr + 7-stellige Seriennummer
 *  geschrieben (US20230397640A1), das EPO-DOCDB-Format — unsere Quelle — lässt
 *  die führende Null der Seriennummer weg (US-2023397640-A1). Beide Formen
 *  stecken im Korpus (2,72 Mio. zehnstellig, 126k elfstellig, gemessen
 *  2026-08-12), und Nutzer kopieren mal die eine, mal die andere. Also beide
 *  abfragen statt den Treffer zu verlieren. */
function numberVariants(num: string): string[] {
  const out = [num];
  const year = parseInt(num.slice(0, 4), 10);
  if (!(year >= YEAR_MIN && year <= YEAR_MAX)) return out;
  if (num.length === 11 && num[4] === "0") out.push(num.slice(0, 4) + num.slice(5));
  if (num.length === 10) out.push(num.slice(0, 4) + "0" + num.slice(4));
  return out;
}

/** Erkanntes Teilstück aus dem Freitext schneiden (durch Leerzeichen
 *  ersetzen, damit nachfolgende Regexe keine Wortgrenzen verlieren). */
function cut(s: string, start: number, len: number): string {
  return s.slice(0, start) + " ".repeat(len) + s.slice(start + len);
}

export function parsePatentQuery(raw: string): ParsedPatentQuery {
  const out: ParsedPatentQuery = { text: "", chips: [] };
  let rest = (raw ?? "").trim();
  if (!rest) return out;

  // 0. Expliziter Anmelder-Operator: company:"Toyota Motor" | firma:samsung
  //    Zuerst, damit ein Firmenname in Anführungszeichen nicht von den
  //    Muster-Regexen zerpflückt wird.
  // Leerzeichen nach dem Doppelpunkt erlaubt ("company: samsung") — getippt
  // wird beides, und ein Operator ohne Wert soll einfach nicht greifen.
  // Mehrteilige Namen ohne Quotes: großgeschriebene Folgewörter gehören zum
  // Namen (company:Toyota Motor battery → "Toyota Motor" + Text "battery");
  // gleiche Heuristik wie research-search.ts.
  // KEIN i-Flag (würde die Titlecase-Klasse des Tails aushebeln) —
  // Case-Toleranz der Operatornamen explizit.
  const COMPANY_RE =
    /\b(?:[Cc]ompany|COMPANY|[Ff]irma|FIRMA|[Aa]ssignee|ASSIGNEE):\s*("([^"]+)"|(\S+(?:\s+[A-ZÀ-Þ][a-zà-þß'’-]+)*))/;
  const cm = rest.match(COMPANY_RE);
  if (cm) {
    const value = (cm[2] ?? cm[3] ?? "").trim();
    if (value) {
      out.company = value;
      out.chips.push({ kind: "company", label: value });
      rest = cut(rest, cm.index ?? 0, cm[0].length);
    }
  }

  // 1. Publikationsnummer — zuerst, sonst frisst die Jahres-Regex die Ziffern
  PUB_RE.lastIndex = 0;
  for (const m of [...rest.matchAll(PUB_RE)]) {
    const [full, auth, rawNum, kind] = m;
    if (!AUTHORITIES.has(auth.toUpperCase())) continue;
    const num = rawNum.replace(/\//g, "");
    // Vierstellige Zahl ohne Kind-Code ist eher ein Jahr als eine Nummer
    if (num.length <= 4 && !kind) continue;
    const variants = numberVariants(num).map((n) => `${auth.toUpperCase()}-${n}`);
    if (kind) {
      out.pubExact = variants.map((v) => `${v}-${kind.toUpperCase()}`);
      out.chips.push({ kind: "patent", label: out.pubExact[0] });
    } else {
      out.pubPrefix = variants.map((v) => `${v}-`);
      out.chips.push({ kind: "patent", label: `${variants[0]} (any kind code)` });
    }
    rest = cut(rest, m.index ?? 0, full.length);
    break; // eine Nummer pro Anfrage genügt
  }

  // 2. CPC-Code
  CPC_RE.lastIndex = 0;
  for (const m of [...rest.matchAll(CPC_RE)]) {
    const [full, sec, cls, sub, group] = m;
    const subclass = `${sec}${cls}${sub}`.toUpperCase();
    out.cpc = subclass;
    if (group) {
      // Die Gruppe wird erkannt und weitergereicht, gefiltert wird aber noch
      // auf Subclass-Ebene (Präfix-Index auf patent_cpc.cpc kommt mit Stufe 2)
      // — das Chip sagt deshalb, was WIRKLICH gefiltert wird.
      out.cpcGroup = `${subclass}${group.replace(/\s/g, "")}`;
      out.chips.push({ kind: "cpc", label: `${subclass} (from ${out.cpcGroup})` });
    } else {
      out.chips.push({ kind: "cpc", label: subclass });
    }
    rest = cut(rest, m.index ?? 0, full.length);
    break;
  }

  // 3. Jahresbereich vor Einzeljahr (sonst greift die Einzeljahr-Regex zuerst)
  RANGE_RE.lastIndex = 0;
  for (const m of [...rest.matchAll(RANGE_RE)]) {
    const a = parseInt(m[1], 10);
    const b = parseInt(m[2], 10);
    if (!inYearRange(a) || !inYearRange(b)) continue;
    // Verdrehte Eingabe ("2024-2019") tauschen statt verwerfen — gemeint ist
    // eindeutig die Spanne.
    const [from, to] = a <= b ? [a, b] : [b, a];
    out.yearFrom = from;
    out.yearTo = to;
    out.chips.push({ kind: "year", label: `${from}–${to}` });
    rest = cut(rest, m.index ?? 0, m[0].length);
    break;
  }
  if (out.yearFrom === undefined) {
    YEAR_RE.lastIndex = 0;
    for (const m of [...rest.matchAll(YEAR_RE)]) {
      const y = parseInt(m[1], 10);
      if (!inYearRange(y)) continue;
      out.yearFrom = y;
      out.yearTo = y;
      out.chips.push({ kind: "year", label: String(y) });
      rest = cut(rest, m.index ?? 0, m[0].length);
      break;
    }
  }

  out.text = rest.replace(/\s+/g, " ").trim();
  return out;
}
