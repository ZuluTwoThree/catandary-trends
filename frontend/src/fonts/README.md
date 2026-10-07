# IBM Plex, lokal eingebunden

Seit 2026-10-07 (Owner): keine Schrift wird mehr beim Build von Google Fonts geholt.
`next/font/google` lud die Font-CSS bei jedem Build neu; eine Änderung bei Google (ein
erweiterter unicode-range) gab der CSS-Datei einen neuen Namen und machte am 07.10. jede
Seite des statischen Exports „geändert" (28.206 statt ~2.600 Dateien, 1,4 GB Upload).
Eingebunden über `next/font/local` in `src/app/layout.tsx`.

**Ziel: dasselbe Schriftbild wie vorher.** Deshalb nicht die neueren IBM-npm-Pakete
(dort ist z. B. die Serif minimal breiter, und `ss01` wäre aktiv — Googles Dateien
enthalten es nicht, das Logo bekäme ein einstöckiges „a"), sondern Googles Quellen:

- Quelle: `github.com/google/fonts`, `ofl/ibmplexserif` (Version 2.6), `ofl/ibmplexmono`
  (2.3), `ofl/ibmplexsans` (variabel, 3.201), Stand Commit `5e8a3ba89955` (07.10.2026).
- Lizenz: SIL Open Font License 1.1 (`LICENSE.txt` = `OFL.txt` aus dem Repo).
- Schnitte: Serif 400/500/600 je normal + kursiv, Mono 400/500/600, Sans 300/400/500/600
  (Sans per `fontTools.varLib.instancer` aus der variablen Datei, `wdth=100`).
- Zeichenumfang: Googles Subsets latin + latin-ext + vietnamese in EINER Datei je Schnitt
  (Kyrillisch/Griechisch fallen auf die Systemschrift zurück — der Feed ist englisch).
- Features wie Googles Auslieferung: `ccmp dnom frac liga numr kern mark`.

```
U="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD,U+100-2BA,U+2BD-2C5,U+2C7-2CC,U+2CE-2D7,U+2DD-2FF,U+304,U+308,U+329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C4,U+2113,U+2C60-2C7F,U+A720-A7FF,U+102-103,U+110-111,U+128-129,U+168-169,U+1A0-1A1,U+1AF-1B0,U+300-301,U+303-304,U+308-309,U+323,U+329,U+1EA0-1EF9,U+20AB"
python -m fontTools.varLib.instancer "IBMPlexSans[wdth,wght].ttf" wght=500 wdth=100 \
  --update-name-table -o IBMPlexSans-Medium.ttf          # je Sans-Gewicht
python -m fontTools.subset IBMPlexSerif-Regular.ttf --unicodes="$U" \
  --layout-features='ccmp,dnom,frac,liga,numr,kern,mark' --flavor=woff2 \
  --output-file=IBMPlexSerif-Regular.woff2               # je Schnitt
```

fontTools mit brotli steckt in der Recherche-venv (`~/venvs/catandary-research`).
