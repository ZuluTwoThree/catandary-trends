import Link from "next/link";
import { listFreeDomains } from "@/lib/discover";
import DiscoverDesk from "@/components/foresight/DiscoverDesk";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Discover — Catandary Trends",
  description: "Type any term: the signals of that domain are selected live, and the pockets inside it found and dated.",
};

/**
 * Live pocket discovery for a free term (Owner 2026-10-01). The term selects a
 * domain from the embedding (a probe trained on the term's full-text hits and its
 * nearest signals); after the owner has looked at the selection, the pockets
 * inside it are found, dated against the archive, grouped and named. The result
 * is a normal emerging run — /trends/foresight/emerging?domain=q_<term>.
 *
 * Owner-only by inheritance (/trends/foresight is blocked under PUBLIC_MODE).
 */
export default async function DiscoverPage() {
  const saved = await listFreeDomains();
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-10">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Signal Space
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Discover <span className="italic">any</span> domain
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Type a term nobody planned for. The signals that belong to it are chosen
          by their meaning, not by a label; you see that selection first, then the
          pockets inside it are found, dated against the whole archive and grouped.
        </p>
        <p className="font-sans text-sm text-muted leading-relaxed max-w-3xl mt-3">
          A pocket is a <em>trend candidate</em>, not a verdict. Its age is only as
          old as our coverage: research and patents reach far back, the trade press
          only a few years. Broad terms drift into their neighbours, and narrow ones
          can be too thin — the preview tells you which before anything is computed.
          Pockets of the regular runs live on{" "}
          <Link href="/trends/foresight/emerging" className="text-accent hover:underline">
            Emerging
          </Link>
          .
        </p>
      </div>
      <DiscoverDesk saved={saved} />
    </div>
  );
}
