---
slug: _template
title: "[Analysis title — one clear claim or question, not a topic label]"
date: 2026-01-01
teaser: "[One sentence for LinkedIn and the /analysis overview — the finding, not the topic.]"
image: _template.png
corpus_asof: 2026-01-01
author: Dirk Herrmann
draft: true
---

## The question

[State the question this analysis answers in one or two sentences. Specific
enough that a reader knows exactly what was checked — not "trends in X" but
"is X actually happening, and how fast."]

## What we found

[The finding, stated plainly, before the evidence. If the honest answer is
"unclear" or "no", say that — this is a placeholder structure only; it does
not assert any real finding.]

- [Placeholder evidence point one — a concrete, checkable observation]
- [Placeholder evidence point two]
- [Placeholder evidence point three]

## The evidence

[Walk through what the corpus actually shows: which signals, how many,
over what time window, from which primary sources. Every specific claim in
a real analysis must trace back to something a reader can click through to
— this section is where that happens.]

## What this means

[Put the finding in context: how it fits the broader mega/macro picture,
what it does *not* prove, and what would change the read. Honesty about the
limits of the evidence is the point — see `frontend/src/app/trends/methodology`
for the standard this has to meet.]

This file is a structural template only (**draft: true** — it is never
listed on `/analysis` or rendered at `/analysis/_template`). It contains no
real data, figures, or claims. Copy it to a new file, replace every
bracketed placeholder, set `draft: false` (or remove the field) once it is
ready to publish, and drop the matching screenshot/chart into
`frontend/public/analyses/<image>`.
