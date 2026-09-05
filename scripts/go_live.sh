#!/usr/bin/env bash
# Launch-Schalter fuer den 01.10.2026 — EIN Kommando, alles nachpruefbar.
#
# Legt um, was den oeffentlichen Auftritt bisher unsichtbar haelt:
#   1. PUBLIC_NOINDEX=0 in ~/.config/catandary/webspace.env  (Export-Build)
#   2. Export neu bauen + hochladen (robots.txt erlaubt dann, meta noindex faellt weg)
#   3. Landing: <meta name="robots" content="noindex"> entfernen und hochladen
#      (docs/launch/preview.html — der Countdown laeuft an dem Morgen ohnehin ab
#       und schaltet die Feed-Links per JS frei)
#   4. Verifikation: robots.txt, Landing, Feed, Sitemap, Bot-Sperre, TDM-Header
#
# Vorher pruefen (Owner): Postfach contact@catandary.de erreichbar, Rechtsfrage
# aus Issue #99 (EU-AI-Act-Kennzeichnung) entschieden, erste Analyse veroeffentlicht.
#
#   scripts/go_live.sh --dry-run     # zeigt nur, was passieren wuerde (Default)
#   scripts/go_live.sh --apply
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$HOME/.config/catandary/webspace.env"
LANDING="$REPO/docs/launch/preview.html"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say() { printf '%s\n' "$*"; }
say "=== Launch-Schalter $(date -Iseconds) ==="
[ -f "$CFG" ] || { say "ABBRUCH: $CFG fehlt"; exit 2; }
grep -q '^PUBLIC_NOINDEX=1' "$CFG" && say "1. webspace.env: PUBLIC_NOINDEX 1 -> 0" || say "1. webspace.env: PUBLIC_NOINDEX bereits nicht 1 (uebersprungen)"
grep -q '<meta name="robots" content="noindex">' "$LANDING" && say "3. Landing: noindex-Meta entfernen" || say "3. Landing: kein noindex-Meta gefunden (uebersprungen)"
if [ "$APPLY" = 0 ]; then
  say ""
  say "Trockenlauf — nichts geaendert. Mit --apply ausfuehren."
  exit 0
fi

sed -i 's/^PUBLIC_NOINDEX=1/PUBLIC_NOINDEX=0/' "$CFG"
python3 - "$LANDING" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
s2 = re.sub(r'\s*<meta name="robots" content="noindex">', "", s)
p.write_text(s2, encoding="utf-8")
print("Landing: noindex entfernt" if s2 != s else "Landing: unveraendert")
PY
say "2. Export bauen und hochladen ..."
"$REPO/scripts/build_public_static.sh"
"$REPO/.venv/bin/python" "$REPO/scripts/publish_static_site.py" --apply
say "3. Landing hochladen ..."
CT_REPO="$REPO" "$REPO/.venv/bin/python" - <<'PY'
import os, pathlib, paramiko
cfg = {}
for line in open(os.path.expanduser("~/.config/catandary/webspace.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); cfg[k.strip()] = v.strip().strip("'\"").split("   #")[0].strip()
t = paramiko.Transport((cfg["HOST"], int(cfg.get("PORT", 22)))); t.connect(username=cfg["USER"], password=cfg["PASSWORD"])
s = paramiko.SFTPClient.from_transport(t); root = cfg["REMOTE_ROOT"]
body = pathlib.Path(os.environ["CT_REPO"], "docs/launch/preview.html").read_bytes()
with s.open(root + "/index.html.tmp", "wb") as f: f.write(body)
try: s.posix_rename(root + "/index.html.tmp", root + "/index.html")
except Exception:
    s.remove(root + "/index.html"); s.rename(root + "/index.html.tmp", root + "/index.html")
print("index.html:", s.stat(root + "/index.html").st_size, "B")
s.close(); t.close()
PY
say ""
say "4. Verifikation"
for u in / /trends /trends/methodology; do
  printf '  %s https://catandary.de%s\n' "$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "https://catandary.de$u")" "$u"
done
printf '  robots.txt: %s\n' "$(curl -s --max-time 25 https://catandary.de/robots.txt | grep -c 'Disallow: /$' || true) Disallow-Zeilen (0 = frei)"
printf '  Landing noindex: %s (0 = weg)\n' "$(curl -s --max-time 25 https://catandary.de/ | grep -c 'content="noindex"' || true)"
printf '  Feed noindex: %s (0 = weg)\n' "$(curl -s --max-time 25 https://catandary.de/trends | grep -c 'content="noindex' || true)"
printf '  GPTBot: %s (403 erwartet) · Googlebot: %s (200 erwartet)\n' \
  "$(curl -s -o /dev/null -w '%{http_code}' -A GPTBot/1.0 --max-time 25 https://catandary.de/trends)" \
  "$(curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0 (compatible; Googlebot/2.1)' --max-time 25 https://catandary.de/trends)"
printf '  TDM-Header: %s\n' "$(curl -sI --max-time 25 https://catandary.de/trends | grep -ci 'tdm-reservation' || true)"
say ""
say "Fertig. Sitemap bei Google/Bing einreichen: https://catandary.de/trends/sitemap.xml"
