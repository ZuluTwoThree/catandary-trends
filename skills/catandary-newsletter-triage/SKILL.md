---
name: catandary-newsletter-triage
description: |
  Triage the Catandary newsletter inbox end-to-end: classify each unread
  message into one of the 8 industry verticals, segment the message into
  individual story stubs that match the Catandary pipeline's `raw_entries`
  schema, write the stubs as a JSON drop-file the pipeline ingests, and
  move the original message into the matching IMAP folder. Use when the
  user asks to "process the newsletter inbox", "triage newsletters",
  "ingest newsletters", or "clean up the inbox".
tools_required:
  - himalaya (IMAP CLI, configured with the Hetzner mailbox)
  - filesystem write access to /home/dirk/projects/catandary-trends/data/email_inbox/
---

# Catandary Newsletter Triage

You are the inbox-triage stage for the Catandary trend-intelligence pipeline.
Original messages stay in IMAP folders as the permanent audit trail; the
pipeline only consumes the JSON drop-files you produce. You do **not** write
to the Catandary database directly — your only outputs are JSON files and
IMAP folder moves.

## Goal in one sentence

For every unread message in `INBOX`, decide *which vertical it belongs to*,
*break it into individual story stubs*, *write one JSON file*, and *move
the original mail* to the matching `INBOX/<VERTICAL>` folder (or
`INBOX/_Unmapped` / `INBOX/_Processed` per the rules below).

---

## Tools you have

- **`himalaya` CLI** for IMAP access. Default account, JSON output via `-o json`.
  - **Important:** Options (`-o json`, `--folder`) must come **before** the query string. No `--query` flag.
  - List unread: `himalaya envelope list -o json --folder INBOX "not flag seen"`
  - Read one: `himalaya message read <id> --folder INBOX -o json`
  - Move: `himalaya message move "INBOX/<target-folder>" <id> --folder INBOX` (target **before** id, use dot-notation `INBOX.FOOD`)
  - Create folder (idempotent): `himalaya folder add "INBOX.<folder-name>"`
- **Filesystem write** under `/home/dirk/projects/catandary-trends/data/email_inbox/` only.

---

## Folder layout

**Source folder (where new newsletters land):**
- `INBOX`

**Destination folders (create on first run if missing):**

| Folder | Use |
|---|---|
| `INBOX/FOOD` | Food & beverage, gastronomy, AgriTech, FoodTech |
| `INBOX/TECH` | Software, hardware, AI, robotics, IoT, devtools |
| `INBOX/HEALTH` | Medicine, pharma, biotech, mental health, longevity, supplements, fitness |
| `INBOX/ECO` | Energy, climate, circular economy, EV, packaging |
| `INBOX/DESIGN` | Product design, architecture, interiors, UX |
| `INBOX/FASHION` | Fashion, beauty, textiles, jewelry |
| `INBOX/BIZ` | Strategy, startups, retail, e-commerce, fintech |
| `INBOX/LIFESTYLE` | Culture, entertainment, gaming, creator economy, travel, sport, EdTech |
| `INBOX/REGULATORY` | Regulatory bodies (FDA, EFSA, EMA, BfR, USDA, EPA, …). The mail is *filed* here for audit; per-story `vertical_hint` still uses one of the 8 verticals above. |
| `INBOX/_Unmapped` | Confidence < 0.7 — needs human review |
| `INBOX/_Processed` | Non-content mail (account confirmation, password reset, sponsorship-only, calendar invite) |

First-time bootstrap (run once before the first triage):

```bash
for f in FOOD TECH HEALTH ECO DESIGN FASHION BIZ LIFESTYLE REGULATORY _Unmapped _Processed; do
  himalaya folder add "INBOX.$f" 2>/dev/null || true
done
```

---

## Procedure (per unread message)

### 1. Fetch

```bash
himalaya envelope list -o json --folder INBOX "not flag seen"
# for each <id> returned:
himalaya message read <id> --folder INBOX -o json
```

The JSON you get includes: `id`, `from`, `subject`, `date`, `message_id`,
`text`, `html`. Use the `text` body when available; fall back to stripped
`html` otherwise.

### 2. Classify the message-level vertical

Inputs: sender domain, subject line, first ~500 chars of the body.

- Map to exactly one of `FOOD, TECH, HEALTH, ECO, DESIGN, FASHION, BIZ, LIFESTYLE`.
|- If the newsletter is from a regulatory body and the content is policy/compliance heavy → message-level vertical is the **dominant subject domain** (FDA-food-policy → FOOD; EMA-drug-approvals → HEALTH), and the message is filed in `INBOX/REGULATORY` *for audit* — but per-story `vertical_hint` still uses one of the 8 verticals.
|- Confidence < 0.7 → move to `INBOX/_Unmapped`, **skip extraction**, continue to next message.

### 3. Detect newsletter format

Pick one — this controls how aggressively you segment:

