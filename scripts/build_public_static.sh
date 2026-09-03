#!/usr/bin/env bash
# Static export of the public website (design Schritt 1 —
# docs/audits/2026-09-02_static_export_design.md; hosting notes in
# docs/launch/HOSTING_HETZNER.md).
#
#   scripts/build_public_static.sh [OUT_DIR]
#
# Builds the Next.js app with `output: "export"` (STATIC_EXPORT=1) in a
# STAGING COPY of frontend/ — never in the source tree — from which every
# path in frontend/static-export.exclude has been removed (the public-mode
# block list, Proxy, the API routes, the non-exportable pages). The result
# lands in OUT_DIR (default frontend/.export/out), with two sibling files:
#
#   <OUT_DIR>.manifest.tsv     sha256  size  path   for every file (sorted;
#                              the basis of the incremental upload, Schritt 8)
#   <OUT_DIR>.build_info.json  when / which commit / how many articles ...
#
# The export also carries trends/index.json — the client-side search index
# (Schritt 5 / D, lib/staticSearch.ts); it is verified below and its size
# lands in build_info.json.
#
# Env (all optional):
#   PUBLIC_WINDOW_DAYS  article window in days (default 30; lib/archiveWindow.ts)
#   PUBLIC_NOINDEX      1 = robots.txt disallow-all + <meta robots noindex>
#                       (default 1 until the 2026-10-01 launch)
#   PUBLIC_SITE_URL     canonical base (default https://catandary.de)
#   KEEP_STAGING        1 = leave frontend/.export/site in place after the build
#
# Two consecutive runs must produce byte-identical OUT_DIRs (constant build
# id, data-derived dates, day-boundary window) — `diff -rq` is the gate.
# The workstation build (`npm run build`, no flag) is untouched by this.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/frontend"
EXPORT_DIR="$FRONTEND/.export"
SITE="$EXPORT_DIR/site"
OUT="${1:-$EXPORT_DIR/out}"
OUT="$(mkdir -p "$(dirname "$OUT")" && cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
MANIFEST="${OUT}.manifest.tsv"
BUILD_INFO="${OUT}.build_info.json"
EXCLUDE_FILE="$FRONTEND/static-export.exclude"
HTACCESS_DIR="$FRONTEND/public-export"

WINDOW="${PUBLIC_WINDOW_DAYS:-30}"
NOINDEX="${PUBLIC_NOINDEX:-1}"
SITE_URL="${PUBLIC_SITE_URL:-https://catandary.de}"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { log "FATAL: $*" >&2; exit 1; }

T0=$(date +%s)
[ -f "$EXCLUDE_FILE" ] || die "missing $EXCLUDE_FILE"
[ -f "$HTACCESS_DIR/trends/.htaccess" ] || die "missing $HTACCESS_DIR/trends/.htaccess"
[ -f "$HTACCESS_DIR/_next/.htaccess" ] || die "missing $HTACCESS_DIR/_next/.htaccess"
[ -d "$FRONTEND/node_modules" ] || die "frontend/node_modules missing — run npm ci first"
command -v rsync >/dev/null || die "rsync not installed"

mkdir -p "$EXPORT_DIR"
# One export at a time (cron + a manual run must not race on the staging tree).
exec 9>"$EXPORT_DIR/.lock"
flock -n 9 || die "another export is running (lock $EXPORT_DIR/.lock)"

log "export: window=${WINDOW}d noindex=${NOINDEX} site=${SITE_URL} out=${OUT}"

# --- 1. staging tree -------------------------------------------------------
log "staging tree -> $SITE"
mkdir -p "$SITE"
rsync -a --delete --delete-excluded --exclude-from="$EXCLUDE_FILE" "$FRONTEND/" "$SITE/"
# Turbopack refuses a symlink that leaves its root; next.config lifts the root
# to $FRONTEND (STATIC_EXPORT_ROOT) so this link resolves inside it.
ln -sfn ../../node_modules "$SITE/node_modules"
# lib/db.ts reads <cwd>/../mega_trends.yaml, scripts/generate-mega-trends.mjs
# reads scripts/../../mega_trends.yaml — both = $EXPORT_DIR/mega_trends.yaml.
ln -sfn ../../mega_trends.yaml "$EXPORT_DIR/mega_trends.yaml"
[ -f "$EXPORT_DIR/mega_trends.yaml" ] || die "mega_trends.yaml symlink is broken"

