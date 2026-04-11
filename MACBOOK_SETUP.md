# Catandary Trends — MacBook Air Setup & Foresight Cockpit Test

Anleitung zum Testen der gesamten Plattform (Frontend + Foresight Cockpit inkl. semantischer Suche) auf MacBook Air mit Apple Silicon und 8 GB RAM.

---

## Voraussetzungen

- **macOS** mit Apple Silicon (M1/M2/M3)
- **Node.js 20+** (`brew install node`)
- **Python 3.12+** (`brew install python`)
- **Ollama** (`brew install ollama`) — nur nötig für semantische Suche, ohne Ollama funktioniert FTS5-only-Fallback
- **Git** (zum Klonen des Repos)

---

## 1. Repo klonen

```bash
git clone git@github.com:ZuluTwoThree/catandary-trends.git
cd catandary-trends
```

---

## 2. Datenbank kopieren

Die SQLite-Datenbank (`data/catandary.db`, ~116 MB) ist nicht im Git-Repo (gitignored). Sie muss vom Windows-Rechner kopiert werden.

```bash
mkdir -p data
# Vom Windows-Rechner übertragen (USB, SCP, AirDrop, etc.):
# Quelle: C:\Users\Dirk\projects\catandary-trends\data\catandary.db
# Ziel:   ./data/catandary.db
```

**Inhalt der DB:** 4782 published Trends mit Embeddings (4096-dim, qwen3-embedding), FTS5 Virtual Table, Lead-Time-Tier-Lookup. Alles ist bereits eingerichtet — kein `setup_db.py` oder `setup_fts5.py` nötig, solange die kopierte DB intakt ist.