| Format | Signal | Output |
|---|---|---|
| `single` | One long article, one main topic, body > 1500 chars without clear story-separators | exactly **1** story stub |
| `digest` | Multiple curated stories with headlines + summaries (Axios, Morning Brew, FoodNavigator daily, Endpoints) | **N** story stubs (typically 5–20) |
| `roundup` | Pure link-list with one-line teasers ("This week in AI", CB Insights link blocks) | **N** story stubs (typically 10–30, mostly excerpt-only) |

### 4. Extract story stubs

Each stub must be valid JSON matching this exact schema:

```json
{
  "source_url": "string (required, canonical article URL, no tracker wrappers)",
  "title": "string (required, 5–150 chars)",
  "excerpt": "string (required, 20–400 chars, 1–3 sentences)",
  "raw_content": "string or null (full text if embedded in the mail)",
  "published_date": "ISO-8601 UTC string or null",
  "newsletter_sender": "string (required, lowercase email of From: header)",
  "newsletter_message_id": "string (required, the IMAP Message-Id including angle brackets)",
  "vertical_hint": "one of FOOD|TECH|HEALTH|ECO|DESIGN|FASHION|BIZ|LIFESTYLE (required)"
}
```

**Rules for each field:**

- **`source_url`** — must be the canonical article URL. Strip tracking wrappers (`email.mg.<host>/c/…`, `link.mail.<host>/click?u=…&id=…`, `t.co/…` shorteners visible in the HTML). When the only available form is the wrapped URL, prefer the unwrapped URL visible in the link-text or `data-href` attribute. Never write `unsubscribe`, `preferences`, `view-in-browser`, or pixel-tracker URLs.
- **`title`** — original capitalization. Strip trailing whitespace. Drop trailing site-name suffixes like " | FoodNavigator" or " — TechCrunch".
- **`excerpt`** — 1 to 3 sentences. Use the newsletter's own teaser if present; otherwise condense from the linked article preview in the body. Never echo the title verbatim.
- **`raw_content`** — full body of the story if the mail embeds it (common in `single`); `null` for `digest` and `roundup` where the mail only has headlines + teasers.
- **`published_date`** — ISO-8601 with `Z` suffix. Use the per-story date if the newsletter shows one; otherwise use the mail's `Date:` header. `null` if neither is available.
- **`newsletter_sender`** — lowercase email address from the `From:` header (strip display name).
- **`newsletter_message_id`** — exact `Message-Id` header value including the `<...>` brackets.
- **`vertical_hint`** — the per-story vertical, **may differ from the message-level vertical**. A HEALTH newsletter may surface a FOOD-policy story → that one stub gets `vertical_hint: "FOOD"`. Picking the right vertical per story is one of your most valuable judgments.

### 5. Skip stubs that are not usable

Drop a stub (do **not** include it in the output) when:

- `source_url` is missing, empty, or only points to `unsubscribe` / `preferences` / `view-in-browser`.
- `title` is pure boilerplate: "This week's newsletter", "Sponsored by …", "Forwarded to you by …", "A message from our partner".
- `excerpt` would be under 20 characters and there is no `raw_content`.
- Duplicate of another stub in the same message (same `source_url` after normalization).

If after filtering **zero stubs remain**, still move the mail to its vertical folder, but write **no** JSON file. Log `"stories": 0, "action": "moved-empty"`.

### 6. Write the drop-file

One JSON file per message, in `/home/dirk/projects/catandary-trends/data/email_inbox/`.

Filename pattern: `<safe-message-id>.json` where `<safe-message-id>` is the `Message-Id` with the characters `< > / \ @ : ? * "` each replaced by `_`. Strip any leading/trailing underscores.

Example: `<CABx7...@mail.gmail.com>` → `CABx7..._mail.gmail.com.json`

If the file already exists → **do not overwrite**. Assume a prior run already produced it; skip writing, but still move the mail to its vertical folder (idempotent re-processing).

**File content:**

```json
{
  "schema_version": "1",
  "message_id": "<original-message-id>",
  "sender": "newsletter@foodnavigator.com",
  "received_at": "2026-06-07T08:30:00Z",
  "format": "digest",
  "message_vertical": "FOOD",
  "filed_folder": "INBOX/FOOD",
  "first_seen_sender": false,
  "stories": [
    { /* StoryStub */ },
    { /* StoryStub */ }
  ]
}
```

- `received_at` = the IMAP `Date:` header in UTC.
- `format` = `single` | `digest` | `roundup`.
- `message_vertical` = your message-level classification.
- `filed_folder` = the actual IMAP folder the mail is moved to.
- `first_seen_sender` = `true` if this sender has not appeared in any previous run (check by scanning the existing `*.json` files in the drop folder for matching `sender`). The pipeline uses this to auto-create a `sources` row.

Write atomically: write to `<filename>.tmp`, then `rename` to `<filename>`. The pipeline polls this folder and will not pick up `.tmp` files.

### 7. Move the original mail

```bash
himalaya message move "INBOX/<TARGET>" <id> --folder INBOX
```

Target folder selection:

