# Review: Die 2.119 unveröffentlichten Drafts — Qualität & Produkt-Mehrwert

Stand 2026-07-14. Auftrag: Qualität der Drafts prüfen und ihren Mehrwert fürs Produkt bewerten.

## Kurzfassung

**Empfehlung: nicht veröffentlichen — weder gebündelt noch selektiv.** Die Drafts zerfallen in
zwei Gruppen mit völlig verschiedenen Problemen, und keine davon ist „gute Artikel, die nur auf
Freigabe warten".

Der wichtigste Nebenbefund: **Volltext verhindert Fabrikation nicht.** Das Modell erfindet
Spezifika auch dann, wenn ihm der ganze Artikel vorliegt.

## Was `confidence` wirklich misst

`trends.confidence` kommt aus `relevance.confidence` (llm_processor:724) — der Sicherheit des
**Relevanz-Filters**, *nicht* der Artikel-Qualität. Die Auto-Publish-Schwelle (≥0.85) fragt also:
„Ist das sicher ein relevantes Trendsignal?" — nicht „Ist der Text gut?". Das erklärt die Struktur:

| Gruppe | n | Warum Draft | Fabrikationsrate |
|---|---|---|---|
| **A** conf ≥0.85 | 633 (30 %) | Relevant, aber vom **Grounding-Gate gehalten** | **85,6 %** |
| **B** 0.70–0.85 | 702 | Relevanz unsicher | 32,2 % |
| **C** 0.50–0.70 | 529 | Relevanz unsicher | 32,5 % |
| **D** <0.50 | 364 | Relevanz unsicher | 32,4 % |

⌀ Textlänge aller Gruppen: ~670–707 Zeichen (≈120 Wörter — **unter** dem 150–250-Wörter-Ziel).

## Gruppe A (633): Erfindungen, kein Mehrwert

Nicht „ein paar unbelegte Zahlen" — **ganze Sachverhalte sind frei erfunden.** Belege (alle drei
Quellen hatten **Volltext**):

- **The Conversation** → *„California's Department of Housing and Development issued a rule
  requiring all new residential projects with 50 or more units to incorporate wildlife corridors
  by 2025 … applies to cities with over 200,000 residents, including Los Angeles and San Diego.
  Violations carry fines up to $50,000."* — eine komplette Regulierung inkl. Bußgeldern, erfunden.
- **Phys.org** → *„analyzed 23 amphibian species across 12 regions"* — Studienzahlen erfunden.
- **Phys.org** → erfundene Jahreszahlen (2015/2023) und Fallzahlen (1.200) zu US-Strafzumessung.

**Mehrwert: null, real negativ.** Veröffentlichung wäre ein Glaubwürdigkeits-GAU für ein Produkt,
dessen USP „evidenzbasiert mit klickbaren Primärquellen" ist. Das Grounding-Gate ist kein
Nice-to-have, sondern hält die Produktversprechen zusammen.

## Gruppe B/C/D (1.595): Qualität ok, aber marginale Signale

Die Fabrikationsrate (~32 %) ist **identisch mit der der publizierten Artikel** — diese Drafts sind
qualitativ *nicht schlechter* als das, was live ist. Die geflaggten Tokens sind hier meist
Paraphrase-Nahtreffer (z. B. „10 to 20 minutes"), keine Erfindungen. Beispiel (conf 0.65, HEALTH,
idw): eine saubere DKFZ-Meldung zu Krafttraining/WHO-Empfehlungen — lesbar, faktisch, brauchbar.

**Sie hängen nicht an der Qualität, sondern an der Relevanz-Unsicherheit.** Mehrwert: sie würden
Volumen bringen und die Relevanz des Free-Layers verwässern. Der Free-Layer ist Lead-Magnet — sein
Job ist Qualität, nicht Masse.

## Der Befund, der über die Drafts hinausgeht

**Volltext löst das Fabrikationsproblem nicht.** Alle drei A-Beispiele hatten den vollen Artikel und
erfanden trotzdem. Gemessen im Testlauf: 35,1 % (Volltext) vs. 31,1 % (Excerpt) — kein Gewinn.
Die Ursache ist **Modell-/Prompt-Verhalten**, nicht Input-Knappheit. Meine Gate-#2-Hypothese zielte
auf die falsche Ursache. (Der zweite Testlauf mit angehobenen Caps 1000→4000 misst nach, ob mehr
Kontext wenigstens etwas bringt — die A-Beispiele lassen wenig erwarten.)

## Empfehlungen

1. **Nicht bulk-publishen.** Gruppe A ist gefährlich, B/C/D verwässert.
2. **Gruppe A nicht blind regenerieren** — mehr Input ist nicht die Kur. Erst am Prompt ansetzen:
   harte Regel „keine Zahl/kein Datum/kein Eigenname, der nicht wörtlich in der Quelle steht",
   dann an einer Stichprobe messen. Erst wenn die Rate fällt, lohnt Regeneration.
3. **Gruppe B/C/D ist eine Relevanz-, keine Qualitätsfrage.** Mehr Volumen ginge über eine
   niedrigere Auto-Publish-Schwelle (0.85→0.75) — aber das publiziert bewusst marginale Signale.
   Meine Empfehlung: **nicht** senken.
4. **Der Draft-Stapel ist ein Symptom, kein Lager.** Bei ~30 % Gate-Hold wächst er strukturell
   (meine zwei Testläufe: +1.051). Entweder die Generierung fixen (Punkt 2) oder Drafts als
   Dead-Letter-Queue behandeln und älter als X Tage verwerfen.
5. **Textlänge prüfen:** ~120 Wörter liegen unter dem 150–250-Ziel — der Wortzahl-Guard greift
   offenbar nicht zuverlässig. Eigener Check wert.
