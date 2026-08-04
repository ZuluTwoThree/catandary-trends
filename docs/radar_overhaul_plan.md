# Overhaul: Das Radar als interaktives Bewertungswerkzeug

**Owner-Auftrag 2026-08-05.** Kompletter Neubau statt weiterer Zusatzansicht.
Grundlage: J. Blechschmidt, *Quick Guide Trendmanagement*, Kap. 8 — insbesondere
die Portfoliodarstellung (Abb. 8.2), die Expertengewichtung (S. 102) und die
Verortung der Reife auf Gartner Hype Cycle bzw. Rogers' Diffusionskurve (S. 100).

---

## 1. Was sich grundlegend ändert

Bisher war das Radar ein **Ausgabegerät**: die Pipeline rechnet, der Nutzer
liest. Der Neubau macht daraus ein **Bewertungswerkzeug**: der Nutzer arbeitet,
die Maschine schlägt vor und rechnet hoch.

| | bisher | neu |
|---|---|---|
| Relevanz | gar nicht vorhanden | **aus bewerteten Einzelsignalen von unten aufgebaut** |
| Reife | H1/H2/H3 je Dimension und Jurisdiktion | **eine Achse**, aus Kurvenposition + Evidenz |
| Jurisdiktionen | 3–6 Spalten je Dimension | **entfallen ersatzlos** |
| Einheit der Arbeit | ein Feld anschauen | **ein Signal bewerten** |
| Bewerter | keiner | mehrere, nach Fachnähe gewichtet |

### 1.1 Warum Relevanz auf Signalebene und nicht auf Feldebene

