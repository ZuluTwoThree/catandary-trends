import Link from "next/link";
import type { Suggestion } from "@/lib/topicSuggestions";

/** Stage 3: terms worth typing, with their label. An invitation, not a finding. */
function Chips({ title, items, hint }: { title: string; items: Suggestion[]; hint: string }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted mb-2">
        {title} <span className="normal-case tracking-normal font-sans">— {hint}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="border border-border px-3 py-1.5 hover:border-accent hover:bg-accent/5 transition-colors"
            title={s.note}
          >
            <span className="font-sans text-sm text-paper">{s.term}</span>
            <span className="font-mono text-[9px] text-muted ml-2">{s.note}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function TopicSuggestions({
  pockets,
  vocabulary,
  asked,
}: {
  pockets: Suggestion[];
  vocabulary: Suggestion[];
  asked: Suggestion[];
}) {
  if (!pockets.length && !vocabulary.length && !asked.length) return null;
  return (
    <section className="border-t border-border pt-8">
      <Chips title="Pockets the corpus found" items={pockets} hint="named emerging pockets, newest evidence first; age and rows from the last run" />
      <Chips title="New vocabulary" items={vocabulary} hint="tags rare two years ago and common now, per pocket" />
      <Chips title="Asked before" items={asked} hint="with the answer they got" />
    </section>
  );
}
