# Field Watch / Trajectory Sheet — Demo-Generatoren (2026-09-20)

Erzeugen die Musterblätter in `docs/samples/` aus der Live-DB. Reine SQL-Messung,
kein Sprachmodell; einziger GPU-Schritt ist der Query-Vektor des Reifegrad-Blocks
(`measure_quant.py`, Cache in `data/`). Das ist der erste Schnitt aus
`docs/value_proposition_field_watch_2026-09-19.md` Abschnitt 5 — noch kein Cron,
kein Kundenfeld-Editor, kein `field_watch_runs`.

```bash
V=.venv/bin/python; D=scripts/field_watch_demo; S=docs/samples
# Field Watch (Wochenblatt, 3 Felder; Datum = ein Tag der zu berichtenden Woche)
$V $D/measure_field.py $D/fields_food.json /tmp/fw_food.json 2026-09-20
$V $D/render_field_watch.py /tmp/fw_food.json $S/field_watch_food_2026-W38.html "Beispiel — Molkerei-/Lebensmittel-Mittelstand"
# Trajectory Sheet (ein Feld)
$V $D/measure_quant.py "lithium iron phosphate battery cells" /tmp/lfp_quant.json   # ~8 min, GPU-Handover
$V -c 'import json;json.dump([json.load(open("'$D'/field_lfp.json"))],open("/tmp/fields_lfp.json","w"))'
$V $D/measure_field.py /tmp/fields_lfp.json /tmp/fw_lfp.json 2026-09-20
$V $D/measure_sheet.py $D/field_lfp.json /tmp/lfp_quant.json /tmp/sheet_lfp.json
$V $D/render_sheet.py /tmp/sheet_lfp.json /tmp/fw_lfp.json $S/trajectory_sheet_lfp_2026-09-20.html
# PDF (Playwright-Chromium, schon installiert)
CH=~/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell
$CH --headless --no-sandbox --disable-gpu --no-pdf-header-footer --print-to-pdf=$S/x.pdf $S/x.html
```

Messregeln stehen im jeweiligen Blatt (Abschnitt „Methodik"). Feld = Liste von
Suchphrasen (`phraseto_tsquery`, Titel/Teaser/Tags bzw. Patent-Volltextindex);
Ebene nach Quellentyp wie `pipeline/tiers.py`; Quartale auf festem Quellenpanel.
