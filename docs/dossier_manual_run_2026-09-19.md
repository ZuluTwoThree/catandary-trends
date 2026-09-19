# Handdurchgang: die Dossier-Frage „datacenter virtualization" selbst beantwortet

> **Intern.** Owner-Auftrag 2026-09-19: die Frage aus Auftrag 39–43 einmal von Hand
> (Claude, Web-Werkzeuge) beantworten und den Arbeitsweg protokollieren, um daraus
> eine Anleitung abzuleiten, was im Rechercheur funktioniert und was nicht.
> Aufwand: 17 Abrufe, ~25 Minuten. Alle Quellen Rang 0/1 außer wo vermerkt.

Frage: *Which virtualization stack should a small German IT service firm run for its
own company group and its regional partner companies after the VMware licensing
change under Broadcom, and which requirements from BSI IT-Grundschutz (SYS.1.5),
GDPR (Art. 28, 32) and the EU Data Act apply? No classified (VS-NfD) data.*

## 1. Antwort

**Worum es geht.** Ein Hypervisor betreibt mehrere virtuelle Server auf einem
physischen. VMware vSphere war dafür der Standard im Mittelstand; seit der
Übernahme durch Broadcom gibt es nur noch Abonnements je CPU-Kern mit
Mindestmengen, und vSphere 8 ist die letzte Version mit Dauerlizenz. Für eine
kleine Firma, die eigene Gruppe und Partner hostet, entscheidet die Wahl des
Stacks über Lizenzkosten, Betriebsaufwand und darüber, ob die Rechtsanforderungen
(BSI, DSGVO, Data Act) mit Bordmitteln erfüllbar sind.

**Entscheidung.**
1. **Proxmox VE (KVM/LXC, AGPLv3) als Standard-Stack**, mit Subscription
   „Basic" je Socket (370 €/Jahr) für den Enterprise-Repository-Zugang — die
   No-Subscription-Repos sind laut Proxmox „not recommended … on production
   servers". Zwei Sockets je Host, drei Hosts = ~2.200 €/Jahr; kein
   Kern-Minimum, kein Mengenzwang.
2. **Hyper-V nur, wenn Windows Server Datacenter ohnehin lizenziert ist:**
   Datacenter (alle Kerne, min. 16 je Host) erlaubt unbegrenzt Windows-VMs;
   Standard nur 2 VMs je Lizenzierung. Für gemischte Linux/Windows-Landschaften
   und Partner-Mandanten ist das teurer als Proxmox, sobald mehr als eine
   Handvoll VMs je Host laufen.
3. **VMware nur bei Bestandsverträgen bis zum 11.10.2027** (Ende General
   Support vSphere 8; danach Technical Guidance ohne Patches). Neu-Abo nur je
   Kern mit 16-Kern-Minimum je CPU (Broadcom-KB 339588, SPD 11/2025); die in der
   Presse genannte 72-Kern-Mindestbestellung ist in den Primärquellen nicht
   belegt (Rang 2).

**Anforderungen, die gelten.**
- **BSI SYS.1.5 Virtualisierung (Edition 2023):** gilt „auf jeden
  Virtualisierungsserver", zusätzlich SYS.1.1 Allgemeiner Server und der
  OS-Baustein (Linux → SYS.1.3). Basis-Anforderungen (Pflicht): A2 sicherer
  Einsatz virtueller IT-Systeme, A3 sichere Konfiguration, A4 sicheres Netz für
  die virtuelle Infrastruktur, A5 Schutz der Administrationsschnittstellen,
  A6 Protokollierung, A7 Zeitsynchronisation. Standard: A8–A17, A19 (Planung,
  Netzplanung, Verwaltungsprozesse, Administration über getrenntes Netz,
  Rechte-/Rollenkonzept, Hardware, Konfigurationsstandards, Kapselung,
  Überwachung, Audits). Erhöht (nur bei Bedarf): A20–A28 (HA, Härtung,
  Snapshots aus, PKI, zertifizierte Software, Verschlüsselung). Ausdrücklich
  NICHT im Baustein: Container, Storage-Virtualisierung, Terminalserver.
  VS-NfD-Zulassung (BSI-CI-RP-0019) ist irrelevant, weil keine Verschlusssachen.
- **DSGVO:** Hostet die Firma Partnerdaten, ist sie Auftragsverarbeiter →
  Art. 28 Abs. 3 Vertrag mit den Punkten (a)–(h) (Weisung, Vertraulichkeit,
  Art.-32-Maßnahmen, Sub-Auftragsverarbeiter nur mit Genehmigung, Unterstützung,
  Löschung/Rückgabe, Nachweis/Audit); Art. 28 Abs. 4 volle Haftung für
  Sub-Auftragsverarbeiter. Art. 32 Abs. 1 (a)–(d): Verschlüsselung/
  Pseudonymisierung, Vertraulichkeit-Integrität-Verfügbarkeit-Belastbarkeit,
  Wiederherstellbarkeit, regelmäßige Wirksamkeitsprüfung — technisch: VM-
  Verschlüsselung, getrennte Mandantennetze, Backup mit Restore-Test,
  Admin-2FA, Protokollierung (deckt sich mit SYS.1.5 A5/A6/A28).