| Situation | Target |
|---|---|
| Classified successfully, confidence ≥ 0.7, content mail | `INBOX/<message_vertical>` (or `INBOX/REGULATORY` if it's a regulatory body) |
| Classification confidence < 0.7 | `INBOX/_Unmapped` |
| Non-content mail (account confirmation, password reset, sponsorship-only, calendar invite, double-opt-in) | `INBOX/_Processed` — write **no** JSON file |
| Spam-like mail that slipped through | `INBOX/_Processed` |

**Never delete mails.** Movement only. The IMAP archive is the audit trail.

### 8. Log one line per message

Emit a single JSON line to stdout for each message — easy for the user to grep / pipe through `jq`:

```json
{"msg_id":"<...>","sender":"newsletter@example.com","vertical":"FOOD","format":"digest","stories":12,"first_seen_sender":false,"action":"moved","target":"INBOX/FOOD"}
```

Actions are: `moved`, `moved-empty`, `unmapped`, `discarded`, `skipped-duplicate-file`, `skipped-error`.

---

## Vertical reference (one-line guidance each)

- **FOOD** — anything you eat or drink, the supply chain behind it, the regulatory layer around it, the science of ingredients, gastronomy, agriculture.
- **TECH** — software, hardware, semiconductors, AI/ML, robotics, IoT, devtools, quantum, cybersecurity, tech startups & VC.
- **HEALTH** — clinical medicine, pharma, biotech, digital health, mental health, supplements, longevity, healthcare IT, fitness physiology.
- **ECO** — climate science, renewables, EV/mobility, circular economy, packaging sustainability, carbon, ESG, climate-tech startups.
- **DESIGN** — product/industrial design, architecture, interiors, urban planning, UX/UI, materials.
- **FASHION** — apparel (luxury → mass), beauty, cosmetics, textiles, jewelry, clean beauty, biotech materials, fashion retail.
- **BIZ** — corporate strategy, startups & VC (non-tech), e-commerce, DTC, fintech, banking, payments, retail business, marketing, leadership.
- **LIFESTYLE** — culture, entertainment, streaming, gaming, social/creator economy, art, EdTech, inclusion, luxury experiential, travel/hospitality, sport.

When a story sits across two verticals (e.g., a fitness-tech wearable), pick the **primary lens**: if the story is about the product/business → BIZ or TECH; if about the health outcome → HEALTH. Consistency matters more than perfection — the pipeline will reclassify in Stage 8 anyway.

---

## Special cases

- **First-time-seen sender** — set `first_seen_sender: true` in the JSON drop. This signals the pipeline to create a new `sources` row.
- **Cross-vertical digest** (e.g., McKinsey weekly with TECH + BIZ + HEALTH stories) — message-level `vertical` = **dominant theme** of the issue, per-story `vertical_hint` = each story's actual vertical. Mail moves to the dominant-theme folder.
|- **Pure regulatory mail** (FDA Constituent Update, EFSA scientific opinion, EMA news) — mail filed in `INBOX/REGULATORY`; per-story `vertical_hint` still one of the 8 verticals based on the regulated domain.
- **Multi-part forward** ("FW: Here's this week's …") — process the forwarded body as if it were the original. Skip the forwarding chrome.
- **Image-only newsletter** (no text body, only embedded images) — move to `_Unmapped` with `action: "unmapped", reason: "image-only"`. Do not attempt OCR.

---

## Error handling

- **IMAP timeout / fetch failure** → log `{"msg_id":"<...>","action":"skipped-error","reason":"<...>"}` and continue. Do **not** move the mail. Next run retries it.
- **Disk full / write permission denied** → abort the entire run after the current message. Do not move any further mails. Emit `{"run":"aborted","reason":"<...>"}`.
- **One story fails to extract inside a digest** → drop that story, keep the others. Add `"stories_dropped": <n>` to the message log line.
- **Unparseable date / charset issues** → set `published_date: null` and continue.
- **Hard failure during extraction of a single message** → log `action: "skipped-error"`, leave the mail untouched. Don't let one bad mail abort the run.

---

## Boundaries — things you must never do

- **Never** move or modify mails outside `INBOX` or the `INBOX/*` tree.
- **Never** delete mails. Movement only.
- **Never** write outside `/home/dirk/projects/catandary-trends/data/email_inbox/`.
- **Never** call the Catandary database, Python scripts, or pipeline directly.
- **Never** overwrite an existing drop-file. Skip if it exists.
- **Never** mark mails as read by any path other than the move-out-of-INBOX (the move implicitly removes them from the "unread in INBOX" set).
- **Never** invent URLs. If a story has no extractable `source_url`, drop the stub.

---

## Termination

Loop until `himalaya envelope list -o json --folder INBOX "not flag seen"` returns an empty array.

Emit a final summary line:

```json
{"run":"complete","messages_processed":N,"stubs_written":M,"unmapped":K,"discarded":J,"errors":E}
```

Where:
- `messages_processed` = total mails handled (any action)
- `stubs_written` = sum of stories across all drop-files written
- `unmapped` = mails moved to `_Unmapped`
- `discarded` = mails moved to `_Processed` (non-content)
- `errors` = mails skipped due to errors
