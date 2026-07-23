# UX-Audit — Umsetzung & Validierung (Branch `UI_UX_Audit`, 2026-07-23)

Bezieht sich auf `AUDIT_2026-07.md` (Befunde) und `ISSUE_REGISTER_2026-07.md` (121 Findings).
Alle Änderungen liegen auf dem Branch `UI_UX_Audit` (Basis `dev`). Verifikation: `tsc` sauber,
ESLint 0 Fehler, **86/86 Vitest-Tests grün** (davon 3 neue Suiten), `next build` erfolgreich,
Live-Smoke-Test gegen einen Produktions-Build auf Port 3011.

---

## 1. Umgesetzt (nach Themenblock, mit Finding-IDs)

### Performance des Erstkontakts — S1
- **ONB-01 / ARCH-02:** `getMethodologyStats` + alle Aggregat-Queries (`getVerticalCounts`,
  `getMegaTrends`, `getTopSourcesByCount`, `getTrendsCount`) laufen über einen In-Process-TTL-Cache
  in `lib/db.ts` (10 min–1 h). **Messung: `/` warm 0,009 s und `/trends/methodology` warm 0,011 s
  (vorher 7–9 s bei jedem Aufruf).** Erster Request nach Prozessstart füllt den Cache (~10 s einmalig).
- **ARCH-11 / KEY-10:** `/trends` bündelt seine 7 DB-Queries in ein `Promise.all`; eine Seitenzahl
  jenseits des Endes leitet auf die letzte reale Seite um statt eine irreführende Leermeldung zu zeigen.

### Monetarisierungs-Funnel — S1
- **ONB-02 / KEY-03 / ARCH-05 / COPY-12:** Header und MobileNav sind session-bewusst: „Sign in" bzw.
  „Account" (bei `AUTH_ENABLED=1`) und „Plans" sind jetzt überall erreichbar; Footer verlinkt Plans,
  Newsletter, Methodology, Imprint, Privacy.
