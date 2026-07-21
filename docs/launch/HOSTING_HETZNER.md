# Hosting the preview on Hetzner

`preview.html` is a **complete, fully self-contained** HTML document — one file, no build,
no server, no database, no external requests (all CSS, JS, fonts-stack, the grain texture,
the favicon and every SVG are inline). It works by double-clicking it locally (`file://`)
and on any static host. It is marked `noindex` so it won't be picked up by search engines
while it's a preview.

> Use **`preview.html`** for hosting (the standalone document).
> `site_preview.html` is the fragment used for the Claude artifact preview only — don't
> upload that one; it has no `<head>`/charset/viewport.

## Option A — Hetzner Webhosting (shared webspace) — simplest
1. Connect to your webspace with SFTP/FTP (host, user & password are in the Hetzner
   *konsoleH* panel; use FileZilla or `sftp`).
2. Upload `preview.html` into your document root (usually `public_html/`, `htdocs/`, or the
   folder mapped to your domain).
3. Open it:
   - as a sub-page: `https://your-domain.de/preview.html`
   - at the domain root: rename it to `index.html` before uploading (or alongside, so `/`
     serves it).
   `.html` is served as `text/html` automatically — nothing else to configure.

```bash
# from the folder that contains preview.html
sftp user@your-space.your-server.de
# then, in the sftp prompt:
cd public_html
put preview.html
```

## Option B — Hetzner VPS / Cloud with Caddy (you already run Caddy)
Drop the file into a served directory and point Caddy at it:
```
preview.catandary.de {
    root * /var/www/catandary-preview
    file_server
}
```
Put `preview.html` there as `index.html` (`/var/www/catandary-preview/index.html`), reload
Caddy — automatic HTTPS is handled for the named domain.

## Notes
- **Updating it:** re-run the generator to regenerate `preview.html` after any change to
  `site_preview.html`:
  ```bash
  cd docs/launch && python3 - <<'PY'
  src=open("site_preview.html",encoding="utf-8").read(); m="</style>"; i=src.find(m)
  head=src[:i+len(m)]; body=src[i+len(m):].lstrip("\n")
  open("preview.html","w",encoding="utf-8").write(
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<meta name="robots" content="noindex">\n'+head+'\n</head>\n<body>\n'+body+'\n</body>\n</html>\n')
  print("regenerated preview.html")
  PY
  ```
- **Countdown:** targets `2026-09-01T09:00:00+02:00` (09:00 CEST). It's computed against the
  visitor's clock as an absolute instant, so it's correct in any timezone. At zero it flips
  to "We are live". To change the date, edit the `new Date("2026-09-01T09:00:00+02:00")`
  line in `site_preview.html` and regenerate.
- **Before a real public launch,** remove the `noindex` meta and swap the preview form/links
  for the live production site (the Next.js `/` route), or point the domain at the app.