# Sanity: nothing from the exclusion list may have survived the copy.
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  case "$line" in src/*) [ ! -e "$SITE/$line" ] || die "excluded path still present: $line" ;; esac
done < "$EXCLUDE_FILE"

# /analysis/[slug]: Next treats an EMPTY generateStaticParams() as missing and
# aborts the export. No published analysis yet -> drop the route for this build.
PUBLISHED_ANALYSES=$(cd "$SITE" && node -e '
const fs=require("fs"),p=require("path"),y=require("js-yaml");
const d="content/analyses"; let n=0;
if (fs.existsSync(d)) for (const f of fs.readdirSync(d)) {
  if (!f.endsWith(".md")) continue;
  const m=/^---\r?\n([\s\S]*?)\r?\n---/.exec(fs.readFileSync(p.join(d,f),"utf8"));
  if (!m) continue;
  const fm=y.load(m[1])||{};
  if (fm.draft!==true) n++;
}
console.log(n)')
if [ "$PUBLISHED_ANALYSES" = "0" ]; then
  log "no published analysis — excluding src/app/analysis/[slug] from this export"
  rm -rf "$SITE/src/app/analysis/[slug]"
else
  log "published analyses: $PUBLISHED_ANALYSES"
fi

# Always start clean: a stale out/ in the tree would be scanned by Tailwind
# (spike: CSS hash drifted). NB: with output:"export" Next treats a custom
# distDir as the EXPORT directory (export/utils.js hasCustomExportOutput), so
# NEXT_DIST_DIR stays unset here — build in .next, export to out/, both inside
# the staging copy (no clash with the source tree's .next of the dev server).
rm -rf "$SITE/out" "$SITE/.next"

# --- 2. build --------------------------------------------------------------
log "next build (output: export) ..."
T1=$(date +%s)
(
  cd "$SITE"
  STATIC_EXPORT=1 \
  STATIC_EXPORT_ROOT="$FRONTEND" \
  PUBLIC_MODE=1 \
  PUBLIC_WINDOW_DAYS="$WINDOW" \
  PUBLIC_NOINDEX="$NOINDEX" \
  PUBLIC_SITE_URL="$SITE_URL" \
  NEXT_DIST_DIR= \
  NEXT_TELEMETRY_DISABLED=1 \
  npm run build --silent
)
T2=$(date +%s)
log "next build done in $((T2 - T1))s"
[ -d "$SITE/out" ] || die "build produced no out/ directory"

# --- 2b. drop the per-segment prefetch payloads ----------------------------
# Next 16 writes, next to every page's .html and .txt, a directory of seven
# `__next.*.txt` segment-prefetch files (client segment cache). There is no
# switch for it in 16.2 (collectSegmentData runs unconditionally in
# app-render.js; no `clientSegmentCache` key in config-shared.js) and they
# were 78 % of the files (106k of 137k) and ~35 % of the bytes. They are
# removed here: the router's fallback for a missing segment payload is the
# page's `.txt` RSC payload (client/components/segment-cache/navigation.js:
# a rejected route entry -> navigateToUnknownRoute -> fetchServerResponse,
# which appends `.txt` in output:"export" mode) — client-side navigation
# stays intact, verified headless (Playwright/Chromium against Apache 2.4,
# 2026-09-02). Every public <Link> carries prefetch={linkPrefetch()} so the
# export does not even request them; trends/.htaccess answers stragglers
# with a bodyless 204.
SEG_BEFORE=$(find "$SITE/out" -type f -name '__next.*.txt' | wc -l)
find "$SITE/out" -type f -name '__next.*.txt' -delete
find "$SITE/out" -depth -type d -empty -delete
SEG_AFTER=$(find "$SITE/out" -type f -name '__next.*.txt' | wc -l)
[ "$SEG_AFTER" = "0" ] || die "segment payloads survived the sweep: $SEG_AFTER"
log "segment prefetch payloads removed: $SEG_BEFORE"

# --- 2c. the webroot stays the owner's --------------------------------------
# index.html (the landing), robots.txt, mark.svg, favicon.ico and newsletter/
# in the webroot are owner-managed; the publisher never uploads them. The
# Next landing still renders (it is the future "/" once its copy is done,
# #93 Etappe 4) but is set aside under a name nothing can mistake for the
# live landing; its RSC payload goes — a client navigation to "/" then does
# a full load of whatever the webroot serves. The export's robots.txt stays
# in place for inspection; the owner's copy only needs the Sitemap: line
# (see public-export/trends/.htaccess, ROOT SNIPPET).
RAW="$SITE/out"
[ -f "$RAW/index.html" ] || die "index.html (Next landing) missing"
mv "$RAW/index.html" "$RAW/_landing_preview.html"
rm -f "$RAW/index.txt"

# --- 2d. feed page 1 also lives under trends/ -------------------------------
# Next writes /trends as the ROOT files trends.html + trends.txt (the trends/
# tree is their sibling). The publisher manages trends/** and _next/** plus
# exactly these two root files (ROOT_ALLOWLIST in publish_static_site.py).
# trends/index.html is the copy Apache serves for /trends (rule 1 in
# public-export/trends/.htaccess) — page 1 then works from inside the managed
# tree, with the trends/ headers, independent of the root upload. trends.txt
# stays at the root: the router fetches /trends.txt on a client navigation
# to /trends.
[ -f "$RAW/trends.html" ] || die "trends.html missing"
cp "$RAW/trends.html" "$RAW/trends/index.html"

# Machine-readable TDM reservation for the whole site (TDMRep, W3C CG;
# §44b Abs. 3 UrhG) — owner decision 2026-09-03. Served from the webroot via
# ROOT_ALLOWLIST in publish_static_site.py; the matching header + meta tags
# come from trends/.htaccess, _next/.htaccess and layout.tsx.
mkdir -p "$RAW/.well-known"
cat > "$RAW/.well-known/tdmrep.json" <<'JSON'
[
  {
    "location": "/*",
    "tdm-reservation": 1,
    "tdm-policy": "https://catandary.de/trends/tdm-policy"
  }
]
JSON

# --- 3. verify -------------------------------------------------------------
[ -f "$RAW/404.html" ] || die "404.html missing"
[ -f "$RAW/trends.txt" ] || die "trends.txt (RSC payload of /trends) missing"
[ -f "$RAW/trends/index.html" ] || die "trends/index.html missing"
[ -f "$RAW/trends/expired.html" ] || die "trends/expired.html missing"
[ -f "$RAW/trends/sitemap.xml" ] || die "trends/sitemap.xml missing"
[ -f "$RAW/robots.txt" ] || die "robots.txt missing"
[ ! -e "$RAW/index.html" ] || die "index.html must not exist in the export (owner-managed webroot)"
[ ! -e "$RAW/sitemap.xml" ] || die "sitemap.xml must live under trends/ (owner-managed webroot)"

ARTICLES=$(find "$RAW/trends" -maxdepth 1 -type f -name '*.html' | grep -Ec -- '-[0-9]+\.html$' || true)
MEGA=$(find "$RAW/trends/mega" -maxdepth 1 -type f -name '*.html' 2>/dev/null | wc -l)
[ "$ARTICLES" -gt 0 ] || die "no article pages in the export (DB unreachable?)"
log "articles: $ARTICLES  mega pages: $MEGA"

# Briefing archive (Schritt E): /trends/newsletter (signup + latest + archive
# list), one page per archived edition (trends/newsletter/<year>-w<week>.html,
# PUBLIC_NEWSLETTER_EDITIONS of them — lib/archiveWindow.ts) and the static
# unsubscribe confirmation that unsubscribe.php redirects to. NB: an EMPTY
# newsletter_editions table would abort the build (Next refuses an empty
# generateStaticParams list, like /analysis/[slug] above) — the Monday cron
# keeps the table filled; there is no automatic fallback.
[ -f "$RAW/trends/newsletter.html" ] || die "trends/newsletter.html missing"
[ -f "$RAW/trends/newsletter/unsubscribed.html" ] || die "trends/newsletter/unsubscribed.html missing"
EDITIONS=$(find "$RAW/trends/newsletter" -maxdepth 1 -type f -name '[0-9][0-9][0-9][0-9]-w[0-9][0-9].html' | wc -l)
[ "$EDITIONS" -gt 0 ] || die "no briefing edition pages in the export (newsletter_editions empty?)"
log "briefing editions: $EDITIONS"

# Search index (Schritt 5 / D): trends/index.json — app/trends/index.json/
# route.ts, one JSON object per line (lib/staticSearch.ts serializeIndex),
# fetched by the client-side search. Must be valid JSON with as many lines
# as entries; the entry count should equal the article pages (both come
# from the same window predicate — they only drift when something publishes
# DURING the build, i.e. the 04:00 cycle; that is a warning, not a failure).
INDEX_FILE="$RAW/trends/index.json"
[ -f "$INDEX_FILE" ] || die "trends/index.json (search index) missing"
INDEX_STATS=$(python3 - "$INDEX_FILE" <<'PY'
import gzip, json, sys
raw = open(sys.argv[1], "rb").read()
data = json.loads(raw)
if not isinstance(data, list):
    raise SystemExit("index.json is not a JSON array")
print(len(data), raw.count(b"\n"), len(raw), len(gzip.compress(raw, 6)))
PY
) || die "trends/index.json is not valid JSON"
read -r INDEX_ENTRIES INDEX_LINES INDEX_BYTES INDEX_GZ <<< "$INDEX_STATS"
[ "$INDEX_LINES" = "$INDEX_ENTRIES" ] || die "index.json: $INDEX_LINES lines for $INDEX_ENTRIES entries (one entry per line expected)"
if [ "$INDEX_ENTRIES" != "$ARTICLES" ]; then
  log "WARN: search index has $INDEX_ENTRIES entries but the export has $ARTICLES article pages (a publish during the build?)"
fi
log "search index: $INDEX_ENTRIES entries, $((INDEX_BYTES / 1024)) KB raw, $((INDEX_GZ / 1024)) KB gzip"

# Hard gate: nothing unpublished may leak into the payloads.
# (grep exits 1 on "no match" — under pipefail that must not abort the run)
DRAFTS=$( (grep -rl --include='*.html' --include='*.txt' -F '"status":"draft"' "$RAW" || true) | wc -l)
[ "$DRAFTS" = "0" ] || die "$DRAFTS files carry a draft status in their payload"

# Informational: the known leftover is the landing copy's Foresight links
# (owner-instance copy; the export's root index.html is not uploaded).
# /trends/pricing and /account no longer exist in the tree (#93, 2026-09-03).
for needle in 'localhost' '/api/' '/trends/foresight'; do
  n=$( (grep -rl --include='*.html' -F -- "$needle" "$RAW" || true) | wc -l)
  log "html files containing '$needle': $n"
done

# --- 4. .htaccess (per directory, never the webroot) + publish to OUT --------
cp -a "$HTACCESS_DIR/." "$RAW/"
[ -f "$RAW/trends/.htaccess" ] || die "trends/.htaccess not in place"
[ -f "$RAW/_next/.htaccess" ] || die "_next/.htaccess not in place"
[ ! -e "$RAW/.htaccess" ] || die "a webroot .htaccess must not be part of the export"
rm -rf "$OUT"
mv "$RAW" "$OUT"
log "published to $OUT"

# --- 5. manifest + build info ----------------------------------------------
STATS=$(python3 - "$OUT" "$MANIFEST" <<'PY'
import hashlib, os, sys
root, manifest = sys.argv[1], sys.argv[2]
rows = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames.sort()
    for fn in sorted(filenames):
        full = os.path.join(dirpath, fn)
        rel = os.path.relpath(full, root)
        h = hashlib.sha256()
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        rows.append((rel, os.path.getsize(full), h.hexdigest()))
rows.sort()
with open(manifest, "w") as f:
    for rel, size, digest in rows:
        f.write(f"{digest}\t{size}\t{rel}\n")
print(len(rows), sum(r[1] for r in rows))
PY
)
FILES=${STATS%% *}
BYTES=${STATS##* }

T3=$(date +%s)
COMMIT=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)
BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
DIRTY=$( (git -C "$REPO" status --porcelain -- frontend 2>/dev/null || true) | (grep -vc '^?? ' || true))
cat > "$BUILD_INFO" <<JSON
{
  "built_at": "$(date -Iseconds)",
  "git_commit": "$COMMIT",
  "git_branch": "$BRANCH",
  "git_dirty_tracked_files": $DIRTY,
  "window_days": $WINDOW,
  "noindex": $([ "$NOINDEX" = "1" ] && echo true || echo false),
  "site_url": "$SITE_URL",
  "articles": $ARTICLES,
  "mega_pages": $MEGA,
  "newsletter_editions": $EDITIONS,
  "published_analyses": $PUBLISHED_ANALYSES,
  "segment_payloads_removed": $SEG_BEFORE,
  "index_entries": $INDEX_ENTRIES,
  "index_bytes": $INDEX_BYTES,
  "index_gzip_bytes": $INDEX_GZ,
  "files": $FILES,
  "bytes": $BYTES,
  "build_seconds": $((T2 - T1)),
  "total_seconds": $((T3 - T0)),
  "out_dir": "$OUT",
  "manifest": "$MANIFEST"
}
JSON

if [ "${KEEP_STAGING:-0}" != "1" ]; then
  rm -rf "$SITE/.next"
fi

log "done: $ARTICLES articles, $FILES files, $((BYTES / 1024 / 1024)) MB, $((T3 - T0))s total"
log "manifest: $MANIFEST"
log "build info: $BUILD_INFO"
