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
        function=("Condenses an audited research result on the chosen theme of the week into a "
                  "300–500-word section. The model only phrases: every figure and URL is "
                  "checked back against the supported claims and citation catalog. Kept for "
                  "stored editions — the researcher behind it (scouting dossiers) was removed "
                  "on 2026-09-19, so the script now records status 'disabled' instead of "
                  "running; this prompt is no longer called."),
        model="Gemma-4-26B-A4B (NEWSLETTER_DEEP_DIVE_MODEL)",
        trigger="None since 2026-09-19 (feature disabled; wrapper flag NEWSLETTER_DEEP_DIVE stays off)",
        symbol="scripts.newsletter_deep_dive:CONDENSE_SYSTEM"),
        "scripts.newsletter_deep_dive", "CONDENSE_SYSTEM"))

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
