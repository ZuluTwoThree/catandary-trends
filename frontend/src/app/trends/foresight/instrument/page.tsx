import InstrumentPreview from "@/components/foresight/InstrumentPreview";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "The plotting table — Catandary Foresight",
  description:
    "Rate signals, and the portfolio positions itself: maturity from evidence, relevance from your judgement.",
};

/**
 * Gestaltungsvorlage des Radar-Neubaus (docs/radar_overhaul_plan.md §5).
 *
 * Bewusst als echte Seite und nicht als Wegwerf-Mockup: sie erbt Schriften,
 * Farbtoken und Layout des Produkts, sodass die Entscheidung über die
 * Gestaltung an dem getroffen wird, was später auch läuft. Die Daten sind hier
 * noch gesetzt — die Strecke dahinter ist Schnitt 1–3.
 */
export default function InstrumentPage() {
  return <InstrumentPreview />;
}
