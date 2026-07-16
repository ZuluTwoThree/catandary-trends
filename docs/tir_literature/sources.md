# TIR-Quellen — kuratierte Kern-Links

Manuell recherchierte Primärquellen zur TIR-Methode, den Wettbewerbern und dem Patent
(Recherche 2026-07-16/17). Die **automatisch erzeugte Zitations-Hülle** (transitiv,
alle aufbauenden Arbeiten) liegt in [`index.md`](index.md) + [`bibliography.json`](bibliography.json);
OA-Volltexte auf `/mnt/data-hdd/tir_literature/pdfs`. Bezug: Issues #57, #45; `docs/tir_reliability_plan.md`.

## Wissenschaftliche Grundlage (die Methode, auf der wir + Wettbewerber stehen)
- Singh, Triulzi, Magee (2021), *Technological improvement rate predictions for all technologies* — Research Policy 50(9) 104294. [DOI](https://doi.org/10.1016/j.respol.2021.104294) · [arXiv 2004.13919](https://arxiv.org/abs/2004.13919) · [SSRN](https://doi.org/10.2139/ssrn.3571060) · [MIT DSpace](https://dspace.mit.edu/handle/1721.1/132865)
- Triulzi, Alstott, Magee (2020), *Estimating technology performance improvement rates by mining patent data* — TFSC 158 120100. [DOI](https://doi.org/10.1016/j.techfore.2020.120100) · [Code (GitHub)](https://github.com/GiorgioTriulzi/TechnologyPerformanceImprovementEstimates)
- Datensatz: *Functional performance improvement data and patent sets for 30 technology domains* — [PMC7490809](https://pmc.ncbi.nlm.nih.gov/articles/PMC7490809/). **= der Ground-Truth auf `/mnt/data-hdd/Domains_patent_info.csv` + `performance_time_series.csv`.**
- MIT-Methodik-Seite: [technologyrates.mit.edu — overall methodology](https://technologyrates.mit.edu/overall-methodology/) · [MIT News 2021](https://news.mit.edu/2021/comprehensive-study-technological-change-0802)
- Hummon & Doreian (1989) — Ursprung des SPNP-Index (in obigen Papers zitiert).

## Patent (FTO — siehe Memory `patent-us12099572-fto`)
- **US12099572B2** *Systems and methods to estimate rate of improvement for all technologies* — Technext Inc (Singh, Magee). [Google Patents](https://patents.google.com/patent/US12099572B2/en) · [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12099572)
- Fortsetzung (anhängig, beobachten): US20240394336A1.

## Wettbewerber (siehe Memory `competitor-tir-landscape`, Issue #57)
- **TechNext** (MIT-Spinout, Singh/Magee): [technext.ai](https://www.technext.ai/) · [Team](https://www.technext.ai/team) · [Patent-PR (BusinessWire)](https://www.businesswire.com/news/home/20250610233784/en/) · [Quantum-PR Nov 2025](https://www.businesswire.com/news/home/20251120072341/en/)
- **GetFocus** (NL, van Ingen/van de Poll): [getfocus.eu](https://www.getfocus.eu/) · [How it works](https://www.getfocus.eu/how-it-works) · [About](https://www.getfocus.eu/about-us) · [Science\|Business-Profil](https://sciencebusiness.net/news/ai/predicting-future-one-patent-citation-time) · [ManufacturingTomorrow](https://www.manufacturingtomorrow.com/news/2025/04/22/getfocus-unlocks-early-signals-of-technology-disruption-giving-rd-teams-a-decisive-edge/24792/) · [R&D World (Philips/Sevvy)](https://www.rdworldonline.com/getfocus-highlights-philips-sevvy-use-cases-for-ai-tech-scouting-platform/)

## Für uns methodisch relevante Weiterentwicklungen (Auswahl aus der Hülle)
- Jiang & Luo (2021) — *Technology fitness landscape: deep neural embeddings of patent data* (1757 Domänen + Rates). Nächster zu unserem Embedding-Ansatz.
- Rezazadegan et al. (2024), Scientometrics — *Quantifying progress of AI subdomains via the patent citation network* (TIR feingranular).
- Ho et al. (2025), TFSC / Sci Reports — *Multilayer citation networks* (Patente+Publikationen+Trials+Markt).
- Lai et al. (2026), Research Policy — *Identification of valuable patents: … effects of prediction time points* (relevant für WS2-Truncation).
- Park et al. (2025) — *Declining Disruptiveness: role of zero-backward-citation works* + Sarica & Luo (2023), *Innovation Slowdown* (Kompositions-Drift als Datenartefakt).
- Fronzetti Colladon (2025), Research Policy — *A new mapping of technological interdependence* ([arXiv 2308.00014](https://arxiv.org/abs/2308.00014)); Composite-Zentralität + Text-Mining, 6,5M USPTO-Patente.
- Niggli & Rutzer (2023) — *Digital technologies, technological improvement rates* (Rate ↔ Breakthrough).
- Review: *Quantitative Technology Forecasting: A Review of Trend Extrapolation Methods* ([arXiv 2401.02549](https://arxiv.org/abs/2401.02549), 2024).
