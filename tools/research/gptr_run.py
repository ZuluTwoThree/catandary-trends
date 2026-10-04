"""gptr-Worker — gpt-researcher unter Catandary-Regeln (Owner 2026-10-04).

Läuft in der Recherche-venv (`~/venvs/catandary-research`), gestartet vom Orchestrator
`scripts/field_research.py` (Main-venv), der vorher den Korpus-Dienst und — bei lokalem
Modell — den llama-server per GPU-Handover bereitstellt.

    gptr_run.py SPEC.json OUT.json

Warum ein eigener Starter statt Fork (docs/gpt_researcher_eval_2026-10-04.md, Abschnitt 6):
gpt-researcher holt Seiten selbst — mit gefälschtem Browser-User-Agent, ohne robots.txt,
ohne TDM-Vorbehalt, 15 parallel. Hier holt es NICHTS selbst:

  1. Retriever `custom` → Korpus-Dienst `/gptr/retrieve`; der liefert nur Treffer MIT
     konform geholtem Text (sonst würde gpt-researcher die URL nachkratzen).
  2. `BrowserManager.browse_urls` → Korpus-Dienst `/gptr/fetch` (article_fetcher).
     `Scraper.run`, `scrape_urls`, `OnlineDocumentLoader.load` → Fehler (fail closed).
  3. Netzsperre auf Socket-Ebene, VOR dem Import: Namensauflösung und Verbindungen nur zu
     127.0.0.1/::1 und den Hosts in `spec["allow_hosts"]` (bei --llm anthropic:
     api.anthropic.com). Jeder andere Versuch wird protokolliert und scheitert.
  4. Konfiguration festgenagelt: CONTEXT_FILTER=keyword (Jev schickte Text an einen
     Drittanbieter), keine Bilder, kein MCP-Retriever, keine source_urls/document_urls.

Ausgabe-JSON: report (Markdown), sources, context_words, costs, model, seconds,
egress_blocked (sollte leer sein), error.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time
from pathlib import Path

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
EGRESS_BLOCKED: list[str] = []
_allowed_ips: set[str] = {"127.0.0.1", "::1"}
_allowed_hosts: set[str] = set(LOOPBACK)


class EgressBlocked(OSError):
    """Verbindung außerhalb der Erlaubnisliste."""


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return host in LOOPBACK


def install_egress_guard(allow_hosts: list[str] | None = None) -> None:
    """Socket-Sperre. Idempotent; wirkt auf alle späteren Verbindungen im Prozess."""
    _allowed_hosts.update(h.lower() for h in (allow_hosts or []))
    if getattr(socket, "_catandary_guard", False):
        return
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_getaddrinfo(host, *args, **kwargs):
        h = host.decode() if isinstance(host, bytes) else (host or "")
        if h and not _is_loopback(h) and h.lower() not in _allowed_hosts:
            EGRESS_BLOCKED.append(f"dns:{h}")
            raise socket.gaierror(socket.EAI_NONAME, f"egress blocked by catandary guard: {h}")
        res = real_getaddrinfo(host, *args, **kwargs)
        for r in res:
            _allowed_ips.add(str(r[4][0]).split("%")[0])
        return res

    def _check(addr):
        if not isinstance(addr, tuple):  # AF_UNIX
            return
        ip = str(addr[0]).split("%")[0]
        if not (_is_loopback(ip) or ip in _allowed_ips):
            EGRESS_BLOCKED.append(f"connect:{ip}")
            raise EgressBlocked(f"egress blocked by catandary guard: {ip}")

    def guarded_connect(self, addr):
        _check(addr)
        return real_connect(self, addr)

    def guarded_connect_ex(self, addr):
        _check(addr)
        return real_connect_ex(self, addr)

    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket._catandary_guard = True


def configure_env(spec: dict) -> None:
    """Setzt die gpt-researcher-Konfiguration. Was hier steht, ist nicht verhandelbar."""
    svc = spec["service"]
    llm = spec.get("llm") or {"backend": "local"}
    env = {
        "RETRIEVER": "custom",
        "RETRIEVER_ENDPOINT": f"{svc['url']}/gptr/retrieve",
        "RETRIEVER_ARG_TOKEN": svc["token"],
        "RETRIEVER_ARG_SCOPE": spec.get("scope", "both"),
        "RETRIEVER_ARG_DOMAINS": ",".join(spec.get("domains") or []),
        "RETRIEVER_ARG_MAX_RESULTS": str(spec.get("max_results", 6)),
        "CONTEXT_FILTER": "keyword",
        "IMAGE_GENERATION_ENABLED": "false",
        "MCP_STRATEGY": "disabled",
        "USER_AGENT": spec.get("user_agent") or "CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology)",
        "SCRAPER": "bs",
        "MAX_SCRAPER_WORKERS": "4",
        "LANGUAGE": spec.get("language", "german"),
        "TOTAL_WORDS": str(spec.get("total_words", 900)),
        "MAX_ITERATIONS": str(spec.get("max_iterations", 3)),
        "MAX_SEARCH_RESULTS_PER_QUERY": str(spec.get("max_results", 6)),
        "REPORT_FORMAT": "APA",
        "LANGCHAIN_TRACING_V2": "false",
        "EMBEDDING": "openai:qwen3-embedding",
        "EMBEDDING_KWARGS": json.dumps({"openai_api_base": spec.get("embed_base", "http://127.0.0.1:8091/v1"),
                                        "check_embedding_ctx_length": False}),
        "OPENAI_API_KEY": "local-no-key",
        "TAVILY_API_KEY": "",
        "TYPESAFE_API_KEY": "",
    }
    if spec.get("since"):
        env["RETRIEVER_ARG_SINCE"] = spec["since"]
    if llm.get("backend") == "anthropic":
        env.update({
            "FAST_LLM": f"anthropic:{llm.get('fast', 'claude-haiku-4-5-20251001')}",
            "SMART_LLM": f"anthropic:{llm.get('smart', 'claude-sonnet-5')}",
            "STRATEGIC_LLM": f"anthropic:{llm.get('strategic', llm.get('smart', 'claude-sonnet-5'))}",
            "FAST_TOKEN_LIMIT": "3000", "SMART_TOKEN_LIMIT": "6000", "STRATEGIC_TOKEN_LIMIT": "3000",
        })
    else:
        model = llm.get("model", "local")
        env.update({
            "OPENAI_BASE_URL": llm.get("base_url", "http://127.0.0.1:8090/v1"),
            "FAST_LLM": f"openai:{model}", "SMART_LLM": f"openai:{model}", "STRATEGIC_LLM": f"openai:{model}",
            # Gemma-26B läuft mit -c 16384 und einem Slot: Ausgabe + Kontext müssen hineinpassen.
            "FAST_TOKEN_LIMIT": "1500", "SMART_TOKEN_LIMIT": "3000", "STRATEGIC_TOKEN_LIMIT": "1500",
        })
    os.environ.update(env)
    for k in ("DOC_PATH", "MCP_SERVERS"):
        os.environ.pop(k, None)


def patch_gptr(service_url: str, token: str) -> None:
    """Leitet jeden Seitenabruf auf den Korpus-Dienst um; alles andere scheitert."""
    import httpx

    from gpt_researcher.actions import web_scraping
    from gpt_researcher.document import online_document
    from gpt_researcher.scraper import scraper as scraper_mod
    from gpt_researcher.skills import browser

    async def browse_urls(self, urls):
        urls = [u for u in (urls or []) if isinstance(u, str)]
        if not urls:
            return []
        async with httpx.AsyncClient(timeout=600) as cl:
            r = await cl.post(f"{service_url}/gptr/fetch", json={"urls": urls},
                              headers={"X-Corpus-Token": token})
            r.raise_for_status()
            content = [d for d in r.json() if isinstance(d, dict) and d.get("raw_content")]
        self.researcher.add_research_sources(content)
        return content

    def blocked(*_a, **_k):
        raise RuntimeError("direct scraping is disabled (catandary compliance): use the corpus service")

    async def blocked_async(*_a, **_k):
        blocked()

    browser.BrowserManager.browse_urls = browse_urls
    browser.scrape_urls = blocked_async
    web_scraping.scrape_urls = blocked_async
    scraper_mod.Scraper.run = blocked_async
    online_document.OnlineDocumentLoader.load = blocked_async


def trim_context(context, max_words: int) -> list[str]:
    """Kontext auf ein Wortbudget kürzen (gpt-researcher kürzt im research_report nicht;
    der lokale Gemma hat 16.384 Token für Prompt + Ausgabe)."""
    items = context if isinstance(context, list) else [str(context or "")]
    out, used = [], 0
    for c in items:
        words = str(c).split()
        if used + len(words) > max_words:
            rest = max_words - used
            if rest > 80:
                out.append(" ".join(words[:rest]) + " …")
            break
        out.append(str(c))
        used += len(words)
    return out


async def run(spec: dict) -> dict:
    from gpt_researcher import GPTResearcher

    t0 = time.time()
    res = GPTResearcher(
        query=spec["query"],
        report_type="research_report",
        report_source="web",
        query_domains=spec.get("domains") or None,
        verbose=bool(spec.get("verbose")),
    )
    await res.conduct_research()
    context = res.get_research_context()
    budget = int(spec.get("context_word_budget", 5500))
    trimmed = trim_context(context, budget)
    if spec.get("extra_context"):
        trimmed = [str(spec["extra_context"])] + trimmed
    report = await res.write_report(ext_context="\n\n".join(trimmed), custom_prompt=spec.get("custom_prompt") or "")
    sources = []
    seen = set()
    for s in res.get_research_sources():
        u = s.get("url") if isinstance(s, dict) else None
        if u and u not in seen:
            seen.add(u)
            sources.append({"url": u, "title": (s.get("title") or "")[:300],
                            "chars": len(s.get("raw_content") or "")})
    return {
        "report": report,
        "sources": sources,
        "source_texts": {s["url"]: (s.get("raw_content") or "")[:20000]
                         for s in res.get_research_sources() if isinstance(s, dict) and s.get("url")},
        "context_items": len(context) if isinstance(context, list) else 1,
        "context_words": sum(len(str(c).split()) for c in trimmed),
        "costs": res.get_costs(),
        "seconds": round(time.time() - t0, 1),
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    install_egress_guard(spec.get("allow_hosts") or [])
    configure_env(spec)
    patch_gptr(spec["service"]["url"], spec["service"]["token"])
    out: dict = {"model": spec.get("llm"), "query": spec["query"]}
    try:
        import asyncio
        out.update(asyncio.run(run(spec)))
        rc = 0
    except Exception as exc:                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        chain, e = [], exc
        while e is not None and len(chain) < 4:      # gpt-researcher verpackt die Ursache
            chain.append(f"{type(e).__name__}: {str(e)[:300]}")
            e = e.__cause__ or e.__context__
        out["error"] = " ← ".join(chain)
        rc = 1
    out["egress_blocked"] = sorted(set(EGRESS_BLOCKED))
    Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
