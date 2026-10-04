"""Korpus-Dienst — HTTP-Hülle um `pipeline/corpus_api.py` (Owner 2026-10-04).

Läuft NICHT dauerhaft. Der MCP-Server (`tools/research/mcp_server.py`) und der
Orchestrator (`scripts/field_research.py`) starten ihn als Kindprozess auf einem
freien Port mit einem Einmal-Token und beenden ihn mit sich (`--parent-pid`).

    python -m pipeline.corpus_service --port 0 --parent-pid <pid>
        Token aus CORPUS_SERVICE_TOKEN (Pflicht). Erste Zeile auf stdout:
        {"port": N} — sobald der Socket lauscht.

Endpunkte (alle nur 127.0.0.1, alle mit Token: Kopf `X-Corpus-Token` oder `?token=`):

    GET  /health                    {"ok": true, "tools": [...]}
    POST /tool/<name>   {args}      {"ok": true, "result": …} | {"ok": false, "error": "…"}
    GET  /gptr/retrieve?query=…     Liste [{url, raw_content, title}] für den custom-Retriever
                                    von gpt-researcher (scope, domains, max_results, since)
    POST /gptr/fetch    {"urls": [...]}   konformer Ersatz für dessen Scraper

Ein Aufruf mit `Origin`-Kopf (Browser) wird abgewiesen — eine fremde Webseite im Browser
des Owners darf den Dienst nicht als Abruf-Proxy benutzen (vgl. Foresight-GET-Routen, 04.10.).
"""
from __future__ import annotations

import argparse
import hmac
import inspect
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("corpus_service")

MAX_BODY = 1_000_000
REPO = Path(__file__).resolve().parents[1]


def _json_default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def call_tool(name: str, args: dict):
    """Ruft ein registriertes Werkzeug; unbekannte/falsche Argumente → ToolError."""
    from pipeline import corpus_api
    fn = corpus_api.TOOLS.get(name)
    if fn is None:
        raise corpus_api.ToolError(f"unknown tool {name!r}")
    if not isinstance(args, dict):
        raise corpus_api.ToolError("arguments must be a JSON object")
    params = inspect.signature(fn).parameters
    unknown = [k for k in args if k not in params]
    if unknown:
        raise corpus_api.ToolError(f"unknown argument(s) {unknown}; allowed: {list(params)}")
    return fn(**args)


class Handler(BaseHTTPRequestHandler):
    server_version = "CatandaryCorpus/1.0"
    token: str = ""

    def log_message(self, fmt, *args):  # noqa: D401 — nach stderr, knapp, ohne Token
        logger.info("%s %s", self.address_string(), re.sub(r"token=[^&\s\"]+", "token=***", fmt % args))

    # -- Hilfen ------------------------------------------------------------
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, default=_json_default, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, qs: dict) -> bool:
        if self.headers.get("Origin"):
            return False
        given = self.headers.get("X-Corpus-Token") or (qs.get("token") or [""])[0]
        return bool(self.token) and hmac.compare_digest(given.encode(), self.token.encode())

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    # -- Routen ------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not self._authorized(qs):
            return self._send(403, {"ok": False, "error": "forbidden"})
        if u.path == "/health":
            from pipeline import corpus_api
            return self._send(200, {"ok": True, "tools": sorted(corpus_api.TOOLS)})
        if u.path == "/gptr/retrieve":
            args = {k: v[0] for k, v in qs.items() if k != "token"}
            try:
                res = call_tool("gptr_retrieve", args)
            except Exception as exc:                                # noqa: BLE001
                logger.warning("gptr_retrieve: %r", exc)
                res = []  # der custom-Retriever erwartet eine Liste; leer = nichts gefunden
            return self._send(200, res)
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        from pipeline.corpus_api import ToolError
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not self._authorized(qs):
            return self._send(403, {"ok": False, "error": "forbidden"})
        try:
            body = self._body()
        except Exception as exc:                                    # noqa: BLE001
            return self._send(400, {"ok": False, "error": f"bad request body: {exc}"})
        if u.path == "/gptr/fetch":
            try:
                return self._send(200, call_tool("gptr_fetch", {"urls": body.get("urls") or []}))
            except Exception as exc:                                # noqa: BLE001
                logger.warning("gptr_fetch: %r", exc)
                return self._send(200, [])
        if u.path.startswith("/tool/"):
            name = u.path[len("/tool/"):]
            t0 = time.time()
            try:
                res = call_tool(name, body)
                logger.info("tool %s ok in %.1fs", name, time.time() - t0)
                return self._send(200, {"ok": True, "result": res})
            except ToolError as exc:
                return self._send(400, {"ok": False, "error": str(exc)})
            except Exception as exc:                                # noqa: BLE001
                logger.exception("tool %s failed", name)
                return self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        return self._send(404, {"ok": False, "error": "not found"})


def _watch_parent(ppid: int) -> None:
    while True:
        time.sleep(2)
        try:
            os.kill(ppid, 0)
        except OSError:
            logger.info("parent %s gone — exiting", ppid)
            os._exit(0)
        if os.getppid() != ppid:
            os._exit(0)


def serve(port: int, token: str, parent_pid: int | None = None) -> None:
    Handler.token = token
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    if parent_pid:
        threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()
    sys.stdout.write(json.dumps({"port": srv.server_address[1]}) + "\n")
    sys.stdout.flush()
    srv.serve_forever()


@contextmanager
def running_service(python: str | None = None, timeout: float = 60):
    """Startet den Dienst als Kindprozess; liefert (base_url, token). Für Aufrufer in der
    Main-venv (`scripts/field_research.py`); der MCP-Server hat einen Zwilling."""
    token = secrets.token_urlsafe(24)
    env = dict(os.environ, CORPUS_SERVICE_TOKEN=token, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([python or sys.executable, "-m", "pipeline.corpus_service", "--port", "0",
                             "--parent-pid", str(os.getpid())],
                            cwd=str(REPO), env=env, stdout=subprocess.PIPE, text=True)
    try:
        t0 = time.time()
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            raise RuntimeError(f"corpus service did not start (rc={proc.poll()})")
        port = json.loads(line)["port"]
        if time.time() - t0 > timeout:
            raise RuntimeError("corpus service start timed out")
        yield f"http://127.0.0.1:{port}", token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=0, help="0 = freier Port (Default)")
    ap.add_argument("--parent-pid", type=int, default=None, help="beenden, sobald dieser Prozess weg ist")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s corpus_service %(levelname)s %(message)s")
    token = os.environ.get("CORPUS_SERVICE_TOKEN", "")
    if len(token) < 16:
        print("CORPUS_SERVICE_TOKEN (>= 16 Zeichen) muss gesetzt sein", file=sys.stderr)
        return 2
    serve(a.port, token, a.parent_pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
