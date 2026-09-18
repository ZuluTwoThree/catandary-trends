"""Catalogue of every system instruction a language model receives in this
repo — for the owner page /trends/ops/prompts (2026-09-18).

One entry per LLM-backed function: what the function does, when it runs, which
model answers, where the prompt lives (file:line) and the prompt text itself,
read LIVE from the modules so the page never drifts from the code. Builders
that assemble a prompt at call time are shown as rendered text where the
inputs are static (classification block from mega_trends.yaml, report outline)
and as the builder's source where they are not (Stage-6 user prompt).

CLI:  python -m pipeline.prompt_catalog --json   # what the page reads
      python -m pipeline.prompt_catalog --list   # one line per entry
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GROUPS = (
    ("feed", "Feed pipeline (nightly cycle, Mon–Fri 04:00)"),
    ("judge", "Draft judge (Stage 10)"),
    ("foresight", "Foresight layer"),
    ("newsletter", "Newsletter"),
    ("dossier", "Scouting dossiers (owner desk)"),
    ("advisor", "Advisor"),
    ("ondemand", "Owner tools, on demand only"),
)


@dataclass
class PromptEntry:
    key: str
    group: str
    title: str
    function: str                 # what the surrounding function does, when it runs
    model: str                    # which model answers, which backend
    trigger: str                  # cron / desk button / on demand / not scheduled
    symbol: str                   # module:NAME or module:func()
    file: str = ""                # repo-relative path
    line: int = 0
    system: str = ""              # the system instruction
    user_template: str = ""       # optional: user-prompt builder (rendered or source)
    user_template_kind: str = ""  # "rendered" | "source" | ""
    notes: list[str] = field(default_factory=list)
    error: str = ""               # import/lookup failure, page shows it instead of hiding


def _rel(path: str | None) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _const_line(module, name: str) -> tuple[str, int]:
    """file + line of a module-level constant (regex over the source)."""
    try:
        src_file = inspect.getsourcefile(module) or ""
        text = Path(src_file).read_text(encoding="utf-8")
    except (OSError, TypeError):
        return "", 0
    m = re.search(rf"^{re.escape(name)}\s*=", text, flags=re.MULTILINE)
    return _rel(src_file), (text[:m.start()].count("\n") + 1) if m else 0


def _func_line(func) -> tuple[str, int]:
    try:
        return _rel(inspect.getsourcefile(func)), inspect.getsourcelines(func)[1]
    except (OSError, TypeError):
        return "", 0


def _load(entry: PromptEntry, module_name: str, name: str, *,
          render=None, user_func=None, user_render=None) -> PromptEntry:
    """Fill system/file/line from the live module; never raise."""
    try:
        mod = importlib.import_module(module_name)
        obj = getattr(mod, name)
        entry.system = render(obj) if render else str(obj)
        entry.file, entry.line = _const_line(mod, name) if not callable(obj) else _func_line(obj)
        if user_func is not None:
            uf = getattr(mod, user_func)
            if user_render is not None:
                entry.user_template = user_render(uf)
                entry.user_template_kind = "rendered"
            else:
                entry.user_template = inspect.getsource(uf)
                entry.user_template_kind = "source"
    except Exception as exc:                                       # noqa: BLE001
        entry.error = f"{type(exc).__name__}: {exc}"
    return entry


def _relevance_user_example(func) -> str:
    """Stage 1 builds a short user prompt inline; show it from the source."""
    src = inspect.getsource(func)
    m = re.search(r'prompt = f"""(.*?)"""', src, flags=re.DOTALL)
    return ("(f-string in step_relevance_filter)\n\n" + m.group(1)) if m else src


def build_catalog() -> list[PromptEntry]:
    E: list[PromptEntry] = []

    # ---------------- Feed pipeline ----------------
    E.append(_load(PromptEntry(
        key="stage1-relevance", group="feed", title="Stage 1 · Relevance gate",
        function=("Decides whether a feed entry is a trend signal at all and assigns the "
                  "vertical. Since #41 (2026-07) the cycle runs the hybrid gate: the distilled "
                  "embedding head settles the sure edges (score ≥ 0.7 keep, < 0.3 discard) and "
                  "only the uncertain band (~21 % of entries) is sent to the model with this "
                  "instruction. RSS_CLASSIFY_MODE=llm restores the all-LLM path."),
        model="Qwen3-8B (llama.cpp, STAGE_8B_MODEL; Ollama fallback; CLASSIFY_BACKEND=anthropic optional)",
        trigger="Nightly full cycle, Mon–Fri 04:00 (scheduled_cycle.sh)",
        symbol="pipeline.llm_processor:RELEVANCE_SYSTEM",
        notes=["Structured output (RelevanceResult), temperature 0.",
               "Stage 0b before it: entries with < MIN_SOURCE_TEXT_CHARS (80) source characters never reach a model."]),
        "pipeline.llm_processor", "RELEVANCE_SYSTEM",
        user_func="step_relevance_filter", user_render=_relevance_user_example))

    E.append(_load(PromptEntry(
        key="stage2-extraction", group="feed", title="Stage 2 · Structured extraction",
        function=("Pulls brand, product, source type, claims, quotes, dates and geography out of "
                  "the source text — strictly extractive. EXTRACTION_STRICT=1 (default since "
                  "2026-08-21) makes every field mandatory and filters quotes/geography for "
                  "verbatim presence. Key figures do NOT come from the model: a regex reads them "
                  "from the source with sentence context. All fields feed the Stage-6 prompt."),
        model="Qwen3-8B (llama.cpp); the NuExtract fallback is disabled",
        trigger="Nightly full cycle",
        symbol="pipeline.llm_processor:EXTRACTION_SYSTEM",
        notes=["Reads up to 12,000 characters of the fetched article (Stage 6 sees only the first 4,000)."]),
        "pipeline.llm_processor", "EXTRACTION_SYSTEM"))

    E.append(_load(PromptEntry(
        key="stage3-classification", group="feed", title="Stage 3 · Classification (LLM path)",
        function=("Verticals, PESTEL, tags, signal type, regions and mega-trend for one entry. In "
                  "the production hybrid mode the distilled embedding heads do this without a "
                  "model; this instruction is what the model gets on the RSS_CLASSIFY_MODE=llm "
                  "fallback and in signal_batch --backend llm. The mega-trend block is rendered "
                  "from mega_trends.yaml at import time."),
        model="Qwen3-8B (llama.cpp) — only on the LLM fallback path",
        trigger="Fallback only (RSS_CLASSIFY_MODE=llm); hybrid mode uses no model here",
        symbol="pipeline.llm_processor:CLASSIFICATION_SYSTEM",
        notes=["Rendered text below includes the current 28 mega-trend keys."]),
        "pipeline.llm_processor", "CLASSIFICATION_SYSTEM"))

    E.append(_load(PromptEntry(
        key="stage6-content", group="feed", title="Stage 6 · Article generation (EN)",
        function=("Writes the ~100-word trend article from title, teaser/full text (first "
                  "STAGE6_SOURCE_MAX_CHARS = 4,000 characters) and the Stage-2 extraction. Always "
                  "English, even for German sources. Followed by the hard garbage guard "
                  "(content_guard: script leak, repetition, non-Latin share → fresh request "
                  "without prompt cache, 3 attempts, then the entry stays unprocessed), the "
                  "soft guard (cliché, length, grounding) and the publish gates (garbled, "
                  "truncated, ungrounded figures, ungrounded person names)."),
        model="Gemma-4-26B-A4B (llama.cpp, start-gemma4-26b.sh; Ollama qwen3:14b fallback) via GPU handover",
        trigger="Nightly full cycle; also the Draft judge's re-rolls and 'Write again' from the review desk",
        symbol="pipeline.llm_processor:CONTENT_EN_SYSTEM",
        notes=["Temperature 0.6–0.8; identity check against /v1/models before every request.",
               "The user prompt is assembled per row by build_content_prompt() — its source is shown below."]),
        "pipeline.llm_processor", "CONTENT_EN_SYSTEM", user_func="build_content_prompt"))

    E.append(_load(PromptEntry(
        key="stage8-reclassify", group="feed", title="Stage 8 · Vertical re-check",
        function=("Second look at the vertical of every fresh draft with a semantic check, "
                  "catching Stage-3 misclassifications (~3.5 % corrections in production). Runs "
                  "over ALL drafts (~20 min per pass) — since 2026-09-09 only when the phase "
                  "created trends."),
        model="Qwen3-8B (llama.cpp)",
        trigger="Nightly full cycle, after Stage 7",
        symbol="pipeline.reclassify:CLASSIFY_SYSTEM"),
        "pipeline.reclassify", "CLASSIFY_SYSTEM"))

    # ---------------- Draft judge ----------------
    E.append(_load(PromptEntry(
        key="stage10-judge", group="judge", title="Stage 10 · Draft judge",
        function=("Editorial verdict on fresh drafts BELOW the 0.85 auto-publish threshold: "
                  "publish only when signal=true and the category is acceptable, otherwise "
                  "hold (never reject). Every release still passes the same gates as "
                  "auto-publish (garbage, truncation, grounding, pgvector dedup against "
                  "published). Garbled candidates are diverted before the judge; each draft "
                  "is judged once (judged_at)."),
        model="Qwen3.8-27B (llama.cpp) via GPU handover with VRAM and identity guards",
        trigger="Nightly full cycle, end of run (DRAFT_JUDGE=0 disables)",
        symbol="pipeline.draft_judge:JUDGE_SYSTEM",
        notes=["Structured output (JudgeVerdict). Counts go to data/draft_judge_last.json → morning mail."]),
        "pipeline.draft_judge", "JUDGE_SYSTEM"))

    # ---------------- Foresight ----------------
    E.append(_load(PromptEntry(
        key="research-pulse", group="foresight", title="Research Pulse · weekly paragraph",
        function=("One sober paragraph (100–150 words) per Mega Signal Theme and ISO week, "
                  "written only from the measured block: volume vs. the four-week median, "
                  "KMeans clusters with c-TF-IDF labels and their growth, the papers closest to "
                  "each centroid. No text below 5 papers. Stored versioned in research_pulse."),
        model="Gemma-4-26B-A4B (llama.cpp, RESEARCH_PULSE_MODEL), T=0.2, seed 73",
        trigger="Saturday 12:00 cron (weekly_research_pulse.sh, since 2026-09-18) and the 'Recompute' button per theme",
        symbol="pipeline.research_pulse:SYSTEM_PROMPT"),
        "pipeline.research_pulse", "SYSTEM_PROMPT"))

    E.append(_load(PromptEntry(
        key="nest-naming", group="foresight", title="Emerging nests · naming",
        function=("Names a dense nest of the emerging-signal layer (/trends/foresight/emerging) "
                  "from its centre-nearest titles. Every meaning-bearing word of the name must "
                  "occur in the nest, otherwise the name is rejected and the keyword label "
                  "stays. The only GPU step of that layer (--no-llm-names switches it off)."),
        model="Gemma-4-26B-A4B (llama.cpp, NEST_NAME_MODEL)",
        trigger="'Recompute pockets' on the emerging page (no cron)",
        symbol="pipeline.nest_naming:SYSTEM_PROMPT"),
        "pipeline.nest_naming", "SYSTEM_PROMPT"))

    E.append(_load(PromptEntry(
        key="mega-reviewer", group="ondemand", title="Mega-trend reviewer (batch re-assignment)",
        function=("Re-assigns the mega-trend of a batch of trends against the canonical list "
                  "(title + summary + current assignment in, best key out). Used by the owner "
                  "scripts review_recent_live.py / review_today_dryrun.py; not part of the cycle."),
        model="MODEL_GENERATE (config; Ollama path)",
        trigger="On demand (scripts/review_recent_live.py, scripts/review_today_dryrun.py)",
        symbol="pipeline.mega_trend_reviewer:REVIEW_SYSTEM",
        notes=["The {mega_trend_block} placeholder is filled from mega_trends.yaml at call time."]),
        "pipeline.mega_trend_reviewer", "REVIEW_SYSTEM"))

    E.append(_load(PromptEntry(
        key="propose-mega", group="ondemand", title="Mega-trend proposals · labelling",
        function=("Bottom-up discovery of new Mega Signal Themes: clusters in the signal space "
                  "become NEW/SPLIT/MERGE candidates, and this instruction names each candidate "
                  "(broad, durable name, German name, one-line description). Read-only; writes "
                  "a candidate file, never the taxonomy."),
        model="Qwen3-8B (llama.cpp)",
        trigger="On demand (scripts/propose_mega_trends.py)",
        symbol="scripts.propose_mega_trends:_LABEL_SYS"),
        "scripts.propose_mega_trends", "_LABEL_SYS"))

    # ---------------- Newsletter ----------------
    E.append(_load(PromptEntry(
        key="newsletter-editorial", group="newsletter", title="Newsletter · editorial",
        function=("Opening editorial of the weekly website edition from the week's published "
                  "articles and counts. The edition is generated deterministically into "
                  "newsletter_editions; nothing is sent without a human approval on "
                  "/trends/newsletter/review (approved_at gate, exit 2 otherwise)."),
        model="MODEL_GENERATE via the Gemma swap in weekly_newsletter_publish.sh",
        trigger="Tuesday 09:00 cron (weekly_newsletter_publish.sh)",
        symbol="pipeline.newsletter_generator:EDITORIAL_SYSTEM_PROMPT",
        notes=["Badge on the page: AI-generated. Disclosure sentence AI_DISCLOSURE_EN in the mail footer."]),
        "pipeline.newsletter_generator", "EDITORIAL_SYSTEM_PROMPT"))

    E.append(_load(PromptEntry(
        key="newsletter-vertical", group="newsletter", title="Newsletter · vertical summaries",
        function=("One short summary per vertical (FOOD … LIFESTYLE) for the same edition, "
                  "naming companies and products from the week's articles."),
        model="MODEL_GENERATE via the Gemma swap",
        trigger="Tuesday 09:00 cron",
        symbol="pipeline.newsletter_generator:VERTICAL_SYSTEM_PROMPT"),
        "pipeline.newsletter_generator", "VERTICAL_SYSTEM_PROMPT"))

    E.append(_load(PromptEntry(
        key="newsletter-deepdive", group="newsletter", title="Newsletter · Deep Dive condensation",
        function=("Condenses a finished scouting dossier (chosen theme of the week, researcher "
                  "run through the dossier order path) into a 300–500-word section. The model "
                  "only phrases: every figure and URL is checked back against the dossier's "
                  "supported claims and citation catalog. Phase 1 = dry-run, never rendered "
                  "publicly (gate_passed && !dry_run required)."),
        model="Gemma-4-26B-A4B (NEWSLETTER_DEEP_DIVE_MODEL)",
        trigger="Only with NEWSLETTER_DEEP_DIVE=dry-run in the Tuesday wrapper (default off)",
        symbol="scripts.newsletter_deep_dive:CONDENSE_SYSTEM"),
        "scripts.newsletter_deep_dive", "CONDENSE_SYSTEM"))

    # ---------------- Dossiers ----------------
    cr = "scripts.corpus_research"
    E.append(_load(PromptEntry(
        key="dossier-profile", group="dossier", title="Dossier · search directions (topic profile)",
        function=("First model call of a dossier run: from topic and question, describe the "
                  "field so the search engine can be asked the right things — who decides, "
                  "what dated events happen, what a board asks about law/IP and market. The "
                  "output seeds the web queries; every fact is verified against pages later."),
        model="Qwen3.8-27B (llama.cpp), structured (TopicProfile)",
        trigger="Every dossier run (desk 'Run now' or scripts/dossier_worker.py)",
        symbol=f"{cr}:PROFILE_SYSTEM",
        notes=["Until 2026-09-18 this name was silently overwritten by the company-profile prompt "
               "further down the file — the search directions ran under the wrong instruction."]),
        cr, "PROFILE_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-planner", group="dossier", title="Dossier · research plan",
        function=("Turns the question into up to N search steps over the own corpus "
                  "(articles, signals, papers, patents), the last one a counter-evidence step."),
        model="Qwen3.8-27B, structured",
        trigger="Every dossier run",
        symbol=f"{cr}:PLANNER_SYSTEM",
        notes=["{max_steps} is filled at call time."]),
        cr, "PLANNER_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-agent", group="dossier", title="Dossier · corpus research agent",
        function=("Step loop over the own corpus: search (vector search via the CPU embedder on "
                  ":8091, FTS fallback), open a catalog entry (source excerpt AND our article, "
                  "separately labelled), or finish. Budgeted; every step lands in the ledger."),
        model="Qwen3.8-27B, structured (AgentAction)",
        trigger="Every dossier run",
        symbol=f"{cr}:AGENT_SYSTEM"),
        cr, "AGENT_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-audit", group="dossier", title="Dossier · evidence audit",
        function=("Maps evidence to claims before writing: supported claims, inferences, gaps. "
                  "Runs after the corpus phase and again after the web phase (re-audit). The "
                  "gaps drive the web agent and the internal sweep; the honesty gates of the "
                  "newsletter deep dive read the same audit."),
        model="Qwen3.8-27B, structured (Audit), T=0.2",
        trigger="Every dossier run (twice)",
        symbol=f"{cr}:AUDIT_SYSTEM"),
        cr, "AUDIT_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-web-agent", group="dossier", title="Dossier · web gap closer",
        function=("Closes audit gaps on the web: Brave Search (SearXNG fallback), fetch through "
                  "the robots/TDM-honouring fetcher (PDFs readable since 2026-09-18), source "
                  "rank filter (registers/agencies 0, own sites/journals 1, press 2, "
                  "self-publishing platforms rejected)."),
        model="Qwen3.8-27B, structured (WebAction)",
        trigger="Every dossier run with web enabled",
        symbol=f"{cr}:WEB_AGENT_SYSTEM"),
        cr, "WEB_AGENT_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-harvest", group="dossier", title="Dossier · fact ledger (DR pre-pass)",
        function=("Deep-research pre-pass (default since 2026-09-13): reads primary pages first "
                  "and takes dated, attributed notes per source into the fact ledger — the "
                  "material the writer must use. Calendar candidates and the actor map are "
                  "derived from it deterministically."),
        model="Qwen3.8-27B, structured (LedgerFacts)",
        trigger="Every dossier run unless params {\"dr\": false} / DOSSIER_DR=0",
        symbol=f"{cr}:HARVEST_SYSTEM"),
        cr, "HARVEST_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-landscape", group="dossier", title="Dossier · landscape map (landscape mode)",
        function=("In --mode landscape: proposes the sub-fields of a broad field; the corpus "
                  "counts each one back (< 5 signals drops it), every remaining sub-field gets "
                  "its own search step and a row in the mandatory '### Landscape' table."),
        model="Qwen3.8-27B, structured (LandscapeMap)",
        trigger="Only in landscape mode",
        symbol=f"{cr}:LANDSCAPE_SYSTEM"),
        cr, "LANDSCAPE_SYSTEM"))

    def _render_report(func):
        return func(measure=True, lang="en", landscape=False)

    E.append(_load(PromptEntry(
        key="dossier-writer", group="dossier", title="Dossier · writer (report system prompt)",
        function=("The writer's instruction: outline of the seven mandatory sections, citation "
                  "rule (catalog ids in double brackets, canonicalised to links afterwards), "
                  "what may not be stated (measured figures are appended by code, never "
                  "quoted by the model). Since 2026-09-14 the report is written section by "
                  "section (DOSSIER_WRITE=sections) with a per-section directive and word "
                  "budget; the rendered directive template is shown below."),
        model="Qwen3.8-27B, or DOSSIER_WRITER_MODEL (Qwen3.8-Flash-Next) after a model swap",
        trigger="Every dossier run",
        symbol=f"{cr}:report_system()",
        notes=["Rendered here with measure=True, lang=en, landscape=False. The landscape variant appends the '### Landscape' outline."]),
        cr, "report_system", render=_render_report, user_func="write_sections"))

    E.append(_load(PromptEntry(
        key="dossier-reader", group="dossier", title="Dossier · the reader (adversarial review)",
        function=("Same model, different role: a demanding board member reads the chosen draft "
                  "and the final version. Findings (max. 8, with passage and a testable "
                  "change; suggestions that introduce figures are dropped) go into the "
                  "targeted rewrite; the final reading is reported as non-blocking "
                  "(reader_ok). It cannot approve, block or rewrite."),
        model="Qwen3.8-27B (or the writer model), structured (ReaderReview)",
        trigger="Every dossier run (DOSSIER_READER=0 disables)",
        symbol=f"{cr}:READER_SYSTEM"),
        cr, "READER_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-repair", group="dossier", title="Dossier · sentence repair before deletion",
        function=("For every sentence the citation check flagged (figure not on the cited page, "
                  "subject mismatch), one attempt to repair it from the cited page before it is "
                  "dropped (R14-4: repair, re-check, then delete)."),
        model="Qwen3.8-27B (or the writer model)",
        trigger="Every dossier run with findings",
        symbol=f"{cr}:REPAIR_SYSTEM"),
        cr, "REPAIR_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-company-site", group="dossier", title="Company dossier · site choice",
        function=("Legacy company path: picks the company's own domain out of search results "
                  "(not directories or press) before the profile is extracted."),
        model="Qwen3.8-27B, structured (SiteChoice)",
        trigger="Company dossiers only",
        symbol=f"{cr}:SITE_CHOICE_SYSTEM"),
        cr, "SITE_CHOICE_SYSTEM"))

    E.append(_load(PromptEntry(
        key="dossier-company-profile", group="dossier", title="Company dossier · profile extraction",
        function=("Legacy company path: extracts a grounded company profile from the fetched "
                  "own-site pages (English fields seeding the corpus search)."),
        model="Qwen3.8-27B, structured (CompanyProfile), T=0.2",
        trigger="Company dossiers only",
        symbol=f"{cr}:COMPANY_PROFILE_SYSTEM",
        notes=["Renamed from PROFILE_SYSTEM on 2026-09-18 (it had shadowed the topic-profile prompt)."]),
        cr, "COMPANY_PROFILE_SYSTEM"))

    # ---------------- Advisor ----------------
    E.append(_load(PromptEntry(
        key="advisor", group="advisor", title="Advisor · options for one client",
        function=("Options section for ONE named client from ONE dossier: closed catalog of the "
                  "dossier's citations, client profile and engagement scope as data, "
                  "zero-option mandatory, effort only from comparable cases. Checked "
                  "(markers, placeholders, foreign figures) and read by the reader; released "
                  "only by a human (approved_at)."),
        model="Qwen3.8-27B with thinking (start-qwen3.8-27b-thinking.sh, 8,192-token thinking budget)",
        trigger="Desk form on the dossier page → scripts/advisory.py (no cron)",
        symbol="pipeline.advisory:ADVISOR_SYSTEM"),
        "pipeline.advisory", "ADVISOR_SYSTEM"))

    # ---------------- On demand / not scheduled ----------------
    E.append(_load(PromptEntry(
        key="press-rounds-llm", group="ondemand", title="Startup explorer · funding-round extraction (LLM modes)",
        function=("Extracts a funding round (company, amount, stage, investors) from a press "
                  "item. The Saturday ingester runs --mode regex only; the llm/hybrid/upgrade "
                  "modes with this prompt are available but not scheduled."),
        model="Qwen3-8B (llama.cpp) when run",
        trigger="Not scheduled (scripts/extract_press_rounds.py --mode llm|hybrid|upgrade)",
        symbol="scripts.extract_press_rounds:LLM_PROMPT"),
        "scripts.extract_press_rounds", "LLM_PROMPT"))

    E.append(_load(PromptEntry(
        key="press-rounds-investors", group="ondemand", title="Startup explorer · investor enrichment",
        function=("Names the investors of a round from the press text (#94 part 2). The cron "
                  "line is commented out in weekly_ingesters.sh — needs the additive migration "
                  "first."),
        model="Qwen3-8B (llama.cpp) when run",
        trigger="Not scheduled (scripts/extract_press_rounds.py --mode investors)",
        symbol="scripts.extract_press_rounds:INVESTOR_ENRICH_SYSTEM"),
        "scripts.extract_press_rounds", "INVESTOR_ENRICH_SYSTEM"))

    return E


def catalog_json() -> dict:
    entries = [asdict(e) for e in build_catalog()]
    return {"groups": [{"key": k, "title": t} for k, t in GROUPS], "entries": entries}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Catalogue of LLM system instructions")
    ap.add_argument("--json", action="store_true", help="print JSON (what /trends/ops/prompts reads)")
    ap.add_argument("--list", action="store_true", help="one line per entry")
    args = ap.parse_args(argv)
    if args.json or not args.list:
        json.dump(catalog_json(), sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
        return 0
    for e in build_catalog():
        flag = f"  !! {e.error}" if e.error else ""
        print(f"{e.key:28} {e.file}:{e.line:<5} {len(e.system):6} chars{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
