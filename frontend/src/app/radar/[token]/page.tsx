import { notFound } from "next/navigation";
import type { Metadata } from "next";
import {
  getCustomerByToken,
  getRadarFeed,
  getBriefingsForCustomer,
} from "@/lib/radar";
import { getVerticalInfo, type Vertical } from "@/lib/types";
import TrendCard from "@/components/TrendCard";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Trend-Radar Portal",
  robots: { index: false, follow: false },
};

export default async function RadarPortalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const customer = getCustomerByToken(token);
  if (!customer || customer.status === "cancelled") {
    notFound();
  }

  const brandColor = customer.brand_color || "#0ea5e9";
  const brandName = customer.brand_name || "Catandary Trend-Radar";
  const { topTrends, watchlistHits, windowStart } = getRadarFeed(customer);
  const briefings = getBriefingsForCustomer(customer.id);
  const watchlistCount = Object.values(watchlistHits).reduce(
    (acc, t) => acc + t.length,
    0
  );

  const trialDaysLeft = customer.trial_ends_at
    ? Math.ceil(
        (new Date(customer.trial_ends_at).getTime() - Date.now()) / 86400_000
      )
    : null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Branded header */}
      <div
        className="rounded-2xl p-8 mb-8"
        style={{
          background: `linear-gradient(135deg, ${brandColor}22, transparent 60%)`,
          border: `1px solid ${brandColor}44`,
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            {customer.brand_logo_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={customer.brand_logo_url}
                alt={brandName}
                className="h-10 mb-3"
              />
            )}
            <h1 className="text-3xl font-bold" style={{ color: brandColor }}>
              {brandName}
            </h1>
            <p className="text-muted mt-1">
              Radar für {customer.name} · Signale seit {windowStart}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              {customer.verticals.map((v) => {
                const info = getVerticalInfo(v as Vertical);
                return (
                  <span
                    key={v}
                    className="text-xs px-2 py-1 rounded-full border border-border"
                    style={{ color: info.color }}
                    title={info.label}
                  >
                    {info.icon} {info.label}
                  </span>
                );
              })}
            </div>
            {customer.tier === "trial" && trialDaysLeft !== null && (
              <span className="text-xs px-3 py-1 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                Testzeitraum — noch {Math.max(0, trialDaysLeft)} Tage
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-8">
        <div>
          {/* Watchlist */}
          {customer.keywords.length > 0 && (
            <section className="mb-10">
              <h2 className="text-xl font-semibold mb-1">
                Ihre Watchlist
                <span className="ml-2 text-sm font-normal text-muted">
                  {watchlistCount} Treffer
                </span>
              </h2>
              <p className="text-sm text-muted mb-4">
                Beobachtete Themen: {customer.keywords.join(" · ")}
              </p>
              {watchlistCount === 0 ? (
                <p className="text-sm text-muted border border-border rounded-xl p-4">
                  Keine neuen Treffer im aktuellen Fenster. Wir melden uns im
                  Briefing, sobald eines Ihrer Themen anschlägt.
                </p>
              ) : (
                Object.entries(watchlistHits).map(([keyword, trends]) => (
                  <div key={keyword} className="mb-6">
                    <h3
                      className="text-sm font-bold uppercase tracking-wide mb-3"
                      style={{ color: brandColor }}
                    >
                      ⌖ {keyword}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {trends.map((trend) => (
                        <TrendCard key={trend.id} trend={trend} />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </section>
          )}

          {/* Top signals */}
          <section>
            <h2 className="text-xl font-semibold mb-1">
              Top-Signale aus Ihren Branchen
            </h2>
            <p className="text-sm text-muted mb-4">
              Kuratiert aus 43 internationalen Primärquellen, sortiert nach
              Relevanz
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {topTrends.map((trend) => (
                <TrendCard key={trend.id} trend={trend} />
              ))}
            </div>
          </section>
        </div>

        {/* Briefing archive */}
        <aside>
          <div className="sticky top-6 rounded-xl border border-border bg-card p-5">
            <h2 className="text-lg font-semibold mb-3">Briefing-Archiv</h2>
            {briefings.length === 0 ? (
              <p className="text-sm text-muted">
                Ihr erstes Wochen-Briefing erscheint am kommenden Montag.
              </p>
            ) : (
              <ul className="space-y-2">
                {briefings.map((b) => (
                  <li key={b.id}>
                    <a
                      href={`/radar/${token}/briefing/${b.id}`}
                      target="_blank"
                      className="block rounded-lg border border-border p-3 hover:border-accent/40 transition-colors"
                    >
                      <div className="text-sm font-semibold">
                        {b.week_label}
                      </div>
                      <div className="text-xs text-muted mt-0.5">
                        {b.trend_count} Signale
                        {b.watchlist_hit_count > 0 &&
                          ` · ${b.watchlist_hit_count} Watchlist-Treffer`}
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-5 pt-4 border-t border-border text-xs text-muted leading-relaxed">
              Konfiguration ändern (Branchen, Watchlist, Empfänger)? Eine
              kurze E-Mail genügt —{" "}
              <a
                href="mailto:radar@catandary.de"
                className="underline hover:text-foreground"
              >
                radar@catandary.de
              </a>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
