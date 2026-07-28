# Newsletter / Double-Opt-in — Textbausteine (ENTWURF)

> ⚠️ **DRAFT — KEINE RECHTSBERATUNG.** Fachliche Einordnung mit Fundstellen. Vor Go-live von
> einem auf IT-/Wettbewerbsrecht spezialisierten Anwalt prüfen lassen. Stand: 2026-07-26.
>
> **Keine offenen Platzhalter mehr.** Das unterzeichnete DPA-PDF wurde am 2026-07-26 geprüft
> (Docusign-Envelope `CC958417-9D1F-42CD-8B94-53B5F496F14E`, Stand 31.12.2025, gegengezeichnet
> 14.01.2026 von Zeno Rocha Bueno Netto, CEO). Ergebnis: **Gründungsstaat und Registernummer
> sind auch dort nicht angegeben** — sie sind in keinem verfügbaren Dokument enthalten und nach
> Art. 13 DSGVO auch nicht erforderlich (Name + Anschrift genügen). Der Text ist damit
> vollständig; *Delaware o. Ä. nicht ergänzen, das wäre geraten.*
>
> **Bestätigt aus dem DPA-PDF:** Anschrift „2261 Market Street #5039 San Francisco, CA 94114"
> (Exhibit B, Data Importer), Kontakt `privacy@resend.com`, Rolle Processor, SCC nach
> Commission Decision 2021/914. Die Kundenseite des Signaturblocks ist leer — das ist
> unschädlich: nach Ziff. 12 dienen die Signaturblöcke „for reference purposes only", der
> Vertrag wird mit Annahme der Terms of Service wirksam.
>
> **Bereits verifiziert** (Primärquellen, 2026-07-26): Firmierung **Plus Five Five, Inc.**
> (nicht „Resend, Inc." — diese Gesellschaft existiert nicht), Anschrift 2261 Market Street
> #5039, San Francisco, CA 94114; DPA gilt automatisch mit Vertragsschluss
> (resend.com/legal/dpa, Ziff. 12); SCC 2021/914 **Modul 2** per Verweis einbezogen;
> DPF-Teilnehmer-ID **8907**, Status „Active – Re-certification under Review", gültig bis
> 03.03.2027, nur EU + UK, nur Non-HR-Daten; **Speicherung ausschließlich in den USA**, auch bei
> Versandregion `eu-west-1`; Retention 30 Tage (Logs) / 90 Tage (nach Kündigung) / 3 Jahre
> (Compliance-Nachweise); 22 Unterauftragsverarbeiter, alle USA.

Die Texte müssen an **drei** Stellen konsistent gehalten werden, sonst driften sie auseinander:

1. Landing-Modal (`Website-landing-hub/index.html`, `#legal-datenschutz`) — hat heute **keinen** Newsletter-Abschnitt
2. `frontend/src/app/privacy/page.tsx` — beschreibt heute Single-Opt-in, keine Speicherdauer
3. `docs/legal/datenschutz.draft.md` — **behauptet bereits Double-Opt-in, was derzeit unwahr ist**

---

## 1. Datenschutzerklärung — neuer Abschnitt

Einzufügen als Abschnitt 7 (Stil: nummerierte Überschrift, Du-Ansprache, wie die bestehenden 1–6).

```html
<h3>7. Newsletter und Launch-Benachrichtigung</h3>

<p><strong>Verarbeitete Daten:</strong> Deine E-Mail-Adresse sowie – ausschließlich zum Nachweis
deiner Einwilligung – der Zeitpunkt der Anmeldung, der Zeitpunkt deiner Bestätigung, die dabei
verwendeten IP-Adressen, die Browser-Kennung (User-Agent) und der Wortlaut der
Einwilligungserklärung in der zum Zeitpunkt deiner Anmeldung gültigen Fassung.</p>

<p><strong>Double-Opt-in:</strong> Nach deiner Anmeldung senden wir dir eine E-Mail mit einem
Bestätigungslink. Erst wenn du dort bestätigst, nehmen wir dich in den Verteiler auf. Diese
Bestätigungsmail enthält keine Werbung. Der Link ist 48 Stunden gültig; bestätigst du nicht,
löschen wir die Anmeldedaten spätestens nach 30 Tagen vollständig.</p>

<p><strong>Zweck:</strong> Benachrichtigung über den Start von Catandary; Versand des
wöchentlichen Catandary-Newsletters; Ermittlung des Interesses an unserem Angebot anhand der
Anzahl der Anmeldungen; Nachweis und Dokumentation deiner Einwilligung; Schutz vor
missbräuchlichen Fremdanmeldungen.</p>

<p><strong>Rechtsgrundlage:</strong> Für den Versand deine Einwilligung nach Art. 6 Abs. 1 lit. a
DSGVO. Für die Protokollierung und die fortgesetzte Aufbewahrung des Einwilligungsnachweises
Art. 6 Abs. 1 lit. c DSGVO i. V. m. Art. 5 Abs. 2 und Art. 7 Abs. 1 DSGVO sowie unser
berechtigtes Interesse an der Abwehr unberechtigter Ansprüche nach Art. 6 Abs. 1 lit. f DSGVO.
Wettbewerbsrechtlich beruht der Versand auf § 7 Abs. 2 Nr. 2 UWG.</p>

<p><strong>Versanddienstleister:</strong> Für den technischen Versand nutzen wir den Dienst
<strong>Resend</strong> der <strong>Plus Five Five, Inc.</strong>, 2261 Market Street #5039,
San Francisco, CA 94114, USA. Mit Plus Five Five, Inc. besteht ein
Auftragsverarbeitungsvertrag nach Art. 28 DSGVO, der mit der Nutzung der Dienste wirksam wird.
Der Dienstleister verarbeitet deine Daten ausschließlich weisungsgebunden für den Versand und
nicht für eigene Zwecke. Er setzt seinerseits Unterauftragsverarbeiter ein; die jeweils
aktuelle Liste ist unter https://resend.com/legal/subprocessors abrufbar.</p>

<p><strong>Übermittlung in die USA:</strong> Deine Daten werden in den Vereinigten Staaten
verarbeitet und gespeichert. Das gilt auch dann, wenn E-Mails über einen europäischen
Versandstandort ausgeliefert werden: Die Wahl der Versandregion steuert nur den Versandweg,
nicht den Speicherort – Kontodaten, E-Mail-Metadaten, Protokolle und API-Aufzeichnungen liegen
ausschließlich in den USA. Die Übermittlung stützt sich auf zwei Grundlagen: zum einen auf den
Angemessenheitsbeschluss (EU) 2023/1795 (EU-US Data Privacy Framework), unter dem
Plus Five Five, Inc. zertifiziert ist (Teilnehmer-ID 8907, Zertifizierung für den EU-US-DPF
sowie die UK-Erweiterung); zum anderen auf die EU-Standardvertragsklauseln nach dem
Durchführungsbeschluss (EU) 2021/914, Modul 2 (Verantwortlicher an Auftragsverarbeiter), die
Bestandteil des Auftragsverarbeitungsvertrags sind. Eine Kopie der Garantien erhältst du auf
Anfrage unter contact@catandary.de. Trotz dieser Garantien lässt sich ein Zugriff
US-amerikanischer Behörden nicht in jedem Fall ausschließen.</p>

<p><strong>Kein Tracking:</strong> Wir messen weder Öffnungen noch Klicks. Unsere E-Mails
enthalten keine Zählpixel und keine getrackten Weiterleitungen. Wie viele Menschen sich
angemeldet haben, ermitteln wir ausschließlich als Gesamtzahl aus unserer eigenen Datenbank –
ohne Cookies, ohne Profilbildung und ohne Auswertung deines individuellen Verhaltens.</p>

<p><strong>Aufbewahrung beim Dienstleister:</strong> Versandprotokolle und E-Mail-Ereignisdaten
werden bei Plus Five Five, Inc. nach 30 Tagen gelöscht. Nach Beendigung unseres Vertrags werden
die dort gespeicherten Daten innerhalb von 90 Tagen gelöscht.</p>

<p><strong>Speicherdauer:</strong> Deine E-Mail-Adresse speichern wir, bis du deine Einwilligung
widerrufst. Nach dem Widerruf entfernen wir dich unverzüglich aus dem Verteiler. Die
Nachweisdaten zu deiner Einwilligung bewahren wir danach noch drei Jahre auf – gerechnet ab dem
Ende des Kalenderjahres, in dem der Widerruf zugegangen ist (§§ 195, 199 BGB) –, um im
Streitfall die Rechtmäßigkeit des Versands belegen zu können. Anschließend löschen wir auch
diese Daten.</p>

<p><strong>Widerruf:</strong> Du kannst deine Einwilligung jederzeit mit Wirkung für die Zukunft
widerrufen – über den Abmeldelink am Ende jeder E-Mail oder formlos an contact@catandary.de. Die
Rechtmäßigkeit der bis zum Widerruf erfolgten Verarbeitung bleibt unberührt (Art. 7 Abs. 3
DSGVO).</p>

<p><strong>Freiwilligkeit:</strong> Die Angabe deiner E-Mail-Adresse ist freiwillig. Ohne Angabe
können wir dir lediglich keinen Newsletter zusenden; andere Nachteile entstehen dir nicht.</p>
```

**Außerdem anzupassen:**
- **Abschnitt 5 (Empfänger)** um Resend erweitern. (Stripe erst nennen, wenn Zahlungen live sind.)
- **Abschnitt 6 (Rechte)** um die zuständige Aufsichtsbehörde ergänzen: *Landesbeauftragter für den
  Datenschutz und die Informationsfreiheit Baden-Württemberg, Lautenschlagerstraße 20, 70173 Stuttgart.*

---

## 2. Direkt am Formular

```html
<label class="nl-consent">
  <input type="checkbox" id="nl-consent" name="consent" required>
  <span>Ja, ich möchte die Launch-Benachrichtigung und den Catandary-Newsletter per E-Mail
  erhalten. Ich kann diese Einwilligung jederzeit über den Abmeldelink in jeder E-Mail oder
  per Mail an contact@catandary.de widerrufen.</span>
</label>

<button type="submit">Newsletter abonnieren</button>

<p class="nl-note">
  Wir senden dir zuerst eine E-Mail mit einem Bestätigungslink – erst nach deiner Bestätigung
  bist du angemeldet (Double-Opt-in). Zum Nachweis speichern wir Anmelde- und
  Bestätigungszeitpunkt, die verwendete IP-Adresse und den Wortlaut dieses Hinweises; diesen
  Nachweis bewahren wir auch nach einem Widerruf noch drei Jahre auf. Der Versand erfolgt über
  unseren Dienstleister Resend mit Sitz in den USA. Keine Weitergabe an Dritte zu Werbezwecken,
  keine Öffnungs- oder Klickmessung.
  Details in unserer <a href="#" data-legal="datenschutz">Datenschutzerklärung</a>.
</p>
```

**Umsetzungsregeln:**
- Checkbox **nicht** vorbelegt (ErwGr 32 DSGVO; EuGH C-673/17 *Planet49*; BGH I ZR 7/16).
- Der Checkbox-Text ist **exakt** der Wortlaut, der als `consent_text` gespeichert wird.
  Bei jeder Änderung `consent_version` hochzählen.
- Nur E-Mail ist Pflichtfeld. Der Datenschutz-Link darf die Formulareingabe nicht verlieren.
- Die Landing hat **Doppelzweck** (Launch-Warteliste *und* Newsletter) → beide Zwecke müssen im
  Einwilligungstext stehen; nachträgliche Zweckerweiterung ist nicht möglich.

**Erfolgsmeldung — identisch für neu / bestehend / unbestätigt / abgemeldet** (Anti-Enumeration):

> „Fast geschafft — bitte bestätige die Anmeldung über den Link, den wir dir gerade geschickt haben."

---

## 3. Bestätigungsmail

```
Absender: Catandary Trends <trends@send.catandary.de>
Betreff:  Bitte bestätige deine Anmeldung
Format:   Text (oder HTML ohne Bilder, ohne Logo, ohne Zählpixel, ohne getrackte Links)

Hallo,

für die E-Mail-Adresse {{email}} wurde am {{datum}} um {{uhrzeit}} Uhr (IP {{ip}}) auf
catandary.de eine Anmeldung zum Newsletter vorgenommen.

Bitte bestätige die Anmeldung über diesen Link:
{{confirm_url}}

Der Link ist 48 Stunden gültig und kann einmal verwendet werden.

Du hast dabei folgender Erklärung zugestimmt:
„{{consent_text}}"

Wenn du dich nicht angemeldet hast, tu einfach nichts. Ohne deine Bestätigung senden wir dir
keine weiteren E-Mails und löschen die Anmeldedaten spätestens nach 30 Tagen.

Widerruf jederzeit über den Abmeldelink in jeder E-Mail oder an contact@catandary.de.

--
Dirk Herrmann, Geiselharz 40/6, 88279 Amtzell, Deutschland
contact@catandary.de · Datenschutzerklärung: https://catandary.de/#datenschutz
```

**Verboten in dieser Mail:** Logo/Bildmarke, „Welcome to Catandary", Slogans, Produktbeschreibungen,
Inhaltsvorschau, Rabatte, Social-Links, Zählpixel, getrackte Redirects.
**Ebenfalls unterlassen:** jede Erinnerungsmail bei ausbleibender Bestätigung — dafür liegt noch
keine Einwilligung vor.

**Confirm-Seite, drei Zustände:** bestätigt · Link abgelaufen (mit „neu anfordern") · ungültig
oder bereits verwendet.

---

## 4. Rechtliche Muss-Punkte

### Gesicherte Rechtslage

| Punkt | Inhalt |
|---|---|
| **Beweislast** | Volle Darlegungs- und Beweislast beim Versender (Art. 7 Abs. 1, Art. 5 Abs. 2 DSGVO). Keine gesetzliche Vermutung eines Verstoßes — ein *non liquet* geht zu Lasten des Versenders. |
| **Was zu protokollieren ist** | Die Erklärung **vollständig und im Wortlaut**, jederzeit ausdruckbar. Die bloße IP-Adresse genügt ausdrücklich **nicht** (DSK-Orientierungshilfe Direktwerbung 18.02.2022, Ziff. 3.3, S. 11 f., unter Verweis auf BGH I ZR 164/09). IP + Zeitstempel sind Teil des Nachweisbündels. |
| **Rechtsgrundlage der Nachweisdaten** | Art. 6 Abs. 1 lit. c i. V. m. Art. 5 Abs. 2, Art. 7 Abs. 1 DSGVO bzw. lit. f — **ausdrücklich nicht** lit. a, sonst entfiele der Nachweis mit dem Widerruf (DSK-OH Ziff. 3.7, S. 14). |
| **Aufbewahrung nach Widerruf** | Adresse sofort aus dem Verteiler, Nachweis noch ca. 3 Jahre (§§ 195, 199 BGB; § 31 Abs. 2 Nr. 1 OWiG). Auf diese Aufbewahrung ist **schon bei der Erhebung** hinzuweisen. Die 5-Jahres-Frist des § 7a UWG gilt nur für Telefonwerbung. |
| **Widerrufsrecht** | Vor Abgabe der Einwilligung und „im direkten Zusammenhang mit der Einholung" zu nennen (Art. 7 Abs. 3 S. 3 DSGVO) — ein bloßer Link auf die Datenschutzerklärung genügt nach Behördenlesart nicht. |
| **Vorangekreuzte Checkbox** | Unwirksam (ErwGr 32; EuGH C-673/17; BGH I ZR 7/16). |
| **Drittlandtransfer Resend** | Resend speichert **alle** Kundendaten in den USA — die Regionswahl steuert nur den Versandort. Eine „Daten bleiben in der EU"-Formulierung wäre **falsch**. Angemessenheitsbeschluss (EU) 2023/1795 + SCC aus dem AVV. EuG T-553/23 (03.09.2025) hat das DPF bestätigt; Rechtsmittel C-703/25 P beim EuGH anhängig. |
| **Tracking-Pixel** | Bräuchte eigene Einwilligung nach § 25 Abs. 1 TDDDG; nicht von der Newsletter-Einwilligung gedeckt. Ist-Zustand unkritisch: Resend-Tracking ist pro Domain und standardmäßig **aus**, `newsletter_sender.py` setzt keine Tracking-Parameter. Per Dashboard-Screenshot mit Datum dokumentieren. |

### Praxis-Auslegung (Ergebnis solide, Begründung nicht überdehnen)

- **DOI ist gesetzlich nirgends angeordnet.** Die DSK hält es für „geboten"; prozessual ist es der
  einzige praktikable Nachweisweg. Wichtig: **BGH I ZR 164/09 hat DOI für E-Mail-Werbung
  ausdrücklich bestätigt** und nur für Telefonwerbung verworfen — das wird oft falsch herum zitiert.
- **Werbefreie Bestätigungsmail** zulässig (OLG Celle 13 U 15/14; OLG Düsseldorf I-15 U 64/15).
  OLG München 29 U 1682/12 blieb Mindermeinung, wurde aber nie höchstrichterlich ausgeräumt →
  streng funktional halten.
- **Namensnennung von Resend:** Zwingend ist nach Art. 13 Abs. 1 lit. e nur „Empfänger **oder**
  Kategorien"; lit. f verlangt die Angabe der **Garantien**, nicht des Namens. Namensnennung ist
  Best Practice (WP260 rev.01 Rn. 31) und dringend zu empfehlen — aber keine harte Pflicht.
  Das Entfernen der Namen aus der Marketing-FAQ war unbedenklich.
- **Kein Import, keine Reaktivierung von Altbeständen.** Für Adressen ohne Nachweis existiert kein
  Nachweis; eine „Bitte bestätige noch"-Mail an sie wäre selbst Werbung ohne Einwilligung.
- **Achtung beim geplanten Gated Content:** E-Mail als Zugangsbedingung ist keine
  Newsletter-Einwilligung — Zugang und Newsletter technisch und optisch trennen
  (Art. 7 Abs. 4 DSGVO, Kopplungsverbot).

---

## 5. Cookies und Interessenmessung — Empfehlung: bei „cookieless" bleiben

Der Owner hat signalisiert, dass für den Zweck „sehen, ob jemand Interesse zeigt" auch
**notwendige Cookies** in Ordnung wären. **Das ist nicht erforderlich** — und der Verzicht ist
hier die bessere Entscheidung:

| Frage | Antwort ohne Cookies |
|---|---|
| Wie viele haben Interesse? | `SELECT count(*) FROM … WHERE confirmed` — reine DB-Abfrage |
| Wie viele Besucher? | Apache-Access-Logs (serverseitig) — bereits von Abschnitt 3 „Server-Logfiles" gedeckt |
| Conversion-Rate? | Anmeldungen ÷ Besucher aus den Logs — kein Cookie nötig |
| CSRF-Schutz des Formulars? | Nicht nötig: Honeypot + Rate-Limit + DOI decken das Risiko ab. Eine „Fremdanmeldung" ist genau das, was DOI ohnehin abfängt. |
| Doppelte Anmeldung verhindern? | Über `email UNIQUE` in der DB, nicht über einen Client-Cookie |

**Konsequenz:** Der DOI-Flow braucht **null Cookies** (Token steht in der URL, Rate-Limit läuft
IP-basiert in der DB). Damit bleibt der Claim „cookieless" auf der Landing **wahr** und es
braucht **kein Consent-Banner** (§ 25 TDDDG greift nicht, wenn nichts auf dem Endgerät
gespeichert oder ausgelesen wird).

⚠️ **Sobald doch ein Analytics-Werkzeug dazukommt** (auch ein selbstgehostetes mit Cookie oder
Fingerprinting), gilt: § 25 Abs. 1 TDDDG → **Einwilligung vor dem Setzen**, also Consent-Banner
— *und* die Claims „cookieless" und „no third-party analytics" auf der Landing müssen weg.
Das ist der eigentliche Preis, nicht die technische Umsetzung. Solange die Anmeldezahl als
Interessensignal genügt, nicht anfassen.

---

## 6. Nachweisfelder (additiv zu `newsletter_subscribers`)

Das Live-Schema (`id, email, verticals, confirmed, subscribed_at, unsubscribed_at`) kann den
DSGVO-Nachweis **nicht** aufnehmen. Zu ergänzen:

| Spalte | Zweck |
|---|---|
| `confirm_token_hash` | nur der SHA-256-Hash des Zufallstokens, nie der Token selbst |
| `confirm_expires_at` | Ablauf (72 h), in SQL gerechnet |
| `confirmed_at` | Zeitpunkt der Bestätigung |
| `signup_ip` / `confirm_ip` | Nachweisbündel |
| `user_agent` | Nachweisbündel |
| `consent_text` / `consent_version` | Wortlaut der Erklärung (Pflicht — IP allein genügt nicht) |

⚠️ Additive Migration **manuell auf der Live-DB nachziehen** — `init_db` macht das nicht.
Genau diese Lücke hat am 2026-07-19 den Stripe-Webhook zerlegt.