Ein Feld direkt zu bewerten („Wie relevant ist Ihnen Machine Learning?") ist eine
Frage, die niemand ehrlich beantworten kann — zu abstrakt, zu groß, zu sehr von
der Tagesform abhängig. **Ein einzelnes Signal zu bewerten ist dagegen leicht:**
„Ist diese Meldung für uns wichtig?" beantwortet ein Fachmann in zwei Sekunden.

Drei Dinge folgen daraus, und sie sind der eigentliche Grund für den Umbau:

1. **Die Feldrelevanz wird abgeleitet, nicht behauptet.** Sie ist das gewichtete
   Mittel der Signalbewertungen — und damit belegt, so wie die Reife belegt ist.
2. **Man kann sie prüfen.** Zu jeder Feldrelevanz gehören die Signale, die sie
   erzeugt haben. Ein Streit darüber wird konkret statt grundsätzlich.
3. **Sie wird lernbar.** Wer 200 Signale bewertet hat, hat ein Trainingsset
   erzeugt. Ein Modell auf den Embeddings kann dann die übrigen 1,13 Mio.
   vorschlagen — das ist die spätere Automatisierung, und sie ist ohne den
   Signalpfad nicht möglich.

---

## 2. Die Reifeachse: Kurvenposition statt Zellenraster

Blechschmidt (S. 100): *„Die Trendreife kann sich aus der Position des Trends im
Gartner Hype Cycle oder dem Diffusionsmodell ergeben."*

Beides sind **Kurvenmodelle über die Zeit** — und Zeitreihen haben wir: jedes
Cluster trägt 440 Monatswerte seines Anteils am Signalaufkommen
(`foresight_clusters.monthly_series`), dazu `momentum` und `sov_delta_pp`.

### 2.1 Was aus der Kurve ablesbar ist

| Kurvenform | Hype Cycle | Rogers | Blechschmidt-Stufe |
|---|---|---|---|
| Anstieg aus dem Nichts, steil, jung | Innovation Trigger | Innovators | **entstehend** |
| Hoch, stark schwankend, jüngst gefallen | Peak / Trough | Early Adopters | **volatil** |
| Erholung nach Einbruch, Marktsignale kommen | Slope of Enlightenment | Early Majority | **reifend** |
| Lange stabil auf hohem Niveau, Handel belegt | Plateau of Productivity | Late Majority | **etabliert** |

Der Klassifikator arbeitet auf der **geglätteten** Reihe (12-Monats-Median) und
erst ab einem Mindestnenner — die frühen Jahre tragen Anteile wie 0,58 bei
zweistelligen Signalzahlen und sind reines Rauschen.

Gemessene Kennzahlen je Feld:
- **Alter**: erster Monat über Rauschschwelle
- **Anstieg**: Steigung der letzten 24 Monate
- **Gipfelabstand**: heutiger Anteil relativ zum historischen Maximum
- **Beständigkeit**: Streuung der letzten 36 Monate
- **Wiederanstieg**: Steigung seit dem Tief nach dem Gipfel

### 2.2 Die Kurve allein reicht nicht

Ein Anteil am Signalaufkommen misst **Aufmerksamkeit**, nicht Marktreife. Ein
Feld kann auf dem Plateau der Berichterstattung sitzen und trotzdem nichts
verkaufen. Deshalb bleibt der Evidenzteil aus `pipeline/radar_maturity.py`
erhalten — Marktverfügbarkeit, Nachfrage, Verstetigung — und die beiden werden
zusammengeführt:

```
Kurvenposition (Aufmerksamkeitsverlauf)  ─┐
                                          ├─→  Reifestufe + Begründung
Evidenzpunkte (Markt, Nachfrage, Dauer)  ─┘
```

Widersprechen sie sich, gewinnt **nicht** die Mehrheit, sondern die Zelle sagt
es: *„Die Berichterstattung ist auf dem Plateau, ein Markt ist aber nicht
belegt."* Das ist selbst eine Aussage — meist die interessanteste.

### 2.3 Der Fallback ist „volatil"

Owner-Vorgabe, und sie ist methodisch richtig: Wo die Reife nicht bestimmbar
ist, steht das Feld auf **volatil** — Handlungsband *Verstehen*. Das ist die
einzige Stufe, deren Empfehlung lautet „genauer hinsehen", und damit die
ehrliche Antwort auf Unwissen. „Entstehend" wäre eine Behauptung über Jugend,
„etabliert" eine über Reife; beides wüssten wir nicht.

Die Zelle trägt das sichtbar: **geschätzt** statt **belegt**.

### 2.4 Semantisches Sensemaking als dritte Quelle

Für Felder, bei denen Kurve und Evidenz auseinanderlaufen oder beide schweigen,
ein **Recherche-Agent** nach dem Muster der Fach-Scouts aus der Kalibrierung
(docs/radar_redesign_proposal.md §8): Er bekommt Label, Belegsignale und
Kurvenform und beantwortet eine einzige Frage — *wo steht dieses Feld auf der
Diffusionskurve, und woran macht man das fest?* — mit Quellenangabe.

Kein Dauerbetrieb: **auf Knopfdruck je Feld**, Ergebnis wird gespeichert und
mit Datum gezeigt. Kosten und Owner-Regel („kein Cron") bleiben gewahrt.

---

## 3. Expertengewichtung

Blechschmidt (S. 102): *„Personen mit wenigen Kontaktpunkten zu den jeweiligen
Themen werden zudem sehr subjektive Meinungen abgeben und so das Gewicht gut
begründeter Bewertungen der (wenigen) Spezialisten verwässern."*

### 3.1 Wie die Fachnähe entsteht

Nicht allein durch Selbstauskunft — die ist notorisch großzügig. Drei Anteile:

| Anteil | Woher | Warum |
|---|---|---|
| **Selbstauskunft** je Vertikale (0–3) | der Nutzer gibt sie an | notwendige Basis, aber nicht hinreichend |
| **Erfahrung** | Zahl bewerteter Signale in diesem Feld, gedeckelt | wer 200 Signale gesichtet hat, kennt das Feld |
| **Beständigkeit** | Übereinstimmung mit den eigenen früheren Bewertungen bei ähnlichen Signalen (Kosinus im Embedding-Raum) | wer wahllos klickt, gewichtet sich selbst herunter |

Gewicht = Selbstauskunft × Erfahrungsfaktor × Beständigkeitsfaktor, gedeckelt
bei 4, Minimum 0,25. **Nie null** — eine Stimme ganz zu streichen wäre eine
Vertrauensfrage, keine Methodik.

### 3.2 Was das Werkzeug daraus zeigt

Nicht nur den Mittelwert. Blechschmidts Warnung richtet sich gegen das
Verschwinden der Spezialistenmeinung, also muss sie **sichtbar** bleiben:

- gewichtetes Mittel als Position im Portfolio
- **Streuung** als Fehlerbalken am Punkt
- bei Uneinigkeit ein Hinweis: *„3 Bewerter, Spanne 1–4 — die Fachnahen sagen 4"*
- Korrektur durch das Trendteam möglich, **mit Notiz und Protokoll**

---

## 4. Der Arbeitsablauf

```
①  Scope wählen        Vertikale · Mega-Trend · Cluster
        ↓
②  Signale bewerten    ein Signal, eine Frage, 0–4, Tastatur
        ↓              (die Maschine schlägt vor, sobald sie gelernt hat)
③  Portfolio füllt sich  Reife (Maschine) × Relevanz (Ihre Bewertungen)
        ↓
④  Feld aufklappen     Begründung beider Achsen, Ihre Signale, Streuung
        ↓
⑤  Handeln             Empfehlung des Felds, Export, Trendporträt
```

Schritt ② ist das Herz. Es muss sich anfühlen wie Karten sortieren, nicht wie
ein Formular: ein Signal groß, Titel und Quelle, fünf Tasten, weiter. Wer in
zehn Minuten sechzig Signale sichtet, hat ein Feld bewertet.

---

## 5. Gestaltung: „Der Messtisch"

**Leitbild:** kein Dashboard, sondern eine **Arbeitsfläche**. Zeichentisch trifft
Oszilloskop. Das Werkzeug soll so wirken, als läge es auf einem Tisch und man
sortiere darauf — nicht, als schaue man auf einen Bericht.

### 5.1 Das Merkmal, das im Kopf bleibt

**Die Reifeachse trägt die Diffusionskurve als Rückgrat.** Statt vier flacher
Zeilen läuft hinter den Stufenbeschriftungen eine gezeichnete S-Kurve (Rogers)
mit dem Hype-Cycle-Buckel — und jedes Feld sitzt sichtbar an seiner Stelle
darauf. Blechschmidts Rasterlogik bleibt exakt erhalten (4 × 3 Felder mit
Handlungsempfehlung), aber die y-Achse erklärt sich selbst: man sieht, warum
„volatil" zwischen Anstieg und Tal liegt.

Das ist zugleich ehrlich: Die Kurve ist die Herleitung, nicht Dekoration.

### 5.2 Typografie und Farbe

Innerhalb der Produktfamilie bleiben, aber dem Werkzeug eine eigene Stimme
geben:

- **Auszeichnung:** eine schmale, technische Groteske mit Charakter für
  Stufen- und Achsenbeschriftung — Kandidat **Space Mono** ist verbraucht;
  Vorschlag **IBM Plex Mono Condensed** (bereits im Haus) für Chrome, dazu
  **Newsreader** oder **Fraunces** als Anzeigeschrift für Feldnamen. Selbst
  gehostet, kein CDN (CSP).
- **Fläche:** Ink `#0a0c0a` bleibt. Neu: ein **Papierton** `#f4f1e8` für die
  Bewertungskarten — sie sind physisch, sie liegen auf dem dunklen Tisch. Der
  Bruch zwischen Tisch und Karte ist die stärkste visuelle Geste des Werkzeugs.
- **Akzent:** Chartreuse `#d4ff3a` bleibt für gesetzte Werte. **Neu:
  Zinnober `#e8503a` für maschinelle Vorschläge** — damit Vorschlag und Setzung
  nie verwechselt werden. Diese Trennung ist keine Kosmetik: sie ist die
  Owner-Vorgabe „leer mit sichtbarem Vorschlag daneben" in Farbe übersetzt.

### 5.3 Raum und Bewegung

- Bewertungsansicht: **eine Karte, mittig, groß**, Rest zurückgenommen. Die
  bewerteten Karten stapeln sich sichtbar links — Fortschritt als Objekt, nicht
  als Balken.
- Portfolio: das Raster füllt sich **animiert**, sobald eine Bewertung die
  Feldposition ändert. Ein Feld, das die Spalte wechselt, wandert sichtbar.
- Kein Ladebalken für die Bewertung: die nächste Karte liegt schon bereit.
- Tastatur zuerst: `0`–`4` bewerten, `→` überspringen, `↩` aufklappen.

### 5.4 Was wegfällt

Jurisdiktionsschalter · H1/H2/H3-Vokabular in der Hauptansicht · der
Horizontbogen als Startbild · die Signalwolke als eigener Reiter (sie wird zum
Aufklapp-Detail eines Felds) · TRL.

---

## 6. Datenmodell

```sql
-- Wer bewertet
CREATE TABLE rater (
    id SERIAL PRIMARY KEY,
    handle TEXT UNIQUE NOT NULL,          -- bis Auth: 'owner'
    display_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Selbstauskunft je Vertikale
CREATE TABLE rater_expertise (
    rater_id INTEGER REFERENCES rater(id) ON DELETE CASCADE,
    vertical TEXT NOT NULL,
    self_declared INTEGER CHECK (self_declared BETWEEN 0 AND 3),
    PRIMARY KEY (rater_id, vertical)
);

-- Die Arbeitseinheit: ein Signal, eine Bewertung
CREATE TABLE signal_relevance (
    id SERIAL PRIMARY KEY,
    rater_id INTEGER REFERENCES rater(id) ON DELETE CASCADE,
    trend_id INTEGER NOT NULL,
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    points INTEGER CHECK (points BETWEEN 0 AND 4),
    skipped BOOLEAN DEFAULT false,
    rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (rater_id, trend_id, workspace_id)
);
CREATE INDEX ON signal_relevance (workspace_id, trend_id);

-- Der Arbeitsbereich einer Organisation: welche Felder, welches Schema
CREATE TABLE workspace (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE workspace_field (
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,              -- 'cluster:63:12' | 'mega:...' | 'vertical:TECH'
    label TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (workspace_id, field_key)
);

-- Ergebnis je Feld, nachrechenbar aus dem Obigen
CREATE TABLE field_assessment (
    workspace_id INTEGER,
    field_key TEXT,
    relevance REAL,           -- gewichtetes Mittel der Signalbewertungen
    relevance_spread REAL,    -- Streuung über die Bewerter
    n_rated INTEGER,
    maturity REAL,            -- 0..3 auf Blechschmidts Stufen
    maturity_stage TEXT,
    maturity_basis TEXT,      -- 'curve' | 'evidence' | 'research' | 'default'
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, field_key)
);
```

Der Kunstgriff: **`field_assessment` ist abgeleitet und jederzeit neu
berechenbar.** Die Wahrheit steht in `signal_relevance` — einzeln, mit Bewerter
und Zeitstempel. Damit ist jede Feldposition auf ihre Belege zurückführbar, und
das spätere Modell hat sein Trainingsset ohne weiteren Bau.

---

## 7. Schnitte

| # | Inhalt | Ergebnis |
|---|---|---|
| **1** | Reifeachse neu: Kurvenklassifikator + Zusammenführung mit Evidenz, Fallback volatil, Jurisdiktionen raus | Eine Achse, begründet, für alle Cluster gerechnet |
| **2** | Bewertungsstrecke: Signalkarten, Tastatur, `signal_relevance`, Fortschritt | Der Nutzer kann arbeiten |
| **3** | Aggregation + Portfolio neu gezeichnet (Kurvenrückgrat, Vorschlag/Setzung farblich getrennt) | Das Werkzeug schließt den Kreis |
| **4** | Fachnähe: Selbstauskunft, Erfahrung, Beständigkeit, Streuungsanzeige | Blechschmidts Gewichtung |
| **5** | Recherche-Agent je Feld auf Knopfdruck; Trendporträt und Export | Semantisches Sensemaking, Dokumentation |
| **6** | ML-Vorschlag der Relevanz aus bewerteten Signalen | Die Automatisierung, die Schnitt 2 vorbereitet hat |

Schnitt 1–3 sind der eigentliche Neubau; danach ist das Werkzeug benutzbar.

---

## 8. Was ich vorher geklärt haben will

1. **Arbeitsbereich = Organisation oder Person?** Das Datenmodell oben nimmt
   einen `workspace` an, in dem mehrere Bewerter arbeiten. Ohne Auth ist das
   ein einzelner Platzhalter — funktioniert, aber Schnitt 4 braucht Konten.
2. **Wie viele Signale je Feld zur Bewertung vorlegen?** Ein Cluster hat bis zu
   40.000. Mein Vorschlag: eine **Stichprobe von 40–60 je Feld**, gezogen über
   die Zeit und über die Signaltypen, damit die Bewertung repräsentativ ist und
   in einer Sitzung zu schaffen. Das muss im Werkzeug stehen, sonst hält der
   Nutzer die Stichprobe für die Grundgesamtheit.
3. **Bleibt das alte Radar erreichbar?** Ich würde es unter einer eigenen URL
   stehen lassen, bis der Neubau trägt — die Kalibrierarbeit aus §8–§11 steckt
   dort drin und ist zu wertvoll für einen harten Schnitt.

---

## 9. Die Grenze, die ich benannt haben will

Die Relevanzachse wird **belegt sein wie noch nie** — jede Position auf
bewertete Einzelsignale zurückführbar. Genau deshalb wird sie *aussehen* wie
eine Messung, und sie ist keine: sie misst, was eine Handvoll Menschen an einem
Tag über eine Stichprobe gedacht hat.

Das Werkzeug muss das tragen, ohne es zu verstecken: Zahl der Bewertungen,
Zahl der Bewerter, Streuung und Datum gehören an jeden Punkt. Ein Feld mit drei
Bewertungen darf nicht aussehen wie eines mit dreihundert.
