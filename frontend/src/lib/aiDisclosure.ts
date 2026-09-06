/**
 * AI disclosure for the weekly briefing (owner mandate 2026-09-06, issue #99).
 *
 * Two things live here, both plain statements of fact:
 *
 *  1. `AI_DISCLOSURE_EN` — the one sentence that travels with every copy of an
 *     edition: the mail footer, the website edition and the release view. It
 *     is a MIRROR of `AI_DISCLOSURE_EN` in pipeline/newsletter_generator.py
 *     (the mail is rendered in Python); tests/test_newsletter_ai_disclosure.py
 *     fails if the two drift apart. Worded so it still holds if the legal
 *     review of #99 (EU AI Act Art. 50) asks for an explicit label — it names
 *     what is machine-made, that checking is automatic, and that a person
 *     released it. No marketing, no method claim.
 *
 *  2. `EDITION_BLOCKS` — per-section provenance, shown as a badge next to each
 *     block in the release view so the owner sees at a glance which part of
 *     the issue a machine wrote. Three honest kinds, kept apart on purpose:
 *       generated  a language model wrote this text
 *       computed   arithmetic over the corpus, no language model involved
 *       curated    a selection of existing articles (which are themselves
 *                  model-written from their source — said, not glossed over)
 */

export const AI_DISCLOSURE_EN =
  "Sections of this briefing are generated from our corpus by a local " +
  "language model and checked automatically; the selection and this edition " +
  "were reviewed and released by a person.";

export type AiProvenance = "generated" | "computed" | "curated";

export interface EditionBlock {
  /** Matches the section keys of an edition record. */
  key: "editorial" | "deep_dive" | "vertical_summaries" | "trend_refs" | "mega_trend_radar";
  label: string;
  provenance: AiProvenance;
  /** How this block came about — one sentence, no hedging. */
  detail: string;
}

export const PROVENANCE_BADGE: Record<AiProvenance, string> = {
  generated: "AI-generated",
  computed: "Computed",
  curated: "Curated",
};

export const EDITION_BLOCKS: EditionBlock[] = [
  {
    key: "editorial",
    label: "Weekly overview",
    provenance: "generated",
    detail:
      "Written by the local language model from this week's signal counts and the cited articles.",
  },
  {
    key: "deep_dive",
    label: "Deep dive",
    provenance: "generated",
    detail:
      "Researched and condensed by local language models, then checked against its own citations before it may appear.",
  },
  {
    key: "vertical_summaries",
    label: "Vertical signals",
    provenance: "generated",
    detail: "One summary per vertical, written by the local language model from that vertical's signals.",
  },
  {
    key: "trend_refs",
    label: "Cited signals",
    provenance: "curated",
    detail:
      "Selected from published articles by signal score; each linked article is itself model-written from its source and links to that source.",
  },
  {
    key: "mega_trend_radar",
    label: "Signal themes radar",
    provenance: "computed",
    detail: "Signal counts per theme, aggregated in SQL. No language model involved.",
  },
];

/** The block record for one section, or undefined for an unknown key. */
export function editionBlock(key: EditionBlock["key"]): EditionBlock | undefined {
  return EDITION_BLOCKS.find((b) => b.key === key);
}