- **EU Data Act (VO 2023/2854), anwendbar seit 12.09.2025:** Ein Hosting für
  Partnerfirmen ist ein „data processing service" (Art. 2 Nr. 8: „digital
  service … enables ubiquitous and on-demand network access to a shared pool of
  configurable, scalable and elastic computing resources"). Dann gilt Kapitel VI:
  Art. 23 Wechsel ermöglichen, Art. 25 Vertragsklauseln (Kündigungs-/
  Übergangsfristen, Datenexport), Art. 29 Wechselentgelte reduziert bis
  11.01.2027, **ab 12.01.2027 verboten**, Art. 30 Funktionsäquivalenz/
  offene Schnittstellen. **Ausnahme Art. 31:** Dienste, deren Hauptfunktionen
  „custom-built to accommodate the specific needs of an individual customer"
  sind und nicht im Katalog angeboten werden, sind von Art. 23(d), 29, 30(1)/(3)
  befreit — für Individual-Hosting je Partner realistisch, aber der Kunde muss
  vor Vertragsschluss informiert werden. Keine KMU-Ausnahme in Kapitel VI.
  Konzerninternes Hosting ohne Kunden im Sinne der VO fällt nicht darunter.

**Termine.** 12.01.2027 Wechselentgelte enden (Art. 29) · 11.10.2027 Ende
General Support vSphere 8 (Rang 2, Broadcom-Lifecycle-Matrix nicht crawlbar) ·
12.09.2027 Kapitel IV auf Altverträge (Art. 50).

**Offen.** Vertragsstand VMware (Change-of-Control-Klausel, Laufzeit), Windows-
Lizenzbestand, VM-Zahl und Kernzahl je Host (bestimmt Proxmox- vs.
Datacenter-Kosten), Backup-Stack (Veeam unterstützt Proxmox seit 2024 — nicht
geprüft), ob Partner als Kunden im Sinne des Data Act auftreten.

## 2. Der Arbeitsweg, Schritt für Schritt

| # | Schritt | Ergebnis | Lehre |
|---|---|---|---|
| 1 | Frage in Pflichtpunkte zerlegen (Stack-Alternativen, Broadcom-Fakten, SYS.1.5-Inhalt, Art. 28/32, Data-Act-Anwendbarkeit) | 5 Punkte | Der Rechercheur macht das seit Stufe 1 (`must_answer`) — richtig. |
| 2 | Je Punkt die **autoritative Quellklasse** benennen, bevor gesucht wird: Broadcom-KB/SPD, Proxmox-Doku, Microsoft-Lizenz-Guidance, BSI-PDF, EUR-Lex | 5 Klassen | Das ist der Kern von Stufe 2 (`source_classes`). Ohne diesen Schritt landen Suchen bei Blogs. |
| 3 | Suche „vSphere 8 end of general support" ohne Domainfilter | 9 Treffer, **alle Blogs/Berater** | Offene Websuche liefert bei Lifecycle-Fragen nur Sekundäres. |
| 4 | Dieselbe Suche mit `allowed_domains broadcom.com` | KB-Artikel, aber nur zu vSphere 7 | Die vSphere-8-Daten stehen in der interaktiven Lifecycle-Matrix — **nicht crawlbar**. Manche Primärfakten sind nur als Konsens der Sekundärquellen greifbar; das muss das Dossier so kennzeichnen, nicht verschweigen. |
| 5 | Proxmox-Preisseite abrufen | Tiers korrekt, aber der Zusammenfasser schrieb „use without subscription only non-production" | **Marketingseite ≠ Lizenz.** Gegencheck FAQ: AGPLv3. Gegencheck Package_Repositories: No-Subscription-Repo „not recommended … production". Zwei Seiten nötig für eine belastbare Aussage. |
| 6 | EUR-Lex Volltext des Data Act abrufen | Abgeschnitten vor Kapitel VI | **Lange Rechtstexte artikelweise abrufen.** Ausweg: artikelweise Spiegel (eu-data-act.com) mit wörtlichem Text — Rang 2 als Host, aber Wortlaut verifizierbar; ideal wäre EUR-Lex je Artikel. |
| 7 | Art. 2, 23, 29, 31, 50 einzeln | Wörtliche Definitionen, Fristen, die Custom-built-Ausnahme | Die **Ausnahme (Art. 31)** ist die entscheidende Information für eine kleine Firma — sie taucht in keiner der fünf Dossierversionen auf, weil niemand den Artikel gelesen hat. |
| 8 | DSGVO Art. 28/32 (gdpr-info.eu) | Wortlaut (a)–(h), (a)–(d) | Reicht; die technische Übersetzung (2FA, Backup-Test) ist Analystenarbeit, keine Quelle. |
| 9 | BSI SYS.1.5 PDF über den Web-Abruf | Binär, unlesbar | Der Repo-Fetcher liest es seit 18.09. (pypdf); hier per pypdf lokal extrahiert: Abgrenzung, A1–A28 mit Stufen (B/S/H). |
| 10 | Microsoft-Lizenz-Guidance | Datacenter = unbegrenzte VMs, Standard = 2, Minimum 16 Kerne | Primär (microsoft.com/licensing). |
| 11 | Broadcom-KB zu Kernminimum | 16 Kerne je CPU belegt; „72-Kern-Minimum" nicht in Primärquellen | Was die Presse behauptet und die Primärquelle nicht hergibt, bleibt als Rang 2 markiert — genau die Regel des Dossiers. |

