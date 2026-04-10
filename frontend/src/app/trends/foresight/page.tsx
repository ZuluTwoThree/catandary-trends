import ForesightCockpit from "@/components/ForesightCockpit";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Foresight Cockpit — Catandary Trends",
  description:
    "Semantische Trend-Suche mit Signal-Timeline, Lead-Time-Analyse und Cross-Vertical-Insights.",
};

export default function ForesightRoute() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <ForesightCockpit />
    </div>
  );
}
