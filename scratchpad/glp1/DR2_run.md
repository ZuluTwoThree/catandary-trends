# DR-Lauf 2 mit Denken, 2026-09-07 (`glp1-dr2` v1, `dossiers.id=27`)

Owner-Freigabe: „nimm die Learnings des DR-Dossier-Laufs und mache einen
weiteren Lauf, bei dem du die Kritikpunkte der Jury adressierst. Du darfst auch
Reasoning in der Modellkarte variieren."

## 1. Was in diesem Lauf anders war

| | DR-Lauf 1 | **DR-Lauf 2** |
|---|---|---|
| Regeln | R9 | R10-1 (datierte Aussage ohne Beleg), R10-2 (Kurzfassung kein Stumpf), R10-3 (Tabelle bleibt heil), R10-4 (Förder-Sweep) |
| Denken | aus | **an** (`--reasoning on`, `reasoning_effort=medium`, Denk-Budget 3.000 Token) |
| Sampling Prosa | temp 0.7 / top_p 0.80 / top_k 20 / presence 1.5 | **temp 1.0 / top_p 0.95 / top_k 20 / presence 0** (Modellkarte, denkender Satz) |
| Notizen | Reihenfolge nach Rang, Kappe 30 | Reihenfolge nach Ertrag (gelesene Seiten → Abstracts → Patente), Kappe 40, **kündige Termine zuerst** |
| Dauer | 1.638 s | 2.638 s |

Modellkarte (huggingface.co/Qwen/Qwen3.8-27B): Denken ist der Default,
gesteuert über `reasoning_effort` (low/medium/xhigh); je Modus ein eigener
Sampling-Satz. Am laufenden Server verifiziert: Prosa-Aufrufe füllen
`reasoning_content`, die schema-gebundenen bleiben mit `enable_thinking=false`
undenkend.

## 2. Zwei Fehler, die erst dieser Lauf gezeigt hat

1. **Der erste Versuch starb am Client-Zeitlimit.** Der Berichtsaufruf trägt
   ~100k Token Prompt; mit Denkspur überschritt er die 600 s aus
   `LLAMACPP_TIMEOUT`, httpx brach ab, und 25 Minuten Recherche waren weg.
   Behoben: im Denkmodus hebt der Lauf die Grenze selbst auf 2.400 s
   (`DOSSIER_DR_TIMEOUT`), nicht global.
2. **Die abgeschnittene Denkspur landete im Berichtstext.** Ist das Denk-Budget
   aufgebraucht, schließt llama.cpp die Denkmarke selbst — und das Modell
   überlegt im Antwortfeld weiter. Das Dokument begann mit **51 Zeilen
   Selbstgespräch** („I genuinely cannot find a 5th. I'll go with 4 and note
   it."). Behoben: `strip_preamble()` schneidet alles vor der ersten
   Pflichtüberschrift weg. Das ausgelieferte Dokument ist mit genau dieser
   Funktion neu abgeleitet — reine Textumformung, kein Modellaufruf.

## 3. Zahlen

| Lauf | sec | Fließtext | datierte Aussagen | davon primärbelegt | Angaben/100 W. | zitiert | davon Rang 0/1 | gelesen | Notizen |
|---|---|---|---|---|---|---|---|---|---|
| B9 v2 (id 25) | 1.427 | 2.418 | 34 | 3 | 0,25 | 25 | 6 | 61 | — |
| DR 1 (id 26) | 1.638 | 2.981 | 33 | 14 | 0,94 | 32 | 12 | 72 | 21 |
| **DR 2 (id 27)** | 2.638 | **1.757** | 38 | **34** | **4,15** | 30 | **28** | **75** | 29 |
| Vergleichstext `C_sonnet` | — | 1.968 | 29 | 5 | 0,81 | — | — | — | — |

Der Förder-Sweep lieferte 14 Katalogquellen; die Ebene „Förderung" ist damit
erstmals im Text belegt.

## 4. Bewertung (jury_17, blind, `G = C_sonnet`, `H = DR 2`)

| Kriterium | Deep Research | **DR 2** |
|---|---|---|
| Belegbarkeit | 6 | 6 |
| Spezifität | **8** | 5 |
| Handlungsrelevanz | **7** | 6 |
| Abdeckung | **8** | 5 |
| Zeitliche Einordnung | **7** | 3 |
| Ehrlichkeit über Grenzen | 6 | **8** |
| Struktur | 6 | **7** |
| **Durchschnitt** | **6,9** | 5,7 |

**Sieger weiterhin Deep Research**, aber der Abstand sinkt von 1,86 auf 1,2,
und zwei Kriterien kippen zu uns (Ehrlichkeit 8:6, Struktur 7:6). Der
Gutachter über unser Dokument: „drei Viertel Primärquellen gegen ein Drittel",
„das einzige Dokument mit einer echten Optionsstruktur", „die einzigen Zahlen
des gesamten Vergleichs, die aus keiner Websuche zu bekommen sind".

## 5. Der teuerste Befund: die Regel drängt die tragende Wahrheit heraus

Wörtlich: „H verwirft mit ,unsupported by primary evidence' genau die Aussage,
an der die Zwölfmonatsplanung hängt (EU-Generika nicht vor 2031) — obwohl die
niederländische SPC bis 19.03.2031 und das Haager Urteil vom 05.08.2026 in
Minuten primär belegbar gewesen wären. Ein Entscheidungspapier, dessen
Regelwerk eine wahre und tragende Tatsache aus dem Text drängt, hat den
Regelapparat über den Zweck gestellt."

Dazu drei weitere Sachbefunde: der erste Satz stellt den Zulassungsstatus von
orforglipron falsch dar (Studienpublikation als Zulassung gelesen; die
FDA-Zulassung vom 01.04.2026 fehlt ganz), zweimal wird ein Verfahrens- oder
Seitenpflegedatum zum Ereignisdatum, und **der Kalender enthält keinen
einzigen GLP-1-Termin** — er besteht aus Horizon-Europe-Programmjahren, die
der Förder-Sweep beigesteuert hat.

## 6. Was das über die eigene Messgröße sagt

Die Faktenquote stieg von 0,25 über 0,94 auf **4,15** — und die Jury senkte
gleichzeitig Spezifität (6→5) und Abdeckung (5→5, gegen 8/9 beim Gegner). Der
Zähler misst *datierte, primärbelegte Angaben je 100 Wörter*; er unterscheidet
nicht, **worüber** die Angabe geht. Ein Dokument voller EFSA-Verfahrensdaten
und Horizon-Europe-Programmjahre erreicht ihn — und verfehlt trotzdem, wonach
gefragt war (Wirkstoffe, Studien, Deals, Erstattung). Die Quote ist ein guter
Wächter gegen Prosa, aber ein schlechter Kompass für Relevanz.

Belege: `jury_17.md` (Zuordnung `blind17_key.txt`), Dokument `DR2_final.md`,
Prüfanhang `DR2_annex.md`, Lauf `DR2_run.log`.
