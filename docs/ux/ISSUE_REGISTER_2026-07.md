# Usability Issue Register — Catandary Trends

Stand: 2026-07-23 · Quelle: 7-Perspektiven-Audit (Live-App :3001 mit AUTH/PAYWALL aktiv + Repository `frontend/src`).
Schweregrade: S0 Blocker · S1 kritisch · S2 hohe Reibung · S3 mittel · S4 Polishing. Aufwand: S/M/L.

Umsetzungsstatus wird in `IMPLEMENTATION_2026-07.md` gepflegt (dieselben IDs).

## S1 (20 Findings)

### ARCH-01 — Bei aktivem Paywall-Gate (PAYWALL_ENABLED=1) sind fast alle bezahlten Features komplett ungated — es gibt faktisch nichts zu kaufen.

- **Screen/Workflow:** /trends/foresight/* + /api/foresight/*
- **Persona:** Anonymer Besucher / Free-User
- **Tier:** free/anonym
- **Beobachtung:** grep über src/app: TierGate/canAccess existiert nur in evolution/page.tsx, dossier/page.tsx und api/foresight/export/route.ts. Live-Beleg: curl auf /trends/foresight/clusters ohne Session liefert HTTP 200 mit 235 KB vollem Cluster-Explorer (h2-Titel wie 'Climate Change · Machine Learning' im HTML); radar/technology ohne Gate-Marker; /api/foresight/query?q=... antwortet anonym. Laut tiers.ts sind Cluster-Explorer+Radar Starter (99 EUR), Technology/TIR Pro (499 EUR), On-Demand-Query Superpro (799 EUR).
- **Ursache:** Entitlement-Layer (entitlement.ts) wurde gebaut, aber nur an 3 von ~12 zahlpflichtigen Oberflächen/Routen angeschlossen; keine zentrale Stelle (Middleware/Layout) erzwingt die Feature-Matrix.
- **Auswirkung:** Die Tier-Matrix ist wirkungslos: Jeder anonyme Besucher erhält Starter-, Pro- und Superpro-Wert gratis; ein Test der Gated-Experience (Zweck des Temp-Test-Modus) läuft ins Leere.
- **Empfohlene Lösung:** Feature-Matrix aus tiers.ts systematisch durchsetzen: TierGate (mit Teaser) um clusters/radar (need=starter) und technology/lead-time-Drilldown (need=pro) legen; canAccess-Checks in api/foresight/query, analyze, tir, trajectory, technology, clusters, radar, lineage (mit 402 + klarer error-Payload). Eine Tabelle Route→need-Tier als Single Source in tiers.ts ablegen.
- **Akzeptanzkriterium:** Anonymer curl auf /trends/foresight/clusters zeigt Teaser+Upgrade-Card statt Clusterdaten; /api/foresight/query ohne Pro/Superpro-Session liefert 402; eingeloggter Superpro-Test-User sieht alles.
- **Aufwand:** M · **Dateien:** frontend/src/lib/entitlement.ts, frontend/src/components/TierGate.tsx, frontend/src/app/trends/foresight/clusters/page.tsx, frontend/src/app/trends/foresight/radar/page.tsx, frontend/src/app/trends/foresight/technology/page.tsx, frontend/src/app/api/foresight/query/route.ts, frontend/src/app/api/foresight/tir/route.ts, frontend/src/app/api/foresight/analyze/route.ts

### ARCH-02 — Landing und Methodology brauchen konstant ~7,2 Sekunden pro Request — nicht nur cold, sondern bei jedem Aufruf.

- **Screen/Workflow:** / (Landing) + /trends/methodology
- **Persona:** Interessent (Erstkontakt)
- **Beobachtung:** Gemessen: / dreimal hintereinander 7,35/7,14/7,19 s; /trends/methodology 7,20 s (curl time_total). Ursache in db.ts getMethodologyStats(): 5 sequentielle Queries, darunter ein GROUP-BY mit CASE über trends JOIN raw_entries JOIN sources (~1,06 Mio. Zeilen laut eigenem Proof-Counter). page.tsx ist force-dynamic; grep findet im gesamten src kein unstable_cache/revalidate.
- **Ursache:** Teure Korpus-Aggregation läuft synchron im Request-Pfad ohne jede Cache-Schicht, obwohl sich die Zahlen höchstens pro Pipeline-Cycle ändern.
- **Auswirkung:** Der allererste Eindruck der Plattform (Landing = Haupteinstieg für Leads) ist eine 7-Sekunden-Wartezeit ohne Ladeindikator — für einen Trend-Intelligence-Anbieter unmittelbar glaubwürdigkeitsschädigend.
- **Empfohlene Lösung:** getMethodologyStats mit unstable_cache (revalidate z. B. 3600s) oder einer materialisierten Stats-Tabelle entkoppeln, die der Pipeline-Cycle schreibt; Landing auf statisches Rendering mit revalidate umstellen (Fallback-Konstanten existieren bereits).
- **Akzeptanzkriterium:** curl -w time_total auf / liefert wiederholt < 500 ms; die Proof-Zahlen aktualisieren sich weiterhin mindestens täglich.
- **Aufwand:** M · **Dateien:** frontend/src/lib/db.ts, frontend/src/app/page.tsx, frontend/src/app/trends/methodology/page.tsx

### ARCH-03 — Der öffentliche Trends-Endpoint liefert unveröffentlichte Drafts aus, weil der status-Parameter ungeprüft an die DB durchgereicht wird.

- **Screen/Workflow:** /api/trends
- **Persona:** Beliebiger anonymer Client
- **Beobachtung:** Live-Beleg: curl 'localhost:3001/api/trends?status=draft&limit=1' liefert einen vollständigen Draft-Artikel (id 1123530, 'Noom Invests in GLP-1...', kompletter summary_en). Zusätzlich: '?limit=abc' → HTTP 500 mit leerem Body (parseInt→NaN ungeprüft an pg).
- **Ursache:** route.ts übernimmt searchParams.get('status') ohne Whitelist; getTrends() filtert jeden übergebenen Status; kein try/catch, keine Validierung von limit/offset.
- **Auswirkung:** Nicht redigierte, evtl. fehlerhafte LLM-Inhalte (auch rejected/review) sind öffentlich abrufbar — untergräbt das Kurations-Versprechen; 500er ohne Fehlerformat brechen Clients.
- **Empfohlene Lösung:** status auf ['published'] hart pinnen (oder Whitelist published|all mit all=nur published+signal), limit/offset mit Number.isFinite validieren und bei Fehlern 400 mit {error} zurückgeben; Route in einen try/catch mit 500-JSON-Format wickeln.
- **Akzeptanzkriterium:** curl '?status=draft' liefert ausschließlich published-Trends (oder 400); '?limit=abc' liefert 400 mit JSON-Fehlermeldung; Vitest-Regressionstest existiert.
- **Aufwand:** S · **Dateien:** frontend/src/app/api/trends/route.ts, frontend/src/lib/db.ts

### ARCH-04 — Nach erfolgreicher Zahlung landet der Kunde ohne jede Bestätigung auf der Kontoseite und sieht wegen Webhook-Verzug weiterhin 'Free' samt 'See plans →'-Link.

- **Screen/Workflow:** /account?checkout=success (Stripe-Rückkehr)
- **Persona:** Frisch zahlender Kunde
- **Tier:** starter/pro/superpro
- **Beobachtung:** stripe/checkout/route.ts setzt successUrl=/account?checkout=success und cancelUrl=/trends/pricing?checkout=cancelled; grep über src zeigt: kein einziger Consumer liest checkout=success/cancelled. account/page.tsx liest keine searchParams und rendert das Tier direkt aus der DB — das erst der Webhook aktualisiert.
- **Ursache:** Die Redirect-Parameter wurden angelegt, aber die UI-Seite dafür nie gebaut; es gibt keinen 'Zahlung wird verarbeitet'-Zwischenzustand für die Webhook-Latenz.
- **Auswirkung:** Der teuerste Moment der Journey (bis 799 EUR/Monat soeben bezahlt) endet in einem Zustand, der wie eine fehlgeschlagene Zahlung aussieht — Support-Fälle und Vertrauensverlust vorprogrammiert.
- **Empfohlene Lösung:** account/page.tsx: bei checkout=success ein Bestätigungs-Banner rendern ('Zahlung erhalten — Plan wird aktiviert, das dauert i. d. R. unter einer Minute') und solange tier==free per Client-Polling (z. B. alle 3 s auf ein kleines /api/me) aktualisieren; pricing/page.tsx bei checkout=cancelled einen dezenten Hinweis zeigen.
- **Akzeptanzkriterium:** Test-Checkout (Stripe-Testkarte): Rückkehrseite zeigt Erfolgsbestätigung, und das angezeigte Tier wechselt ohne manuellen Reload auf den gekauften Plan.
- **Aufwand:** S · **Dateien:** frontend/src/app/account/page.tsx, frontend/src/app/trends/pricing/page.tsx, frontend/src/app/api/stripe/checkout/route.ts

### ARCH-05 — Der komplette Monetarisierungs-Funnel ist aus der Navigation unsichtbar: kein Sign-in, kein Account, kein Pricing, kein Login-Status.

- **Screen/Workflow:** Header/Footer (global)
- **Persona:** Alle — vom Interessenten bis zum zahlenden Kunden
- **Beobachtung:** Header.tsx NAV_ITEMS enthält 10 Ziele + Newsletter — Pricing, Sign-in und Account fehlen; grep auf 'signin|Sign in|account' in Header.tsx/Footer.tsx: 0 Treffer. Header ist eine statische Server-Komponente ohne getSession-Aufruf. /trends/pricing ist nur von der Landing (die vom Logo aus unerreichbar ist, Logo→/trends), von TierGate-Karten (die live nie erscheinen, siehe ARCH-12) und der Account-Seite (selbst Waise) verlinkt.
- **Ursache:** Auth/Paywall wurden env-gated nachgerüstet, aber die Navigations-Schicht wurde nie auf den AUTH_ENABLED-Zustand reagierend gebaut.
- **Auswirkung:** Free-User können ihr Konto nicht finden, eingeloggte Kunden sehen nicht, dass sie eingeloggt sind, und kein organischer Besucher stolpert je über die Pläne — der Funnel existiert nur für Leute, die URLs raten.
- **Empfohlene Lösung:** Header bei AUTH_ENABLED=1 um 'Pricing' und einen Session-abhängigen Eintrag ergänzen (ausgeloggt: 'Sign in' → /account/signin; eingeloggt: E-Mail/Tier-Badge → /account). Header dafür die Session serverseitig lesen lassen; MobileNav identisch nachziehen.
- **Akzeptanzkriterium:** Ausgeloggt erscheint 'Sign in' + 'Pricing' in Desktop- und Mobile-Nav; nach Login zeigt der Header E-Mail oder Tier und führt zu /account.
- **Aufwand:** S · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/MobileNav.tsx, frontend/src/lib/auth.ts

### ARCH-06 — Die Pricing-Seite verkauft Features, die im Code nicht existieren — Verstoß gegen die eigenen Marketing-Ehrlichkeitsregeln.

- **Screen/Workflow:** /trends/pricing
- **Persona:** Kaufinteressent
- **Beobachtung:** tiers.ts listet für Starter 'Saved searches & alerts', für Superpro 'API access', 'Custom reports'. grep über das gesamte src nach saved search/alert: Treffer nur in tiers.ts und der Landing-Copy (app/page.tsx) — es gibt keinerlei Implementierung (kein Speichern, kein Alerting, kein API-Key-Mechanismus, keine Report-Generierung).
- **Ursache:** Die Feature-Matrix wurde als Zielbild formuliert und unverändert als Verkaufsversprechen ausgespielt.
- **Auswirkung:** Ein Starter-Kunde, der für 99 EUR/Monat 'Alerts' kauft, findet das Feature nirgends — Erstattungs-/Churn-Risiko und direkter Widerspruch zur dokumentierten Truth-Matrix-Regel (keine unbelegten Claims).
- **Empfohlene Lösung:** Nicht existierende Punkte aus TIERS entfernen oder ehrlich als 'coming soon' kennzeichnen (eigenes Feld im TierInfo, gedimmt gerendert); alternativ Minimal-Implementierung (z. B. gespeicherte Suche als URL-Bookmark + wöchentliche Mail) vor Launch nachziehen.
- **Akzeptanzkriterium:** Jedes Feature-Bullet auf /trends/pricing ist entweder in der App klickbar erreichbar oder sichtbar als 'coming soon' markiert.
- **Aufwand:** S · **Dateien:** frontend/src/lib/tiers.ts, frontend/src/app/trends/pricing/page.tsx, frontend/src/app/page.tsx

### CONF-01 — Die oeffentliche Trends-API liefert ohne Default-Status-Filter das gesamte bezahlpflichtige Signal-Korpus plus unveroeffentlichte Drafts und rejected-Inhalte aus.

- **Screen/Workflow:** /api/trends (frontend/src/app/api/trends/route.ts, frontend/src/lib/db.ts getTrends)
- **Persona:** Wettbewerber / Data-Scraper
- **Tier:** Public
- **Beobachtung:** `getTrends` (db.ts:72-75) setzt den Status-Filter nur, WENN ein `status`-Param uebergeben wird — sonst kein `WHERE status`-Constraint. Der Handler (trends/route.ts:10-15) reicht `status` ungeprueft durch. Belegt per curl mit aktiver Paywall: `?status=signal` → total 1.059.838 (Rohsignale, das Foresight-Produktkorpus, frei paginierbar via offset), `?status=draft` → 3.100 (inkl. vollem `body_en`, 930+ Zeichen, auch vom Grounding-Gate zurueckgehaltene), `?status=rejected` → 131, `?status=review` → 3. Ein Signal-Record exponiert mega_trend, verticals, pestel, confidence (0.96) und source_url.
- **Ursache:** Fehlender Default-/Whitelist-Filter auf `status`; die Query filtert nur bei explizit gesetztem Param.
- **Auswirkung:** Das gesamte Monetarisierungs-Fundament (1M+ klassifizierte science→patents→funding→market-Signale) ist per anonymem GET exfiltrierbar; pre-publication Drafts und explizit zurueckgehaltene Grounding-Holds werden entgegen V6 der Truth-Matrix oeffentlich.
- **Empfohlene Lösung:** In `getTrends`/`getTrendsCount`/`getVerticalCounts` per Default auf `status='published'` filtern und den `status`-Param serverseitig gegen eine Whitelist (nur 'published') pruefen; nicht-published-Status ausschliesslich hinter Auth/Review-Rolle zulassen. Alternativ die Public-Route ganz von der internen `getTrends`-Funktion entkoppeln (eigene published-only-Query).
- **Akzeptanzkriterium:** `curl '/api/trends?status=signal'` (und draft/rejected/review) liefert 0 Ergebnisse bzw. 400; nur `status=published` bzw. kein Param gibt ausschliesslich published trends zurueck; automatisierter Test deckt alle vier internen Status ab.
- **Aufwand:** S · **Dateien:** frontend/src/app/api/trends/route.ts, frontend/src/lib/db.ts

### CONF-02 — Trotz aktiver Paywall (PAYWALL_ENABLED=1) sind alle Foresight-Premium-Daten ausser dem CSV-Export ohne Entitlement-Check direkt per API abrufbar.

- **Screen/Workflow:** /api/foresight/* (query, trajectory, tir, technology, clusters, analyze, radar, lineage)
- **Persona:** Nicht zahlender Nutzer / Wettbewerber
- **Tier:** Subscriber (starter/pro/superpro)
- **Beobachtung:** Gating-Scan der Routen: nur `export/route.ts:21` prueft `canAccess('pro')`; analyze, clusters, lineage, query, query/evidence, radar, technology, tir, trajectory sind UNGATED. Die Paywall wirkt nur in der UI ueber `TierGate` — und das nur auf 2 Seiten (dossier, evolution). Belegt mit aktiver Paywall: `/api/foresight/clusters?limit=1` liefert vollstaendige Cluster (label, size, cohesion, momentum, reps mit source_url), `/api/foresight/technology?cpc=H02S` liefert die volle TIR-/Lead-Time-Analyse (tir_pct 18.4, tir_direction). tiers.ts weist Technology-Explorer/TIR als Pro (€499) und On-demand-Analyse/`query` als Super Pro+ (€799) aus.
- **Ursache:** Entitlement-Enforcement liegt nur in React-Server-Komponenten (TierGate), nicht in der Datenschicht/API; die API-Routen wurden nicht mit `canAccess` abgesichert.
- **Auswirkung:** Die kostenpflichtigen Foresight-Differenzierer (Cluster-Momentum, Lead-Time, TIR, on-demand) sind vollstaendig gratis abgreifbar; die Tier-Struktur ist wertlos, sobald jemand die API kennt.
- **Empfohlene Lösung:** In jeder Premium-Foresight-Route am Anfang `if (!(await canAccess(<tier>))) return 402` ergaenzen (clusters/radar→'starter', technology/tir/trajectory/lineage/analyze→'pro', query/query/evidence→'superpro'), analog zu export/route.ts. Zusaetzlich einen gemeinsamen Guard/Middleware fuer /api/foresight/* einziehen, damit neue Routen nicht erneut ungated starten.
- **Akzeptanzkriterium:** Mit PAYWALL_ENABLED=1 und free-Session liefern alle genannten Routen 402/403; nur mit passender Tier-Session kommen Daten; ein Test pro Route deckt den Gate ab.
- **Aufwand:** M · **Dateien:** frontend/src/app/api/foresight/clusters/route.ts, frontend/src/app/api/foresight/technology/route.ts, frontend/src/app/api/foresight/tir/route.ts, frontend/src/app/api/foresight/query/route.ts, frontend/src/app/api/foresight/analyze/route.ts, frontend/src/app/api/foresight/trajectory/route.ts, frontend/src/app/api/foresight/lineage/route.ts, frontend/src/app/api/foresight/radar/route.ts

### COPY-01 — Der wichtigste Conversion-Moment des Free-Layers antwortet auf Deutsch in einer komplett englischen UI.

- **Screen/Workflow:** /trends/newsletter (Signup-Formular)
- **Persona:** Neuer Lead (primäre Conversion)
- **Tier:** free
- **Beobachtung:** Seite und Formular sind Englisch ("Subscribe", "Free · one email per week · no spam"), aber die API liefert deutsche Meldungen, die 1:1 angezeigt werden: "Erfolgreich angemeldet! Du erhältst bald die ersten Trends.", "Bitte gib eine gültige Email-Adresse ein.", "Willkommen zurück! Du bist wieder angemeldet." (app/api/newsletter/route.ts:75,92,95,100,105; Anzeige ungefiltert in SignupForm, app/trends/newsletter/page.tsx:104-108).
- **Ursache:** API-Microcopy wurde nie mit der EN-Umstellung des Frontends mitgezogen.
- **Auswirkung:** Ein internationaler B2B-Lead sieht direkt nach der Email-Eingabe eine unverständliche Meldung — wirkt kaputt und untergräbt das Trust-Versprechen der Marke im entscheidenden Moment.
- **Empfohlene Lösung:** Die fünf Strings in app/api/newsletter/route.ts auf Englisch umstellen (z.B. "You're subscribed — the first briefing lands Monday.", "Please enter a valid email address.", "Welcome back — you're subscribed again.").
- **Akzeptanzkriterium:** POST /api/newsletter liefert für alle Pfade (neu/re-subscribe/bereits angemeldet/invalid/Fehler) englische message/error-Strings; Signup auf /trends/newsletter zeigt durchgängig Englisch.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/api/newsletter/route.ts, /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx

### COPY-02 — Das Pro-Flaggschiff-Feature mischt auf einem Screen Deutsch und Englisch, dazu Du/Sie-Mix und inkonsistentes Zahlenformat.

- **Screen/Workflow:** /trends/foresight/technology (Technology-Analyzer)
- **Persona:** Pro-Kaufinteressent (Kernfeature-Demo)
- **Tier:** pro
- **Beobachtung:** Seitenkopf und Karten sind Englisch ("Where innovation moves fastest", "Pro preview"), das interaktive Tool darunter komplett Deutsch: "—— Technologie-Analyse · Verbesserungsrate & Innovationskette", Button "Analysieren"/"Analysiere…", "Patentklassen — deine Auswahl", "Meistzitierte Patente in dieser Auswahl", Fehler "Zeitüberschreitung — versuch eine engere Phrase"/"Netzwerkfehler" (components/foresight/TechnologyTool.tsx:226-380). Im selben Component Duzen ("du wählst, welche", Z.231) UND Siezen ("Die Einordnung überlassen wir Ihnen.", Z.313-315). Zahlen mit toLocaleString("de") (Z.285) vs. "en-US" in TechnologyCard — 1.234 neben 1,234.
- **Ursache:** Das Tool wurde separat (auf Deutsch) entwickelt und nie an die EN-Produktlinie angeglichen.
- **Auswirkung:** Genau das Feature, das den 499-EUR-Tier verkaufen soll, wirkt wie ein Fremdkörper aus einem anderen Produkt — maximaler Glaubwürdigkeitsschaden beim teuersten Demo-Moment.
- **Empfohlene Lösung:** TechnologyTool.tsx vollständig auf Englisch übersetzen (eine Anredeform: keine — Imperativ), toLocaleString auf "en-US" vereinheitlichen, ebenso den deutschen Timeout-Fehler der API (COPY-14).
- **Akzeptanzkriterium:** Auf /trends/foresight/technology existiert kein deutscher String mehr (UI + Fehlerpfade + Off-Topic-Meldung "Das sieht nicht nach einer Technologie aus."); alle Zahlen im en-US-Format.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TechnologyTool.tsx

### COPY-03 — Nach einer Zahlung von bis zu 799 EUR gibt es keinerlei Bestätigungs-Microcopy — der Erfolgs-Query-Parameter wird ignoriert.

- **Screen/Workflow:** /account nach Stripe-Checkout (Success-Rückkehr)
- **Persona:** Frischer zahlender Kunde
- **Tier:** starter/pro/superpro
- **Beobachtung:** Checkout setzt successUrl `${base}/account?checkout=success` (app/api/stripe/checkout/route.ts:47), aber app/account/page.tsx liest searchParams nicht — der Kunde landet auf der generischen Account-Seite. Wegen Webhook-Latenz kann dort in den ersten Sekunden sogar noch "Current plan: Free" stehen. Auch die cancelUrl `?checkout=cancelled` (Z.48) wird auf /trends/pricing nirgends ausgewertet.
- **Ursache:** Query-Parameter wurden beim Bau der Checkout-Route vorgesehen, die Auswertung im Frontend fehlt.
- **Auswirkung:** Der psychologisch heikelste Moment (Geld weg, Gegenwert unklar) bleibt unbeantwortet; "Free" nach Zahlung erzeugt akute Storno-/Support-Impulse.
- **Empfohlene Lösung:** Auf /account bei checkout=success einen Bestätigungsblock rendern: "Payment received — your {tier} plan activates within a minute. Refresh if it still shows Free." + direkter Link "Open Foresight →". Auf /trends/pricing bei checkout=cancelled eine neutrale Zeile: "Checkout cancelled — no charge was made."
- **Akzeptanzkriterium:** /account?checkout=success zeigt eine sichtbare Erfolgsbestätigung mit nächstem Schritt; /trends/pricing?checkout=cancelled zeigt eine Keine-Abbuchung-Zeile; beides ohne Query-Param unverändert.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/account/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/api/stripe/checkout/route.ts

### COPY-04 — Die Pricing-Seite verkauft Features als Starter (99 EUR: "Trend radar", "Cluster explorer") und Pro (499 EUR: "Technology explorer", lead-time), die trotz aktivem Paywall-Modus für anonyme Free-Nutzer vollständig zugänglich sind.

- **Screen/Workflow:** /trends/foresight/radar, /clusters, /technology, /lead-time vs. /trends/pricing
- **Persona:** Kaufinteressent, der vor dem Kauf prüft
- **Tier:** starter/pro
- **Beobachtung:** Bei AUTH_ENABLED=1/PAYWALL_ENABLED=1 rendern Radar (216 KB), Clusters (235 KB), Technology (1,88 MB) und Lead-Time komplett ohne Gate an einen anonymen curl; TierGate wird nur in evolution/page.tsx:157 und dossier/page.tsx:75 verwendet. Die Technology-Seite trägt lediglich ein "Pro preview"-Badge; der Code kommentiert "Subscription gating is display-only for this test" (technology/page.tsx:22-24). Gleichzeitig listet lib/tiers.ts genau diese Features als Kaufgrund.
- **Ursache:** Gating wurde nur für 2 von 6 Foresight-Ansichten implementiert; die Featurematrix in tiers.ts wurde nicht mit dem realen Gate-Zustand abgeglichen.
- **Auswirkung:** Wer vor dem Kauf klickt, stellt fest, dass es alles gratis gibt — das Wertversprechen der Tiers wird live widerlegt; wer dennoch zahlt und es später merkt, fühlt sich getäuscht. Beides zerstört Preisbereitschaft.
- **Empfohlene Lösung:** Entweder die vier Ansichten mit TierGate + Free-Teaser versehen (Teaser-Prop existiert bereits) oder — falls bewusst offen als Demo — auf Radar/Clusters/Lead-Time dieselbe transparente "Pro preview — free during alpha"-Kennzeichnung wie auf Technology setzen und diese Formulierung auch auf der Pricing-Seite spiegeln ("currently open in the alpha").
- **Akzeptanzkriterium:** Für jede in TIERS gelistete Feature-Zeile gilt live entweder (a) Gate mit passendem TierGate oder (b) sichtbares "free during alpha/preview"-Label auf Feature-Seite UND Pricing-Karte — kein Feature wird verkauft, das unkommentiert gratis ist.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/lib/tiers.ts, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/radar/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/clusters/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/technology/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/lead-time/page.tsx

### DS-01 — Primär-CTAs mit bg-accent sind praktisch unlesbar, weil die Textfarb-Klasse text-ink auf ein nicht existierendes Token zeigt.

- **Screen/Workflow:** /trends (Pagination, TrendsEmpty), /trends/newsletter (Submit), Foresight-Seiten (ForesightCta), FilterBar (DateRangeChips)
- **Tier:** free
- **Beobachtung:** `text-ink`/`bg-ink` werden 7× verwendet (u.a. ForesightCta.tsx:13/36, Pagination.tsx:67, TrendsEmpty.tsx:64, newsletter/page.tsx:142, DateRangeChips.tsx:47, TechnologyTool.tsx:238), aber @theme in globals.css definiert nur --color-background (Kommentar "--ink"), kein --color-ink. Verifiziert: `grep -c text-ink` im kompilierten CSS (/_next/static/chunks/01ov7_ilynsct.css) = 0, während die Klasse im Live-HTML von /trends (4×) und /trends/newsletter (2×) ausgeliefert wird. Ergebnis: Chartreuse-Button (#d4ff3a) erbt die helle Body-Textfarbe #d8d5c8 → Kontrast ca. 1,3:1.
- **Ursache:** Tailwind v4 generiert Utilities nur für in @theme definierte Tokens; unbekannte Klassen werden still verworfen — kein Build-Fehler.
- **Auswirkung:** Die wichtigsten Handlungsaufforderungen (Newsletter-Signup = primärer Lead-Magnet, Foresight-Upsell-CTA, aktive Seitenzahl) sind visuell defekt; wirkt kaputt und kostet Conversions.
- **Empfohlene Lösung:** In globals.css `--color-ink: #0a0c0a;` im @theme ergänzen (deckt text-ink und bg-ink ab); alternativ alle Vorkommen auf `text-background` umstellen. Danach kompiliertes CSS erneut gegen die Klassenliste prüfen.
- **Akzeptanzkriterium:** Im kompilierten CSS existiert `.text-ink{color:...#0a0c0a...}`; auf /trends/newsletter hat der Subscribe-Button dunklen Text auf Chartreuse (Kontrast >= 7:1).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCta.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/Pagination.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TrendsEmpty.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/DateRangeChips.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TechnologyTool.tsx

### KEY-01 — Das Tier-Gating widerspricht bei aktivem Paywall der Pricing-Seite: vier von sieben bezahlten Foresight-Features sind komplett offen.

- **Screen/Workflow:** /trends/foresight/radar, /clusters, /technology, /lead-time
- **Persona:** Key User / Power User
- **Tier:** Starter/Pro laut tiers.ts
- **Beobachtung:** Mit PAYWALL_ENABLED=1 liefern Radar (216 KB, 102 Blips), Clusters (235 KB, volle Cards), Technology (1,88 MB inkl. Analyse-Tool) und Lead-Time als anonymer Nutzer den vollen Inhalt — grep nach 'tier-gate' in allen vier HTML-Responses: 0 Treffer. Nur dossier/page.tsx:75 und evolution/page.tsx:157 nutzen TierGate, dazu export/route.ts:21. Laut tiers.ts sind Radar+Clusters Starter (99 €), Technology/TIR/Lead-Time Pro (499 €). Zusätzlich stale Copy auf technology/page.tsx:23+137-167: 'Subscription gating is display-only for this test', 'Pro preview', 'Get notified when plans launch →' — obwohl Pricing+Checkout live sind.
- **Ursache:** Gating wurde nur für Dossier/Export/Evolution nachgerüstet (Issue #17), die vier älteren Tool-Seiten behielten das 'display-only'-Konzept aus der Vor-Paywall-Zeit.
- **Auswirkung:** Ein zahlungsbereiter Power-User sieht: Alles Wesentliche ist gratis, nur der CSV-Export kostet 499 €/Monat — die Tier-Story kollabiert. Umgekehrt wirkt die 'Pro preview'-Beschriftung wie ein nicht eingelöstes Versprechen.
- **Empfohlene Lösung:** Entweder die vier Seiten mit TierGate (need=starter bzw. pro, mit Teaser wie bei Evolution: freier Hook + gegatetes Drilldown) versehen, oder die Feature-Matrix in tiers.ts an die reale Offenheit anpassen. Stale 'plans launch'/'display-only'-Copy auf technology/page.tsx entfernen und durch Link auf /trends/pricing ersetzen.
- **Akzeptanzkriterium:** Bei PAYWALL_ENABLED=1 zeigt jede in tiers.ts als Starter/Pro gelistete Tool-Seite als anonymer Nutzer mindestens ein tier-gate-Element (curl-Test), und 'Get notified when plans launch' kommt auf keiner Seite mehr vor.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/foresight/radar/page.tsx, frontend/src/app/trends/foresight/clusters/page.tsx, frontend/src/app/trends/foresight/technology/page.tsx, frontend/src/app/trends/foresight/lead-time/page.tsx, frontend/src/lib/tiers.ts

### KEY-02 — Die Pricing-Seite verkauft 'Saved searches & alerts' als Starter-Feature (99 €/Monat), das Feature existiert aber nirgends im Frontend-Code.

- **Screen/Workflow:** /trends/pricing
- **Persona:** Key User / Power User
- **Tier:** Starter
- **Beobachtung:** tiers.ts:53 listet 'Saved searches & alerts' unter Starter; live auf /trends/pricing gerendert (HTML-Auszug: '"children":"Saved searches & alerts"'). Repo-weites grep nach savedSearch/saved.search/alert in frontend/src trifft nur tiers.ts und die Landing page.tsx — keine Speicher-, Alert- oder Benachrichtigungslogik, kein localStorage, keine DB-Route.
- **Ursache:** Feature-Matrix wurde vor der Implementierung finalisiert; das Feature wurde nie gebaut.
- **Auswirkung:** Genau das Feature, das den täglichen Power-Workflow trägt (gespeicherte Filteransichten, Benachrichtigung bei neuen Treffern), wird verkauft, aber nicht geliefert — nach Kauf ein handfester Erwartungsbruch und laut den eigenen Marketing-Ehrlichkeitsregeln des Projekts unzulässig.
- **Empfohlene Lösung:** Kurzfristig 'Saved searches & alerts' aus tiers.ts entfernen (erscheint dann automatisch weder auf Pricing noch im Account). Mittelfristig als echtes Feature bauen — die URL-basierte Filterarchitektur macht 'gespeicherte Ansichten' technisch trivial (benannte URLs pro Account speichern) und der Newsletter-Versandweg existiert bereits für Alerts.
- **Akzeptanzkriterium:** Auf /trends/pricing wird kein Feature mehr genannt, das im Code nicht existiert — oder ein eingeloggter Starter-Nutzer kann eine Filter-URL benennen/speichern und unter /account wieder aufrufen.
- **Aufwand:** S · **Dateien:** frontend/src/lib/tiers.ts, frontend/src/app/trends/pricing/page.tsx

### KEY-03 — Bei aktivem Auth/Paywall gibt es in Header und Footer keinen einzigen Link zu Sign-in, Account oder Pricing — ein zahlender Kunde findet den Login nicht.

- **Screen/Workflow:** Header/Footer (alle Seiten)
- **Persona:** Key User / Power User (zahlender Kunde)
- **Beobachtung:** Header.tsx:3-14 NAV_ITEMS enthält nur Trends/Mega/Cross-Industry/Foresight-Tools/Newsletter; Footer.tsx nur Methodology + catandary.de. Live-Verifikation der Link-Liste auf /trends: kein href auf /account/signin, /account oder /trends/pricing. /account/signin existiert und funktioniert (HTTP 200, Magic-Link-Formular), ist aber nur über TierGate-Karten ('See plans →' → Pricing → Checkout) oder URL-Wissen erreichbar. Auch /trends/foresight/dossier ist in keiner Navigation verlinkt (nur von der Landing /).
- **Ursache:** Header/Footer stammen aus der Vor-Auth-Phase und wurden beim Aktivieren der Gates nicht nachgezogen.
- **Auswirkung:** Ein Pro-Kunde auf neuem Gerät kann sich nicht einloggen und sieht stattdessen Upgrade-Karten für Features, die er bezahlt hat; das Dossier — das Pro-Arbeitsartefakt — ist unauffindbar.
- **Empfohlene Lösung:** Bei AUTH_ENABLED=1 im Header rechts einen 'Sign in'/Account-Link (Session-abhängig) und 'Pricing' ergänzen; Dossier in die Foresight-Navigation oder auf die Foresight-Index-Seite aufnehmen.
- **Akzeptanzkriterium:** Anonymer curl auf /trends zeigt im Header einen Link auf /account/signin und /trends/pricing; eingeloggt erscheint stattdessen /account. /trends/foresight/dossier ist von mindestens einer Navigationsebene aus verlinkt.
- **Aufwand:** S · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/Footer.tsx, frontend/src/components/MobileNav.tsx

### ONB-01 — Die beiden wichtigsten Vertrauensseiten laden 7-9 Sekunden und zerstoeren damit den Erstkontakt.

- **Screen/Workflow:** / (Landing) und /trends/methodology
- **Persona:** Alle (Erstnutzer)
- **Tier:** free
- **Beobachtung:** Drei Messungen auf / ergaben 7,37 s / 7,68 s / 8,55 s TTFB, /trends/methodology 7,27 s — waehrend /trends (0,5 s) und Artikel (0,04 s) schnell sind. Beide Seiten setzen `export const dynamic = "force-dynamic"` und rufen pro Request getMethodologyStats() auf, das u.a. `SELECT COUNT(*) FROM trends` (1,1 Mio Zeilen) plus einen 3-Wege-JOIN mit GROUP BY ueber alle Trends ausfuehrt.
- **Ursache:** frontend/src/app/page.tsx:10 (force-dynamic) + lib/db.ts:387-419 (ungecachte Vollscans pro Request); es existieren sogar verifizierte FALLBACK-Werte im Code, die nicht als Cache genutzt werden.
- **Auswirkung:** Ein Erstbesucher, der von einem Link kommt, sieht 8 Sekunden nichts — bei einer Plattform, die mit "Ops maturity" und Performance wirbt. Hoechste Absprungwahrscheinlichkeit am wichtigsten Punkt des Funnels.
- **Empfohlene Lösung:** getMethodologyStats() mit unstable_cache/revalidate (z.B. 1h) cachen oder die Zahlen per Cron in eine Stats-Tabelle materialisieren; force-dynamic auf beiden Seiten entfernen (ISR mit revalidate genuegt fuer Zaehler, die sich stundenweise aendern).
- **Akzeptanzkriterium:** curl -w '%{time_total}' auf / und /trends/methodology liefert warm < 1,0 s; die angezeigten Zahlen weichen max. 1 h vom Live-Stand ab.
- **Aufwand:** S · **Dateien:** frontend/src/app/page.tsx, frontend/src/app/trends/methodology/page.tsx, frontend/src/lib/db.ts

### ONB-02 — Mit aktivem AUTH_ENABLED=1 gibt es in der gesamten UI keinen auffindbaren Weg zum Sign-in.

- **Screen/Workflow:** Header/MobileNav/Footer + /trends/pricing
- **Persona:** Onboarding-Nutzer, wiederkehrender zahlender Kunde
- **Tier:** free
- **Beobachtung:** grep ueber Header.tsx, MobileNav.tsx und Footer.tsx findet keinerlei account/signin-Link (leeres Ergebnis). Auf /trends/pricing wird der einzige vorgesehene Einstieg ("Sign up free" auf der Free-Karte) fuer anonyme Besucher unterdrueckt: viewerTier() liefert fuer Anonyme 'free' (entitlement.ts:17), dadurch greift isCurrent und die Karte zeigt "Your current plan" statt des Sign-up-Buttons — beobachtet im gelieferten HTML.
- **Ursache:** pricing/page.tsx:21+47+70: `current = viewerTier()` unterscheidet nicht zwischen "eingeloggt mit Free-Tier" und "gar nicht eingeloggt" (session null); Header/Footer wurden nie um einen Account-Einstieg ergaenzt.
- **Auswirkung:** Ein Neuer kann kein Konto anlegen, ein zahlender Kunde kann sich nach Session-Ablauf nicht wieder einloggen — ausser er raet die URL /account/signin oder stolpert ueber den Checkout-Redirect. Zusaetzlich wirkt "Your current plan" auf Anonyme irritierend ("Ich habe doch gar keinen Account?").
- **Empfohlene Lösung:** (1) "Sign in"-Link in Header und MobileNav (bei Session: "Account"). (2) In pricing/page.tsx isCurrent nur setzen, wenn eine Session existiert (session != null), sonst "Sign up free" zeigen.
- **Akzeptanzkriterium:** Anonymer GET /trends/pricing enthaelt "Sign up free" (nicht "Your current plan"); jede Seite enthaelt im Header einen Link auf /account/signin bzw. /account.
- **Aufwand:** S · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/MobileNav.tsx, frontend/src/app/trends/pricing/page.tsx, frontend/src/lib/entitlement.ts

### ONB-03 — Trotz PAYWALL_ENABLED=1 sind die laut Pricing kostenpflichtigen Kern-Features (Radar+Clusters=Starter €99, Technology+Lead-Time/TIR=Pro €499) fuer anonyme Besucher vollstaendig offen.

- **Screen/Workflow:** /trends/foresight/radar, /clusters, /technology, /lead-time
- **Persona:** Kaufinteressent, zahlender Kunde
- **Tier:** starter/pro
- **Beobachtung:** Anonyme curl-GETs liefern HTTP 200 mit vollem Inhalt: Radar mit allen Clustern, Cluster-Explorer mit Momentum/Evidenz ("174,451 analyzed signals"), Technology-Explorer mit kompletten TIR-/Lead-Time-Daten pro Technologie. grep zeigt: TierGate wird nur in foresight/evolution/page.tsx:157 und foresight/dossier/page.tsx:75 verwendet — nirgends auf radar/clusters/technology/lead-time.
- **Ursache:** Die Owner-Regel "gate at the value drill-down, not at the door" (entitlement.ts Kommentar) wurde nur fuer Evolution/Dossier/Export-API umgesetzt; die uebrigen Foresight-Seiten haben schlicht keinen Gate-Aufruf.
- **Auswirkung:** Doppelter Schaden: Ein Kaufinteressent fragt sich, wofuer er €99/€499 zahlen soll, wenn alles offen ist (Pricing-Versprechen wird von der Realitaet widerlegt); und falls die Gates spaeter greifen, hat der Free-Nutzer einen Rueckschritt-Schock. Die Gated-Experience, die der Testmodus zeigen soll, existiert auf diesen Seiten nicht.
- **Empfohlene Lösung:** TierGate (mit Teaser, wie vorgesehen) um die Drill-down-Bereiche von radar (need=starter), clusters (starter), technology (pro) und lead-time (pro) legen — z.B. Top-3-Cluster frei, Rest gegated; oder bewusst entscheiden, dass diese Seiten Free-Teaser sind, und dann die Pricing-Featurematrix entsprechend umformulieren.
- **Akzeptanzkriterium:** Mit PAYWALL_ENABLED=1 zeigt ein anonymer GET auf jede der vier Seiten entweder eine Upgrade-Karte/Teaser ODER die Pricing-Seite listet das Feature nicht mehr als kostenpflichtig; beides zusammen tritt nie auf.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/foresight/radar/page.tsx, frontend/src/app/trends/foresight/clusters/page.tsx, frontend/src/app/trends/foresight/technology/page.tsx, frontend/src/app/trends/foresight/lead-time/page.tsx, frontend/src/components/TierGate.tsx

### ONB-04 — Es gibt keinerlei Rechtstexte — kein Impressum, keine Datenschutzerklaerung, keine AGB — obwohl Newsletter-Erfassung und Stripe-Checkout aktiv sind.

- **Screen/Workflow:** Footer / alle Seiten
- **Persona:** Alle, besonders fachlich kompetent aber digital unerfahren (sucht Impressum als Serioesitaetssignal)
- **Tier:** free
- **Beobachtung:** Alle Kandidaten-Routen liefern 404: /impressum, /privacy, /datenschutz, /trends/privacy, /trends/imprint, /legal, /agb, /trends/terms. Der Footer enthaelt nur "How we measure" und "Powered by Catandary Foresight". Gleichzeitig verspricht die Landing-FAQ Datenschutz-Details ("processed by named EU-based providers (Resend, Stripe, Hetzner)") — ohne verlinkbare Datenschutzerklaerung.
- **Ursache:** Keine legal-Routen im App-Verzeichnis (frontend/src/app enthaelt nur account, api, trends).
- **Auswirkung:** Fuer eine deutsche kommerzielle Site (catandary.de) Impressumspflicht-Verstoss (§5 DDG) und DSGVO Art. 13-Verstoss ab dem ersten Newsletter-Signup/Checkout — abmahnfaehig. Deutsche B2B-Kunden pruefen das Impressum als Vertrauenssignal vor dem Kauf. Zum Public Launch ist das S0.
- **Empfohlene Lösung:** Impressum-, Datenschutz- und AGB-Seiten anlegen und im Footer jeder Seite verlinken; im Datenschutztext die bereits in der FAQ genannten Prozessoren (Resend, Stripe, Hetzner) formal ausweisen.
- **Akzeptanzkriterium:** GET /impressum und /datenschutz (o.ae.) liefern 200 mit Inhalt; der Footer jeder Seite verlinkt beide; die Newsletter-Formulare verlinken die Datenschutzerklaerung.
- **Aufwand:** M · **Dateien:** frontend/src/components/Footer.tsx, frontend/src/app

## S2 (42 Findings)

### A11Y-01 — Kein einziges Eingabefeld der Konversionspfade hat ein programmatisches Label — nur Placeholder.

- **Screen/Workflow:** Newsletter-Signup, /account/signin, Foresight-Cockpit, Technology-Tool
- **Persona:** Screenreader-Nutzer auf dem Haupt-Konversionspfad
- **Tier:** free
- **Beobachtung:** Gerendertes HTML bestaetigt: /account/signin liefert `<input type="email" required placeholder="you@company.com" class="signin-input">` ohne label/aria-label; /trends/newsletter enthaelt 2x `<input type="email" placeholder="Your email address">` ohne Label; ForesightCockpit.tsx:171-178 (Suchfeld) und TechnologyTool.tsx:238 ebenso. Kein Feld hat autocomplete="email". Nur SearchInput (aria-label="Search trends") und SortSelect sind korrekt benannt.
- **Ursache:** Placeholder-als-Label-Pattern in SignInForm.tsx:66-73 und newsletter/page.tsx:130-138.
- **Auswirkung:** WCAG 1.3.1/3.3.2/1.3.5 Fail auf dem Lead-Magnet (Newsletter) und dem Auth-Einstieg; Placeholder verschwindet zudem beim Tippen.
- **Empfohlene Lösung:** aria-label (oder sichtbares label + htmlFor) auf alle vier Felder plus autocomplete="email" bei den E-Mail-Feldern; im WeekSelector-Select (newsletter/page.tsx:188) aria-label="Edition auswaehlen" ergaenzen.
- **Akzeptanzkriterium:** Jedes input/select in SignInForm, Newsletter-SignupForm, WeekSelector, ForesightCockpit und TechnologyTool hat einen Accessible Name (axe: label-Regel 0 Violations) und E-Mail-Felder haben autocomplete="email".
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCockpit.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TechnologyTool.tsx

### A11Y-02 — Async-Status- und Fehlermeldungen werden nie announced — es gibt im gesamten Frontend kein aria-live, role="alert" oder role="status".

- **Screen/Workflow:** Alle Formulare (Newsletter, Sign-in, Checkout, Technology-Tool)
- **Persona:** Screenreader-Nutzer
- **Beobachtung:** grep ueber frontend/src liefert 0 Treffer fuer aria-live/role="alert"/role="status" (einziges sr-only ist die TierCurveChart-Tabelle). SignInForm.tsx:59-64 rendert Fehler als einfaches <p>, newsletter/page.tsx:118-152 Success/Error ebenso. CheckoutButton.tsx schluckt Fehler sogar komplett (catch -> setBusy(false), keinerlei Meldung fuer niemanden).
- **Auswirkung:** WCAG 4.1.3 Fail: Blinde Nutzer erfahren weder Erfolg noch Fehler beim Newsletter-Signup/Sign-in; bei Stripe-Fehler friert der Checkout kommentarlos ein.
- **Empfohlene Lösung:** Statusmeldungs-Container mit role="status" (Erfolg) bzw. role="alert" (Fehler) rendern und per aria-describedby ans Feld haengen; CheckoutButton braucht zusaetzlich eine sichtbare Fehlermeldung im catch-Zweig.
- **Akzeptanzkriterium:** Nach Submit mit Fehler wird die Meldung von NVDA/VoiceOver automatisch vorgelesen; CheckoutButton zeigt bei fetch-Fehler eine sichtbare + announced Meldung.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/CheckoutButton.tsx

### A11Y-03 — Der Radar erzeugt 97 fokussierbare, unbenannte Tab-Stops ohne sichtbaren Fokus, und das Readout-Update wird nicht announced.

- **Screen/Workflow:** /trends/foresight/radar (TrendRadar)
- **Persona:** Tastatur-/Screenreader-Nutzer
- **Tier:** Foresight-Feature (Lead-Nachweis)
- **Beobachtung:** Gerendertes foresight_radar.html enthaelt 97x tabindex="0" auf <g>-Elementen ohne role/aria-label (TrendRadar.tsx:166-194); CSS `.radar-blip { outline: none }` (Z.269) ersetzt den Fokusring nur durch fill-opacity 0.6->0.95; das per onFocus befuellte <aside class="radar-readout"> hat kein aria-live. onClick auf <g> ist ohne Enter/Space-Handler nicht tastaturaktivierbar.
- **Auswirkung:** WCAG 4.1.2 + 2.4.7 Fail: 97 stumme Tab-Stops machen die Seite fuer Tastaturnutzer praktisch unpassierbar; Screenreader hoeren nur "Gruppe" 97-mal.
- **Empfohlene Lösung:** Jedem Blip role="button" + aria-label (z.B. `${label}, ${tier}, ${momentum}, ${size} signals`) geben, sichtbaren Fokusring (SVG-stroke) statt outline:none, Readout-Panel mit aria-live="polite" versehen; alternativ die Blip-Liste zusaetzlich als visually-hidden Liste mit Links rendern.
- **Akzeptanzkriterium:** Tab auf einen Blip liest Name+Tier+Momentum vor, zeigt einen sichtbaren Ring, und das Readout-Update wird announced.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TrendRadar.tsx

### A11Y-04 — Der Fullscreen-Drawer des MobileNav hat kein Fokus-Management: kein Fokus-Trap, Fokus wird beim Oeffnen nicht hineingesetzt und beim Schliessen nicht zurueckgegeben.

- **Screen/Workflow:** Header / MobileNav (alle Seiten < md)
- **Persona:** Tastatur-Nutzer auf Mobile/Tablet
- **Beobachtung:** MobileNav.tsx:58-96: Drawer ist ein position:fixed <div> ohne role="dialog"/aria-modal; nach Klick auf den Hamburger bleibt der Fokus auf dem Trigger, Tab wandert danach durch den (visuell verdeckten) Seiteninhalt hinter dem Overlay. Escape-Close und Scroll-Lock sind korrekt implementiert (Z.20-30), aria-expanded vorhanden (Z.37).
- **Auswirkung:** WCAG 2.4.3: Tastaturnutzer verlieren sich hinter dem Overlay; Screenreader-Nutzer merken nicht, dass ein Modal offen ist.
- **Empfohlene Lösung:** role="dialog" aria-modal="true" setzen, beim Oeffnen Fokus auf den Close-Button setzen, Tab/Shift-Tab im Drawer zyklisch halten (Focus-Trap), beim Schliessen Fokus auf den Hamburger zurueckgeben.
- **Akzeptanzkriterium:** Bei geoeffnetem Drawer erreicht Tab ausschliesslich Drawer-Elemente; nach Escape liegt der Fokus wieder auf dem Hamburger-Button.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/MobileNav.tsx

### A11Y-05 — Die beiden wichtigsten Geld-CTAs (Checkout, Sign-in-Submit) fallen mit 3,30:1 durch den Textkontrast.

- **Screen/Workflow:** /trends/pricing (CheckoutButton), /account/signin (Submit-Button)
- **Persona:** Sehbehinderte Kaufinteressenten
- **Tier:** starter/pro/superpro
- **Beobachtung:** Berechnet: #ffffff auf #16a34a = 3,30:1 bei 14px/600 (kein Large Text, AA verlangt 4,5:1). CheckoutButton.tsx:30 `bg-[#16a34a] text-white text-sm font-semibold` — auf der Live-Pricing-Seite 6x als "Choose ..." gerendert; SignInForm.tsx:93 identisch (.signin-btn background:#16a34a; color:white). Auffaellig auch als einziger Fremdkoerper im sonst chartreuse/dunklen Designsystem (dort ist der Primaer-CTA #0a0c0a auf #d4ff3a = 16,98:1).
- **Auswirkung:** WCAG 1.4.3 Fail auf dem Bezahl-/Login-Pfad.
- **Empfohlene Lösung:** Auf das bestehende Accent-Pattern wechseln (bg-accent text-ink wie der Newsletter-Subscribe-Button) oder das Gruen auf mind. #15803d abdunkeln UND Schriftgroesse/Gewicht auf Large-Text heben — einfachster Fix: Token-Konsistenz mit lp-btn-primary.
- **Akzeptanzkriterium:** Kontrast Button-Text zu Button-Flaeche >= 4,5:1 auf /trends/pricing und /account/signin (nachgemessen).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/CheckoutButton.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx

### A11Y-06 — Alle mit text-muted/60 abgeschwaechten Texte liegen bei ~2,76:1 und fallen deutlich durch AA.

- **Screen/Workflow:** /trends (SearchInput-Placeholder, ScoreSlider-Skala, TrendCard-Quellname)
- **Persona:** Sehbehinderte Nutzer
- **Beobachtung:** Berechnet: #8a8d82 mit 60% Alpha ueber #0a0c0a ergibt ~#575952 = 2,76:1 (AA: 4,5:1). Betroffen: SearchInput.tsx:68 `placeholder:text-muted/60` (einzige sichtbare Feldbeschreibung!), ScoreSlider.tsx:62 Skalenwerte 0/50/100 in `text-muted/60` bei 9px, TrendCard.tsx:86 Quellname `text-muted/60`, TrendRadar radar-src opacity-55. Volles text-muted (#8a8d82) besteht dagegen mit 5,81:1.
- **Auswirkung:** WCAG 1.4.3 Fail; beim Suchfeld faellt damit die einzige Eingabehilfe unter die Wahrnehmbarkeitsschwelle.
- **Empfohlene Lösung:** /60-Abstufungen von text-muted entfernen (volles --color-muted verwenden) oder einen eigenen Token >= #7d8077 definieren, der auf #0a0c0a noch 4,5:1 erreicht.
- **Akzeptanzkriterium:** Kein gerenderter Text unter 4,5:1 (Stichprobe: Search-Placeholder, Slider-Skala, Card-Footer mit Kontrast-Tool geprueft).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/filters/SearchInput.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/ScoreSlider.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TrendCard.tsx

### A11Y-07 — Zwei tastaturbedienbare Controls entfernen den Fokusindikator ersatzlos.

- **Screen/Workflow:** /trends (ScoreSlider), /trends/newsletter (WeekSelector)
- **Persona:** Tastatur-Nutzer
- **Beobachtung:** ScoreSlider.tsx:79 setzt im styled-jsx `outline: none` auf das range-Input ohne jeglichen :focus-visible-Ersatz — der Slider ist per Pfeiltasten bedienbar, aber der Fokus ist unsichtbar. newsletter/page.tsx:194: WeekSelector-<select> mit `focus:outline-none` ohne Ersatz. (Zum Vergleich korrekt geloest: SearchInput/SortSelect kompensieren outline-none per focus-within:border-accent auf dem Wrapper.)
- **Auswirkung:** WCAG 2.4.7 Fail auf dem einzigen Slider der App und der Newsletter-Archivnavigation.
- **Empfohlene Lösung:** outline entfernen streichen und stattdessen `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px }` setzen; fuer den Slider zusaetzlich Thumb-Fokusstil (::-webkit-slider-thumb:focus-visible).
- **Akzeptanzkriterium:** Tab auf Slider und Wochen-Select zeigt einen sichtbaren Indikator mit >= 3:1 Kontrast zum Umfeld.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/filters/ScoreSlider.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx

### ARCH-07 — Es existiert keinerlei Fehler-, Lade- oder Not-Found-Infrastruktur — kein error.tsx, global-error.tsx, loading.tsx oder not-found.tsx im gesamten App-Baum.

- **Screen/Workflow:** global (alle Routen)
- **Persona:** Alle
- **Beobachtung:** find über src/app: 0 Treffer für error/not-found/loading/global-error. Alle 38 Seiten/Routen sind force-dynamic mit DB-Zugriff im Render-Pfad (pg.ts ohne Fallback); die Suspense-Grenzen in trends/page.tsx haben durchgehend fallback={null}. Bei einem DB-Ausfall wirft q() ungefangen → Next-Default-Fehlerseite; bei Navigation gibt es keinerlei Ladeindikator.
- **Ursache:** Die App wurde happy-path-first gebaut; Next-App-Router-Konventionsdateien wurden nie angelegt.
- **Auswirkung:** Jeder Postgres-Schluckauf zeigt Besuchern eine generische Next-Fehlerseite ohne Branding und Ausweg; langsame Seiten (7 s Landing!) wirken wie eingefroren, weil nichts einen Ladezustand anzeigt.
- **Empfohlene Lösung:** app/error.tsx + global-error.tsx (Branding, 'Kurz nicht erreichbar', Retry-Button), app/not-found.tsx (siehe ARCH-14) und mindestens für /trends und /trends/foresight/* loading.tsx-Skeletons anlegen; Suspense-Fallbacks mit einfachen Platzhaltern statt null füllen.
- **Akzeptanzkriterium:** Bei gestopptem Postgres rendert jede Seite eine gebrandete Fehlerseite mit Navigation; beim Wechsel auf /trends erscheint sofort ein Skeleton.
- **Aufwand:** M · **Dateien:** frontend/src/app/layout.tsx, frontend/src/app/trends/page.tsx, frontend/src/lib/pg.ts

### ARCH-08 — Die Hauptnavigation nutzt rohe <a>-Tags statt next/link und hat keinerlei aktiven Zustand — jeder Klick ist ein Full-Page-Reload ohne Orientierung, wo man ist.

- **Screen/Workflow:** Header (alle Seiten)
- **Persona:** Alle
- **Beobachtung:** Header.tsx rendert alle NAV_ITEMS als <a href> (Zeilen 28–45); grep über components: kein einziges usePathname/aria-current. Damit entfallen Client-Transitions und Prefetching komplett, und keiner der 10 Einträge markiert je die aktuelle Seite.
- **Ursache:** Header wurde als rein statische Server-Komponente ohne Pfad-Kenntnis gebaut; Link-Komponente wird andernorts (TierGate, Pricing) korrekt genutzt, nur die zentrale Nav nicht.
- **Auswirkung:** Auf einer force-dynamic-App ohne loading-States bedeutet jeder Nav-Klick einen harten, weißen Reload (bei / bis 7 s); Nutzer verlieren zusätzlich die Verortung zwischen 10 ähnlich benannten Foresight-Zielen.
- **Empfohlene Lösung:** NAV_ITEMS über next/link rendern und eine kleine Client-Teilkomponente mit usePathname für aria-current + visuellen Aktiv-Stil (Accent-Unterstreichung) einführen; MobileNav gleichziehen.
- **Akzeptanzkriterium:** Klick auf einen Nav-Eintrag löst eine Client-Transition aus (kein document-Reload im Network-Tab) und der aktive Eintrag ist visuell + per aria-current markiert.
- **Aufwand:** S · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/MobileNav.tsx

### ARCH-09 — Der Checkout-Button schluckt alle Fehler stumm und verliert beim Login-Umweg den Kaufkontext.

- **Screen/Workflow:** /trends/pricing (CheckoutButton)
- **Persona:** Kaufinteressent
- **Tier:** free
- **Beobachtung:** CheckoutButton.tsx: bei !data.url ohne needSignin (also 503 'billing not configured', 400, 502 'checkout failed') wird nur setBusy(false) ausgeführt — keinerlei Meldung; der catch-Block ist leer. Bei 401 wird hart auf /account/signin umgeleitet ohne returnTo; nach Magic-Link-Login landet der Nutzer laut callback/route.ts auf /account — nicht zurück auf der Pricing-Seite.
- **Ursache:** Fehler- und Kontextpfade des Kauf-Flows wurden nicht zu Ende gebaut (kein Fehler-State im Button, kein next-Parameter im Auth-Flow).
- **Auswirkung:** Ein Klick auf 'Choose Pro' kann kommentarlos nichts tun (Kaufabbruch ohne Erklärung); wer sich erst einloggen muss, wird aus dem Kauf-Funnel geworfen und muss Pricing selbst wiederfinden.
- **Empfohlene Lösung:** Im Button einen sichtbaren Fehlerzustand ergänzen ('Checkout derzeit nicht möglich — bitte später erneut versuchen'); needSignin-Redirect mit ?next=/trends/pricing versehen und callback/route.ts einen validierten next-Parameter (Whitelist interner Pfade) respektieren lassen.
- **Akzeptanzkriterium:** Bei abgeschaltetem Stripe-Key zeigt der Klick eine Fehlermeldung; ein nicht eingeloggter Kaufklick führt nach Magic-Link-Login zurück auf /trends/pricing.
- **Aufwand:** S · **Dateien:** frontend/src/components/CheckoutButton.tsx, frontend/src/app/api/auth/callback/route.ts, frontend/src/app/api/stripe/checkout/route.ts

### ARCH-10 — Es gibt keinerlei Subscription-Management — Kunden können weder kündigen noch Zahlungsdaten ändern noch up-/downgraden.

- **Screen/Workflow:** /account
- **Persona:** Zahlender Kunde
- **Tier:** starter/pro/superpro
- **Beobachtung:** account/page.tsx zeigt nur Tier-Label + Blurb + Logout; ein Stripe-Billing-Portal-Endpoint existiert nicht (api/stripe/ enthält nur checkout und webhook). Der Upgrade-Link ('See plans →') erscheint sogar nur bei tier==='free' — ein Starter-Kunde hat nicht mal einen Upgrade-Pfad auf der Kontoseite.
- **Ursache:** Der Webhook verarbeitet subscription.deleted korrekt (Downgrade auf free), aber es wurde nie eine UI gebaut, die dieses Event auslösen kann.
- **Auswirkung:** Kündigung ist nur per Support-Mail möglich — rechtlich problematisch (EU-Kündigungsbutton-Pflicht für Verbraucher, und auch B2B erwartet Self-Service) und maximale Reibung für Bestandskunden.
- **Empfohlene Lösung:** POST /api/stripe/portal (Billing-Portal-Session via customer id, analog zum fetch-basierten stripe.ts-Stil) + 'Manage subscription'-Button auf /account; 'See plans →' für alle Tiers anzeigen.
- **Akzeptanzkriterium:** Ein Test-Abonnent erreicht aus /account das Stripe-Billing-Portal, kündigt dort, und der Webhook setzt sein Tier auf free (auf /account sichtbar).
- **Aufwand:** M · **Dateien:** frontend/src/app/account/page.tsx, frontend/src/lib/stripe.ts

### ARCH-11 — Die Hauptseite feuert 7 sequentielle DB-Queries pro Request, darunter drei Full-Table-Aggregationen — bei jedem Aufruf neu.

- **Screen/Workflow:** /trends
- **Persona:** Alle Leser
- **Beobachtung:** trends/page.tsx awaited nacheinander: getTrendsFiltered, getTrendsFilteredCount, getVerticalCountsScoped, getVerticalCounts, getTrendsCount (COUNT über alle ~1M trends), getMegaTrends (GROUP BY über die ganze Tabelle), getTopSourcesByCount. Gemessen: konstant ~0,51 s pro Request; force-dynamic, kein Cache.
- **Ursache:** Unabhängige Queries werden seriell awaited statt per Promise.all; die filterunabhängigen Aggregate (globale Counts, Mega-Optionen, Quellen) werden nicht gecacht.
- **Auswirkung:** Eine halbe Sekunde Serverzeit pro Feed-Aufruf skaliert schlecht und addiert sich zum Full-Reload-Navigationsmodell (ARCH-08) zu spürbar zäher Bedienung.
- **Empfohlene Lösung:** Die 7 Aufrufe in Promise.all bündeln; getVerticalCounts/getMegaTrends/getTopSourcesByCount/getTrendsCount mit unstable_cache (revalidate 300–3600 s) versehen — nur getTrendsFiltered(+Count) muss request-frisch sein.
- **Akzeptanzkriterium:** curl -w time_total auf /trends liegt wiederholt unter 200 ms; Filterwechsel liefern weiterhin korrekte Counts.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/page.tsx, frontend/src/lib/db.ts

### ARCH-12 — Die einzige inhaltlich Pro-gegatete Seite zeigt live nur den Empty-State — ein zahlender Pro-Kunde bekäme für sein Geld eine leere Seite, und das Gate/Teaser-Muster ist nirgends erlebbar.

- **Screen/Workflow:** /trends/foresight/evolution
- **Persona:** Pro-Kunde
- **Tier:** pro
- **Beobachtung:** curl auf /trends/foresight/evolution: HTML enthält zweimal 'Evolution is being computed' und keinerlei Threads/Upgrade-Marker — getLatestLineage('global') liefert null (kein Lineage-Artefakt in der DB). Damit wird der TierGate-Block (Zeilen 157–178) nie erreicht.
- **Ursache:** Das Lineage-Snapshot-Artefakt (Pipeline-Seite) fehlt für den global-Scope; die Seite hängt vollständig an diesem Batch-Output.
- **Auswirkung:** Das Pro-Verkaufsargument 'Trend evolution & lineage' ist aktuell nicht demonstrierbar; zusammen mit ARCH-01 existiert damit im Live-Zustand kein einziger sichtbarer Free→Pro-Kontrast.
- **Empfohlene Lösung:** Lineage-Snapshot-Job für global (und die Vertical-Scopes) laufen lassen bzw. in den scheduled Cycle aufnehmen; zusätzlich einen Monitoring-Hinweis für den Owner (leerer Scope = Pipeline-Regression, nicht nur UX-Empty-State).
- **Akzeptanzkriterium:** /trends/foresight/evolution zeigt ohne Login 'Emerging now' + Upgrade-Card, mit Pro-Session zusätzlich 'Established & moving'/'Fading' mit realen Threads.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/foresight/evolution/page.tsx, frontend/src/lib/foresight.ts

### ARCH-13 — Der wichtigste wiederkehrende Conversion-CTA ('Discover Catandary Foresight →') führt aus dem Produkt heraus auf die externe catandary.de statt auf die eigene Pricing-Seite.

- **Screen/Workflow:** /trends/* (ForesightCta, auf fast jeder Seite)
- **Persona:** Free-User mit Kaufinteresse
- **Beobachtung:** ForesightCta.tsx verlinkt beide CTAs auf https://catandary.de; die Komponente wird auf /trends, Artikelseiten, mega-, evolution- u. a. Seiten gerendert. Die interne /trends/pricing existiert seit dem Tier-Ausbau, wird vom CTA aber ignoriert.
- **Ursache:** Der CTA stammt aus der Zeit vor der eigenen Pricing-/Checkout-Strecke und wurde nicht nachgezogen.
- **Auswirkung:** Interessierte Leser werden an der teuersten Stelle des Funnels auf eine externe Seite ohne Checkout geschickt — die eigene Kaufstrecke bleibt unbespielt.
- **Empfohlene Lösung:** ForesightCta auf /trends/pricing (intern, next/link) umstellen; der externe Firmenlink bleibt im Footer erhalten.
- **Akzeptanzkriterium:** Alle ForesightCta-Instanzen navigieren intern auf /trends/pricing.
- **Aufwand:** S · **Dateien:** frontend/src/components/ForesightCta.tsx

### ARCH-14 — Es gibt keinerlei Impressum- oder Datenschutz-Seite bzw. -Link — für den geplanten öffentlichen DE-Launch (catandary.de, Newsletter, Bezahlung) rechtlich zwingend.

- **Screen/Workflow:** Footer (global)
- **Persona:** Owner / Rechtliches
- **Beobachtung:** Footer.tsx enthält nur Copyright, 'How we measure' und den externen Foresight-Link; find/grep über src: keine Route und kein Link zu Impressum/Privacy/Datenschutz. Gleichzeitig werden E-Mail-Adressen (Newsletter, Auth) und Zahlungsdaten (Stripe) verarbeitet.
- **Ursache:** Rechtsseiten wurden im Launch-Paket bisher nicht angelegt.
- **Auswirkung:** Abmahnrisiko ab dem ersten öffentlichen Tag (Impressumspflicht §5 DDG, DSGVO-Informationspflichten bei Newsletter/Auth/Stripe); auch Stripe-Live-Freischaltung erwartet ein Impressum.
- **Empfohlene Lösung:** Statische Seiten /imprint und /privacy anlegen (reine Server-Komponenten) und im Footer verlinken; Newsletter-/Signin-Formulare mit Privacy-Hinweis versehen.
- **Akzeptanzkriterium:** Footer jeder Seite verlinkt auf erreichbare Impressum- und Datenschutz-Seiten mit den Pflichtangaben.
- **Aufwand:** S · **Dateien:** frontend/src/components/Footer.tsx, frontend/src/app/layout.tsx

### ARCH-15 — Das Pro-Aushängeschild 'Dossier + CSV-Export' ist eine unverlinkte Waisen-Seite, und der CSV-Link zeigt Free-Usern rohes JSON als Fehlerseite.

- **Screen/Workflow:** /trends/foresight/dossier (+ ExportButton)
- **Persona:** Pro-Interessent
- **Tier:** pro
- **Beobachtung:** grep über src: foresight/dossier wird ausschließlich in der eigenen Datei referenziert — kein Link aus Nav, Clusters oder Landing. ExportButton.tsx rendert den CSV-Export als nacktes <a href='/api/foresight/export...'>; ohne Pro-Session antwortet die API mit HTTP 402 {'error':'Pro plan required'} — der Browser zeigt diese JSON-Zeile als ganze Seite (live verifiziert).
- **Ursache:** Seite wurde gebaut, aber nie in die Informationsarchitektur eingehängt; der Export-Fehlerpfad wurde nicht als UI-Fall behandelt.
- **Auswirkung:** Ein verkaufsrelevantes Pro-Feature ist unauffindbar; wer es doch findet und nicht Pro ist, endet auf einer rohen JSON-Fehlerseite statt einem Upgrade-Prompt.
- **Empfohlene Lösung:** Dossier aus der Clusters-Seite und/oder Foresight-Übersicht verlinken; ExportButton per fetch downloaden lassen und bei 402 eine Upgrade-Meldung mit Pricing-Link rendern (statt Browser-Navigation auf die API).
- **Akzeptanzkriterium:** Dossier ist über mindestens einen sichtbaren Link erreichbar; Klick auf 'Download CSV' ohne Pro zeigt eine In-Page-Upgrade-Meldung, nie rohes JSON.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/foresight/dossier/page.tsx, frontend/src/components/foresight/ExportButton.tsx, frontend/src/app/api/foresight/export/route.ts

### CONF-03 — Die Technology-API gibt den rohen JSONB-Payload inklusive interner Methoden-/Build-Felder an den Client aus, die nicht fuer die Anzeige bestimmt sind.

- **Screen/Workflow:** /api/foresight/technology (frontend/src/lib/technology.ts getTechnology)
- **Persona:** Wettbewerber (Methoden-Reverse-Engineering)
- **Tier:** Internal
- **Beobachtung:** `getTechnology`/`getTechnologies` (technology.ts:60-74) selektieren `payload` komplett und die Route (technology/route.ts:22) gibt `tech` unveraendert zurueck. curl `/api/foresight/technology?cpc=H02S` liefert im `patent_dynamics`-Block interne Felder: `tir_method:"spnp-fullarchive"`, `built_in_s`, `cycle_cov:8158`, `tir_n:56954`, `tir_earliest:1901`. Der Code kommentiert intern zusaetzlich die Index-Formel (technology.ts:42 'immediate importance × 1/cycle-time', 'blueprint §2.1.1').
- **Ursache:** Kein DTO/Field-Whitelisting — der komplette Snapshot-Payload wird 1:1 durchgereicht.
- **Auswirkung:** Interne Methoden-Identifier und Kalibrierungs-Parameter (der laut Truth-Matrix schuetzenswerte 'edge': Korpus + Kalibrierung) werden preisgegeben; erleichtert Nachbau durch Wettbewerber mit identischer SPNP-Basis.
- **Empfohlene Lösung:** Im API-Layer nur die Anzeigefelder projizieren (lead_time-Serien, cycle_time_years, tir_pct, tir_direction, top_patents, convergence) und interne Felder (tir_method, built_in_s, cycle_cov, tir_n, tir_earliest) vor der Response entfernen. Idealerweise ein explizites `TechPublicPayload`-Mapping statt Passthrough.
- **Akzeptanzkriterium:** `curl '/api/foresight/technology?cpc=H02S'` enthaelt keine Schluessel tir_method/built_in_s/cycle_cov/tir_n/tir_earliest mehr; nur kuratierte Anzeigefelder bleiben.
- **Aufwand:** S · **Dateien:** frontend/src/lib/technology.ts, frontend/src/app/api/foresight/technology/route.ts

### COPY-05 — Die Newsletter-Einwilligung ist beim Sign-in vorangekreuzt — ein klassisches Dark Pattern und unter DSGVO (EuGH Planet49) keine wirksame Einwilligung.

- **Screen/Workflow:** /account/signin (Newsletter-Checkbox)
- **Persona:** Neuer Account-Nutzer
- **Tier:** free
- **Beobachtung:** SignInForm.tsx:12 initialisiert `useState(true)` für die Checkbox "Also send me the weekly trend newsletter"; im Live-HTML von /account/signin ist die Box vorab gesetzt.
- **Ursache:** Growth-freundlicher Default ohne Consent-Prüfung.
- **Auswirkung:** Rechtliches Risiko (unwirksame Einwilligung, Abmahnbarkeit) und Vertrauensschaden bei genau der B2B-Zielgruppe, der die Landing "no tracking cookies" verspricht.
- **Empfohlene Lösung:** Default auf `useState(false)` setzen; die Checkbox-Zeile darf werben ("Also get the weekly briefing — 1 email/week"), aber nicht vorab angekreuzt sein.
- **Akzeptanzkriterium:** Checkbox auf /account/signin ist initial nicht gesetzt; Newsletter-Anmeldung erfolgt nur bei aktivem Anhaken.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx

### COPY-06 — Export-Buttons sind für Free-Nutzer sichtbar und "Download CSV" endet auf einer rohen JSON-Fehlerseite ohne Rückweg.

- **Screen/Workflow:** /trends/foresight/dossier (Free-Ansicht)
- **Persona:** Free-Nutzer vor dem Gate
- **Tier:** free
- **Beobachtung:** ExportButton wird außerhalb des TierGate gerendert (dossier/page.tsx:72 vor TierGate Z.75); "Download CSV" ist ein <a href> auf /api/foresight/export, das für Free HTTP 402 mit Body {"error":"Pro plan required"} liefert (export/route.ts:22, live verifiziert) — der Browser navigiert auf die nackte JSON-Antwort. "Print / PDF" druckt die Gate-Karte.
- **Ursache:** Button-Platzierung außerhalb des Gates + Link statt gehandelter Aktion.
- **Auswirkung:** Frustmoment mit Sackgasse: sichtbares Feature, das beim Klick in einer Fehlerseite ohne Upgrade-Pfad endet — das Gegenteil des fairen TierGate-Patterns.
- **Empfohlene Lösung:** ExportButton in den TierGate-Children rendern (nur für Pro sichtbar) oder für Free deaktiviert mit Inline-Hinweis "CSV export is part of Pro — see plans →" darstellen; nie auf rohe JSON navigieren.
- **Akzeptanzkriterium:** Als Free-Nutzer führt kein Klick auf der Dossier-Seite auf eine JSON-Fehlerantwort; der Export ist entweder unsichtbar oder erklärt gesperrt mit Pricing-Link.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/dossier/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/ExportButton.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/api/foresight/export/route.ts

### COPY-07 — Die Pricing-Seite erklärt dem Kunden die eigene Marketing-Strategie statt seinen Nutzen: er wird als "lead magnet"-Ziel adressiert.

- **Screen/Workflow:** /trends/pricing (Intro-Text)
- **Persona:** Kaufinteressent
- **Tier:** free
- **Beobachtung:** Wörtlich auf der Live-Seite: "the free feed is the lead magnet, the paid tiers are where the lead-time edge lives" (app/trends/pricing/page.tsx:35-37). "Lead magnet" ist Innensicht (wie WIR euch akquirieren), keine Nutzenaussage (was IHR bekommt).
- **Ursache:** Interne Positionierungsnotiz (Owner-Sprache aus tiers.ts-Kommentaren) in Kunden-Copy durchgesickert.
- **Auswirkung:** Wirkt zynisch und entwertet den Free-Layer ("nur ein Köder") — genau vor der Preisliste, wo Reziprozität und Vertrauen kaufentscheidend sind.
- **Empfohlene Lösung:** Nutzenformulierung: "The curated feed and weekly briefing are free — the paid tiers add the lead-time edge: see what's rising months before the market, with evidence you can cite."
- **Akzeptanzkriterium:** Der Begriff "lead magnet" (und vergleichbare Innensicht-Formulierungen) kommt in keiner kundensichtbaren Copy mehr vor.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx

### COPY-08 — Die Featurelisten der teuren Tiers sind reine Feature-/Jargon-Sprache ohne Nutzenübersetzung — der Mehrwert von Pro (499) und Super Pro+ (799) wird nicht verkauft.

- **Screen/Workflow:** /trends/pricing (Feature-Listen)
- **Persona:** Nicht-technischer Entscheider (Budget-Freigabe)
- **Tier:** pro/superpro
- **Beobachtung:** Wörtlich aus lib/tiers.ts: "Technology explorer: CPC lead-time axes" (Z.64), "TIR metrics (cycle time, immediate importance)" (Z.65), "On-demand analysis of your own scopes (lazy-embed)" (Z.78), "Raw evidence graph" (Z.80), "Corpus counter & mega-trend teasers" (Z.40). CPC, TIR und lazy-embed werden nirgends auf der Seite erklärt; "lazy-embed" ist ein internes Implementierungsdetail. Der Sprung 99→499 EUR wird nur durch diese Jargon-Zeilen begründet.
- **Ursache:** Featurematrix wurde 1:1 aus der Engineering-Sicht (Owner-Notiz) übernommen.
- **Auswirkung:** Wer das Budget freigibt, versteht den 5x-Preissprung nicht; kognitive Last verlagert die Entscheidung auf "später" — der teuerste Abbruchpunkt.
- **Empfohlene Lösung:** Jede Feature-Zeile als Nutzen + Feature formulieren, z.B. "See how fast any technology improves — peer-reviewed improvement rates (TIR)", "Know how early you are: research-to-market lead times per technology", "Analyze any topic you bring — on-demand, results in minutes". "lazy-embed" und "Corpus counter" streichen.
- **Akzeptanzkriterium:** Keine unerklärte Abkürzung (CPC, TIR) und kein Implementierungsjargon (lazy-embed) in TIERS-features; jede Pro-/Superpro-Zeile beginnt mit dem Nutzen.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/lib/tiers.ts

### COPY-09 — Anonyme Besucher sehen auf der Free-Karte "Your current plan" — falsche Personalisierung, die den Sign-up-CTA ersetzt.

- **Screen/Workflow:** /trends/pricing (Free-Karte, anonym)
- **Persona:** Anonymer Besucher
- **Tier:** free
- **Beobachtung:** viewerTier() liefert für nicht eingeloggte Besucher "free" (lib/entitlement.ts:15-17); pricing/page.tsx:68 rendert dann "Your current plan" statt des "Sign up free"-Links (Z.72-77). Live per curl (ohne Cookie) verifiziert: 2x "Your current plan", kein "Sign up free".
- **Ursache:** isCurrent unterscheidet nicht zwischen "eingeloggt mit free" und "gar kein Account".
- **Auswirkung:** Suggeriert fälschlich einen bestehenden Account und eliminiert den Account-Erstellungs-CTA — der Einstieg in den Funnel (Email-Capture) geht auf der wichtigsten Seite verloren.
- **Empfohlene Lösung:** In PricingPage zusätzlich prüfen, ob eine Session existiert: ohne Session auf der Free-Karte "Sign up free" zeigen, "Your current plan" nur für eingeloggte Free-Nutzer.
- **Akzeptanzkriterium:** curl ohne Session-Cookie auf /trends/pricing enthält "Sign up free" und kein "Your current plan".
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/lib/entitlement.ts

### COPY-10 — Die beiden Foresight-Upsell-CTAs der Mega-Trend-Seiten sind tot bzw. irreführend: einer ist ein nicht klickbarer Span, der andere verlinkt woandershin als beschriftet.

- **Screen/Workflow:** /trends/mega und /trends/mega/[megatrend] (Premium-CTAs)
- **Persona:** Free-Nutzer mit Foresight-Interesse
- **Tier:** free
- **Beobachtung:** MegaTrendHeader.tsx:85-89: "Want the full mega-trend forecast? Discover Catandary Foresight →" ist ein <span> ohne <a>/<Link> — akzentfarben mit Pfeil, sieht klickbar aus, tut nichts. MegaTrendsPage.tsx:150-152: "Full Forecast / Catandary Foresight →" ist Teil des Karten-Links und führt zur Mega-Detailseite, nicht zu Foresight.
- **Ursache:** CTA-Optik ohne verdrahtetes Ziel; Karten-Link umschließt die CTA-Zeile.
- **Auswirkung:** Der Teaser-Layer (laut Strategie der Brückenpfeiler zu Foresight) endet in einer Sackgasse — Interessenten mit Kaufsignal werden fallengelassen.
- **Empfohlene Lösung:** Beide CTAs auf /trends/foresight (oder /trends/pricing) verlinken; die Kartenzeile umbenennen in "Open mega-trend →" wenn sie zur Detailseite führt.
- **Akzeptanzkriterium:** Jeder als "Foresight/Forecast" beschriftete CTA auf den Mega-Seiten ist ein echter Link und führt auf eine Foresight- oder Pricing-Route.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/MegaTrendHeader.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/MegaTrendsPage.tsx

### COPY-11 — Der meistplatzierte Upsell-CTA ("Discover Catandary Foresight →") führt aus dem Produkt heraus auf die externe Domain-Root statt zum In-App-Foresight oder Pricing.

- **Screen/Workflow:** /trends, Artikel-Seiten, /trends/methodology (ForesightCta)
- **Persona:** Free-Nutzer am Ende jedes Artikels
- **Tier:** free
- **Beobachtung:** ForesightCta.tsx:12 und :35 verlinken auf https://catandary.de (absolute externe URL); der Baustein hängt unter jedem Artikel, auf /trends und /trends/methodology. Auf localhost:3001 springt der Klick sogar auf die Produktiv-Domain. Der Text verspricht zudem "strategic recommendations tailored to your business" — ein Deliverable, das kein Subscription-Tier enthält (nur Hypercare).
- **Ursache:** CTA stammt aus der Zeit vor dem In-App-Foresight; Zieladresse und Versprechen nie aktualisiert.
- **Auswirkung:** Conversion-Traffic wird auf die Landing zurückgeworfen statt in Cockpit/Pricing geführt; das übersteigerte Versprechen ("tailored to your business") erzeugt Erwartungsbruch im Free-zu-Paid-Übergang.
- **Empfohlene Lösung:** href auf /trends/foresight (compact: /trends/pricing) ändern; Copy auf reale Tier-Leistung anpassen: "See momentum, lead-time and evidence for any topic — Catandary Foresight →".
- **Akzeptanzkriterium:** ForesightCta verlinkt nur noch auf interne Routen; kein CTA-Text verspricht Leistungen, die kein Tier enthält.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCta.tsx

### COPY-12 — Bei aktivem Auth+Paywall gibt es in Header und Footer weder "Plans/Pricing" noch "Sign in/Account" — die Monetarisierung ist unauffindbar.

- **Screen/Workflow:** Header/Footer (alle Seiten)
- **Persona:** Kaufinteressent & wiederkehrender Kunde
- **Tier:** free
- **Beobachtung:** Header.tsx:3-14 listet 10 Nav-Items (Trends…Technology, extern "Catandary") + Newsletter-Button; Footer.tsx enthält nur Copyright, "How we measure" und "Powered by Catandary Foresight". /trends/pricing ist nur über TierGates (die es nur auf Evolution/Dossier gibt, COPY-04) und die Landing erreichbar; /account nur per URL-Eingabe.
- **Ursache:** Nav wurde vor Einführung von Auth/Paywall gebaut und nicht erweitert.
- **Auswirkung:** Zahlungsbereite Nutzer finden den Kaufpfad nicht; eingeloggte Kunden finden ihren Account nicht — beides erhöht Support-Aufwand und drückt Conversion.
- **Empfohlene Lösung:** "Plans" in Header (oder mindestens Footer) aufnehmen; rechts neben Newsletter ein "Sign in"/"Account"-Link, der auf Session-Status reagiert.
- **Akzeptanzkriterium:** Von jeder Seite aus sind /trends/pricing und /account/signin (bzw. /account) mit maximal einem Klick über die persistente Navigation erreichbar.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/Header.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/Footer.tsx

### COPY-13 — Der Kauf-Button scheitert stumm und verliert bei ausgeloggten Nutzern die Kauf-Intention.

- **Screen/Workflow:** /trends/pricing (CheckoutButton)
- **Persona:** Kaufwilliger Nutzer
- **Tier:** starter/pro/superpro
- **Beobachtung:** CheckoutButton.tsx: bei Fehlerantworten ohne url und ohne needSignin (z.B. 503 "billing not configured", 502 "checkout failed") wird nur busy zurückgesetzt — keinerlei Meldung (Z.19-25); im catch ebenso. Busy-Label ist "…" (Z.33). Ausgeloggte werden kommentarlos auf /account/signin geworfen (Z.21), der Auth-Callback landet danach auf /account (auth/callback/route.ts:22) — der gewählte Tier ist vergessen.
- **Ursache:** Fehler- und Intent-Handling im Checkout-Flow nicht ausgebaut.
- **Auswirkung:** Nutzer klickt "Choose Pro", nichts passiert (oder er landet nach Magic-Link im Account statt im Checkout) — der Kaufimpuls verpufft genau am Zahlmoment.
- **Empfohlene Lösung:** Fehlerzeile unter dem Button ("Checkout didn't start — please try again or contact us"); Busy-Label "Opening checkout…"; bei needSignin Redirect mit Kontext (z.B. /account/signin?next=checkout:pro) und Hinweis "Sign in first — we'll bring you right back to checkout", Callback wertet next aus.
- **Akzeptanzkriterium:** Jeder Fehlerpfad des Checkout-Starts zeigt eine sichtbare Meldung; nach Sign-in via Checkout-Einstieg landet der Nutzer wieder im Checkout des gewählten Tiers (oder mindestens auf /trends/pricing mit Hinweis).
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/CheckoutButton.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/api/auth/callback/route.ts

### COPY-14 — Deutsche Meta-Descriptions auf englischen Seiten und ein deutscher API-Fehlertext im englischen Foresight.

- **Screen/Workflow:** Meta-Descriptions + Foresight-Fehlertexte
- **Persona:** SEO-Besucher / Foresight-Nutzer
- **Tier:** free
- **Beobachtung:** app/trends/foresight/page.tsx:14: description "Semantische Trend-Suche mit Signal-Timeline, Lead-Time-Analyse und Cross-Vertical-Insights."; app/trends/cross-vertical/page.tsx:11: "Trend-Signale, die mehrere Branchen gleichzeitig betreffen."; app/api/foresight/analyze/route.ts:83 liefert bei Timeout "Berechnung dauert zu lange — bitte erneut versuchen (GPU wird geladen)" — angezeigt im (nach COPY-02 englischen) Technology-Tool.
- **Ursache:** Reste der ursprünglich zweisprachigen Ausrichtung.
- **Auswirkung:** Google zeigt deutsche Snippets für englische Seiten (CTR-Verlust, Sprachsignal-Verwirrung bei html lang=en); der deutsche GPU-Fehler wirkt wie ein Systemleck.
- **Empfohlene Lösung:** Beide Descriptions auf Englisch umstellen; Timeout-Fehler z.B. "This analysis is taking longer than usual (the model is warming up) — please try again in a minute."
- **Akzeptanzkriterium:** Alle metadata.description-Strings und alle API-Fehlertexte, die im UI landen, sind englisch.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/cross-vertical/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/api/foresight/analyze/route.ts

### COPY-15 — Das Sign-in-Formular verdeckt den Rate-Limit-Fall hinter einer generischen Fehlermeldung, die zum sofortigen Retry auffordert — und das Limit damit verschärft.

- **Screen/Workflow:** /account/signin (Fehler-Feedback)
- **Persona:** Nutzer im Rate-Limit
- **Tier:** free
- **Beobachtung:** SignInForm.tsx:26 wirft bei jedem !res.ok weg, was die API sagt; Z.63 zeigt immer "Something went wrong. Please try again." Die API antwortet aber differenziert: 429 "too many requests" mit retry-after 60/300s, 502 "could not send sign-in email" (app/api/auth/request/route.ts:55-58,69).
- **Ursache:** Fehlerbody wird im Client nicht ausgewertet.
- **Auswirkung:** Nutzer im Rate-Limit retryen in Schleife und kommen nie rein; bei Mail-Ausfall fehlt der Hinweis, dass es nicht an ihnen liegt.
- **Empfohlene Lösung:** Status auswerten: 429 → "Too many attempts — please wait a minute and try again."; 5xx → "We couldn't send the email right now — please try again shortly."
- **Akzeptanzkriterium:** 429- und 5xx-Antworten der Auth-Request-API führen zu unterscheidbaren, handlungsleitenden Meldungen im Formular.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/api/auth/request/route.ts

### DS-02 — Die 43-fach genutzte Klasse text-text zeigt auf ein nicht definiertes Token und wird still verworfen — Textfarben funktionieren nur zufällig über Vererbung, Inline-Hervorhebungen scheitern real.

- **Screen/Workflow:** Clusters, Lead-Time, Technology, Methodology, Newsletter, Quality-Preview, TrendsHero u.a. (43 Stellen)
- **Beobachtung:** `--color-text` fehlt im @theme; `.text-text` kommt im kompilierten CSS nicht vor (verifiziert per grep), wird aber z.B. 196× im Live-HTML von /trends/foresight/clusters ausgeliefert. Konkret sichtbar defekt: lead-time/page.tsx:88 — `<span className="text-text">timing, not volume</span>` innerhalb eines text-muted-Absatzes bleibt muted statt hervorgehoben; quality-preview/page.tsx:158/197 — `text-text/85` verliert die 85%-Abstufung komplett.
- **Ursache:** Vermutlich Umbenennung des Tokens (DESIGN_REVAMP nennt --text) ohne Definition in @theme; Tailwind v4 meldet unbekannte Utilities nicht.
- **Auswirkung:** Bewusste Text-Hierarchie (foreground vs. muted vs. Hervorhebung) greift an dutzenden Stellen nicht; jede Änderung der Eltern-Textfarbe bricht unbeabsichtigt Kindtexte.
- **Empfohlene Lösung:** `--color-text: #d8d5c8;` (Alias auf foreground) im @theme definieren — deckt alle 43 Stellen sofort — oder projektweit auf text-foreground refactoren; ESLint-Regel/Check gegen unbekannte Farb-Utilities ergänzen.
- **Akzeptanzkriterium:** `.text-text` (inkl. /85-Variante) existiert im kompilierten CSS; auf /trends/foresight/lead-time ist "timing, not volume" sichtbar heller als der umgebende muted-Text.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/lead-time/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/quality-preview/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TrendsHero.tsx

### DS-03 — Die Lead-Time-Tier-Farbcodierung (das zentrale Produktkonzept) ist auf der Landing anders belegt als im Produkt-Chart — Violett bedeutet auf der Landing Science, im Chart Patents.

- **Screen/Workflow:** Landing (/) vs. /trends/foresight/lead-time
- **Beobachtung:** Landing (HeroInstrument.tsx:14-19, TechReader.tsx:30, globals.css --t-*): SCIENCE #a78bfa, PATENTS #60a5fa, FUNDING #34d399, MARKET #d4ff3a. TierCurveChart.tsx:17-22 dagegen: Research #22d3ee (cyan), Patents #a78bfa (violett), Funding #fb923c (orange), Market #bde63a. Die in globals.css:200-203 eigens definierten --t-*-Tokens werden vom Chart ignoriert.
- **Ursache:** TierCurveChart wurde mit eigener, CVD-optimierter Palette gebaut (Kommentar im File), ohne die Landing-Tokens zu konsolidieren.
- **Auswirkung:** Wer vom Landing-Hero ("science -> market") in die Lead-Time-View klickt, muss die Farbsemantik neu lernen; Violett wechselt die Bedeutung — aktives Fehllese-Risiko beim USP-Feature.
- **Empfohlene Lösung:** Eine kanonische Tier-Palette festlegen (empfohlen: die CVD-geprüfte Chart-Palette), als globale Tokens --t-science/--t-patent/--t-funding/--t-market definieren und HeroInstrument, TechReader, lp-Pillar-Icons (page.tsx:162-165) und TierCurveChart daraus speisen.
- **Akzeptanzkriterium:** Science/Research, Patents, Funding, Market haben auf Landing-Hero, TechReader-Lanes und TierCurveChart identische Hex-Werte (ein Grep pro Farbe zeigt nur noch die Token-Definition).
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TierCurveChart.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/landing/HeroInstrument.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/landing/TechReader.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/app/page.tsx

### DS-04 — Die komplette Monetarisierungs- und Auth-Strecke nutzt ein zweites, generisches Designsystem (rounded-2xl, font-bold, grünes #16a34a), das mit der Editorial-Identität bricht — genau dort, wo bezahlt werden soll.

- **Screen/Workflow:** /trends/pricing, /account, /account/signin, TierGate (Radar/Evolution/Dossier)
- **Tier:** free→paid (Conversion-Strecke)
- **Beobachtung:** pricing/page.tsx:50 `rounded-2xl border`, Z.33 `text-3xl font-bold` (Sans statt font-display); CheckoutButton.tsx:31 `rounded-lg bg-[#16a34a] text-white`; TierGate.tsx:40 grüner Pill-Badge #16a34a + border-radius 14px + `color: canvas` im Hover (Z.44, ungetesteter Systemfarbwert auf Dark-Theme); SignInForm.tsx:87-93 rounded 16px Card + grüner Button; account/page.tsx:24 rounded-xl. Kontrast dazu: die Landing-Pricing-Sektion (lp-prices) ist mono/chartreuse/scharfkantig. AUTH_ENABLED=1 + PAYWALL_ENABLED=1 machen diese Flächen aktuell für jeden Besucher sichtbar.
- **Ursache:** Auth/Paywall-Epic (W2) wurde funktional gebaut, bevor die Editorial-Sprache auf diese Flächen ausgerollt wurde; grün #16a34a als improvisierte "Erfolgs"-Farbe.
- **Auswirkung:** Der Interessent erlebt beim Klick von der hochwertigen Landing auf /trends/pricing einen sichtbaren Produktwechsel — Vertrauensverlust an der teuersten Stelle des Funnels (99-799 EUR/Monat B2B).
- **Empfohlene Lösung:** Pricing/Account/SignIn/TierGate auf die Editorial-Tokens umbauen: font-display-Headlines, mono Eyebrows, scharfe Ecken mit border-border, CTA als bg-accent/text-ink (nach DS-01-Fix) statt #16a34a; TierGate-Badge als Mono-Border-Chip wie MomentumBadge; die lp-price-Kartenstruktur der Landing als Vorlage wiederverwenden.
- **Akzeptanzkriterium:** Auf /trends/pricing existiert kein rounded-*, kein font-bold und kein #16a34a mehr; Headline nutzt font-display; CheckoutButton/TierGate-CTA nutzen das Accent-Token-Paar.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/CheckoutButton.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TierGate.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/SignInForm.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/account/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/LogoutButton.tsx

### DS-05 — Die Foresight-Sektion spricht zwei Designsprachen: Radar/Evolution/Dossier sind generisch (Sans-font-bold-Headline, rounded-full-Pill-Filter), Clusters/Lead-Time/Technology/Cockpit editorial — alle liegen als Nachbarn im selben Header-Menü.

- **Screen/Workflow:** /trends/foresight/radar, /evolution, /dossier vs. /clusters, /lead-time, /technology
- **Beobachtung:** radar/page.tsx:42 und evolution/page.tsx:102 `text-3xl font-bold tracking-tight` + `rounded-full px-3 py-1` Vertical-Pills + `rounded-xl` Empty-States (radar:80, evolution:130); dossier/page.tsx:58 gleiche Pills. Dagegen clusters/page.tsx:51-56 mono-Eyebrow "—— Signal Space" + font-display-Serif-Headline + eckige Mono-Chips (Z.78), lead-time/page.tsx:40-45 identisch editorial. TrendRadar.tsx:273-283 bringt zusätzlich eigenes Ad-hoc-CSS (border-radius 14px Readout, 999px Tags, font-weight 700).
- **Ursache:** Radar/Evolution/Dossier entstanden in einem späteren Epic offenbar ohne Rückgriff auf die bestehenden Seiten-Header- und Filter-Patterns.
- **Auswirkung:** Beim Durchklicken der Hauptnavigation springt das Produktgefühl pro Seite; Vertical-Filter sehen auf /trends (Mono-Border-Bar), /clusters (Mono-Chips) und /radar (runde Pills) dreimal anders aus, obwohl sie dasselbe tun.
- **Empfohlene Lösung:** Header-Pattern (Eyebrow + font-display-Headline + Sans-Lede) und das eckige Mono-Chip-Filter-Pattern aus clusters/page.tsx als gemeinsame Komponenten extrahieren und in Radar/Evolution/Dossier einsetzen; TrendRadar-Readout auf border-border/scharfe Ecken und Plex-Mono-Labels umstellen.
- **Akzeptanzkriterium:** Alle sechs Foresight-Seiten nutzen dieselbe Header-Komponente und denselben Vertical-Filter-Chip-Stil; kein rounded-full/rounded-xl mehr in radar/evolution/dossier.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/radar/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/evolution/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/dossier/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TrendRadar.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/clusters/page.tsx

### KEY-04 — Die beiden Analyse-Werkzeuge haben keinerlei URL-State — Ergebnisse sind nicht teilbar, nicht bookmarkbar und gehen bei Navigation/Refresh verloren.

- **Screen/Workflow:** /trends/foresight (Cockpit) und /trends/foresight/technology (Analyse-Tool)
- **Persona:** Key User / Power User
- **Beobachtung:** ForesightCockpit.tsx:90-92 hält query/vertical/data nur in useState; TechnologyTool.tsx:179-184 ebenso (q, CPC-Auswahl, Ergebnis). Kein router.push, kein searchParams-Read in beiden Komponenten. Kontrast: /foresight/lead-time?cpc=... und /radar?vertical=... machen es richtig (Links mit URL-State).
- **Ursache:** Beide Tools wurden als reine Client-Fetch-Widgets gebaut, ohne die im restlichen Produkt etablierte URL-State-Konvention (filter-params.ts).
- **Auswirkung:** Der Kern-Workflow eines Analysten — 'schick dem Kollegen die Analyse zu solid-state batteries' — ist unmöglich; nach versehentlichem Navigieren muss eine 76-Sekunden-GPU-Analyse (KEY-05) komplett neu laufen. Das Pro-Alleinstellungsmerkmal ist flüchtig.
- **Empfohlene Lösung:** Query und Auswahl in die URL spiegeln (?q=..., beim Tool zusätzlich ?codes=A23C19/08,...) und beim Mount aus der URL initial ausführen — das Muster aus filter-params.ts/lead-time wiederverwenden.
- **Akzeptanzkriterium:** Aufruf von /trends/foresight?q=longevity bzw. /trends/foresight/technology?q=solid-state+battery führt die Analyse automatisch aus; die URL im Adressfeld reproduziert nach Reload denselben Ergebnisstand.
- **Aufwand:** M · **Dateien:** frontend/src/components/ForesightCockpit.tsx, frontend/src/components/foresight/TechnologyTool.tsx

### KEY-05 — Die Technologie-Analyse dauerte real 76 Sekunden bei versprochenen '~10–30s', ohne Fortschrittsanzeige, ohne Rate-Limit und ohne Ergebnis-Persistenz.

- **Screen/Workflow:** /trends/foresight/technology (Analyse-Tool)
- **Persona:** Key User / Power User
- **Beobachtung:** Live gemessen: GET /api/foresight/analyze?q=solid-state+battery → HTTP 200 nach 76,1 s. Die Loading-Meldung (TechnologyTool.tsx:252) verspricht '(~10–30s)', der Client bricht erst bei 115 s ab (Zeile 191). analyze/route.ts hat im Gegensatz zu trajectory/route.ts (6/min) kein Rate-Limit — jeder Aufruf belegt GPU (Embedding-Handover) plus SQL. Wegen fehlendem URL-State (KEY-04) kostet jede Wiederholung erneut die volle Zeit.
- **Ursache:** Embedding-GPU-Handover plus Vollarchiv-SQL im synchronen Request-Pfad; die Latenzangabe stammt aus einer optimistischeren Messung.
- **Auswirkung:** Ein Power-User, der 3–4 Technologien vergleichen will, wartet Minuten pro Anfrage und blockiert dabei die gemeinsame GPU; die falsche Zeitangabe erzeugt Abbrüche kurz vor Fertigstellung.
- **Empfohlene Lösung:** Latenzangabe ehrlich machen ('bis ~2 Minuten') und einen Zwischenstatus anzeigen; Ergebnis serverseitig cachen (gleiche Phrase → gleicher CPC-Satz ist deterministisch) und ein Rate-/Concurrency-Limit analog trajectory/route.ts setzen.
- **Akzeptanzkriterium:** Zweiter Aufruf derselben Phrase antwortet in <2 s (Cache); die UI-Zeitangabe deckt die real gemessene P90-Latenz ab; paralleler Doppel-Request wird per 429/Gate serialisiert.
- **Aufwand:** M · **Dateien:** frontend/src/components/foresight/TechnologyTool.tsx, frontend/src/app/api/foresight/analyze/route.ts

### KEY-06 — Trend-Cluster sind nicht einzeln adressierbar und erlauben keinen Drilldown in ihre Mitglieds-Signale — die Evidenzkette endet nach drei externen Links.

- **Screen/Workflow:** /trends/foresight/clusters, /radar, /trends (MovingNow)
- **Persona:** Key User / Power User
- **Beobachtung:** ClusterCard.tsx:58-85 zeigt pro Cluster (z. B. 'size: 1.200 signals') nur 3 'Representative signals' als externe source_url-Links; kein Link auf eine interne Signalliste. MovingNow.tsx:44 und TrendRadar.tsx:237 linken nur auf /clusters?vertical=X — nie auf den konkreten Cluster (keine Anchor-IDs, kein ?cluster=-Param, kein Filter in filter-params.ts). Die im Radar angeklickte Blip-Auswahl ist reiner Client-State.
- **Ursache:** Cluster-Snapshots haben IDs (cluster.id wird als React-key genutzt), aber es wurde nie eine Detail-Route oder ein Filter-Param dafür gebaut.
- **Auswirkung:** Der Kern-Claim 'evidence one click away' bricht: Ein Analyst kann weder einem Kollegen einen bestimmten Cluster schicken noch die 1.197 nicht gezeigten Signale eines Clusters einsehen — genau das wäre der Arbeitsschritt vor einer Entscheidung.
- **Empfohlene Lösung:** Anchor-IDs pro ClusterCard (#cluster-<id>) plus Deep-Link aus MovingNow/Radar; für den Drilldown eine Cluster-Detailansicht oder einen /trends?cluster=<run:id>-Filter, der die Mitglieds-Signale (IDs liegen im Snapshot) als normale gefilterte Liste zeigt.
- **Akzeptanzkriterium:** Ein Link auf einen konkreten Cluster ist kopierbar und landet beim richtigen Cluster; von der ClusterCard aus ist eine Liste aller Mitglieds-Signale erreichbar (nicht nur 3 Repräsentanten).
- **Aufwand:** M · **Dateien:** frontend/src/components/foresight/ClusterCard.tsx, frontend/src/components/MovingNow.tsx, frontend/src/components/foresight/TrendRadar.tsx, frontend/src/lib/filter-params.ts

### KEY-07 — Evolution — ein Header-Nav-Item — ist im Default-Zustand eine Daten-Sackgasse: nur der HEALTH-Scope hat Daten.

- **Screen/Workflow:** /trends/foresight/evolution
- **Persona:** Key User / Power User
- **Beobachtung:** Live getestet: /foresight/evolution (All industries), ?vertical=TECH und ?vertical=FOOD zeigen alle nur 'Evolution is being computed' (24 KB-Seite); nur ?vertical=HEALTH liefert Inhalte ('Emerging now' + korrektes Pro-Gate). Der Code (evolution/page.tsx:73-76) fällt von fehlendem Scope auf 'global' zurück — aber global existiert selbst nicht. Der leere Zustand nennt kein Datum und keine Perspektive.
- **Ursache:** Die Lineage-Pipeline hat bisher nur einen HEALTH-Run persistiert; die Seite wurde trotzdem prominent in die Hauptnavigation gehängt.
- **Auswirkung:** Ein täglicher Nutzer klickt das Nav-Item, sieht wochenlang dieselbe Baustellen-Meldung und lernt: 'Foresight ist leer' — Vertrauensschaden genau an der Produktkante, die verkauft werden soll.
- **Empfohlene Lösung:** Solange nur ein Scope Daten hat: Default auf den besten vorhandenen Scope umleiten (statt leerem global) und im leeren Zustand das Datum des letzten Runs bzw. 'derzeit nur Health & Wellness' nennen; alternativ das Nav-Item erst mit breiter Datenlage aktivieren und die fehlenden Lineage-Runs (global + Top-Verticals) erzeugen.
- **Akzeptanzkriterium:** Der Aufruf von /trends/foresight/evolution ohne Parameter zeigt nie den leeren Zustand, solange irgendein Scope Daten hat.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/foresight/evolution/page.tsx, frontend/src/components/Header.tsx

### KEY-08 — Der Export-Button wird Free-Nutzern angezeigt, führt aber auf rohes Fehler-JSON statt auf einen Upsell.

- **Screen/Workflow:** /trends/foresight/dossier (Free-Nutzer)
- **Persona:** Key User / Power User (Free, Upgrade-Kandidat)
- **Beobachtung:** dossier/page.tsx:72 rendert ExportButton außerhalb des TierGate; 'Download CSV' ist ein <a href="/api/foresight/export?..."> (ExportButton.tsx:10). Live als anonymer Nutzer: HTTP 402 mit Body {"error":"Pro plan required"} als nackte JSON-Seite im Browser. 'Print / PDF' (window.print) druckt bei Free-Nutzern die Upgrade-Karte, da der Dossier-Inhalt gegated ist.
- **Ursache:** Button-Sichtbarkeit ist nicht an die Entitlement-Prüfung gekoppelt; der API-402 hat keinen Browser-tauglichen Fallback.
- **Auswirkung:** Der wertvollste Upsell-Moment (Nutzer will exportieren!) endet in einer JSON-Fehlerseite ohne Weg zurück — statt einem 'Pro freischalten'-Dialog.
- **Empfohlene Lösung:** ExportButton innerhalb des TierGate rendern (oder bei fehlendem Entitlement als disabled-Zustand mit Link auf /trends/pricing); zusätzlich im Export-Route-402-Fall auf /trends/pricing redirecten, wenn Accept: text/html.
- **Akzeptanzkriterium:** Ein Free-Nutzer sieht auf /trends/foresight/dossier entweder keinen aktiven CSV-Button oder landet beim Klick auf einer erklärenden Upgrade-Seite — nie auf rohem JSON.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/foresight/dossier/page.tsx, frontend/src/components/foresight/ExportButton.tsx, frontend/src/app/api/foresight/export/route.ts

### ONB-05 — Die Newsletter-Einwilligung im Sign-in-Formular ist vorangekreuzt — Dark Pattern und DSGVO-widrig.

- **Screen/Workflow:** /account/signin
- **Persona:** Alle
- **Tier:** free
- **Beobachtung:** Das ausgelieferte HTML enthaelt `<input type="checkbox" checked=""/>` neben "Also send me the weekly trend newsletter"; Ursache ist `const [newsletter, setNewsletter] = useState(true)` in SignInForm.tsx:12.
- **Ursache:** frontend/src/components/SignInForm.tsx:12 initialisiert die Einwilligung mit true.
- **Auswirkung:** Vorangekreuzte Einwilligungskaestchen sind nach EuGH Planet49 (C-673/17) unwirksam — die so gewonnenen Newsletter-Einwilligungen sind rechtlich wertlos und das Pattern beschaedigt den "Honest by construction"-Markenkern der Landing.
- **Empfohlene Lösung:** useState(false) als Default; optional stattdessen den Newsletter nach dem ersten Login aktiv anbieten (Opt-in-Moment mit erklaertem Nutzen).
- **Akzeptanzkriterium:** GET /account/signin liefert die Checkbox ohne checked-Attribut; ein Sign-up ohne Anklicken erzeugt kein Newsletter-Abo.
- **Aufwand:** S · **Dateien:** frontend/src/components/SignInForm.tsx

### ONB-06 — Drei Seiten erzaehlen drei widersprechende Monetarisierungs-Geschichten: Early-Access-Anfrage, Sofort-Checkout und "Plaene noch nicht gestartet".

- **Screen/Workflow:** / vs. /trends/pricing vs. /trends/foresight/technology
- **Persona:** Kaufinteressent
- **Tier:** alle Paid-Tiers
- **Beobachtung:** Landing-Pricing-Sektion: Buttons "Request early access" (→ /trends/pricing) und FAQ "The paid tiers are opening in early access". /trends/pricing: gruene Buttons "Choose Starter/Pro/Super Pro+" die per CheckoutButton direkt eine Stripe-Session starten (stripeReady=true beobachtet). /trends/foresight/technology (page.tsx:164): "You are viewing the Pro preview. Get notified when plans launch →" mit Link auf den Newsletter.
- **Ursache:** Die drei Oberflaechen wurden zu verschiedenen Zeitpunkten des Alpha-Rollouts gebaut und nie auf eine gemeinsame Botschaft synchronisiert; pricing/page.tsx hat sogar eine "coming soon"-Logik, die nur ohne Stripe-Keys greift.
- **Auswirkung:** Ein Interessent weiss nicht, ob er jetzt kaufen kann, sich bewerben muss oder warten soll — im schlimmsten Fall klickt er von der Landing ("Request early access") auf einen Sofort-Bezahlbutton und fuehlt sich ueberrumpelt.
- **Empfohlene Lösung:** Eine Botschaft festlegen (z.B. "Paid tiers live") und alle drei Stellen daran ausrichten: Landing-CTAs auf "Choose plan" umbenennen, den "plans launch"-Satz auf der Technology-Seite entfernen bzw. in einen Upgrade-Link aendern.
- **Akzeptanzkriterium:** Alle Seiten verwenden dieselbe Formulierung fuer den Paid-Status; kein Text verspricht mehr "early access"/"when plans launch", solange Checkout live ist (oder umgekehrt).
- **Aufwand:** S · **Dateien:** frontend/src/app/page.tsx, frontend/src/app/trends/pricing/page.tsx, frontend/src/app/trends/foresight/technology/page.tsx

### ONB-07 — Die 404-Seite ist serverseitig komplett leer und clientseitig nur der unbrandete Next-Default — eine Sackgasse ohne Navigation.

- **Screen/Workflow:** /trends/gibtesnicht (404)
- **Persona:** Occasional User (alte Links, Tippfehler), niedrige Medienkompetenz
- **Tier:** free
- **Beobachtung:** GET /trends/gibtesnicht liefert 404 mit einem Body, der nur `<div hidden><!--$--><!--/$--></div>` plus Scripts enthaelt (verifiziert am Roh-HTML); ohne JavaScript eine weisse Seite, mit JavaScript der generische Next-404 ohne Header, Suche oder Links. Es existiert keine not-found.tsx im gesamten app-Verzeichnis (find bestaetigt).
- **Ursache:** Fehlende app/not-found.tsx; das Root-Layout wird im Default-404-Pfad nicht mitgerendert.
- **Auswirkung:** Wer einem veralteten oder vertippten Link folgt (bei 60k Artikeln und Newsletter-Links realistisch), landet im Nichts und muss die URL manuell reparieren — fuer die Persona mit niedriger Medienkompetenz ist die Session dort beendet.
- **Empfohlene Lösung:** app/not-found.tsx mit Site-Layout anlegen: kurze Meldung, Suchfeld und Links auf /trends und die Vertikale.
- **Akzeptanzkriterium:** GET einer Nicht-Route liefert 404 mit sichtbarem Site-Header, einer Erklaerung und mindestens einem Link auf /trends im SSR-HTML (ohne JS pruefbar).
- **Aufwand:** S · **Dateien:** frontend/src/app

### ONB-08 — Mitten in der durchgehend englischen Site ist der zentrale Analyse-Abschnitt der Technology-Seite deutsch und in Du-Form.

- **Screen/Workflow:** /trends/foresight/technology
- **Persona:** Alle Nicht-Deutschsprachigen; irritiert auch deutsche Nutzer (Du-Form)
- **Tier:** pro
- **Beobachtung:** Im ausgelieferten HTML: "—— Technologie-Analyse · Verbesserungsrate & Innovationskette", "Beschreibe eine Technologie. Wir loesen sie auf feine Patentklassen auf — du waehlst, welche …", Button "Analysieren" — direkt unter englischen Ueberschriften ("Where innovation moves fastest"). Quelle: TechnologyTool.tsx:227-241.
- **Ursache:** Die Komponente wurde offenbar auf Deutsch entwickelt und nie an die englische Site-Sprache angeglichen.
- **Auswirkung:** Fuer internationale B2B-Interessenten (die Pro-Zielgruppe dieser Seite) ist das Kern-Interaktionselement unverstaendlich; fuer alle wirkt es wie ein Versehen und untergraebt die Professionalitaet ausgerechnet auf der teuersten Feature-Seite.
- **Empfohlene Lösung:** Die Strings in TechnologyTool.tsx auf Englisch umstellen ("Describe a technology…", "Analyze"); falls DE-Support gewollt ist, sauber per i18n statt gemischt.
- **Akzeptanzkriterium:** GET /trends/foresight/technology enthaelt keine deutschen UI-Strings mehr (grep auf "Beschreibe"/"Analysieren" leer).
- **Aufwand:** S · **Dateien:** frontend/src/components/foresight/TechnologyTool.tsx

### ONB-09 — Der Checkout-Button schluckt Fehler stumm und verliert beim Sign-in-Umweg den Kaufkontext.

- **Screen/Workflow:** /trends/pricing (Checkout-Klick)
- **Persona:** Kaufinteressent
- **Tier:** starter/pro/superpro
- **Beobachtung:** CheckoutButton.tsx: bei fetch-Fehler nur `catch { setBusy(false) }` — der Button springt kommentarlos von "…" zurueck auf "Choose Pro", keinerlei Fehlermeldung. Bei `data.needSignin` wird hart auf /account/signin umgeleitet, ohne returnTo/Tier-Parameter; die Signin-Seite erwaehnt den unterbrochenen Kauf nicht und fuehrt nach dem Magic-Link nicht zum Checkout zurueck.
- **Ursache:** frontend/src/components/CheckoutButton.tsx (leerer catch, Redirect ohne Kontext); /account/signin/page.tsx wertet keinen returnTo aus.
- **Auswirkung:** Genau im Moment der hoechsten Kaufbereitschaft: Bei einem Stripe-/Netzwerkfehler wirkt der Button kaputt ("passiert nichts"), und wer erst einloggen muss, muss danach den Kauf selbststaendig neu finden — beides klassische Checkout-Abbruchursachen.
- **Empfohlene Lösung:** Fehlerzustand im Button anzeigen ("Something went wrong — try again"); bei needSignin `?returnTo=/trends/pricing&tier=pro` mitgeben und nach Magic-Link-Login dorthin zurueckfuehren, idealerweise mit Hinweis "Sign in to continue your Pro checkout".
- **Akzeptanzkriterium:** Simulierter API-Fehler zeigt eine sichtbare Fehlermeldung am Button; der Signin-Redirect enthaelt den Ursprungs-/Tier-Kontext und fuehrt nach Login zurueck zum Checkout.
- **Aufwand:** M · **Dateien:** frontend/src/components/CheckoutButton.tsx, frontend/src/app/account/signin/page.tsx

## S3 (44 Findings)

### A11Y-08 — Kein Skip-Link — vor dem Inhalt liegen auf jeder Seite 11 Header-Links.

- **Screen/Workflow:** Alle Seiten (globales Layout)
- **Persona:** Tastatur-Nutzer
- **Beobachtung:** grep nach "Skip"/skip-link ueber frontend/src ist leer; layout.tsx:50-54 rendert Header (10 Nav-Links + Logo) direkt vor <main> ohne Sprunganker. In globals.css existiert keine .sr-only/skip-Klasse.
- **Auswirkung:** WCAG 2.4.1: Tastaturnutzer tabben auf jeder Seite erst durch die komplette Navigation.
- **Empfohlene Lösung:** Als erstes Element in <body> einen visually-hidden, bei Fokus sichtbaren `<a href="#main">Skip to content</a>` einbauen und <main id="main" tabIndex={-1}> setzen.
- **Akzeptanzkriterium:** Erster Tab auf jeder Seite zeigt den Skip-Link; Enter setzt den Fokus in main.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/layout.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/globals.css

### A11Y-09 — Pagination ohne nav-Landmark und ohne aria-current — die aktuelle Seite ist nur farblich markiert.

- **Screen/Workflow:** /trends (Pagination)
- **Persona:** Screenreader-Nutzer
- **Beobachtung:** Pagination.tsx:33-85: Wrapper ist ein <div> (kein <nav aria-label="Pagination">), aktiver Button unterscheidet sich nur per Klasse bg-accent (Z.66-67); grep ueber src liefert 0x aria-current — auch im gerenderten p20.html nicht vorhanden. Seiten sind Buttons mit router.push, daher kein Open-in-new-tab.
- **Auswirkung:** WCAG 1.3.1/4.1.2: Screenreader koennen die aktuelle Seite nicht identifizieren; Landmark-Navigation findet die Pagination nicht.
- **Empfohlene Lösung:** Wrapper zu <nav aria-label="Pagination"> machen, aktiver Seite aria-current="page" geben; idealerweise Links (next/link mit ?page=) statt Buttons rendern.
- **Akzeptanzkriterium:** axe meldet aria-current auf der aktiven Seite; Rotor/Landmark-Liste zeigt "Pagination".
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/Pagination.tsx

### A11Y-10 — Saemtliche Control-Grenzen (Inputs, Chips, Buttons) haben mit border #2a2d25 auf #0a0c0a nur 1,40:1 statt der geforderten 3:1.

- **Screen/Workflow:** Alle Formulare/Filter (globales Designsystem)
- **Persona:** Sehbehinderte Nutzer
- **Beobachtung:** Berechnet: #2a2d25 vs #0a0c0a = 1,40:1, #3a3d35 (--color-rule) = 1,77:1. Das gesamte Filter-UI (VerticalsMultiFilter, DateRangeChips, PestelFilter, SearchInput, Newsletter-Input) grenzt interaktive Flaechen ausschliesslich ueber diese 1px-Border ab — es gibt keinen zweiten visuellen Hinweis (kein Flaechenkontrast: bg transparent).
- **Auswirkung:** WCAG 1.4.11 Fail: Feldgrenzen sind fuer kontrastschwache Nutzer praktisch unsichtbar — wo ein Eingabefeld anfaengt, ist nicht erkennbar.
- **Empfohlene Lösung:** Border-Token fuer interaktive Controls auf mind. #4d5147 (≈3:1 auf #0a0c0a) anheben oder Controls zusaetzlich mit fill (bg-card) hinterlegen; reine Deko-Trennlinien koennen bei #2a2d25 bleiben.
- **Akzeptanzkriterium:** Input-/Chip-Grenzen erreichen >= 3:1 gegen den umgebenden Hintergrund (Stichprobe SearchInput, DateRangeChips).
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css

### A11Y-11 — Heading-Hierarchie springt: auf /trends folgt auf die h1 direkt h3 (Card-Titel), die h2-Sektionen kommen erst danach; auf Artikelseiten h1 -> h3 ohne h2.

- **Screen/Workflow:** /trends, Artikel-Seite
- **Persona:** Screenreader-Nutzer (Heading-Navigation)
- **Beobachtung:** Gerenderte Heading-Reihenfolge /trends: h1, 12x h3 (TrendCard.tsx:63), dann h2 "Strategic Forecasts" + h2 "What's moving". Artikel: h1, 3x h3 (Related, TrendArticle.tsx:249) — die Sektion "Related in ..." selbst ist nur ein <div> (Z.233), ebenso "Original Source" (Z.215). Jede Seite hat korrekt genau eine h1.
- **Auswirkung:** Heading-Outline ist fuer SR-Nutzer unlogisch; Sektionen wie Related/Source sind per Heading-Navigation unauffindbar (WCAG 1.3.1 Best Practice).
- **Empfohlene Lösung:** Auf /trends eine (ggf. sr-only) h2 "Latest signals" vor dem Grid einfuegen und Card-Titel als h3 belassen; im Artikel "Related" und "Original Source" als h2 auszeichnen.
- **Akzeptanzkriterium:** Heading-Outline beider Seiten ist lueckenlos (h1 > h2 > h3, axe heading-order 0 Violations).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TrendArticle.tsx

### A11Y-12 — Die CRS-Erklaerung (Was bedeutet der Score?) existiert nur als Hover-Tooltip — nicht per Tastatur oder Touch erreichbar.

- **Screen/Workflow:** TrendCard/TrendArticle (TrendScore/CRS)
- **Persona:** Tastatur- und Touch-Nutzer
- **Beobachtung:** TrendScore.tsx:15-18: Tooltip haengt an onMouseEnter/onMouseLeave eines nicht fokussierbaren <div class="cursor-help">; kein onFocus/tabIndex, kein Touch-Pfad. Der Scorewert selbst ist als Text "CRS 82" sichtbar (gut, nicht nur Farbe).
- **Auswirkung:** WCAG 1.4.13/2.1.1: Der zentrale Produktbegriff CRS bleibt fuer Tastatur-/Mobile-Nutzer unerklaert.
- **Empfohlene Lösung:** Aus dem Wrapper einen fokussierbaren Button machen (aria-describedby auf den Tooltip, Anzeige auch bei :focus-visible, Dismiss per Escape) oder auf /trends/methodology verlinken.
- **Akzeptanzkriterium:** Tooltip erscheint bei Tastaturfokus und laesst sich mit Escape schliessen; auf Touch oeffnet Tap die Erklaerung.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TrendScore.tsx

### A11Y-13 — Das Technology-Tool ist komplett deutsch auf einer als lang="en" deklarierten, sonst englischen Site — ohne lang-Auszeichnung.

- **Screen/Workflow:** /trends/foresight/technology (TechnologyTool)
- **Persona:** Screenreader-Nutzer, internationale B2B-Leads
- **Beobachtung:** layout.tsx:47 setzt html lang="en"; TechnologyTool.tsx:226-245 rendert "Technologie-Analyse · Verbesserungsrate & Innovationskette", "Beschreibe eine Technologie...", "Analysiere…", "Patentklassen — deine Auswahl" ohne lang="de" auf einem Container.
- **Auswirkung:** WCAG 3.1.2: Screenreader lesen deutschen Text mit englischer Aussprache; zudem Sprachbruch im Produkt (alle anderen Foresight-Seiten englisch).
- **Empfohlene Lösung:** Kurzfristig lang="de" auf die Tool-Section setzen; eigentlicher Fix: Tool-Texte auf Englisch angleichen (Konsistenz mit Rest der Site).
- **Akzeptanzkriterium:** Entweder alle Tool-Strings englisch oder die Section traegt lang="de".
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TechnologyTool.tsx

### A11Y-14 — Das Quellen-Ausschluss-Dropdown schliesst nicht per Escape und missbraucht das listbox-Pattern ohne dessen Tastatursemantik.

- **Screen/Workflow:** /trends (SourceExcludeToggle-Dropdown)
- **Persona:** Tastatur-Nutzer
- **Beobachtung:** SourceExcludeToggle.tsx:33-39 schliesst nur bei mousedown ausserhalb; kein Escape-Handler, kein Fokus-Management. Z.73/87: role="listbox" mit <button role="option"> — Screenreader erwarten dann Pfeiltasten-Navigation, tatsaechlich funktioniert nur Tab. Multi-Select-Zustand via aria-selected ist zwar gesetzt, aber das Zustands-Icon ✕/+ ist aria-hidden und der Farbwechsel (text-warn) der einzige Namens-unabhaengige Hinweis neben aria-selected.
- **Auswirkung:** Tastaturnutzer stranden im offenen Dropdown (Escape tut nichts); SR-Nutzer bekommen ein inkonsistentes Widget-Modell.
- **Empfohlene Lösung:** Escape-Handler zum Schliessen + Fokusrueckgabe auf den Trigger; role="listbox/option" entfernen und als simples Menue aus Toggle-Buttons mit aria-pressed auszeichnen (passt zum restlichen Chip-Pattern).
- **Akzeptanzkriterium:** Escape schliesst das Dropdown und fokussiert den Trigger; axe meldet keine invaliden ARIA-Rollen-Kombinationen.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/filters/SourceExcludeToggle.tsx

### A11Y-15 — dt/dd werden ohne umschliessendes dl gerendert (invalides HTML), und die Breadcrumb-nav ist nicht von der Haupt-nav unterscheidbar.

- **Screen/Workflow:** Artikel-Seite (Meta-Block, Breadcrumb)
- **Persona:** Screenreader-Nutzer
- **Beobachtung:** TrendArticle.tsx:149-193: <div class="grid ..."> enthaelt direkt <dt>/<dd>-Paare (Signal Type, Mega Trend, Brands, Regions) ohne <dl> — invalide Struktur, Definitionssemantik geht verloren. Z.65: zweites <nav> (Breadcrumb) ohne aria-label; die Artikelseite hat damit 2 anonyme navs (gerendert bestaetigt: 2x <nav>).
- **Auswirkung:** WCAG 1.3.1: AT kann die Zuordnung Label->Wert nicht als Definitionsliste vermitteln; Landmark-Liste zeigt zwei ununterscheidbare "navigation".
- **Empfohlene Lösung:** Meta-Block in <dl> mit div-Gruppen pro Paar umbauen (dl erlaubt div-Wrapper) oder auf einfache span-Paare wechseln; Breadcrumb-nav aria-label="Breadcrumb" geben.
- **Akzeptanzkriterium:** W3C-Validator ohne dt/dd-Nesting-Fehler; Landmark-Liste zeigt "Breadcrumb" benannt.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TrendArticle.tsx

### A11Y-18 — Der Radar skaliert als 640er-viewBox auf 375px herunter — Ring-/Segment-Labels schrumpfen auf effektiv ~6-7px, Blips auf teils <10px Tap-Flaeche.

- **Screen/Workflow:** /trends/foresight/radar auf Mobile (375px)
- **Persona:** Mobile Nutzer
- **Beobachtung:** TrendRadar.tsx:33 SIZE=640, .radar-svg width:100% (Z.264); bei 375px Viewport Skalierungsfaktor ~0,55: 11-12px SVG-Text -> ~6-7px, kleinste Blips (r=5 -> ~5,5px Durchmesser gerendert ~6px) weit unter 24px Zielgroesse. Layout selbst bricht korrekt einspaltig um (@media max-width:900px, Z.262) — das Readout-Panel rutscht unter den Radar, Hover-Alternativen (Tap) existieren.
- **Auswirkung:** WCAG 2.5.8 (Blip-Tapziele) + praktische Unlesbarkeit der Radar-Beschriftung auf dem Smartphone.
- **Empfohlene Lösung:** Unter 640px ein groesseres Mindest-Tap-Ziel per unsichtbarem <circle r={Math.max(b.r,14)}> hinterlegen und SVG-Textgroessen responsive anheben (z.B. font-size in px via CSS statt im viewBox-Massstab), oder mobil eine Listen-Alternative anbieten.
- **Akzeptanzkriterium:** Auf 375px sind alle Blips mit >= 24px effektiver Tap-Flaeche antippbar und Ringlabels >= 10px effektiv lesbar.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TrendRadar.tsx

### ARCH-16 — Ungültige Slugs und tote Routen landen auf der unveränderten Next-Default-404 ('This page could not be found.') ohne Ausweg-Angebot.

- **Screen/Workflow:** 404 (ungültiger Slug / tote Route)
- **Persona:** Leser über alte Links/SEO
- **Beobachtung:** curl /trends/definitely-not-a-real-slug-xyz → 404 mit Next-Standardtext im Layout (Header/Footer vorhanden, aber kein Hinweis, kein Link zum Feed, generischer Seitentitel). notFound() wird in [slug]/page.tsx und mega/[megatrend]/page.tsx aufgerufen; ein not-found.tsx existiert nicht (find leer). Ironie: TrendsEmpty.tsx zeigt, dass das Team schöne Leerzustände kann — nur nicht hier.
- **Ursache:** Fehlende not-found.tsx-Konventionsdatei.
- **Auswirkung:** Trend-Artikel veralten/rotieren (Sitemap listet nur die letzten 500) — 404 ist ein häufiger Eintrittspunkt aus Suchmaschinen und verschenkt jeden dieser Besucher.
- **Empfohlene Lösung:** app/not-found.tsx im TrendsEmpty-Stil: Erklärung + Suchfeld/Link auf /trends + Top-Mega-Trends als Einstiege.
- **Akzeptanzkriterium:** Ungültiger Slug rendert eine gebrandete 404 mit mindestens einem CTA in den Feed.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/[slug]/page.tsx, frontend/src/components/TrendsEmpty.tsx

### ARCH-17 — Sprach- und Tonalitätsmix: deutsche API-Meldungen in einer durchgehend englischen UI, plus technisch-rohe bzw. irreführende Fehlertexte.

- **Screen/Workflow:** /trends/newsletter (+ API-Fehlertexte allgemein)
- **Persona:** Alle
- **Beobachtung:** api/newsletter/route.ts antwortet deutsch ('Bitte gib eine gültige Email-Adresse ein.', 'Du bist bereits angemeldet.') und die Newsletter-Seite rendert data.message/data.error direkt; mega/[megatrend] setzt den Metadaten-Titel 'Mega-Trend nicht gefunden'; foresight/page.tsx hat eine deutsche meta-description — bei html lang='en' und komplett englischer UI. Dazu: SignInForm zeigt bei 429 'Something went wrong. Please try again.' (widerspricht dem Rate-Limit) und ForesightCockpit setzt error auf 'HTTP 429' roh in die UI.
- **Ursache:** Meldungstexte leben verstreut in den Routen/Komponenten ohne Sprachkonvention; Client-Handler unterscheiden Statuscodes nicht.
- **Auswirkung:** Wirkt unfertig und verletzt die Owner-Vorgabe 'Klartext statt Jargon'; beim 429 führt der Text zu genau dem falschen Verhalten (sofort nochmal versuchen).
- **Empfohlene Lösung:** Alle nutzerseitigen Meldungen auf Englisch vereinheitlichen; SignInForm und ForesightCockpit 429/400 gesondert behandeln ('Too many attempts — please wait a minute.'); Retry-After-Header dafür auswerten.
- **Akzeptanzkriterium:** Kein deutscher String mehr in API-Responses/Metadaten; 429 zeigt in SignInForm und Cockpit eine spezifische Wartemeldung.
- **Aufwand:** S · **Dateien:** frontend/src/app/api/newsletter/route.ts, frontend/src/components/SignInForm.tsx, frontend/src/components/ForesightCockpit.tsx, frontend/src/app/trends/mega/[megatrend]/page.tsx, frontend/src/app/trends/foresight/page.tsx

### ARCH-18 — Die Desktop-Nav zeigt ab 768px elf Einträge in einer Zeile — rechnerisch ~1000px+ Inhaltsbreite, die auf Tablet-Breiten überläuft bzw. den Logo-Bereich quetscht.

- **Screen/Workflow:** Header (Tablet/kleines Desktop)
- **Persona:** Tablet-Nutzer
- **Beobachtung:** Header.tsx: 'hidden md:flex' bei 10 NAV_ITEMS + Newsletter-Button; Labels summieren ~100 Zeichen Mono-Uppercase mit je 24px Padding (11×) plus Logo — deutlich über den bei md (768px) bzw. lg (1024px) verfügbaren Platz in der max-w-7xl-Zeile; flex ohne wrap/overflow-Handling.
- **Ursache:** Die Nav wuchs mit jedem Foresight-Feature um einen Top-Level-Eintrag, ohne Gruppierung; der MobileNav-Breakpoint blieb bei md.
- **Auswirkung:** Auf iPad-/Split-Screen-Breiten ragt die Nav aus der Zeile bzw. kollidiert mit dem Logo; zudem verwässern 6 gleichrangige Foresight-Einträge die Informationsarchitektur.
- **Empfohlene Lösung:** Foresight-Unterseiten (Radar/Evolution/Lead Time/Clusters/Technology) unter einen 'Foresight'-Eintrag mit Dropdown bzw. Sekundär-Nav auf den Foresight-Seiten gruppieren; alternativ Hamburger bis lg: beibehalten.
- **Akzeptanzkriterium:** Bei 768–1100px Viewport bleibt die Kopfzeile einzeilig ohne horizontales Überlaufen (DevTools-Prüfung), Top-Level ≤ 6 Einträge.
- **Aufwand:** S · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/MobileNav.tsx

### ARCH-19 — Der Fallback für die Magic-Link-Basis-URL zeigt auf Port 3004, die App läuft auf 3001 — ohne gesetzte PUBLIC_BASE_URL sind alle Sign-in-Links tot.

- **Screen/Workflow:** lib/auth.ts (Magic-Link-Basis-URL)
- **Persona:** Owner/Deploy
- **Beobachtung:** auth.ts Zeile 235: const base = process.env.PUBLIC_BASE_URL || "http://localhost:3004". Aktuell rettet frontend/.env.local (PUBLIC_BASE_URL=http://localhost:3001) den Flow; der Default widerspricht sowohl dem Dev-Port 3001 als auch jeder Prod-Domain. assertAuthConfigured() prüft PUBLIC_BASE_URL nicht.
- **Ursache:** Hartkodierter Rest aus einer früheren Testumgebung; keine Konfigurationsprüfung für die Basis-URL.
- **Auswirkung:** Ein Deploy ohne die Env-Variable erzeugt E-Mails mit klickbaren, aber toten Links — der komplette Login fällt still aus.
- **Empfohlene Lösung:** Fallback auf den Request-Origin ableiten (wie callback/route.ts es tut) oder in assertAuthConfigured() PUBLIC_BASE_URL in Produktion verpflichtend machen.
- **Akzeptanzkriterium:** Ohne PUBLIC_BASE_URL enthält der Magic-Link die tatsächliche Origin der Anfrage bzw. der Request schlägt in Prod mit klarer Config-Fehlermeldung fehl.
- **Aufwand:** S · **Dateien:** frontend/src/lib/auth.ts, frontend/src/app/api/auth/request/route.ts

### ARCH-20 — Die UX-/Funnel-kritischen Schichten sind komplett ungetestet — getestet ist nur die lib-Ebene von Auth, Stripe-Webhook und Rate-Limit.

- **Screen/Workflow:** Tests (frontend gesamt)
- **Persona:** Owner/Wartung
- **Beobachtung:** find: genau 3 Testdateien (auth.test.ts, stripe.test.ts, rateLimit.test.ts — inhaltlich gründlich, u. a. Webhook-Reordering). Null Tests für: entitlement/tierAllows/TierGate (das Paywall-Loch ARCH-01 wäre aufgefallen), /api/trends-Parametervalidierung (Draft-Leak ARCH-03 wäre aufgefallen), filter-params.ts (376 Zeilen URL-Parsing), db.ts-Query-Builder, sämtliche API-Routen außer auth/stripe, alle Komponenten.
- **Ursache:** Testfokus lag auf den sicherheitskritischen Neubauten (Auth/Stripe); für die gewachsene Feed-/Gating-Schicht wurde nie nachgezogen.
- **Auswirkung:** Genau die Fehlerklassen, die dieses Audit fand (offene Gates, Parameter-Leaks), haben kein Sicherheitsnetz — Regressionen bleiben bis zum nächsten manuellen Audit unentdeckt.
- **Empfohlene Lösung:** Drei gezielte Vitest-Suiten ergänzen: (1) Entitlement-Matrix (jede gated Route × jedes Tier), (2) /api/trends-Parametervalidierung inkl. status-Whitelist, (3) filter-params Roundtrip (parse→buildQueryString).
- **Akzeptanzkriterium:** npm test deckt Entitlement-Matrix, trends-API-Validierung und filter-params ab; ein absichtlich entfernter canAccess-Check lässt die Suite fehlschlagen.
- **Aufwand:** M · **Dateien:** frontend/src/lib/entitlement.ts, frontend/src/lib/filter-params.ts, frontend/src/app/api/trends/route.ts

### ARCH-21 — Der Frontend-Abschnitt der CLAUDE.md beschreibt in mehreren Punkten eine Realität, die es nicht mehr (oder nie) gab — Verstoß gegen die eigene Doku-spiegelt-Realität-Regel.

- **Screen/Workflow:** CLAUDE.md Frontend-Abschnitt (Doku-Drift)
- **Persona:** Owner/Doku (konstitutionelle Regel)
- **Beobachtung:** Konkret gegen Repo/Live geprüft: (1) 'Next.js 14 (App Router)' — real Next 16.2.10, React 19.2.4, Tailwind v4 (package.json). (2) Route '/trends/search → Volltextsuche + Filter' — existiert nicht, HTTP 404 live; Suche lebt in FilterBar (?q=) + /api/search + Foresight-Cockpit. (3) 'DE/EN-Switcher' (Sprint-3-Haken) — kein Switcher im Code, html lang='en', DE-Content eingestellt. (4) Routenliste nennt weder /trends/foresight/* (7 Seiten) noch /pricing, /methodology, /cross-vertical, /account. (5) 'PM2 oder systemd' bzw. Caddy-Beispiel auf Port 3000 — real systemd-Unit catandary-frontend auf 3001. (6) Sitemap-Basis catandary.de stimmt, aber die dokumentierte Lead-Capture-Strecke (Gated Content/Email-Gate) heißt real Tier-/Paywall-System.
- **Ursache:** Frontend-Abschnitt wurde seit Sprint-3-Zeiten nicht mit dem Tier-/Foresight-Ausbau synchronisiert.
- **Auswirkung:** Jeder Agent/Entwickler, der der Doku folgt, plant gegen falsche Routen und Versionen (z. B. Features für den nicht existenten /trends/search).
- **Empfohlene Lösung:** Frontend-Abschnitt der CLAUDE.md in einem Doku-Sync-Commit auf Ist-Stand bringen: Versionsangaben, echte Routenliste (inkl. foresight/*, pricing, account), Suche-per-Filter statt /trends/search, DE/EN-Switcher-Absatz streichen, Deploy-Absatz auf systemd/3001 vereinheitlichen.
- **Akzeptanzkriterium:** Jede in CLAUDE.md genannte Frontend-Route antwortet live mit 200; Versions- und Deploy-Angaben entsprechen package.json bzw. der systemd-Unit.
- **Aufwand:** S · **Dateien:** CLAUDE.md, frontend/package.json, frontend/src/app/trends/page.tsx

### CONF-04 — Jede Trend-Antwort enthaelt interne Scoring- und Pipeline-Felder, die im UI nicht angezeigt werden.

- **Screen/Workflow:** /api/trends + alle Card-Queries (frontend/src/lib/db.ts TREND_COLS)
- **Persona:** Wettbewerber / neugieriger Nutzer
- **Tier:** Internal
- **Beobachtung:** `TREND_COLS` (db.ts:48-54) selektiert u.a. `confidence`, `trend_score`, `auto_published`, `raw_entry_id`. curl `/api/trends` gibt fuer einen Draft `confidence:0.351`, `trend_score:0.49`, `auto_published:false`, `raw_entry_id:23117834` aus — auch fuer published Trends sichtbar.
- **Ursache:** Explizite Spaltenliste (gut gegen Vektor-Leak) enthaelt jedoch interne Scoring-Felder ohne Public/Internal-Trennung.
- **Auswirkung:** Interne Auto-Publish-Schwellen und Vertrauens-Scores werden ableitbar (z.B. welche confidence auto-published wird); geringe, aber vermeidbare Preisgabe der Pipeline-Logik.
- **Empfohlene Lösung:** Fuer Public-Endpoints ein reduziertes Feldset ausliefern (ohne confidence, trend_score, auto_published, raw_entry_id); interne Felder nur in Review-/Admin-Kontexten. Am einfachsten ein `toPublicTrend()`-Mapping vor der JSON-Response in trends/route.ts.
- **Akzeptanzkriterium:** `/api/trends` enthaelt keine Felder confidence/trend_score/auto_published/raw_entry_id mehr; UI-Anzeige unveraendert.
- **Aufwand:** S · **Dateien:** frontend/src/lib/db.ts, frontend/src/app/api/trends/route.ts

### COPY-16 — Die Cluster-Zusammenfassung verdoppelt sich selbst: "Holding steady — holding steady" bzw. "Gaining ground — gaining share of attention".

- **Screen/Workflow:** /trends/foresight/clusters, /trends/foresight, Landing (ClusterCard)
- **Persona:** Alle Leser der Cluster-Ansichten
- **Tier:** starter
- **Beobachtung:** Live-HTML auf /trends/foresight/clusters: "Holding steady — holding steady, confirmed by 4 independent sources." Ursache in ClusterCard.tsx:15: Template kombiniert eine eigene Momentum-Phrase mit momentumText(), die für "stable" identisch ist ("holding steady", MomentumBadge.tsx CONFIG).
- **Ursache:** Zwei Textquellen für dieselbe Aussage im selben Satz.
- **Auswirkung:** Liest sich wie ein Template-Bug — untergräbt die "Evidence, not vibes"-Positionierung ausgerechnet im Beweis-Feature.
- **Empfohlene Lösung:** Eine Quelle verwenden: "Holding steady — confirmed by 4 independent sources." bzw. "Gaining ground (+X pp share of attention) — confirmed by …".
- **Akzeptanzkriterium:** Kein Cluster-Summary enthält dieselbe Momentum-Phrase doppelt; für alle vier Momentum-Zustände geprüft.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/ClusterCard.tsx

### COPY-17 — Der zentrale Score hat drei Namen (CRS, Min Score, Signal strength) und seine einzige Erklärung ist ein reiner Maus-Hover.

- **Screen/Workflow:** /trends (Karten, Filter, Sortierung)
- **Persona:** Neuer Besucher
- **Tier:** free
- **Beobachtung:** Karten zeigen "CRS 73" (TrendScore.tsx:33); die Erklärung existiert nur als Hover-Tooltip via onMouseEnter (Z.17-18) — auf Touch/Tastatur unzugänglich. Der Score-Filter heißt "Min Score" (ScoreSlider.tsx:43), die Sortieroption "Signal strength" (Live-HTML Sort-Dropdown) — nirgends wird verknüpft, dass alle drei dasselbe meinen.
- **Ursache:** Begriff je Komponente einzeln benannt.
- **Auswirkung:** Neue Nutzer können das prominenteste Qualitätssignal der Karten nicht deuten und den Filter nicht darauf beziehen — unnötige kognitive Last im Free-Kernscreen.
- **Empfohlene Lösung:** Einheitlich "CRS" benennen ("Min CRS", Sort: "CRS (relevance)"), Tooltip zusätzlich auf focus/click öffnen, und im /trends-Hero oder der ersten Karte einmal inline auflösen: "CRS — relevance 0–100".
- **Akzeptanzkriterium:** Score heißt in Karte, Filter und Sortierung identisch; Erklärung ist per Tastatur/Touch erreichbar oder einmal im Screen inline sichtbar.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TrendScore.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/ScoreSlider.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/SortSelect.tsx

### COPY-18 — Unerklärte Abkürzungen im Beweis-Layer: "Peak SoV year" und "(FTS only)".

- **Screen/Workflow:** /trends/foresight/lead-time + Foresight-Cockpit
- **Persona:** Analyst (Profi) und Neuling gleichermaßen
- **Tier:** pro
- **Beobachtung:** Lead-Time-Tabelle (Live-HTML): "Tier | Peak SoV year" — SoV (Share of Voice) wird nirgends aufgelöst. Foresight-Cockpit Meta-Zeile: "N matches (FTS only)" (ForesightCockpit.tsx:~243) — Volltextsuche-Jargon aus der Entwicklung.
- **Ursache:** Interne Metrik-/Tech-Namen ohne Publikums-Übersetzung.
- **Auswirkung:** Gerade die Screens, die Methoden-Vertrauen aufbauen sollen, wirken für Nicht-Analysten kryptisch; "FTS only" versteht auch mancher Profi nicht.
- **Empfohlene Lösung:** "Peak year (share of voice)" bzw. Spaltenkopf "Peak year"; "(FTS only)" ersetzen durch "text match only — semantic search unavailable".
- **Akzeptanzkriterium:** Weder "SoV" noch "FTS" erscheinen unerklärt im UI.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/lead-time/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCockpit.tsx

### COPY-19 — "Complete Mega/Macro/Micro classification" ist das meistwiederholte Premium-Versprechen, aber Macro und Micro werden im gesamten Produkt nie erklärt oder gezeigt.

- **Screen/Workflow:** ForesightCta / Pricing (Mega/Macro/Micro-Versprechen)
- **Persona:** Free-Nutzer, der das Premium-Versprechen bewerten soll
- **Tier:** free
- **Beobachtung:** ForesightCta (unter jedem Artikel, /trends, Methodology): "Catandary Foresight delivers the full Mega/Macro/Micro classification…" (ForesightCta.tsx:9,30-32). Nur "Mega" wird auf /trends/mega erklärt ("10–25 years"); Macro/Micro tauchen sonst nirgends auf — auch nicht in der Tier-Featurematrix, d.h. das Versprechen hängt in der Luft.
- **Ursache:** Taxonomie-Teaser aus dem Konzept übernommen, Erklärung nie gebaut.
- **Auswirkung:** Ein Versprechen, das der Empfänger nicht dekodieren kann, erzeugt keinen Kaufwunsch — der Teaser-Layer verliert seine Zugkraft.
- **Empfohlene Lösung:** Im CTA einen erklärenden Halbsatz ergänzen ("…from 25-year mega-shifts down to the 6-month micro-trends they spawn") oder auf konkrete, erlebbare Foresight-Features (Momentum, Lead-Time) umschwenken, die es wirklich zu kaufen gibt.
- **Akzeptanzkriterium:** Jede Stelle, die Mega/Macro/Micro bewirbt, erklärt die Staffel in einem Satz oder verlinkt eine Erklärung; das Versprechen entspricht real verkauften Features.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCta.tsx, /home/dirk/projects/catandary-trends/frontend/src/lib/tiers.ts

### COPY-20 — Die Landing verspricht "Request early access" und "paid tiers are opening in early access", die Pricing-Seite bietet direkten Kauf ("Choose Starter") — widersprüchliche Erwartungen im selben Klickpfad.

- **Screen/Workflow:** Landing (/) vs. /trends/pricing (CTA-Konsistenz)
- **Persona:** Kaufinteressent im Funnel Landing→Pricing
- **Tier:** starter/pro
- **Beobachtung:** app/page.tsx:422,441,462: Tier-CTAs "Request early access" → /trends/pricing; FAQ Z.547-549: "The paid tiers are opening in early access." Auf /trends/pricing steht bei aktivem Stripe aber "Choose Starter/Pro/Super Pro+" mit sofortigem Checkout (live verifiziert).
- **Ursache:** Landing-Copy entstand vor Aktivierung des Stripe-Checkouts (Truth-Matrix-Stand "coming soon").
- **Auswirkung:** Wer eine Warteliste erwartet und im Checkout landet (oder umgekehrt), erlebt einen Framing-Bruch — kleiner, aber unnötiger Vertrauensverlust direkt vor der Zahlung.
- **Empfohlene Lösung:** Eine Linie wählen: entweder überall "early access"-Framing (dann auf Pricing z.B. "Join the early access — €99/mo") oder Landing-CTAs auf "See plans"/"Choose your plan" umstellen, sobald Checkout live ist.
- **Akzeptanzkriterium:** Landing-Tier-CTAs, FAQ-Antwort und Pricing-Buttons verwenden dasselbe Framing (Early Access ODER Direktkauf).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx

### COPY-21 — Der TierGate ist fair, aber generisch: gleicher Verkaufstext für jedes Feature und kein Hinweis, was der Nutzer aktuell hat.

- **Screen/Workflow:** TierGate (Evolution, Dossier)
- **Persona:** Free-Nutzer am Gate
- **Tier:** free
- **Beobachtung:** TierGate.tsx:30-33 verkauft immer "momentum, lead-time and evidence across the whole signal space" — auch am Export-Dossier, wo es um CSV/PDF geht; Badge ist immer grün, der aktuelle Plan des Nutzers wird nicht genannt. Positiv: Plan wird benannt, Pricing verlinkt, kein Dark Pattern.
- **Ursache:** Ein statischer Standardtext für alle need-Stufen/Features.
- **Auswirkung:** Der Gate-Moment ist der beste Verkaufsmoment — ein unpassender Text verschenkt ihn ("warum brauche ich Momentum, ich wollte exportieren?").
- **Empfohlene Lösung:** Optionalen benefit-Prop ergänzen und je Einsatzort füllen (Dossier: "Hand your team a cited one-pager — CSV and print-ready PDF."); Zeile "You're on Free" ergänzen, wenn Session vorhanden.
- **Akzeptanzkriterium:** Evolution- und Dossier-Gate zeigen featurespezifische Nutzentexte; bei eingeloggten Nutzern wird der aktuelle Plan im Gate genannt.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TierGate.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/dossier/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/evolution/page.tsx

### COPY-22 — Neun flache Nav-Punkte, davon fünf Foresight-Fachbegriffe auf Top-Level (Radar, Evolution, Lead Time, Clusters, Technology) — keine Hierarchie, keine progressive Disclosure.

- **Screen/Workflow:** Header-Navigation (alle Seiten)
- **Persona:** Erstbesucher
- **Tier:** free
- **Beobachtung:** Header.tsx:3-14: "Trends | Mega Trends | Cross-Industry | Foresight | Radar | Evolution | Lead Time | Clusters | Technology | Catandary | Newsletter". Für Neue ist nicht erkennbar, dass Radar–Technology Unterseiten von Foresight sind; "Evolution" und "Lead Time" sind ohne Kontext nicht dekodierbar. Zusätzlich verwirrend: Nav-Item "Catandary" (extern, neuer Tab) neben dem Logo "Catandary." (intern /trends) — gleicher Name, zwei Ziele.
- **Ursache:** Jede neue Foresight-Ansicht wurde als Top-Level-Item angehängt.
- **Auswirkung:** Kognitive Überlastung beim Einstieg; die Free-Kernnavigation (Trends, Newsletter) geht zwischen Experten-Jargon unter.
- **Empfohlene Lösung:** Foresight-Unterseiten unter einem "Foresight"-Dropdown/Untermenü gruppieren (Desktop) bzw. im MobileNav einrücken; das externe "Catandary"-Item umbenennen (z.B. "About") oder mit ↗-Kennzeichnung versehen.
- **Akzeptanzkriterium:** Top-Level-Navigation enthält maximal ~5 Einträge; Foresight-Ansichten sind als Untermenü erkennbar; kein doppelter "Catandary"-Eintrag mit unterschiedlichen Zielen.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/Header.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/MobileNav.tsx

### COPY-23 — Die Filterleiste ist strukturell gut gelöst (Advanced eingeklappt), aber einzelne Labels sind kryptisch bzw. inkonsistent.

- **Screen/Workflow:** /trends (Filterleiste)
- **Persona:** Neuer Besucher (Profi kommt klar)
- **Tier:** free
- **Beobachtung:** Suchfeld-Präfix "? Query" (SearchInput.tsx:59) statt eines verständlichen Labels; "Min Score" ohne Bezug zum CRS (siehe COPY-17); Sortieroptionen mischen Metaphern ("Signal strength" vs. "Most read" vs. "Source date"). Positiv: 11 Filterkomponenten sind auf 2 sichtbare Reihen + "Advanced ——"-Toggle mit Aktiv-Zähler reduziert (FilterBar.tsx:40-56, Auto-Expand bei aktiven Advanced-Filtern) — das ist gelungene progressive Disclosure.
- **Ursache:** Editorial-Zine-Ästhetik ("? Query") über Verständlichkeit gestellt.
- **Auswirkung:** Der Einstiegs-Screen erzeugt Deko-Rauschen an der wichtigsten Interaktionsfläche; Profis fehlt umgekehrt nichts Wesentliches.
- **Empfohlene Lösung:** "? Query" → "Search"; Sortier-Labels konsistent benennen ("Newest first / Oldest first / Highest CRS / Most read"); "Min Score" → "Min CRS".
- **Akzeptanzkriterium:** Alle Filter-Labels sind selbsterklärend; Nutzertest-Frage "Wonach sortiert 'Signal strength'?" ist aus dem Label beantwortbar.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/filters/SearchInput.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/SortSelect.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/ScoreSlider.tsx

### DS-06 — Die PESTEL-Farben sind zu 5/6 identisch mit Vertical-Farben — ein orangefarbenes Legal-Badge ist auf einer FOOD-Karte farblich nicht vom Vertical unterscheidbar.

- **Screen/Workflow:** TrendCard, TrendArticle, PestelFilter (alle Karten/Detail/Filter)
- **Beobachtung:** types.ts:72-79 vs. 62-69: L=#f97316=FOOD, E=#60a5fa=BIZ, S=#34d399=HEALTH, T=#a78bfa=TECH, En=#22d3ee=ECO. Das Mapping selbst entspricht exakt der CLAUDE.md-Vorgabe (P=Rot, E=Blau, S=Grün, T=Violett, En=Türkis, L=Orange) und wird konsistent über getPestelInfo in PestelBadge.tsx und PestelFilter.tsx:50 verwendet — die Konsistenz ist gut, nur der Farbraum ist doppelt belegt. Auf einer TECH-Karte (violetter Stripe) erscheint das violette T-Badge wie eine Vertical-Wiederholung.
- **Ursache:** Beide Paletten wurden unabhängig aus derselben Tailwind-400er-Reihe gewählt.
- **Auswirkung:** Zwei Taxonomien (Branche vs. PESTEL-Dimension) sind visuell nicht als getrennte Systeme lesbar; Lerneffekt der Farbcodierung wird geschwächt.
- **Empfohlene Lösung:** Eine der beiden Paletten verschieben — pragmatisch: PESTEL auf abgesenkte/entsättigte Varianten oder eigene Töne (z.B. L=#fb923c anstatt #f97316, E dunkleres Blau) und beide Paletten als @theme-Tokens führen; CLAUDE.md-Farbnamen (Rot/Blau/Grün/...) bleiben dabei erfüllt.
- **Akzeptanzkriterium:** Kein Hex-Wert kommt gleichzeitig in VERTICALS und PESTEL vor; Badges bleiben den CLAUDE.md-Farbfamilien zugeordnet.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/lib/types.ts, /home/dirk/projects/catandary-trends/frontend/src/components/PestelBadge.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/filters/PestelFilter.tsx

### DS-07 — Die dreistufige CRS-Farblogik ist defekt: Stufe >=80 und Stufe >=65 sind beide Chartreuse (einmal als Token, einmal hartkodiert), erst <65 springt hart auf Warnorange.

- **Screen/Workflow:** TrendCard/TrendRow/TrendArticle (CRS-Score)
- **Beobachtung:** TrendScore.tsx:12: `const color = crs >= 80 ? "var(--color-accent)" : crs >= 65 ? "#d4ff3a" : "var(--color-warn)"` — #d4ff3a IST --color-accent, der Mittelzweig ist toter Code. Zusätzlich zeigt TrendRow.tsx:71 den Score-Balken immer in bg-accent ohne jede Abstufung — zwei Score-Darstellungen mit unterschiedlicher Semantik.
- **Ursache:** Hardcodierter Hex statt Token beim Bau der Abstufung; vermutlich war für die Mittelstufe ein anderer Wert (z.B. accent-deep) gemeint.
- **Auswirkung:** Die versprochene Score-Differenzierung existiert visuell nicht; Nutzer sehen nur binär Chartreuse/Orange, TrendRow widerspricht TrendCard.
- **Empfohlene Lösung:** Mittelstufe auf var(--color-accent-deep) setzen (oder Dreistufigkeit bewusst streichen) und dieselbe Logik in TrendRow anwenden; Hex-Literal durch Token ersetzen.
- **Akzeptanzkriterium:** CRS 70 rendert sichtbar anders als CRS 90; TrendCard und TrendRow nutzen dieselbe Farb-Funktion.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TrendScore.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/TrendRow.tsx

### DS-08 — Drei verschiedene Grüns konkurrieren als Positiv-Semantik (#22c55e rising, #16a34a new/auth, #34d399 auch HEALTH-Vertical), und TechReader nutzt das Rising-Grün zusätzlich als Technologie-Identitätsfarbe.

- **Screen/Workflow:** MomentumBadge, MegaTrendsPage, Evolution-Badges, TechReader, MomentumBoard
- **Beobachtung:** MomentumBadge.tsx:8 rising=#22c55e; evolution/page.tsx:193 "New"-Badge=#16a34a; TechReader.tsx:25 CRISPR=#22c55e als Kurvenfarbe direkt neben Battery=#34d399 — Grün ist hier Identität, eine Zeile darüber Semantik. globals.css:204 definiert --lp-rising=#22c55e nur landing-scoped, MomentumBadge hardcodet denselben Wert separat. Momentum "unknown"=#a855f7 (violett) kollidiert zudem mit TECH-nahen Violett-Tönen.
- **Ursache:** Semantik-Farben wurden nie als globale Tokens angelegt; jede Komponente definiert lokal.
- **Auswirkung:** "Grün = steigend" wird verwässert; im TechReader kann eine fallende Kurve theoretisch grün sein, weil Grün dort Identität ist.
- **Empfohlene Lösung:** Globale Semantik-Tokens --color-rising/--color-declining/--color-stable/--color-new definieren, alle Komponenten darauf umstellen; TechReader-Kurven auf Nicht-Semantik-Farben (z.B. Tier- oder Neutraltöne) umfärben.
- **Akzeptanzkriterium:** Genau ein Grün-Hex für "rising/new" im Codebase (als Token); TechReader-Identitätsfarben enthalten kein #22c55e/#16a34a.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/MomentumBadge.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/MegaTrendsPage.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/evolution/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/landing/TechReader.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/globals.css

### DS-09 — Es gibt kein Fokus-System: kein einziges focus-visible im Codebase, und der TrendRadar setzt outline:none auf fokussierbare Blips ohne gleichwertigen Ersatz.

- **Screen/Workflow:** gesamte App (interaktive Elemente)
- **Persona:** Keyboard-/Power-User (B2B-Analysten)
- **Beobachtung:** `grep -rc focus-visible frontend/src` = 0 Treffer. Nur 3 Inputs definieren `focus:outline-none focus:border-accent` (SearchInput, TechnologyTool.tsx:238, ForesightCockpit). TrendRadar.tsx:269 `.radar-blip { outline: none }` bei tabIndex=0 (Z.173) — Fokus ist nur eine fill-opacity-Änderung 0.6→0.95. Alle Karten-Links, Filter-Chips, Pagination-Buttons verlassen sich auf die UA-Default-Outline, die zum Editorial-Look nicht passt und teils schwer sichtbar ist. Disabled-Stile divergieren: opacity-30/40/50/60 je nach Komponente.
- **Ursache:** Zustände wurden pro Komponente ad hoc gelöst; kein gemeinsames Interaktions-Primitive.
- **Auswirkung:** Tastaturbedienung ist auf dem Radar praktisch unsichtbar; inkonsistente Fokus-/Disabled-Optik wirkt unfertig und ist ein A11y-Risiko für B2B-Abnahmen.
- **Empfohlene Lösung:** Globale Regel in globals.css: `:where(a,button,[tabindex]):focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }`; outline:none im Radar entfernen bzw. durch Stroke-Highlight ersetzen; Disabled auf einen Standard (z.B. opacity-40 + cursor-not-allowed) normieren.
- **Akzeptanzkriterium:** Tab-Navigation zeigt auf /trends, /trends/foresight/radar und im FilterBar durchgehend einen sichtbaren Accent-Fokusring; genau ein Disabled-Opacity-Wert im Codebase.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TrendRadar.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/Pagination.tsx

### DS-10 — font-bold (Gewicht 700) wird auf 6 Seiten genutzt, aber IBM Plex Sans ist nur in 300-600 geladen — der Browser rendert Faux-Bold.

- **Screen/Workflow:** /trends/pricing, /account, Radar/Evolution/Dossier, Newsletter-Unsubscribe
- **Beobachtung:** layout.tsx:22-27 lädt IBM_Plex_Sans mit weight ["300","400","500","600"]. `grep -rln font-bold` trifft account/page.tsx, pricing/page.tsx, foresight/evolution, newsletter/unsubscribe, foresight/radar, foresight/dossier (z.B. radar/page.tsx:42 `text-3xl font-bold`). 700 wird vom Browser synthetisch verbreitert — sichtbar schlechteres Letterform-Rendering als echtes Plex SemiBold.
- **Ursache:** Off-System-Seiten nutzen die Tailwind-Default-Skala statt der geladenen Gewichte.
- **Auswirkung:** Headlines der generischen Seiten wirken matschig/verzerrt gegenüber dem restlichen Schriftbild.
- **Empfohlene Lösung:** Entweder Gewicht 700 in next/font aufnehmen oder (besser, im Zuge von DS-04/DS-05) font-bold durch font-semibold bzw. font-display-Serif ersetzen.
- **Akzeptanzkriterium:** Kein font-bold ohne geladenes 700er-Gewicht; Rendering der Pricing-Headline entspricht einem tatsächlich geladenen Font-Weight.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/layout.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/foresight/radar/page.tsx

### KEY-09 — Pagination und sämtliche Filter-Controls sind onClick-Buttons mit router.push statt echte Links — kein Öffnen in neuem Tab, keine crawlbaren hrefs.

- **Screen/Workflow:** /trends (Pagination + alle Filter-Controls)
- **Persona:** Key User / Power User
- **Beobachtung:** Pagination.tsx:35-83 rendert ausschließlich <button onClick={goToPage}>; alle 11 Filter-Komponenten nutzen router.push (grep: ActiveChips, SearchInput, SignalTypeFilter, DateRangeChips, ScoreSlider, PestelFilter, SourceExcludeToggle, VerticalsMultiFilter, ViewModeToggle, SortSelect, MegaTrendChips). Der Docblock in filter-params.ts:5 behauptet dagegen 'every filter control is a link'. Mittelklick/Cmd-Klick auf 'Seite 2' oder einen Vertical-Chip ist unmöglich.
- **Ursache:** Einheitliches Client-Handler-Muster statt <Link href>-Muster; die Dokumentation beschreibt den ursprünglichen Plan.
- **Auswirkung:** Power-User-Grundgesten (Ergebnisseite im Hintergrund-Tab öffnen, Filtervariante parallel vergleichen) funktionieren nicht; Suchmaschinen sehen keine paginierten Folgeseiten.
- **Empfohlene Lösung:** Mindestens Pagination und die reinen Toggle-Chips (Vertical, PESTEL, Range, Mega) auf <Link href={buildQueryString(...)}> umstellen — die Query-Strings werden bereits zentral gebaut; Slider/Suche dürfen Buttons bleiben.
- **Akzeptanzkriterium:** Cmd/Mittelklick auf eine Paginierungszahl und auf einen Vertical-Chip öffnet die korrekte gefilterte URL in einem neuen Tab.
- **Aufwand:** M · **Dateien:** frontend/src/components/Pagination.tsx, frontend/src/components/filters/VerticalsMultiFilter.tsx, frontend/src/components/filters/DateRangeChips.tsx, frontend/src/lib/filter-params.ts

### KEY-10 — Eine Seitenzahl jenseits des Endes zeigt eine irreführende Leermeldung und keine Rückkehr-Navigation.

- **Screen/Workflow:** /trends?page=<out-of-range>
- **Persona:** Key User / Power User
- **Beobachtung:** Live: /trends?page=9999 (max. wäre 5.041) → leerer Zustand mit '—— 404 · No signals' / 'The signal channel is quiet' / 'The pipeline is running — new signals will appear here once classified' (TrendsEmpty.tsx:39-47, Zweig ohne aktive Filter) — die Pagination wird bei 0 Treffern gar nicht gerendert (page.tsx:125). Kein 'Clear all', kein Link auf Seite 1.
- **Ursache:** parseFilterParams clampt page nur nach unten (>=1), nicht gegen totalPages; TrendsEmpty unterscheidet nicht zwischen 'keine Daten' und 'Seite außerhalb des Bereichs'.
- **Auswirkung:** Wer eine gebookmarkte tiefe Seite öffnet (Bestand schrumpft/Filter ändert sich), liest fälschlich 'Plattform ist leer' und hat nur den Browser-Back-Button.
- **Empfohlene Lösung:** Wenn page > totalPages: auf die letzte gültige Seite redirecten (Server-seitig trivial, total liegt vor) oder im Empty-State einen 'Zur ersten Seite'-Link plus korrekte Copy ('Diese Seite existiert nicht mehr') zeigen.
- **Akzeptanzkriterium:** curl auf /trends?page=9999 liefert entweder einen Redirect auf die letzte Seite oder eine Meldung mit funktionierendem Link zu Seite 1 — nie die 'signal channel is quiet'-Copy.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/page.tsx, frontend/src/components/TrendsEmpty.tsx, frontend/src/lib/filter-params.ts

### KEY-11 — Debounced Zwischenzustände werden per router.push in die Browser-History geschrieben — die Zurück-Taste iteriert durch Tippfragmente und Slider-Schritte.

- **Screen/Workflow:** /trends (Suchfeld + Score-Slider)
- **Persona:** Key User / Power User
- **Beobachtung:** SearchInput.tsx:30/37 committet nach 300 ms Debounce mit router.push — wer 'longevity' mit Denkpausen tippt, erzeugt History-Einträge für 'lon', 'longev', 'longevity'. ScoreSlider.tsx:29/36 pusht analog jeden 250-ms-Zwischenwert beim Ziehen.
- **Ursache:** router.push statt router.replace für nicht-finale Zustände.
- **Auswirkung:** Der Zurück-Button — für Power-User das Werkzeug, um zur vorherigen Ansicht zu springen — führt durch eine Kette von Suchfragmenten statt zur letzten echten Ansicht.
- **Empfohlene Lösung:** Debounce-Commits mit router.replace ausführen; nur explizite Commits (Enter, Blur, Slider-Release/onPointerUp) mit router.push in die History schreiben.
- **Akzeptanzkriterium:** Nach Eintippen eines Suchbegriffs mit Pausen führt ein einziger Zurück-Klick zur Ansicht vor der Suche.
- **Aufwand:** S · **Dateien:** frontend/src/components/filters/SearchInput.tsx, frontend/src/components/filters/ScoreSlider.tsx

### KEY-12 — Die Sortieroption 'Source date' liefert dieselbe Reihenfolge wie 'Newest first' — eine redundante, verwirrende Auswahl.

- **Screen/Workflow:** /trends (Sort-Dropdown)
- **Persona:** Key User / Power User
- **Beobachtung:** db.ts buildOrderBy: date_desc → 'ORDER BY t.sort_date DESC NULLS LAST', source_date_desc → 'ORDER BY t.sort_date DESC NULLS LAST, t.created_at DESC' — identische Primärsortierung. Live verifiziert: die ersten 5 Slugs von /trends?view=list und /trends?view=list&sort=source_date_desc sind identisch.
- **Ursache:** CAPPED_DATE wurde auf t.sort_date vereinheitlicht; die frühere Unterscheidung Publikations- vs. Quellendatum ging dabei verloren, das Label blieb.
- **Auswirkung:** Ein Power-User, der bewusst nach Quellendatum sortieren will (z. B. um Publikations-Lag der Pipeline auszublenden), bekommt kommentarlos dasselbe Ergebnis und misstraut fortan der Sortierung.
- **Empfohlene Lösung:** Entweder source_date_desc auf das echte raw_entries.published_date sortieren lassen oder die Option aus VALID_SORT_BY/SORT_LABELS entfernen.
- **Akzeptanzkriterium:** Beide Sortieroptionen liefern nachweislich unterschiedliche Reihenfolgen, oder es gibt nur noch eine 'Newest first'-Option.
- **Aufwand:** S · **Dateien:** frontend/src/lib/db.ts, frontend/src/lib/filter-params.ts

### KEY-13 — Das zentrale Analyse-Tool ist komplett deutschsprachig, während die gesamte restliche Site englisch ist.

- **Screen/Workflow:** /trends/foresight/technology
- **Persona:** Key User / Power User
- **Beobachtung:** TechnologyTool.tsx: '—— Technologie-Analyse · Verbesserungsrate & Innovationskette', 'Beschreibe eine Technologie', 'Analysieren'/'Analysiere…', 'Patentklassen — deine Auswahl', Fehlertexte 'Analyse fehlgeschlagen', 'Zeitüberschreitung — versuch eine engere Phrase', Zahlformat toLocaleString('de') — direkt über/unter englischen Überschriften ('Where innovation moves fastest', 'How we predict improvement rates'). Auch die metadata der Foresight-Index-Seite (foresight/page.tsx:14) ist deutsch.
- **Ursache:** Das Tool wurde später separat entwickelt, ohne die EN-Sprachkonvention der Site.
- **Auswirkung:** Auf der Pro-Flaggschiff-Seite wirkt der Sprachbruch unfertig und schließt internationale Nutzer vom wichtigsten Werkzeug aus (Duzen inklusive).
- **Empfohlene Lösung:** TechnologyTool-Strings und die Foresight-metadata auf Englisch umstellen (Zahlformat 'en-US' wie im Rest der Site).
- **Akzeptanzkriterium:** Auf /trends/foresight/technology existiert kein deutschsprachiger UI-String mehr (grep nach 'Analysieren', 'Beschreibe', 'Zeitüberschreitung' leer).
- **Aufwand:** S · **Dateien:** frontend/src/components/foresight/TechnologyTool.tsx, frontend/src/app/trends/foresight/page.tsx

### KEY-14 — Cockpit-Fehler erscheinen als rohe HTTP-Codes, und das 30/min-Rate-Limit ist bei der tipp-getriebenen Suche schnell erreicht.

- **Screen/Workflow:** /trends/foresight (Cockpit)
- **Persona:** Key User / Power User
- **Beobachtung:** ForesightCockpit.tsx:109 wirft bei !resp.ok 'HTTP 429' als Fehlertext in die UI — ohne Retry-Hinweis, obwohl die API einen retry-after-Header liefert (search/route.ts:361). Die Suche feuert nach jedem 400-ms-Tippstopp (Zeile 125); /api/search erlaubt 30 req/min. Erster Cold-Request live: 11,8 s (Ollama-Embedding-Load) mit nur einem Spinner, warm 0,6-0,7 s.
- **Ursache:** Fehlerpfad reicht die rohe Exception durch; kein 429-Sonderfall.
- **Auswirkung:** Ein Power-User, der Query-Varianten durchprobiert, landet im Limit und sieht kryptisch 'HTTP 429'; der 12-Sekunden-Cold-Start ohne Erklärung wirkt wie ein Hänger.
- **Empfohlene Lösung:** 429 gesondert behandeln ('Zu viele Suchanfragen — in Xs wieder verfügbar' aus retry-after) und beim ersten Request einen Hinweis wie 'Erste Suche wärmt das Modell auf' zeigen; Suche erst ab z. B. 3 Zeichen auslösen.
- **Akzeptanzkriterium:** Ein provoziertes 429 zeigt eine verständliche Meldung mit Countdown statt 'HTTP 429'.
- **Aufwand:** S · **Dateien:** frontend/src/components/ForesightCockpit.tsx, frontend/src/app/api/search/route.ts

### KEY-15 — Es gibt keinerlei 'Neu seit letztem Besuch'-Mechanik — der Rückkehrer muss die Antwort selbst konstruieren.

- **Screen/Workflow:** /trends (Wiederkehr-Szenario)
- **Persona:** Occasional User (Rückkehr nach 4 Wochen)
- **Beobachtung:** Kein localStorage/Cookie-Merker im gesamten Frontend (grep leer), keine Neu-Markierung auf Karten, Datumsfilter endet bei 30d (DateRangeChips), /trends/newsletter hat kein Archiv vergangener Ausgaben. Der Rückkehrer kann sich nur ?range=30d&sort=date_desc zusammenbauen — muss diese Kombination aber kennen; bei >4 Wochen Abwesenheit greift selbst das nicht mehr. MovingNow ('rising for months') und der Cluster-Stand (Radar 'As of Jul 14, 2026' — bei Abruf 9 Tage alt) beantworten 'was hat sich bewegt' nur auf Cluster-Ebene ohne Bezugspunkt 'seit wann'.
- **Ursache:** Es existiert kein Konzept eines Besuchszeitpunkts (weder anonym client-seitig noch im Account).
- **Auswirkung:** Der Occasional User — die Newsletter-Zielgruppe — findet den Einstieg 'was ist neu für mich' nicht und springt ab; genau dieses Bedürfnis soll die Plattform als Lead-Magnet bedienen.
- **Empfohlene Lösung:** Anonym per localStorage den letzten Besuchszeitpunkt merken und beim Wiederkommen einen dismissbaren Chip 'Seit deinem letzten Besuch: N neue Signale — anzeigen' rendern, der auf die bestehende Filter-URL (?range=…&sort=date_desc) mappt; für Accounts denselben Wert serverseitig.
- **Akzeptanzkriterium:** Ein Besucher, der nach >7 Tagen zurückkehrt, sieht auf /trends einen Hinweis mit der Anzahl neuer Signale seit dem letzten Besuch, der per Klick die entsprechend gefilterte Liste öffnet.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/page.tsx, frontend/src/components/TrendsHero.tsx

### ONB-10 — Zentrale Kuerzel und Fachbegriffe werden am Ort der Nutzung nicht erklaert: CRS nur per Maus-Hover, TIR/CPC/pp/SPNP/lazy-embed gar nicht.

- **Screen/Workflow:** /trends (Karten), /trends/pricing, / (Landing)
- **Persona:** Niedrige Medienkompetenz; fachlich kompetent aber digital unerfahren
- **Tier:** free
- **Beobachtung:** Auf jeder Trend-Karte steht "CRS 73" ohne title-Attribut oder Link; die Erklaerung existiert nur als Hover-Tooltip in TrendScore.tsx (onMouseEnter — auf Touch-Geraeten und per Tastatur unerreichbar) und versteckt auf /trends/methodology ("Catandary Relevance Score (0-100)"). Pricing-Features: "Technology explorer: CPC lead-time axes", "TIR metrics (cycle time, immediate importance)", "On-demand analysis of your own scopes (lazy-embed)" — lazy-embed ist internes Implementierungsvokabular. Landing: "+6.3 pp", "SPNP method" ohne Kurzerklaerung.
- **Ursache:** TrendScore.tsx (nur Mouse-Events); tiers.ts Feature-Strings wurden aus der internen Featurematrix uebernommen.
- **Auswirkung:** Die beiden simulierten Personas koennen den zentralen Score der Plattform nicht deuten (Touch-Nutzer sehen die Erklaerung nie) und verstehen auf der Pricing-Seite nicht, was sie fuer €499 bekommen — Jargon ersetzt den Nutzen.
- **Empfohlene Lösung:** CRS-Badge klickbar auf /trends/methodology#crs verlinken + title-Attribut setzen; Pricing-Features in Nutzenprache umschreiben ("lazy-embed" streichen, "CPC" zu "patent-class", TIR beim ersten Auftreten ausschreiben); auf der Landing "pp" als "percentage points" ausschreiben oder Tooltip.
- **Akzeptanzkriterium:** CRS ist auf Karten per Tap/Klick erklaerbar (Link oder Touch-faehiger Tooltip); die Pricing-Featureliste enthaelt keine der Zeichenketten "lazy-embed", "CPC" (unerklaert) mehr.
- **Aufwand:** S · **Dateien:** frontend/src/components/TrendScore.tsx, frontend/src/lib/tiers.ts, frontend/src/app/page.tsx

### ONB-11 — Der Pricing-Untertitel bezeichnet das Free-Angebot gegenueber dem Kunden selbst als "lead magnet" — internes Marketing-Vokabular in der Kundenansprache.

- **Screen/Workflow:** /trends/pricing
- **Persona:** Alle Kaufinteressenten
- **Tier:** free
- **Beobachtung:** Beobachteter Text auf /trends/pricing: "Evidence-based foresight with clickable primary sources — the free feed is the lead magnet, the paid tiers are where the lead-time edge lives." (pricing/page.tsx:36).
- **Ursache:** Formulierung aus der internen Strategie (CLAUDE.md: "Free Layer … Lead-Generator") wurde woertlich in die UI uebernommen.
- **Auswirkung:** Der Nutzer liest, dass er als "Lead" eingefangen werden soll — das kollidiert frontal mit dem "Honest by construction"-Markenversprechen und wirkt bei einer sonst betont ehrlichen Site unfreiwillig zynisch.
- **Empfohlene Lösung:** Umschreiben in Nutzersprache, z.B. "The free feed is yours to keep — the paid tiers open the lead-time engine."
- **Akzeptanzkriterium:** Der String "lead magnet" kommt in keiner ausgelieferten Seite mehr vor (curl-grep leer).
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/pricing/page.tsx

### ONB-12 — Elf Top-Level-Navigationspunkte ohne Hierarchie, darunter fuenf Foresight-Unterseiten neben "Foresight" selbst und ein zweites "Catandary" neben dem Logo.

- **Screen/Workflow:** Header (alle Seiten)
- **Persona:** Onboarding-Nutzer, niedrige Medienkompetenz
- **Tier:** free
- **Beobachtung:** Nav auf jeder Seite: Trends, Mega Trends, Cross-Industry, Foresight, Radar, Evolution, Lead Time, Clusters, Technology, Catandary, Newsletter — Radar/Evolution/Lead Time/Clusters/Technology sind alle Unterseiten von /trends/foresight/, stehen aber gleichrangig neben "Foresight". "Catandary" (externer Link auf https://catandary.de) steht zusaetzlich zum Brand-Logo "Catandary." links.
- **Ursache:** frontend/src/components/Header.tsx listet alle Foresight-Routen flach.
- **Auswirkung:** Ein Erstnutzer kann nicht erkennen, was Ober- und Unterseite ist, was "Lead Time" von "Evolution" unterscheidet oder warum "Catandary" zweimal vorkommt — die Informationsarchitektur der App wird unlesbar, bevor man sie benutzt hat.
- **Empfohlene Lösung:** Foresight-Unterpunkte unter einem "Foresight"-Dropdown (oder Sekundaer-Nav innerhalb des Cockpits) gruppieren; den externen "Catandary"-Link als "catandary.de ↗" kennzeichnen oder in den Footer verschieben.
- **Akzeptanzkriterium:** Die Top-Level-Nav hat max. 6 Punkte; Foresight-Unterseiten sind visuell als Unterpunkte erkennbar; kein doppeltes "Catandary".
- **Aufwand:** M · **Dateien:** frontend/src/components/Header.tsx, frontend/src/components/MobileNav.tsx

### ONB-13 — Ein Hauptmenuepunkt fuehrt fuer alle Scopes auf einen leeren "wird noch berechnet"-Zustand.

- **Screen/Workflow:** /trends/foresight/evolution
- **Persona:** Occasional User
- **Tier:** pro
- **Beobachtung:** GET /trends/foresight/evolution zeigt fuer "All industries" wie "Health & Wellness" nur: "Evolution is being computed — The cross-window lineage for this scope is still being built." Kein Datum, keine Angabe wann. Das Feature ist zugleich als Pro-Feature ("Trend evolution & lineage") auf der Pricing-Seite gelistet und mit TierGate versehen (evolution/page.tsx:157), der Gate greift aber nie, weil der Empty-State vorher rendert.
- **Ursache:** Die Lineage-Daten sind serverseitig nicht berechnet; der Menuepunkt ist trotzdem prominent in der Top-Nav.
- **Auswirkung:** Wer aus Neugier (oder als zahlender Pro-Kunde wegen des Pricing-Versprechens) klickt, bekommt nichts — ein leeres Kernfeature in der Hauptnavigation beschaedigt die Glaubwuerdigkeit der uebrigen Zahlen.
- **Empfohlene Lösung:** Menuepunkt ausblenden bis Daten existieren, oder den Empty-State mit konkretem Zeitpunkt/Umfang versehen ("computed weekly, first run …") — und das Feature solange auf der Pricing-Seite als "coming soon" kennzeichnen.
- **Akzeptanzkriterium:** Entweder liefert /trends/foresight/evolution echte Lineage-Inhalte, oder der Nav-Punkt fehlt bzw. das Pricing kennzeichnet "Trend evolution" als coming soon.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/foresight/evolution/page.tsx, frontend/src/components/Header.tsx, frontend/src/lib/tiers.ts

### ONB-14 — Die Technology-Seite liefert 1,88 MB SSR-HTML, weil pro Technologie jede Jahreszeile als Text gerendert wird.

- **Screen/Workflow:** /trends/foresight/technology
- **Persona:** Mobile Nutzer, Occasional User
- **Tier:** pro
- **Beobachtung:** curl misst 1.884.559 Bytes HTML (6.307 sichtbare Textzeilen), u.a. wiederholte Zeilen wie "1990: 0.63% of research activity", "1991: 0.33% …" fuer jede kuratierte Technologie und jedes Jahr 1990-2026. Zum Vergleich: /trends 108 KB, Radar 216 KB, Clusters 235 KB.
- **Ursache:** Die Chart-Rohdaten werden als serverseitige Textlisten (vermutlich sr-only/noscript-Fallback) fuer den gesamten Katalog mitgeliefert statt nachgeladen oder aggregiert.
- **Auswirkung:** Auf Mobilfunk mehrere Sekunden Transfer + Parse fuer eine Seite, die als Pro-Verkaufsargument dient; Suchmaschinen und Screenreader ertrinken in Zahlenzeilen.
- **Empfohlene Lösung:** Jahresreihen als JSON fuer die Client-Charts liefern (oder per API nachladen) und den textuellen Fallback auf eine komprimierte Zusammenfassung pro Technologie reduzieren.
- **Akzeptanzkriterium:** GET /trends/foresight/technology liefert < 500 KB HTML bei unveraendertem sichtbarem Funktionsumfang.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/foresight/technology/page.tsx, frontend/src/components/foresight/TechnologyTool.tsx

### ONB-15 — Rohe, unaufbereitete Quellen-Strings werden als "Trends" bzw. Beleg praesentiert: CPC-Klassentitel und ALL-CAPS-Granttitel mit Tippfehlern.

- **Screen/Workflow:** /trends/foresight + /foresight/lead-time + /foresight/clusters
- **Persona:** Niedrige Medienkompetenz, Onboarding-Nutzer
- **Tier:** free/starter
- **Beobachtung:** Foresight-Cockpit/Lead-time-Teaser listet als Technologien woertlich CPC-Klassentexte: "Making textile fabrics, e.g. from fibres or filamentary material — research ~3y ahead" und "Sound-producing devices". Cluster-Explorer zeigt als "Representative signals" rohe Granttitel inkl. Quell-Tippfehlern: "Innate reponses to microbial infection", "Mitochondrial phophorylatioon signaling", "LABTM IC100 HIGH THROUGHPUT MICROSCOPY SYSTEM: CELL BIOLOGY" (zweimal fast identisch). Tag-Listen mischen Duplikate: "machine_learning · machine learning", "drug discovery · drug_discovery".
- **Ursache:** CPC-Titel und Signal-Titel werden ungefiltert aus der DB gerendert; keine Titel-Normalisierung/Dedup fuer die Anzeige.
- **Auswirkung:** Der erste Eindruck der Foresight-Ebene (das Verkaufsargument) wirkt wie ein Datenbank-Dump: Ein Neuer kann "Sound-producing devices ~3y ahead" nicht als Trend lesen und zweifelt an der Kuratierungsqualitaet — im direkten Widerspruch zum "curated/defensible"-Versprechen.
- **Empfohlene Lösung:** CPC-Titel fuer die Anzeige kuerzen/uebersetzen (Mapping-Tabelle fuer die Top-Klassen), Representative-Signals nach Titel-Aehnlichkeit dedupen und lange ALL-CAPS-Titel in Title-Case normalisieren; Tag-Duplikate (underscore vs. space) zusammenfuehren.
- **Akzeptanzkriterium:** Lead-time-Teaser zeigt keine rohen CPC-Langtitel mit "e.g." mehr; in einer Cluster-Karte erscheinen keine zwei nahezu identischen Repraesentativ-Signale und keine underscore/space-Tag-Duplikate.
- **Aufwand:** M · **Dateien:** frontend/src/components/ForesightCockpit.tsx, frontend/src/app/trends/foresight/lead-time/page.tsx, frontend/src/app/trends/foresight/clusters/page.tsx

### ONB-16 — Die erste Seite des Cross-Industry-Feeds bestand komplett aus Pharma-Artikeln zweier Schwester-Quellen vom selben Tag.

- **Screen/Workflow:** /trends (Seite 1)
- **Persona:** Onboarding-Nutzer
- **Tier:** free
- **Beobachtung:** Alle 12 Karten auf Seite 1 (Sortierung "Newest first") stammten vom 23 JUL 2026 aus Fierce Pharma/Fierce Biotech (HLTH/TECH-Pharma-Themen) — direkt unter dem Hero, der "Cross-Industry Trend Intelligence" mit 8 Vertikalen verspricht.
- **Ursache:** Newest-first + batchweises Publizieren pro Quelle: der juengste Publish-Batch dominiert Seite 1 vollstaendig.
- **Auswirkung:** Der Erstbesucher sieht das Kernversprechen (branchenuebergreifend) auf der wichtigsten Seite widerlegt und haelt das Produkt fuer ein Pharma-Newsletter-Tool.
- **Empfohlene Lösung:** Default-Sortierung fuer die Erstansicht diversifizieren: pro Quelle/Vertikale interleaven (z.B. max. 3 Karten derselben Quelle in Folge) oder einen "Top across verticals"-Default mit CRS-Gewichtung anbieten; "Newest first" bleibt als explizite Option.
- **Akzeptanzkriterium:** Die ungefilterte Erstansicht von /trends zeigt Karten aus mindestens 3 Vertikalen bzw. nie mehr als 4 aufeinanderfolgende Karten derselben Quelle.
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/page.tsx, frontend/src/lib/db.ts

### ONB-17 — Ein als Trend-Signal publizierter Artikel basiert auf gesponsertem Content der Quelle, ohne dass das im Artikel gekennzeichnet ist.

- **Screen/Workflow:** /trends/[slug] (Artikel)
- **Persona:** Fachlich kompetent aber digital unerfahren (prueft Quellen)
- **Tier:** free
- **Beobachtung:** Der Artikel "Insurance Coverage Barriers Limit Non-Opioid Pain Therapy Adoption" verlinkt als Original Source auf https://www.fiercepharma.com/sponsored/access-key-driver-non-opioid-pain-management-adoption — ein /sponsored/-Pfad (Advertorial), im UI aber gleichrangig als "Trade / Fierce Pharma" mit CRS 73 ausgewiesen.
- **Ursache:** Die Pipeline unterscheidet beim Ingest nicht zwischen redaktionellem und gesponsertem Content derselben RSS-Quelle; das Frontend hat keine Kennzeichnung dafuer.
- **Auswirkung:** Wer die Quelle prueft (das beworbene Kernverhalten: "every number one click from its primary source"), entdeckt Werbung hinter einem "Signal" — genau der Moment, in dem das Evidence-Versprechen zum Bumerang wird.
- **Empfohlene Lösung:** URLs mit /sponsored/ o.ae. beim Ingest markieren und entweder herausfiltern oder im Artikel sichtbar als "Sponsored source" labeln (und im CRS beruecksichtigen).
- **Akzeptanzkriterium:** Artikel mit /sponsored/-Quell-URL tragen ein sichtbares Label oder erscheinen nicht mehr im publizierten Feed.
- **Aufwand:** M · **Dateien:** frontend/src/components/TrendArticle.tsx, pipeline/feed_poller.py

## S4 (15 Findings)

### A11Y-16 — Filter-Entfernen-Chips kommunizieren ihre Aktion nicht, und das aria-label auf dem Wrapper-div ist wirkungslos.

- **Screen/Workflow:** /trends (ActiveChips)
- **Persona:** Screenreader-Nutzer
- **Beobachtung:** ActiveChips.tsx:28-31: aria-label="Active filters" auf einem <div> ohne role wird von AT ignoriert. Z.36-48: Der Button heisst nur nach dem Chip-Wert (z.B. "TECH"), das × ist aria-hidden — dass Klick den Filter ENTFERNT, wird nicht vermittelt; identisch benannte Filter-Buttons (aria-pressed-Chips) existieren gleichzeitig auf der Seite.
- **Auswirkung:** Verwechslungsgefahr: "TECH" (Filter setzen) vs. "TECH" (Filter entfernen) sind fuer SR-Nutzer nicht unterscheidbar.
- **Empfohlene Lösung:** Wrapper role="group" (oder ul/li) geben; Buttons aria-label={`Remove filter: ${c.label}`}.
- **Akzeptanzkriterium:** SR liest "Remove filter: TECH, button"; Gruppe erscheint benannt im Rotor.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/filters/ActiveChips.tsx

### A11Y-17 — Ein grosser Teil der UI-Beschriftung ist 8-10px klein (Mono-Labels), teils mit 0.22em Sperrung in Uppercase.

- **Screen/Workflow:** Landing + Foresight (Mikro-Labels)
- **Persona:** Aeltere/sehbehinderte B2B-Entscheider
- **Beobachtung:** globals.css: .lp-lbl .56rem (~9px, Z.244), .lp-ticks .52rem (~8,3px, Z.303), .lp-instrument .lp-cap .56rem (Z.247); Komponenten durchgaengig text-[9px]/text-[10px] (z.B. ScoreSlider.tsx:42, DateRangeChips, Header-Nav 10px). Kontrast besteht (5,8:1), aber die Groessen liegen weit unter der 12px-Lesbarkeitsschwelle.
- **Auswirkung:** Kein harter WCAG-Fail (Zoom funktioniert), aber hohe Lesereibung fuer die Kernzielgruppe; Uppercase+Letterspacing verschlechtert es zusaetzlich.
- **Empfohlene Lösung:** Funktionale Labels (Filternamen, Slider-Skala, Proof-Labels) auf mind. 11-12px anheben; 8-9px nur fuer reine Deko-Eyebrows behalten.
- **Akzeptanzkriterium:** Kein bedeutungstragendes Label unter 11px computed font-size auf Landing und /trends.
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css

### A11Y-19 — Das Cockpit-Suchfeld erzwingt autoFocus beim Seitenaufbau.

- **Screen/Workflow:** /trends/foresight (Cockpit)
- **Persona:** Screenreader-/Tastatur-Nutzer
- **Beobachtung:** ForesightCockpit.tsx:178 setzt autoFocus auf das Suchfeld — beim Laden springt der Fokus an der kompletten Navigation vorbei mitten in die Seite; SR-Nutzer verlieren den Seitenkontext (Titel/Ueberschrift wird uebersprungen).
- **Auswirkung:** Erschwerte Orientierung beim Seiteneinstieg (WCAG 2.4.3-Graubereich); in Kombination mit fehlendem Skip-Link inkonsistentes Fokusverhalten zwischen Seiten.
- **Empfohlene Lösung:** autoFocus entfernen; stattdessen Shortcut (z.B. "/") zum Fokussieren anbieten.
- **Akzeptanzkriterium:** Nach Laden von /trends/foresight liegt der Fokus auf dem Dokumentanfang.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/ForesightCockpit.tsx

### ARCH-22 — Die Sitemap ignoriert die Landing, alle Foresight-Seiten, Pricing und Methodology und listet nur die letzten 500 von ~60k Artikeln.

- **Screen/Workflow:** sitemap.ts / robots
- **Persona:** SEO/Owner
- **Beobachtung:** sitemap.ts enthält statisch nur /trends, /mega, /cross-vertical, /newsletter plus Mega-Detail und getTrends({limit:500}); weder / noch /trends/foresight/* noch /trends/pricing noch /trends/methodology kommen vor.
- **Ursache:** Sitemap stammt aus der Zeit vor Landing/Foresight/Pricing und wurde nicht erweitert.
- **Auswirkung:** Die konversionsrelevantesten Seiten (Landing, Pricing, Foresight-USPs) sind für Crawler unangekündigt — verschenktes SEO für den Lead-Generator.
- **Empfohlene Lösung:** Statische Einträge für /, alle foresight-Unterseiten, /pricing, /methodology ergänzen; Artikel-Limit erhöhen oder paginierte Sitemaps generieren.
- **Akzeptanzkriterium:** GET /sitemap.xml enthält Landing, Pricing, Methodology und alle Foresight-Routen.
- **Aufwand:** S · **Dateien:** frontend/src/app/sitemap.ts

### CONF-05 — Die Landing-Page nennt interne DB-Schema- und Pipeline-Begriffe als Marketing-Microcopy.

- **Screen/Workflow:** / Landing (frontend/src/app/page.tsx)
- **Persona:** Besucher
- **Tier:** Public
- **Beobachtung:** page.tsx:184 rendert oeffentlich 'Evidence · source_url NOT NULL + grounding gate' — belegt im gerenderten HTML von `/`. Das exponiert den DB-Spaltennamen `source_url` samt `NOT NULL`-Constraint und den internen Modulnamen 'grounding gate'.
- **Ursache:** Evidenz-Annotationen aus der Truth-Matrix wurden woertlich (inkl. Schema-/Modulbezeichnern) in die UI uebernommen statt in Nutzersprache uebersetzt.
- **Auswirkung:** Geringe, aber unnoetige Preisgabe interner Implementierungsdetails; wirkt zudem fuer Nicht-Techniker kryptisch.
- **Empfohlene Lösung:** Die Evidenz-Zeile in Klartext-Nutzen umformulieren, z.B. 'Jeder Trend verlinkt seine Primaerquelle; erfundene Zahlen werden vor Veroeffentlichung zurueckgehalten' — ohne Spaltennamen/Constraints/Modulnamen.
- **Akzeptanzkriterium:** Der gerenderte `/`-HTML enthaelt keine Strings 'source_url', 'NOT NULL' oder 'grounding gate' mehr; die Aussage (Traceability + Anti-Fabrication) bleibt erhalten.
- **Aufwand:** S · **Dateien:** frontend/src/app/page.tsx

### COPY-24 — Der ansonsten vorbildliche Empty State ist mit "—— 404 · No signals" beschriftet, obwohl es kein 404 ist.

- **Screen/Workflow:** /trends (Empty State)
- **Persona:** Nutzer mit zu engen Filtern
- **Tier:** free
- **Beobachtung:** TrendsEmpty.tsx:29: Eyebrow "—— 404 · No signals" auf der normalen /trends-Seite bei leerem Filterergebnis. Der Rest ist stark: aktive Filter-Chips werden gezeigt, CTA "Clear all filters →" vorhanden.
- **Ursache:** HTTP-Code als Deko-Element verwendet.
- **Auswirkung:** Technisch versierte Nutzer deuten 404 als Fehler/kaputten Link statt als leeres Filterergebnis.
- **Empfohlene Lösung:** Eyebrow ändern in "—— 0 results" oder "—— No signals".
- **Akzeptanzkriterium:** Kein Empty State verwendet HTTP-Statuscodes als Beschriftung.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/TrendsEmpty.tsx

### COPY-25 — Kleinere Transparenzlücken am Kaufabschluss: "Talk to us" öffnet unangekündigt den Mail-Client, und nirgends steht, ob monatlich kündbar ist.

- **Screen/Workflow:** /trends/pricing (Hypercare-CTA) + Kauf-Transparenz
- **Persona:** Entscheider kurz vor Vertragsabschluss
- **Tier:** superpro
- **Beobachtung:** pricing/page.tsx:113-118: Hypercare-CTA "Talk to us" ist ein mailto:-Link ohne Kennzeichnung; auf der gesamten Pricing-Seite fehlen Angaben zu Kündigung/Laufzeit/Zahlungsrhythmus (nur "/mo") — keine Dark Patterns, aber auch keine beruhigende Transparenz, die den 499/799-EUR-Schritt absichert.
- **Ursache:** Pricing-Seite auf Featurematrix reduziert; Vertragsdetails nie ergänzt.
- **Auswirkung:** B2B-Käufer, die Kündigungsbedingungen nicht finden, vertagen den Kauf oder eskalieren an den Einkauf.
- **Empfohlene Lösung:** Unter dem Grid eine Zeile "Monthly billing via Stripe · cancel anytime · prices excl. VAT" (Inhalt mit Owner klären); "Talk to us" → "Email us about Hypercare".
- **Akzeptanzkriterium:** Pricing nennt Abrechnungsrhythmus und Kündbarkeit; der Hypercare-CTA kündigt die Mail-Aktion im Label an.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/pricing/page.tsx

### COPY-26 — Zwei identische Signup-Formulare auf einer Seite mit unterschiedlichen Begleittexten und ein SSR-sichtbarer "Loading…"-Block.

- **Screen/Workflow:** /trends/newsletter (Seitenstruktur)
- **Persona:** Newsletter-Interessent
- **Tier:** free
- **Beobachtung:** SignupForm wird oben (Z.274, "Free · one email per week · no spam") und unten (Z.472, "No spam. One email per week with the most important trend signals.") gerendert; dazwischen zeigt das Server-HTML dauerhaft "Loading…" (Z.283, live im curl-HTML sichtbar), weil Edition/Archiv rein clientseitig geladen werden.
- **Ursache:** Above-the-fold-Capture (bewusst) plus Bottom-Capture ohne Textabgleich; Client-only-Fetching.
- **Auswirkung:** Gering — aber der doppelte, leicht abweichende "No spam"-Text wirkt unaufgeräumt und das "Loading…" im initialen HTML kostet wahrgenommene Qualität (und SEO-Inhalt).
- **Empfohlene Lösung:** Begleittexte vereinheitlichen; die aktuelle Edition serverseitig rendern oder den Ladeblock durch einen inhaltlichen Platzhalter ("This week's briefing…") ersetzen.
- **Akzeptanzkriterium:** Beide Signup-Blöcke haben identische Trust-Zeilen; das initiale HTML von /trends/newsletter enthält kein nacktes "Loading…".
- **Aufwand:** M · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/trends/newsletter/page.tsx

### DS-11 — Einzelne Editorial-Kontexte enthalten Fremdformen: MovingNow-Karten sind rounded-lg mit runden Farb-Dots mitten im scharfkantigen Grid, quality-preview markiert mit roher Tailwind-Palette (red-500/red-300) statt Tokens.

- **Screen/Workflow:** MovingNow (auf /trends), quality-preview
- **Beobachtung:** MovingNow.tsx:45 `rounded-lg border border-border`, Z.50 `rounded-full`-Dot — direkt oberhalb des scharfkantigen TrendCard-Grids auf /trends. quality-preview/page.tsx:60 `bg-red-500/25 text-red-300 rounded-sm` statt --color-warn-Ableitung. Zusätzlich liegt das Grain-Overlay (globals.css:56, z-index:100) über dem MobileNav-Drawer (z-50) und dem TrendScore-Tooltip (z-50) — bei 3% Opacity funktional unkritisch, aber Layering-Ordnung ist undefiniert.
- **Ursache:** MovingNow wurde als Epic-W-Strip gebaut (gleiche Familie wie die Off-System-Seiten); quality-preview ist ein internes Werkzeug.
- **Auswirkung:** Kleine, aber sichtbare Stilbrüche auf der Startseite des Trends-Bereichs; rote Roh-Palette umgeht das Token-System.
- **Empfohlene Lösung:** MovingNow auf scharfe Ecken + 3px-Vertical-Stripe (TrendCard-Muster) umstellen; Markierungsfarbe aus --color-warn ableiten; Z-Index-Skala dokumentieren (Grain < Overlays).
- **Akzeptanzkriterium:** MovingNow enthält kein rounded-*; quality-preview-Marks nutzen Token-basierte Farben.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/MovingNow.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/trends/quality-preview/page.tsx, /home/dirk/projects/catandary-trends/frontend/src/app/globals.css

### DS-12 — Die acht --color-v-*-Vertical-Tokens im @theme werden nirgends verwendet — die Vertical-Farben leben als duplizierte Hex-Werte in types.ts und in dutzenden style-Props.

- **Screen/Workflow:** globals.css / types.ts (Token-Architektur)
- **Beobachtung:** globals.css:18-25 definiert --color-v-food bis --color-v-lifestyle; `grep -rn "v-food|v-tech|..."` über src/*.tsx liefert 0 Treffer. types.ts:62-69 hält dieselben Hex-Werte separat; Komponenten (TrendCard.tsx:43, TrendsHero.tsx:145 u.v.m.) inlinen sie via style. Insgesamt ~80 Hardcoded-Hex-Vorkommen in .tsx (Top: #d4ff3a 26x, #8a8d82 14x).
- **Ursache:** TS-Objekt und CSS-Theme wurden parallel angelegt, nie zusammengeführt.
- **Auswirkung:** Zwei Quellen der Wahrheit — eine Palettenänderung muss an zwei Orten passieren und kann still divergieren; tote Tokens täuschen ein Systemlevel vor, das nicht existiert.
- **Empfohlene Lösung:** types.ts-Farben auf `var(--color-v-*)` umstellen (CSS-Variablen funktionieren in style-Props und SVG-fills) oder die ungenutzten Tokens entfernen und types.ts explizit als Single Source of Truth dokumentieren.
- **Akzeptanzkriterium:** Vertical-Hex-Werte existieren genau einmal im Repo (Token ODER types.ts); kein toter --color-v-*-Block.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/lib/types.ts

### DS-13 — Diagramm-Beschriftungen nutzen generische Systemfonts (ui-sans-serif/ui-monospace) statt der geladenen IBM-Plex-Tokens — Charts fallen typografisch aus dem Produkt.

- **Screen/Workflow:** TierCurveChart, TrendRadar, HeroInstrument, TechReader (Chart-Typografie)
- **Beobachtung:** TierCurveChart.tsx:147/170/202 `font: "...ui-sans-serif, system-ui"` bzw. ui-monospace; HeroInstrument.tsx:76/156 und TechReader.tsx:88 `9px ui-monospace` im Canvas; TrendRadar-Labels (radar-ring-label etc.) definieren gar keine font-family und erben Sans. Der Rest des Produkts setzt Datenlabels konsequent in IBM Plex Mono.
- **Ursache:** SVG/Canvas-Code greift nicht auf die CSS-Variablen zu (bei Canvas muss der berechnete Font-String übergeben werden).
- **Auswirkung:** Gerade die beweisführenden Visualisierungen (USP) wirken leicht fremd; Mono-Tabellenziffern-Anmutung geht verloren.
- **Empfohlene Lösung:** In SVGs `style={{ font: "10px var(--font-mono)" }}` bzw. Tailwind-Klassen auf text-Elemente anwenden; im Canvas den Font einmalig aus getComputedStyle(document.body).getPropertyValue('--font-plex-mono') zusammensetzen.
- **Akzeptanzkriterium:** Achsen-/Ring-/Verdikt-Labels aller vier Visualisierungen rendern in IBM Plex Mono/Sans (visuelle Stichprobe).
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TierCurveChart.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/foresight/TrendRadar.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/landing/HeroInstrument.tsx, /home/dirk/projects/catandary-trends/frontend/src/components/landing/TechReader.tsx

### DS-14 — Die Design-Doku dokumentiert die getroffene Entscheidung nicht: empfohlen ist Option A mit Fraunces/JetBrains Mono/Source Sans 3, implementiert ist Option-A-Farbwelt mit Option-B-Typografie (IBM Plex Trio).

- **Screen/Workflow:** frontend/DESIGN_REVAMP.md
- **Beobachtung:** DESIGN_REVAMP.md:23-26 nennt Fraunces + JetBrains Mono + Source Sans 3 für Option A und empfiehlt A (Z.236); globals.css:27-30 und layout.tsx:2 laden stattdessen IBM Plex Serif/Mono/Sans (die Option-B-Fonts, Z.71-74 der Doku). Der finale Hybrid (A-Farben + B-Typo) steht nirgends; die Doku endet vor der Entscheidung.
- **Ursache:** Nach dem Revamp wurde das Planungsdokument nicht um den Umsetzungsstand ergänzt.
- **Auswirkung:** Verstößt gegen die konstitutionelle Repo-Regel "Doku spiegelt Realität"; künftige Design-Arbeit (Deliverable 9) könnte auf die falschen Fonts aufsetzen.
- **Empfohlene Lösung:** DESIGN_REVAMP.md um einen kurzen "Implemented (Stand 2026-07)"-Abschnitt ergänzen: Option-A-Farb-/Formensprache + IBM-Plex-Typografie, inkl. Verweis auf globals.css als Token-Quelle; alternativ die IST-Spezifikation aus diesem Audit dort einpflegen.
- **Akzeptanzkriterium:** DESIGN_REVAMP.md nennt den implementierten Hybrid explizit; Fonts in Doku und layout.tsx stimmen überein.
- **Aufwand:** S · **Dateien:** /home/dirk/projects/catandary-trends/frontend/DESIGN_REVAMP.md, /home/dirk/projects/catandary-trends/frontend/src/app/globals.css, /home/dirk/projects/catandary-trends/frontend/src/app/layout.tsx

### KEY-16 — Die UI deckt die Filter-Wertebereiche nur teilweise ab: 12 von 21 Mega-Trends, 20 von 137 Quellen; URL-Params sind zudem case-sensitiv ohne Feedback.

- **Screen/Workflow:** /trends (Mega-Trend-Chips, Source-Exclude)
- **Persona:** Key User / Power User
- **Beobachtung:** page.tsx:50 slice(0,12) für megaOptions (RSC-Payload live: 12 Keys, Taxonomie lt. Doku 21); page.tsx:58 getTopSourcesByCount(20). Die restlichen Werte sind nur per Hand-URL erreichbar, deren Key-Format (z. B. 'artificial_intelligence_and_automation') man erraten muss. ?v=food (lowercase) wird von der Whitelist still verworfen — live: 60.482 statt 4.211 Treffer, keine Meldung.
- **Ursache:** Bewusste Top-N-Kürzung für die UI, ohne 'alle anzeigen'-Weg; Whitelist-Parsing ohne Normalisierung.
- **Auswirkung:** Power-User, die gezielt einen Nischen-Mega-Trend verfolgen oder eine kleine Quelle ausblenden wollen, stoßen an eine unsichtbare Grenze; hand-editierte URLs scheitern lautlos an Groß-/Kleinschreibung.
- **Empfohlene Lösung:** Vertical/PESTEL-Params beim Parsen uppercasen; Mega-Chips um 'alle anzeigen' erweitern (die 21 Werte sind statisch generiert in mega-trends.generated.ts); Source-Exclude-Dropdown mit Suchfeld über alle Quellen.
- **Akzeptanzkriterium:** ?v=food filtert wie ?v=FOOD; jeder existierende Mega-Trend und jede aktive Quelle ist über die UI als Filter erreichbar.
- **Aufwand:** S · **Dateien:** frontend/src/lib/filter-params.ts, frontend/src/app/trends/page.tsx, frontend/src/components/filters/MegaTrendChips.tsx, frontend/src/components/filters/SourceExcludeToggle.tsx

### KEY-17 — Die Technology-Seite liefert 1,88 MB HTML pro Abruf — die kompletten Kurvendaten aller kuratierten Technologien doppelt (SSR + RSC-Payload), ohne Caching.

- **Screen/Workflow:** /trends/foresight/technology
- **Persona:** Key User / Power User (täglicher Abruf)
- **Beobachtung:** curl live: 1.884.559 Bytes, davon ~1,1 MB RSC-Payload in 234 Script-Chunks; force-dynamic (technology/page.tsx:7) verhindert jedes Caching, obwohl die zugrundeliegenden CPC-Insights per Batch-Skript erzeugt werden und sich zwischen Läufen nicht ändern. Zum Vergleich: /trends = 108 KB.
- **Ursache:** Alle TechnologyCard-Zeitreihen werden vollständig server-gerendert und im Next-RSC-Format nochmals eingebettet.
- **Auswirkung:** Für einen Nutzer, der die Seite täglich über die Nav öffnet, ist das der mit Abstand schwerste Request der Site — auf Mobilnetzen mehrere Sekunden nur Transfer.
- **Empfohlene Lösung:** Seite auf revalidate (z. B. 1 h) statt force-dynamic stellen und die Kurvendaten pro Karte ausdünnen (Sparkline braucht keine volle Auflösung) oder Karten unterhalb des Folds nachladen.
- **Akzeptanzkriterium:** Der HTML-Transfer von /trends/foresight/technology liegt unter 500 KB oder die Seite wird cachebar (Cache-Control/ETag greift bei Folgeabrufen).
- **Aufwand:** M · **Dateien:** frontend/src/app/trends/foresight/technology/page.tsx, frontend/src/components/foresight/TechnologyCard.tsx

### ONB-18 — Kleinere Polier-Luecken auf Newsletter- und Radar-Seite: generischer Titel, SSR-"Loading…", fehlender Datenschutzhinweis am Formular, 9 Tage alter "now"-Stand.

- **Screen/Workflow:** /trends/newsletter + /trends/foresight/radar
- **Persona:** Occasional User
- **Tier:** free
- **Beobachtung:** (a) /trends/newsletter hat den generischen <title> "Catandary Trends — Cross-Industry Trend Intelligence" statt eines Newsletter-Titels und rendert das Briefing-Archiv rein clientseitig — SSR/No-JS zeigt dauerhaft "Loading…" (page.tsx laedt per useEffect /api/newsletter). (b) Am Signup-Formular fehlt jeder Datenschutz-/Abmelde-Hinweis (nur "no spam"). (c) Radar/Clusters sagen "What's moving now", tragen aber "As of Jul 14, 2026" — beim Besuch am 23.07. neun Tage alt.
- **Ursache:** newsletter/page.tsx ist eine reine Client-Komponente ohne metadata-Export; Radar-Daten stammen aus dem letzten Cluster-Lauf.
- **Auswirkung:** Einzeln klein, in Summe wirkt der wichtigste Lead-Kanal unfertig; das alte "now"-Datum laesst Occasional User an der Aktualitaet der ganzen Plattform zweifeln.
- **Empfohlene Lösung:** Newsletter-metadata setzen, letzte Edition serverseitig vorrendern, einen Satz "Abmeldung jederzeit; Datenschutz: …" unter das Formular; Cluster-Lauf-Frequenz erhoehen oder Formulierung auf "updated weekly" abschwaechen.
- **Akzeptanzkriterium:** curl auf /trends/newsletter zeigt einen Newsletter-spezifischen <title> und die letzte Edition ohne JS; unter dem Formular steht ein Datenschutz-/Abmeldehinweis; das Radar-Datum ist < 7 Tage alt oder die Ueberschrift behauptet kein "now" mehr.
- **Aufwand:** S · **Dateien:** frontend/src/app/trends/newsletter/page.tsx, frontend/src/app/trends/foresight/radar/page.tsx