- **COPY-09:** Pricing zeigt Anonymen „Sign up free" — „Your current plan" nur noch mit Session.
- **ONB-09 / ARCH-09 / COPY-13:** CheckoutButton zeigt Fehler sichtbar an („Checkout didn't start …"),
  Busy-Label „Opening checkout…"; der Sign-in-Umweg trägt `?next=/trends/pricing&reason=checkout`
  durch den kompletten Magic-Link-Flow (Request → Mail-Link → Callback, Whitelist-validiert via
  `isSafeInternalPath`) und die Sign-in-Seite erklärt den Kontext.
- **ARCH-04 / COPY-03:** `/account?checkout=success` zeigt ein Bestätigungs-Banner; solange der
  Stripe-Webhook noch nicht durch ist, aktualisiert die Seite sich selbst (begrenztes Polling via
  `router.refresh`, max. 10 Versuche).
- **KEY-02 / ARCH-06:** Nicht existierende Features aus der Preisliste entfernt („Saved searches &
  alerts") bzw. ehrlich markiert („API access — coming soon"); Regressionstest in `tiers.test.ts`.
- **ONB-06 / COPY-20:** Eine Monetarisierungs-Geschichte: Landing-CTAs sind dynamisch („Choose plan"
  wenn Checkout live, sonst „Request early access"), der stale „plans launch soon"-Block auf der
  Technology-Seite ist ersetzt, die FAQ-Kosten-Antwort folgt demselben Flag.
- **ARCH-13 / COPY-11 / COPY-19 / COPY-10:** Der wiederkehrende Foresight-CTA führt in Produkt
  bzw. Pricing statt auf die externe Domain; tote/irreführende Mega-Trend-CTAs repariert.
- **ONB-11 / COPY-07 / COPY-25:** Pricing-Copy in Nutzersprache (kein „lead magnet" mehr),
  Transparenzzeile „Monthly billing via Stripe · cancel anytime · prices excl. VAT",
  „Email us about Hypercare" statt unangekündigtem Mail-Client.

### Paywall-Konsistenz — S1
- **ONB-03 / KEY-01 / ARCH-01 / COPY-04 / CONF-02:** Die Feature-Matrix aus `tiers.ts` wird jetzt
  durchgesetzt — Seiten nach der Owner-Regel „gate at the value drill-down, not at the door":
  | Feature | Gate | Freier Teaser |
  |---|---|---|
  | Clusters | Starter | Top-3-Cluster + Zähler |
  | Radar | Starter | 8 am stärksten steigende Blips |
  | Technology (kuratiert) | Pro | Top-3-Karten |
  | Lead-Time | Pro | Schaufenster-Technologie mit voller Kurve (Deep-Link `?cpc=` wird für Free ignoriert) |
  | On-Demand-Analyzer | Super Pro+ | kuratierte Karten als Format-Referenz |
  | Evolution, Dossier | Pro | (bestand schon) + `benefit`-Texte |
  Alle 9 Foresight-API-Routen (`clusters`, `radar`, `technology`, `tir`, `trajectory`, `lineage`,
  `analyze`, `query`, `query/evidence`) prüfen `canAccess` und liefern sonst 402 mit Upgrade-Hinweis.
  **Bei `PAYWALL_ENABLED=0` (Soll-Zustand der Localhost-Instanz) ist alles unverändert offen.**
- **KEY-08 / ARCH-15 / COPY-06:** CSV-Export lädt per fetch und zeigt bei 402 eine lesbare
  Upgrade-Meldung statt Roh-JSON; ExportButton steht im Dossier innerhalb des Gates.

### API-Härtung / Vertraulichkeit — S1
- **CONF-01 / ARCH-03:** `/api/trends` ist auf `status='published'` gepinnt (lieferte vorher Drafts
  und rejected-Inhalte aus), validiert `vertical`/`limit`/`offset` (400 statt NaN) und antwortet bei
  DB-Fehlern mit sauberem 500-JSON.
- **CONF-04:** Public-Antworten ohne interne Felder (`confidence`, `auto_published`, `raw_entry_id`,
  `status`); `trend_score` bleibt (wird als CRS angezeigt).
- **CONF-03:** Technology-API projiziert per Allowlist — interne Build-/Methodenfelder
  (`tir_method`, `built_in_s`, `cycle_cov`, `tir_n`, `tir_earliest`) verlassen den Server nicht.
- **CONF-05:** Landing ohne DB-Schema-Jargon („source_url NOT NULL" → Klartext).

### Recht & Einwilligung — S1/S2
- **ONB-04 / ARCH-14:** `/imprint` + `/privacy` (EN, DSGVO-Struktur: Prozessoren Stripe/Resend/
  Hetzner, keine Tracking-Cookies, Betroffenenrechte), im Footer verlinkt. ⚠️ **Owner-Gate:** Der
  Adressblock im Impressum enthält markierte `[Owner: …]`-Felder — Name/Anschrift kann nur der
  Betreiber einsetzen; vor Public-Launch zwingend.
- **ONB-05 / COPY-05:** Newsletter-Checkbox im Sign-in ist **nicht mehr vorangekreuzt** (EuGH
  Planet49); Formulare tragen Privacy-Hinweis + „unsubscribe anytime".

### Design-System — S1/S2
- **DS-01 / DS-02:** Tokens `--color-ink` und `--color-text` existieren jetzt — die 43+ Nutzungen
  von `text-text` und alle `text-ink`-CTAs (Pagination, Empty-State, ForesightCta …) rendern korrekt.
- **DS-04:** Die komplette Geld-Strecke (Pricing, Sign-in, TierGate, CheckoutButton, Account) läuft
  auf den Editorial-Tokens — das zweite, generische Designsystem (rounded-2xl, Grün `#16a34a`,
  Inline-`<style>`) ist entfernt. Damit auch **A11Y-05** gelöst (Kontrast der Geld-CTAs).
- **DS-03:** Kanonische Lead-Time-Tier-Palette (Science `#22d3ee` / Patents `#a78bfa` / Funding
  `#fb923c` / Market `#bde63a`) — Landing (HeroInstrument, TechReader, Pillar-Icons) und
  Produkt-Chart sagen jetzt dasselbe; `--t-*`-Tokens dokumentiert.
- **DS-07:** CRS-Dreistufigkeit real (Mitte = `--color-accent-deep` statt Hex-Duplikat), identisch
  in TrendScore und TrendRow.
- **DS-08 (teilweise):** Semantik-Tokens `--color-rising`/`--color-declining` definiert.
- **DS-05 (teilweise):** Radar- und Dossier-Header/Filter auf das Editorial-Muster (Eyebrow,
  font-display, eckige Mono-Chips) umgestellt.
- **DS-11:** MovingNow + quality-preview auf scharfe Kanten/Tokens.
- **DS-13 (teilweise):** SVG-Texte im Radar auf `--font-mono`.

### Accessibility — S2/S3 (WCAG 2.2 AA)
- **DS-09 / A11Y-07:** Globales `:focus-visible`-System (2px Akzent) via `:where()`;
  `outline:none`-Stellen (Slider, Selects, Radar, Cockpit, Inputs) ersatzlos entfernt.
- **A11Y-08:** Skip-Link + `<main id="main">`-Landmark.
- **A11Y-01/02:** Alle Konversions-Formulare (Sign-in, Newsletter, Analyzer, Cockpit-Suche) haben
  programmatische Labels + `autocomplete="email"`; Status-/Fehlermeldungen mit `role="status"`/
  `role="alert"`.
- **A11Y-03/18:** Radar-Blips sind `role="button"` mit sprechenden Labels, sichtbarem Fokus-Stroke,
  `aria-live`-Readout und vergrößerten Tap-Zielen (r≥14).
- **A11Y-04:** MobileNav ist ein echter Dialog (Fokus-Falle, Fokus-Rückgabe, Escape).
- **A11Y-06:** `text-muted/60`-Kontrastverstöße in Cards/Filtern angehoben.
- **A11Y-09 / KEY-09 (teilweise):** Pagination als echte Links in `<nav aria-label>` mit
  `aria-current`; öffnen-in-neuem-Tab funktioniert.
- **A11Y-11/15:** Überschriften-Hierarchie (sr-only-h2 auf /trends, h2 im Artikel), valides `<dl>`,
  Breadcrumb-Label.
- **A11Y-12:** CRS-Erklärung per Tastatur/Touch erreichbar (fokussierbares Badge +
  `aria-describedby`, ohne invalides Button-in-Link).
- **A11Y-14/16/19:** SourceExclude-Dropdown (Escape + `aria-pressed` statt Fake-listbox),
  ActiveChips-Gruppensemantik + Remove-Labels, Cockpit-`autoFocus` entfernt.

### Sprache & Microcopy — S1/S2/S3
- **COPY-01/02, ONB-08, KEY-13, A11Y-13, COPY-14, ARCH-17:** Produkt durchgehend Englisch —
  TechnologyTool komplett übersetzt (inkl. SVG-Labels, en-US-Zahlen), Newsletter-API-Antworten,
  Meta-Descriptions (Foresight, Cross-Vertical), Analyze-Timeout. Gerenderte Kernrouten enthalten
  **0 deutsche UI-Strings** (verifiziert per Sweep).
- **KEY-05 (teilweise):** Ehrliche Latenzangabe im Analyzer („up to ~2 minutes") + Zwischenstatus.
- **KEY-14:** Cockpit-Fehler nach Status (429 mit retry-after, 402 mit Plans-Link, 5xx freundlich);
  Suche erst ab 3 Zeichen.
- **COPY-16/17/18/23/24:** Cluster-Summaries dedupliziert („Gaining ground (+X pp) — confirmed by
  N independent sources."), Score heißt überall CRS („Min CRS", „Highest CRS"), „Search" statt
  „? Query", „text match only", „Peak year (share of voice)", Empty-State „0 results" statt „404".
- **COPY-21:** TierGate mit `benefit`-Prop je Einsatzort + „You're on {Tier}"-Zeile.
- **ONB-13 / KEY-07:** Evolution zeigt statt leerem Global-Scope automatisch den besten vorhandenen
  Scope („Currently available for Health & Wellness …") und erklärt den leeren Zustand.

### Navigation & IA — S2/S3
- **ONB-12 / ARCH-08 / ARCH-18 / COPY-22:** Header von 11 flachen Items auf 5 + gruppiertes
  Foresight-Dropdown; `next/link` mit `aria-current`-Aktivzuständen (kein Full-Reload mehr);
  MobileNav gruppiert (Explore / Foresight / Account); externer Firmenlink nur noch im Footer mit ↗.
- **ARCH-07 / ONB-07 / ARCH-16:** `error.tsx`, `global-error.tsx`, `not-found.tsx` (gebrandet, mit
  Auswegen) und `loading.tsx`-Skeleton für /trends.
- **KEY-11:** Debounce-Zwischenstände via `router.replace` — die Zurück-Taste iteriert nicht mehr
  durch Tippfragmente.
- **KEY-12 / KEY-16:** Redundante Sortieroption „Source date" entfernt; `?v=food`/`?pestel=en`
  werden case-insensitiv akzeptiert.
- **ARCH-22:** Sitemap mit Landing, allen Foresight-Seiten, Pricing, Methodology, Rechtsseiten;
  Artikel-Limit 500 → 5000.
- **ARCH-19:** Magic-Link-Basis-URL fällt auf den Request-Origin zurück (statt totem :3004).

### Tests & Doku
- **ARCH-20:** Neue Suiten `tiers.test.ts` (tierAllows-Matrix, Ehrlichkeits-Regression),
  `filter-params.test.ts` (Parse-Roundtrip, Invalid-Fallbacks), `auth-path.test.ts`
  (Open-Redirect-Guard). Gesamt: 86 Tests grün.
- **ARCH-21 / DS-14:** CLAUDE.md-Frontend-Abschnitt auf Ist-Stand (Next 16, echte Routen, Gating,
  systemd/3001, kein `/trends/search`, kein DE/EN-Switcher); DESIGN_REVAMP.md um
  „Implemented"-Abschnitt ergänzt.

---

## 2. Bewusst NICHT umgesetzt (Empfehlungen / Owner-Gates)

| ID | Thema | Grund / nächster Schritt |
|---|---|---|
| ONB-04 (Rest) | Impressum-Adressblock | **Owner-Gate:** Name/Anschrift einsetzen (`src/app/imprint/page.tsx`, `OPERATOR`) |
| ARCH-10 | Stripe Billing-Portal (Kündigung self-service) | Übergangslösung: „email us"-Zeile auf /account; Portal-Route als Folge-Issue empfohlen |
| ONB-16 | Feed-Monotonie (Seite 1 = eine Quelle) | Sortier-/Interleaving-Änderung in `lib/db.ts` — Produktentscheidung, als Issue empfohlen |
| ONB-17 | Sponsored-Quellen kennzeichnen | Pipeline-Änderung (`feed_poller`), nicht Frontend — als Issue empfohlen |
| ARCH-12 | Evolution-Snapshots für global/alle Scopes | Pipeline-/Cron-Job (Owner); UI degradiert jetzt sauber |
| KEY-04 | URL-State für Cockpit/Analyzer | M-Aufwand, Folge-PR sinnvoll (Muster aus filter-params wiederverwendbar) |
| KEY-06 (Rest) | Cluster-Drilldown in Mitglieds-Signale | Anker-IDs existieren jetzt; echte Detailansicht = Folge-Feature |
| KEY-15 | „Neu seit letztem Besuch" | Neues Feature, nicht Polishing |
| KEY-17 / ONB-14 | Technology-Seite 1,88 MB SSR-Payload | Datenausdünnung der Kurven = eigener sorgfältiger PR |
| ONB-15 | CPC-/Grant-Rohtitel normalisieren | Mapping-Tabelle + Pipeline-Anteil, als Issue empfohlen |
| DS-06 | PESTEL- vs. Vertical-Palette entzerren | Farbentscheidung mit Owner (CLAUDE.md definiert PESTEL-Farben) |
| DS-10 (Rest) | `font-bold` ohne 700er-Schnitt außerhalb der Geld-Strecke | in umgebauten Screens behoben; Rest beim nächsten Screen-Refactor |
| A11Y-10 | 3:1-Kontrast ALLER Control-Borders | `--color-border-strong` eingeführt + in neuen/umgebauten Controls genutzt; flächendeckende Umstellung = Folge-PR |
| A11Y-17 | 8–10px-Mono-Labels global anheben | Nav/CTAs auf 11px angehoben; Rest ist Design-Abwägung |

**Betriebs-Hinweis (kein Code):** `.env.local` steht noch im „TEMP TEST MODE"
(`AUTH_ENABLED=1`/`PAYWALL_ENABLED=1` + aktive Keys) — laut deinem eigenen Kommentar sollte der
Block nach dem Kauf-Test entfernt und beide Gates auf 0 gesetzt werden. Mit Gates auf 0 verhält
sich die Instanz wieder wie die gewohnte Voll-Demo (alle Gates dieser Umsetzung sind No-Ops).

---

## 3. Validierungsbericht (Vorher → Nachher)

| Kriterium | Vorher | Nachher (Prod-Build, Port-3011-Smoke-Test) |
|---|---|---|
| TTFB `/` | 7,4–8,6 s **pro Request** | 0,009 s warm (einmalig ~10 s Cache-Fill nach Prozessstart) |
| TTFB `/trends/methodology` | 7,3 s pro Request | 0,011 s warm |
| Login auffindbar | nirgends verlinkt | Header/MobileNav „Sign in"/„Account", Pricing „Sign up free" |
| Pricing anonym | „Your current plan" (falsch) | „Sign up free" + Transparenzzeile |
| Bezahlte Features bei aktiver Paywall | Radar/Clusters/Technology/Lead-Time + 8 APIs komplett offen | Seiten: Teaser + Gate; APIs: 402 (alle 8 verifiziert) |
| `/api/trends?status=draft` | lieferte Drafts + interne Felder | published-gepinnt, 400 bei invaliden Params, interne Felder entfernt |
| 404 | leerer Body | gebrandete Seite mit 3 Auswegen |
| Deutsche Strings in Kernrouten | Technology-Tool, Newsletter-API, Metas | 0 Treffer im Sweep über 7 Routen |
| Newsletter-Einwilligung | vorangekreuzt | aktives Opt-in + Privacy-Hinweis |
| Rechtstexte | keine (alle 404) | /imprint + /privacy, im Footer verlinkt (Adress-Owner-Gate offen) |
| Fokus-Indikatoren | keinerlei `:focus-visible`, mehrfach `outline:none` | globales Fokus-System, outline:none entfernt |
| Checkout-Fehler | stumm verschluckt | sichtbare Meldung + Kontext-erhaltender Sign-in-Umweg |
| Tests | 3 lib-Suiten | 6 Suiten / 86 Tests, inkl. Ehrlichkeits-Regression |
| Lint/Build | — | ESLint 0 Fehler, `next build` grün |

Getestete Personas/Tiers im Smoke-Test: anonym/Free (Gates, Teaser, Sign-up-Pfad), Checkout-Umweg
(Sign-in-Kontext), API-Konsument (402/400-Verhalten). Eingeloggte Tier-Durchstiche (starter/pro/
superpro) folgen dem `tierAllows`-Pfad, der durch die neue Testmatrix abgedeckt ist.
