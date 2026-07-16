# TIR-Literatur

Quellen- und Literatur-Sammlung zur Technology-Improvement-Rate-Methode (Singh/
Triulzi/Magee-Linie), den Wettbewerbern und dem Patent. Angelegt 2026-07-17.

| Datei | Inhalt |
|---|---|
| [`sources.md`](sources.md) | **Kuratierte Kern-Links** — Grundlagenpaper, MIT-Datensatz, Patent, Wettbewerber (GetFocus/TechNext), die für uns relevanten Weiterentwicklungen. Der Einstieg. |
| [`index.md`](index.md) | **Auto-generierte Zitations-Hülle** — alle Arbeiten, die auf den zwei Seed-Papern aufbauen, transitiv (forward-citation closure). Tabelle mit OA-PDF-Links. |
| `bibliography.json` | Vollständige Metadaten aller Arbeiten der Hülle (paperId, DOI, arXiv, OA-URL, Zitationen, depth). Maschinenlesbar. |
| `pdf_manifest.csv` | Pro Arbeit: OA-PDF-URL + Status (`open_access`/`paywalled`). |

## Erzeugung / Aktualisierung
```bash
python scripts/tir_lit_snowball.py --depth 3 --download   # Hülle + OA-Volltexte
```
Snowball über die **Semantic Scholar Graph API** (forward citations, resumable,
rate-limit-schonend). Seeds = Singh/Triulzi/Magee 2021 + Triulzi/Alstott/Magee 2020.

## Volltexte
**Open-Access-PDFs liegen auf der HDD, NICHT im Repo:** `/mnt/data-hdd/tir_literature/pdfs/`
(je `<paperId>.pdf`) — bulkig und copyright-gebunden; das Repo führt nur die Links.
**Paywall-Volltexte können nicht automatisch gezogen werden** und sind im Manifest als
`paywalled` markiert (Zugriff via DOI/Institutions-Lizenz).

## Tiefe & Relevanz
depth 0 = Seeds · depth 1 = direkte „bauen darauf auf" · depth 2 = deren Zitierende ·
depth 3 = usw. Ab depth 2 sinkt die Themen-Relevanz (viele Anwendungs-Arbeiten aus
Nachbarfeldern zitieren die Methode nur am Rande); die Hülle ist bei `--max-papers`
gedeckelt und re-runbar für mehr. Der kuratierte Kern steht in `sources.md`.
