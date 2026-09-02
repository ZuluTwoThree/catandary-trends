# Hosting the landing on Hetzner

`preview.html` is the **versioned copy of the live landing** on `https://catandary.de/`
(state 2026-09-01, uploaded 17:47 CEST). It is one self-contained HTML document — no build,
no database; CSS, JS, font stack, grain texture and inline SVGs are embedded. It references
three sibling files that live next to it in the webroot and in this folder:

| File | Purpose |
|---|---|
| `preview.html` | the page — upload **renamed to `index.html`** |
| `mark.svg` | icon (`<link rel="icon" type="image/svg+xml" href="/mark.svg">`) |
| `favicon.ico` | fallback icon, 16×16 + 32×32 (`<link rel="alternate icon">`) |
| `robots.txt` | allow-all; the page itself still carries `<meta name="robots" content="noindex">` |

The newsletter form posts to `/newsletter/subscribe.php` (double opt-in backend on the same
webspace) — see `newsletter-doi-php/EINBAU.md` for that package and the upload order
(`newsletter/` first, then the four files above).

> **Provenance:** the version that went live on 2026-07-27 (DOI form with consent, legal
> modal for Impressum/Datenschutz, OG meta tags, icon links) was never committed — the repo
> only held the 2026-07-22 base plus the 2026-08-25 edits (`6df0581`: countdown 01.10.,
> radar promise withdrawn). On 2026-09-01 the two were merged (live HTML + exactly those
> five edits) and uploaded; that merged file is this `preview.html`.
>
> `site_preview.html` is the **stale** 2026-08-25 fragment used only for an early Claude
> artifact preview — it has no DOI form, no legal modal, no `<head>`. Don't upload it and
> **don't regenerate `preview.html` from it** (the old regenerate snippet would silently drop
> the form and the modal). Edit `preview.html` directly.

## Option A — Hetzner Webhosting (shared webspace) — what is in use
1. Connect to the webspace with SFTP (host, user & password in the Hetzner *konsoleH* panel).
2. Upload `preview.html` as `index.html` into the document root, plus `mark.svg`,
   `favicon.ico`, `robots.txt` alongside.
3. Verify: `curl -sI https://catandary.de/ | grep -i last-modified` and
   `curl -s https://catandary.de/ | grep -o '2026-10-01T09:00:00+02:00'`.

```bash
# from docs/launch
sftp user@your-space.your-server.de
cd public_html
put preview.html index.html
put mark.svg
put favicon.ico
put robots.txt
```

## Option B — VPS with Caddy — **dropped (owner decision 2026-09-02)**
The VPS path (`HOSTING_PUBLIC_VPS.md`) was never ordered and is off the table. The public
site will be a **static export** of the Next.js app uploaded to the same webspace as this
landing (design: `docs/audits/2026-09-02_static_export_design.md`, plan:
`docs/launch/09_launch_plan_2026-09-02.md`). Until the export ships, this static file stays
the whole public site; once it ships, `/` may be replaced by the exported landing route.

## Notes
- **Countdown:** targets `2026-10-01T09:00:00+02:00` (09:00 CEST), computed against the
  visitor's clock as an absolute instant. At zero it flips to "We are live" — which is why
  the file must be re-uploaded *before* the date if the launch moves again (on 2026-09-01 the
  old 01.09. target expired on the live site while the repo already said 01.10.). To change
  the date, edit **both** the `<span class="cd-date">` text and the
  `new Date("2026-10-01T09:00:00+02:00")` line in `preview.html`.
- **Still in the page and still open (#93):** the €99/499/799 tier table and the
  "Explore the live engine" CTA reflect the withdrawn SaaS model — the "analyses instead of
  platform" rewrite is the owner's voice and not done yet.
- **Before the real public launch:** remove the `noindex` meta and upload the static export
  next to it (no DNS change — same webspace; `HOSTING_PUBLIC_VPS.md` is archived).