**Was funktioniert hat:** Zerlegung in Pflichtpunkte; Quellklasse vor Suche;
Domainfilter auf die Klasse; artikelweises Lesen von Rechtstexten; Gegencheck
einer Zusammenfassung an einer zweiten Seite desselben Hauses; Kennzeichnung
statt Auslassung, wenn die Primärquelle nicht erreichbar ist.

**Was nicht funktioniert hat:** offene Websuche für Lifecycle-Daten (nur Blogs);
Volltext-Abruf langer Verordnungen; ein einzelner Zusammenfasser-Aufruf auf einer
Marketingseite (verdrehte „non-production"); interaktive Herstellerportale.

## 3. Was daraus für den Rechercheur folgt

1. **Quellklasse vor Suche** (Stufe 2) ist der größte Hebel — im Handdurchgang
   waren 12 von 17 Abrufen Rang 0/1, weil die Klasse zuerst feststand. Die
   Dossierläufe lagen bei 29–62 %.
2. **Rechtstexte artikelweise:** der Web-Agent braucht für EUR-Lex/Gesetze eine
   Regel „Artikel-URL statt Volltext" (EUR-Lex bietet `#art_23`-Anker; sonst
   artikelweise Spiegel als Rang 2 mit Wortlaut). Sonst bleibt Art. 31 unentdeckt.
3. **Zwei Seiten je Hersteller-Aussage:** Preisseite + Doku/FAQ; eine Aussage,
   die nur auf der Preis- oder Produktseite steht, gilt als Marketing.
4. **Nicht-crawlbare Primärquellen** (Lifecycle-Matrizen, Portale) als solche im
   Dossier benennen: „Primärquelle interaktiv, Datum aus n Sekundärquellen
   übereinstimmend" — ehrlicher als Rang-2-Vermerk ohne Erklärung.
5. **Die Entscheidung ist Analystenarbeit auf belegten Fakten**, nicht selbst ein
   Fakt: „Proxmox mit Basic-Subscription, Hyper-V nur bei vorhandener
   Datacenter-Lizenz, VMware nur bis 10/2027" folgt aus fünf belegten Zahlen
   und zwei Rechtsdefinitionen. Der Advisor darf genau das tun; das Dossier
   liefert die fünf Zahlen — und muss sie liefern (Pflichtpunkte).

## 4. Einschätzung: ist das Ziel technisch erreichbar?

**Ja für Evidenz- und Regulatorikfragen, mit dem 27B — unter drei Bedingungen,
die alle im Plan stehen:** (a) Quellklasse vor Suche und artikelweises Lesen
(Stufe 2 + eine Web-Agent-Regel), (b) Entscheidung im Advisor auf Pflichtpunkten
aus dem Dossier (Stufe 1 hat die Weiche), (c) Prüfen statt Streichen mit
Aussagenprüfung (Stufe 4, gebaut). Der Handdurchgang zeigt: das nötige Material
ist mit 17 Abrufen erreichbar und passt in ein 1.800-Wörter-Dossier; nichts daran
verlangt ein größeres Modell, aber alles verlangt die richtige Reihenfolge.

**Nein für Urteilsfragen ohne Kundenprofil** („which stack should *the firm*
run" ohne Lizenzbestand, VM-Zahl, Vertragsstand): die Antwort hängt an Daten,
die kein Korpus und keine Websuche kennt. Das ist keine Modellgrenze, sondern
eine Auftragsgrenze — Intake (Stufe 1) muss diese Angaben abfragen oder das
Dossier muss sie als Bedingungen ausweisen (was v3/v4 andeuteten und der Leser
als „Nicht-Antwort" wertete). **Der Leser-Maßstab „beantwortet die Frage" ist
für ein empfehlungsfreies Dossier falsch gewählt** — er muss auf die
Pflichtpunkte des Briefs zeigen, nicht auf die Frage. Das ist eine Änderung von
einer Zeile im Leser-Prompt und gehört in Stufe 3.

**Was das 27B nicht kann, zeigt der Handdurchgang auch:** Schritt 5 (die
Zusammenfassung der Preisseite war falsch) — ein kleiner Zusammenfasser
verdreht Bedingungen; die Aussagenprüfung (Stufe 4) fängt genau das, wenn die
zweite Seite im Katalog ist. Deshalb Regel 3 oben.
