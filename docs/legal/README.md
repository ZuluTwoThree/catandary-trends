# Rechtstexte — ENTWÜRFE (Epic W2.7, issue #17)

> ⚠️ **DRAFT — KEINE RECHTSBERATUNG.** Diese Texte sind strukturierte Entwürfe,
> die der Code-Agent aus den technischen Fakten des Projekts erstellt hat. Sie
> **müssen vor dem Livegang** von dir (und idealerweise einem Anwalt / einer
> Anwältin für IT-/Datenschutzrecht) geprüft und vervollständigt werden.
> Platzhalter `[…]` sind von dir auszufüllen. Nichts davon ist bisher als Seite
> veröffentlicht.

## Warum jetzt nötig

Ab dem Moment, in dem die Alpha **Accounts anlegt** (E-Mail-Gate) und **Zahlungen**
(Stripe) anbietet, greifen in Deutschland Impressumspflicht (DDG/§5), DSGVO
(Datenschutzerklärung mit Auftragsverarbeitern), Fernabsatz-/Widerrufsrecht und
AGB. Diese Entwürfe decken die vier Pflichtdokumente ab.

## Festgestellte Verarbeiter / Datenflüsse (Grundlage der Datenschutzerklärung)

| Verarbeiter | Zweck | Daten |
|---|---|---|
| **Hetzner** (Hosting) | Server/DB (Hetzner VPS) | alle serverseitigen Daten, IP-Logs |
| **Resend** (E-Mail) | Magic-Link-Login + Newsletter | E-Mail-Adresse |
| **Stripe** (Zahlungen) | Abo-Abwicklung, Stripe Tax | Name, E-Mail, Zahlungsdaten (bei Stripe, nicht bei uns) |
| **eigene LLM-Pipeline** (lokal) | Content-Generierung | **keine Nutzerdaten** — nur öffentliche Trendquellen |

**Kein** Drittanbieter-Analytics/Tracking mit personenbezogenem Bezug geplant
(Owner-Vorgabe: cookielos/aggregiert). Das vereinfacht die Cookie-Pflichten
erheblich (kein Consent-Banner nötig, wenn wirklich nur technisch notwendige
Cookies + aggregierte, nicht-personenbezogene Zählung).

## Dateien

- `impressum.draft.md`
- `datenschutz.draft.md`
- `agb.draft.md`
- `widerruf.draft.md`

## Offene Platzhalter, die nur du füllen kannst

- Firmierung / Rechtsform / Anschrift / Vertretungsberechtigte(r)
- USt-IdNr. (falls vorhanden), Handelsregister (falls eingetragen)
- Kontakt-E-Mail für Datenschutzanfragen
- Ob eine **Kleinunternehmer**-Regelung (§19 UStG) gilt (beeinflusst USt-Ausweis)
- Auftragsverarbeitungsverträge (AVV) mit Resend + Stripe abschließen (beide
  bieten Standard-AVV im Dashboard an) — Abschlussdatum in die Datenschutzerklärung
- Finale Preis-/Leistungsbeschreibung + Kündigungsfristen der Abos (für AGB)
