# Source Use & Removal Requests — draft for the methodology page

Status: draft (2026-09-02, compliance review follow-up). English, intended for
`/trends/methodology` (public) — the internal procedure is at the end. Legal
texts on this site are drafts without lawyer review (`docs/legal/README.md`).
Contact address and 72-hour promise are the owner's commitments; change them
here and the tool (`scripts/takedown.py`) will still work.

---

## How we use sources

Catandary Trends reads publicly available RSS/Atom feeds, press-release wires,
newsrooms and open research/funding databases. Every published trend article is
our own analytical text, generated and gated by our pipeline — it is not a copy,
excerpt or translation of the source article.

- **Attribution and backlink are mandatory.** Every article names the source and
  links to the original. We do not publish an article we cannot cite.
- **Feed content.** From a feed we keep the title, the publisher's own teaser
  (at most 2,000 characters) and the link — the material the publisher chose to
  syndicate.
- **Full text, for analysis only.** For a subset of sources we fetch the article
  page to ground our text in what the source actually says (figures, dates,
  quotes). That copy is used for text and data mining only (§44b UrhG), is never
  shown to readers, and is deleted after the processing window (14 days).
- **Quotations** are limited to short, verbatim snippets (at most three per
  article, at most ~200 characters each) and are used only where they serve the
  analysis.
- **Images, audio and video are never copied.**
- **We identify ourselves.** Our crawler uses the User-Agent
  `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`,
  fetches at most one page per second per host and at most one feed request per
  source per day.

## Machine-readable opt-out (honoured automatically)

You do not need to write to us to keep our crawler off your pages:

| Signal | Effect |
|---|---|
| `robots.txt` disallow for `*` or `CatandaryTrendsBot` | page is not fetched |
| HTTP header `TDM-Reservation: 1` or `<meta name="tdm-reservation" content="1">` (TDMRep) | full text is not stored; only the feed teaser is used |
| `/.well-known/tdmrep.json` with a matching `location` and `tdm-reservation: 1` | same |
| `<meta name="robots" content="… noai …">` / `X-Robots-Tag: noai` | treated as a reservation (same effect) |

A reservation stops the full-text copy; it does not stop us from citing and
linking to your public feed items, which is what a feed is for. If you would
rather not be cited at all, use the removal request below.

## Removal requests

If you are a rights holder and object to how a source of yours is used, or to a
specific article, write to **trends@catandary.de** with:

1. the URL of our article (`https://catandary.de/trends/…`) and/or the URL of
   your original,
2. what you would like removed — a single article, or every use of your
   publication as a source,
3. a way to reach you back.

**We act within 72 hours** of receiving the request. What happens:

- The article is withdrawn (it disappears from the site with the next export
  and from the newsletter archive), and any stored full-text copy of your
  article is deleted.
- If you ask for your publication to be excluded as a source, we stop using it
  for article generation and delete stored full texts of it. Your feed items
  will no longer be turned into articles.
- Withdrawn articles are not offered through archive or cache links.
- We confirm by email what was done.

We do not require a formal notice for this. Where a request concerns personal
data rather than copyright, the same address applies and the procedure of our
privacy notice governs.

---

## Internal procedure (not for the public page)

Runbook for `trends@catandary.de` requests — everything below runs from the repo
root, dry run by default, `--apply` writes.

1. **Identify** the article(s) or the source:
   ```
   .venv/bin/python scripts/takedown.py --url https://publisher.example/story
   .venv/bin/python scripts/takedown.py --url https://catandary.de/trends/<slug>
   .venv/bin/python scripts/takedown.py --source "Publisher Name"      # or the feed host
   ```
   The dry run prints the affected trends / the source footprint (stored full
   texts, drafts, published) and changes nothing.
2. **Article takedown** — `--apply` sets `trends.status = 'rejected'`, stamps
   `reviewed_at` (a human decision; the dedup window then lets another outlet's
   coverage of the same story through) and NULLs `raw_entries.raw_content` of
   the underlying entry (`--keep-raw` to skip). A rejected trend is never
   rendered, exported or listed in the sitemap. It is **not** added to
   `dead_links` — that table drives the archive-link badge, which withdrawn
   content must not get.
3. **Source block** — `--apply` sets `sources.llm_pipeline = FALSE` (never again
   article material; distill signals unaffected). Add `--purge-raw` to delete
   every stored full text of the source, `--deactivate` to stop polling
   (`sources.active = FALSE`), `--reject-all` to reject its drafts/published
   trends. Then edit `sources.yaml`: `active: false` and/or remove
   `fulltext: true` — the poller and the fetcher read the yaml, not the DB flag.
4. **Re-export** the static site so the public feed drops the article, and
   regenerate the newsletter edition if the article was in the current one
   (`pipeline/newsletter_generator.py`, idempotent per week).
5. **Reply** to the requester within 72 hours; the record in
   `data/takedown_log.jsonl` (`--note "mail 2026-09-02 …"`) is the audit trail.
6. If the request is about a *pattern* (a publisher objects to full-text use
   but not to citation): drop `fulltext: true` for the source in `sources.yaml`
   and run `scripts/takedown.py --source … --purge-raw --apply` — no need to
   reject articles.
