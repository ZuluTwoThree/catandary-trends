#!/usr/bin/env bash
# Local Apache 2.4 for testing the export's .htaccess rules (there is no
# Apache on the workstation; the webspace is shared hosting). Serves
# frontend/.export/out read-only on 127.0.0.1:8098 from the official
# httpd:2.4 image with the modules the rules need and AllowOverride All —
# i.e. the most permissive setting; if a rule 500s on the real webspace,
# AllowOverride there is narrower (see the TEST PLAN block at the end of
# frontend/public-export/trends/.htaccess).
#
#   scripts/htaccess_test_server.sh [OUT_DIR]     # (re)start the container
#   scripts/htaccess_test_server.sh --stop
#
# Re-run after every build: build_public_static.sh replaces the out/
# directory (rm + mv), which leaves a running container's bind mount stale.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${HTACCESS_TEST_CONTAINER:-ct-htaccess}"
PORT="${HTACCESS_TEST_PORT:-8098}"
CONF_DIR="$REPO/frontend/.export/apache"

if [ "${1:-}" = "--stop" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  echo "stopped $NAME"
  exit 0
fi

OUT="${1:-$REPO/frontend/.export/out}"
OUT="$(cd "$OUT" && pwd)"
[ -f "$OUT/trends/.htaccess" ] || { echo "no trends/.htaccess in $OUT — run scripts/build_public_static.sh first" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker not installed" >&2; exit 1; }

# The image's stock httpd.conf with rewrite/headers/deflate/expires on and
# .htaccess honoured for the document root.
mkdir -p "$CONF_DIR"
docker run --rm httpd:2.4 cat /usr/local/apache2/conf/httpd.conf \
  | sed -e 's|^#LoadModule rewrite_module|LoadModule rewrite_module|' \
        -e 's|^#LoadModule deflate_module|LoadModule deflate_module|' \
        -e 's|^#LoadModule expires_module|LoadModule expires_module|' \
        -e '/<Directory "\/usr\/local\/apache2\/htdocs">/,/<\/Directory>/ s|AllowOverride None|AllowOverride All|' \
  > "$CONF_DIR/httpd.conf"
grep -q '^LoadModule headers_module' "$CONF_DIR/httpd.conf" || { echo "headers_module not enabled in the stock conf?" >&2; exit 1; }

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:80" \
  -v "$CONF_DIR/httpd.conf:/usr/local/apache2/conf/httpd.conf:ro" \
  -v "$OUT:/usr/local/apache2/htdocs:ro" \
  httpd:2.4 >/dev/null
sleep 1
echo "Apache on http://127.0.0.1:${PORT}/  (htdocs = $OUT)"
for u in /trends /trends/ /trends/page/2 /trends/v/tech /trends/v/TECH /trends/imprint /trends/index.json /trends/does-not-exist-123 /trends/does-not-exist; do
  printf '  %-28s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://127.0.0.1:${PORT}${u}")"
done
