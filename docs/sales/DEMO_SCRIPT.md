# Demo-Script — Trend-Radar (15–20 Minuten)

**Ziel jeder Demo: Trial im Gespräch aktivieren.** Nicht „Folien zeigen und auf Rückmeldung
warten" — am Ende des Gesprächs sind Branchen + Watchlist des Interessenten erfasst und der
Trial-Start zugesagt.

## Vorbereitung (5 Min vor dem Call)

1. Website des Interessenten: Welche Branchen? Welche Mandate/Kunden? 2–3 Watchlist-Begriffe raten.
2. Demo-Kunde im System auf diese Vermutung umkonfigurieren:
   `python scripts/radar_admin.py set <demo-id> --verticals TECH,FOOD --keywords "..."`
   `python -m pipeline.briefing_generator --customer <demo-id>`
3. Portal-Link + frisches Briefing im Browser-Tab bereit.

## Ablauf

**1. Eröffnung (2 Min) — sie reden, nicht Sie.**
„Bevor ich etwas zeige: Wie läuft Trend-/Markt-Monitoring bei Ihnen heute?
Wer macht das, wie oft, mit welchen Quellen?"
→ Notieren. Die Antwort liefert die Schmerzpunkte, auf die jede spätere Aussage einzahlt.

**2. Das Briefing (5 Min) — das Produkt ist die Demo.**
Briefing öffnen (auf ihre Branchen konfiguriert):
- „So sieht Ihr Montagmorgen aus." — Watchlist-Treffer zuerst zeigen: „Diese Begriffe habe
  ich von Ihrer Website geraten — was wären Ihre echten?" → **die Antwort ist die Trial-Konfiguration.**
- Ein Signal anklicken: Relevanz-Score, PESTEL, Quellenlink. „Jedes Signal führt zur
  Originalquelle — Sie können alles verifizieren und in Mandatsarbeit zitieren."

**3. Das Portal (3 Min).**
- Branding-Header zeigen: „Im Pro-Tarif steht hier Ihr Logo — das hier könnten Sie morgen
  Ihren Mandanten schicken."
- Briefing-Archiv: „Nach drei Monaten haben Sie hier eine durchsuchbare Trend-Historie."

**4. Preis (2 Min) — selbstbewusst, ohne Umwege.**
„Vier Tarife: 99 für eine Branche, 249 für drei Branchen mit täglichen Alerts,
490 mit allen Branchen und White-Label, 890 wenn Sie eigene Mandanten-Radare
weitergeben wollen. Monatlich kündbar. Zum Vergleich: ein WGSN-Seat kostet
über 10.000 im Jahr."
Dann schweigen. Einwände kommen lassen (→ POSITIONIERUNG.md).
*Hinweis: Im Gespräch nie mit Basic anfangen — Beratungen brauchen Pro (White-Label).
Basic ist der Auffangtarif, wenn das Budget-Nein kommt.*

**5. Abschluss (3 Min) — Trial aktivieren, nicht anbieten.**
„Ich schlage vor: Ich richte Ihnen das Radar jetzt mit genau diesen Branchen und Ihrer
Watchlist ein. Sie bekommen morgen das erste Briefing, zwei Wochen kostenlos, ohne Karte.
Welche E-Mail-Adresse nehmen wir?"
→ Branchen, Keywords, Empfänger notieren. Nach dem Call sofort:
`python scripts/radar_admin.py trial --name ... --email ... --verticals ... --keywords ...`
`python -m pipeline.briefing_generator --customer <id> --send`

## Nach der Demo

- Gleicher Tag: Onboarding-Mail mit Portal-Link.
- Trial-Betreuung nach OUTREACH.md (Tag 7 Frage, Tag 10 Anruf, Tag 13 Konversionsmail).