**Prüfen nach dem Kopieren:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/catandary.db')
c = conn.cursor()
c.execute(\"SELECT COUNT(*) FROM trends WHERE status='published'\")
print(f'Published: {c.fetchone()[0]}')
c.execute(\"SELECT name FROM sqlite_master WHERE name='trends_fts'\")
print(f'FTS5: {bool(c.fetchone())}')
c.execute(\"SELECT COUNT(*) FROM trends WHERE embedding IS NOT NULL AND status=\'published\'\")
print(f'Embeddings: {c.fetchone()[0]}')
"
# Erwartete Ausgabe: Published: 4782, FTS5: True, Embeddings: 4782
```

---

## 3. Frontend installieren & starten

```bash
cd frontend
npm install
npm run dev
```

Das startet:
1. `predev` Script: generiert `src/lib/mega-trends.generated.ts` aus `mega_trends.yaml`
2. Next.js Dev-Server mit Turbopack auf **http://localhost:3001**

**Seiten zum Testen:**
- `http://localhost:3001` — Trend-Startseite (Card-Grid mit Vertical-Filter)
- `http://localhost:3001/mega-trends` — Mega-Trends-Übersicht
- `http://localhost:3001/foresight` — **Foresight Cockpit** (Hybrid-Suche)

---

## 4. Ollama für semantische Suche (optional, aber wichtig zu testen)

### 4a. Ollama installieren & Embedding-Modell laden

```bash
# Ollama starten (falls nicht als Service aktiv)
ollama serve &

# Nur das Embedding-Modell wird für die Suche gebraucht
ollama pull qwen3-embedding
```

**RAM-Verbrauch qwen3-embedding:** ~5-6 GB. Bei 8 GB unified Memory ist das eng — macOS wird Speicher swappen. Das ist der Kerntest: funktioniert die Suche trotzdem mit akzeptabler Latenz?

### 4b. Testen ob Ollama erreichbar ist

```bash
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool
# Sollte qwen3-embedding in der Liste zeigen
```

### 4c. Falls qwen3-embedding nicht läuft (8 GB zu knapp)

Das Foresight Cockpit hat einen **automatischen FTS5-only-Fallback**: Wenn Ollama nicht erreichbar ist oder das Embedding fehlschlägt, liefert die Suche nur FTS5-Textsuche (ohne semantische Ergebnisse). Das funktioniert ohne Ollama.

**Alternativen mit kleinerem Modell (spätere Evaluation):**
- `nomic-embed-text` (~270 MB) — deutlich kleiner, aber andere Embedding-Dimension (768 statt 4096). Würde Neuberechnung aller Trend-Vektoren erfordern.
- `all-minilm` (~23 MB) — minimaler RAM, Dimension 384. Nur als Notfall-Fallback.

**Wichtig:** Ein Modellwechsel ändert die Embedding-Dimension. Die DB-Embeddings (4096-dim) sind dann inkompatibel. Für den Test reicht FTS5-only oder das originale `qwen3-embedding`.

---

## 5. Testplan

### Test 1: Frontend-Grundfunktion (ohne Ollama)
1. Ollama stoppen (`killall ollama` oder nicht starten)
2. `npm run dev` im `frontend/`-Ordner
3. `http://localhost:3001` öffnen — Trends-Grid sollte laden
4. Vertical-Filter durchklicken (FOOD, TECH, HEALTH, etc.)
5. Einzelnen Trend-Artikel öffnen (Klick auf Karte)
6. Mega-Trends-Seite aufrufen (`/mega-trends`)
7. **Erwartung:** Alles lädt, Daten aus SQLite korrekt, kein Fehler

### Test 2: Foresight Cockpit — FTS5-only (ohne Ollama)
1. Ollama weiterhin gestoppt
2. `http://localhost:3001/foresight` öffnen
3. Suchbegriff eingeben: `protein` (breiter Begriff, viele Treffer)
4. **Erwartung:** Ergebnisse erscheinen (nur FTS5-Textsuche), Relevanz-Prozente werden angezeigt, Analytics-Sidebar (Timeline, PESTEL, etc.) wird bei genug Treffern eingeblendet
5. Suchbegriff: `AI` — sollte viele Treffer mit Analytics liefern
6. Suchbegriff: `cheese` — wenige Treffer, Analytics-Hinweis "Zu wenige Signale"
7. Vertical-Filter testen (z.B. nur FOOD)

### Test 3: Foresight Cockpit — Hybrid-Suche (mit Ollama)
1. Ollama starten: `ollama serve`
2. Sicherstellen: `ollama list` zeigt `qwen3-embedding`
3. Frontend neu starten (damit Embedding-Cache neu geladen wird)
4. `http://localhost:3001/foresight` — Suchbegriff: `protein`
5. **Erwartung:** Mehr und relevantere Treffer als FTS5-only, höhere Relevanz-Prozente (RRF aus beiden Quellen)
6. Suchbegriff: `Ernährung der Zukunft` (semantisch, kein exakter Match)
7. **Erwartung:** Semantische Treffer erscheinen, Banner "Ergebnisse basieren auf semantischer Ähnlichkeit" wenn kein FTS5-Hit
8. Suchbegriff: `xyz123` (Gibberish)
9. **Erwartung:** 0 Ergebnisse (strict threshold 0.60 filtert Noise)

### Test 4: Performance & RAM (mit Ollama)
1. Ollama + Frontend gleichzeitig laufen lassen
2. Activity Monitor öffnen → Memory Pressure beobachten
3. Mehrere Suchen hintereinander ausführen
4. **Dokumentieren:**
   - Memory Pressure (grün/gelb/rot)
   - Swap-Nutzung
   - Antwortzeit der Suche (subjektiv: <1s / 1-3s / >3s)
   - Antwortzeit des Embedding-Calls (sichtbar in Terminal-Log)
5. Falls Memory Pressure rot → Ollama stoppen, FTS5-only-Fallback dokumentieren

### Test 5: Production Build
1. `npm run build` im `frontend/`-Ordner (testet ob Build durchläuft)
2. `npm start` — Production-Server starten
3. Gleiche Tests wie oben wiederholen
4. **Erwartung:** Schnellere Ladezeiten als Dev-Modus

---

## 6. Ergebnisse dokumentieren

Nach dem Test bitte folgende Punkte festhalten:

```
## MacBook Air Test — Ergebnisse (Datum: ____)

### Hardware
- Modell: MacBook Air M_ / __GB RAM
- macOS Version: ____

### Frontend
- [ ] Trends-Grid lädt korrekt
- [ ] Vertical-Filter funktioniert
- [ ] Einzelne Trend-Artikel laden
- [ ] Mega-Trends-Seite lädt
- [ ] DE/EN-Umschaltung funktioniert

### Foresight Cockpit — FTS5-only
- [ ] Suche liefert Ergebnisse
- [ ] Analytics-Sidebar wird bei >=30 Treffern angezeigt
- [ ] Relevanz-Prozente plausibel

### Foresight Cockpit — Hybrid (Ollama)
- [ ] qwen3-embedding läuft auf 8GB: ja/nein
- [ ] Semantische Suche liefert Ergebnisse
- [ ] Embedding-only-Banner erscheint bei semantischen Queries
- [ ] Gibberish-Queries (xyz123) liefern 0 Ergebnisse
- [ ] Antwortzeit Suche: ___s
- [ ] Memory Pressure: grün/gelb/rot
- [ ] Swap-Nutzung: ___MB

### Production Build
- [ ] `npm run build` erfolgreich
- [ ] Production-Server startet

### Fazit
- Empfehlung: Ollama auf 8GB tragbar / nur FTS5 / kleineres Modell nötig
- Notizen: ____
```

---

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| `better-sqlite3` Build-Fehler | `npm rebuild better-sqlite3` — sollte Apple Silicon Prebuild nutzen |
| DB nicht gefunden | `DATABASE_PATH` in `.env` prüfen, oder `data/catandary.db` relativ zum `frontend/`-Ordner |
| FTS5 nicht verfügbar | `python3 scripts/setup_fts5.py` ausführen (nur nötig falls DB neu erstellt) |
| Ollama Connection Refused | `ollama serve` starten, Port 11434 prüfen |
| qwen3-embedding OOM | Ollama stoppen, FTS5-only nutzen — das ist der erwartete Fallback |
| `predev` Script fehlt `mega_trends.yaml` | Datei ist im Git-Repo, `git pull` sollte reichen |
| Suche langsam (>5s) | Embedding-Cache wird beim ersten Request geladen (~75 MB für 4782 Trends), danach schneller |

---

## Umgebungsvariablen (.env)

Im Projektroot eine `.env` anlegen (Kopie von `.env.example`):

```bash
cp .env.example .env
```

Für den MacBook-Test reichen die Defaults:
```
OLLAMA_HOST=http://127.0.0.1:11434
DATABASE_PATH=./data/catandary.db
```

Die Frontend Search API liest `OLLAMA_CLIENT_HOST` (default: `http://127.0.0.1:11434`) und `DATABASE_PATH`.
