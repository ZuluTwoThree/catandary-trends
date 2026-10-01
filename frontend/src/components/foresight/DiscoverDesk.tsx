"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { FreeDomain } from "@/lib/discover";
import type { DiscoverJob, PreviewCard, ServiceHealth } from "@/lib/discoverJobs";
import { isRunning, STATE_LABEL } from "@/lib/discoverJobs";

const TIER_LABEL: Record<string, string> = {
  science: "Research",
  patent: "Patents",
  funding: "Funding",
  market: "Market",
  none: "Unplaced",
};
const POLL_MS = 1500;
const STORE_KEY = "discover-job";

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}
function writeStored(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORE_KEY, id);
    else window.localStorage.removeItem(STORE_KEY);
  } catch {
    /* storage blocked — the job just is not resumed after a reload */
  }
}

const label = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted";
const button =
  "font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-2 border transition-colors disabled:opacity-40";

function Cards({ title, cards, note }: { title: string; cards: PreviewCard[]; note: string }) {
  return (
    <div>
      <div className={`${label} mb-1`}>{title}</div>
      <p className="font-sans text-xs text-muted mb-2">{note}</p>
      <ul className="space-y-1.5">
        {cards.map((c) => (
          <li key={c.id} className="font-sans text-sm text-text leading-snug">
            <span className="font-mono text-[10px] text-muted mr-2">
              {TIER_LABEL[c.tier] ?? c.tier} · {c.month ?? "undated"} · p {c.p.toFixed(2)}
            </span>
            {c.title || <span className="text-muted">(no title)</span>}
          </li>
        ))}
        {cards.length === 0 && <li className="font-sans text-sm text-muted">none</li>}
      </ul>
    </div>
  );
}

export default function DiscoverDesk({ saved }: { saved: FreeDomain[] }) {
  const router = useRouter();
  const [term, setTerm] = useState("");
  const [also, setAlso] = useState("");
  const [months, setMonths] = useState(12);
  const [job, setJob] = useState<DiscoverJob | null>(null);
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [unit, setUnit] = useState<{ active: string; enabled: string } | null>(null);
  const [switching, setSwitching] = useState(false);
  const [round, setRound] = useState(0); // re-arms the polling for the same job

  const loadHealth = useCallback(async () => {
    fetch("/api/foresight/discover/service", { cache: "no-store" })
      .then((r) => r.json())
      .then(setUnit)
      .catch(() => setUnit(null));
    try {
      const r = await fetch("/api/foresight/discover", { cache: "no-store" });
      const d = (await r.json()) as { health: ServiceHealth | null; error: string | null };
      setHealth(d.health);
      setError(d.health ? null : d.error);
    } catch {
      setHealth(null);
    }
  }, []);

  // health now and every 20 s; a job left running before a reload is picked up again
  useEffect(() => {
    const first = setTimeout(() => {
      loadHealth();
      const id = readStored();
      if (id) setJobId(id);
    }, 0);
    const t = setInterval(loadHealth, 20_000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [loadHealth]);

  // follow the job until it waits for a decision or ends
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    let t: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      const r = await fetch(`/api/foresight/discover/${jobId}`, { cache: "no-store" }).catch(() => null);
      if (stop) return;
      if (!r || !r.ok) {
        writeStored(null);
        setJob(null);
        return;
      }
      const j = (await r.json()) as DiscoverJob;
      if (stop) return;
      setJob(j);
      if (isRunning(j.state)) t = setTimeout(tick, POLL_MS);
      else if (j.state === "done") router.refresh();
      else if (j.state === "discarded") writeStored(null);
    };
    t = setTimeout(tick, 0);
    return () => {
      stop = true;
      if (t) clearTimeout(t);
    };
  }, [jobId, round, router]);

  const follow = (id: string) => {
    writeStored(id);
    setJobId(id);
    setRound((r) => r + 1);
  };

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await fetch("/api/foresight/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          term,
          also: also.split(",").map((s) => s.trim()).filter(Boolean),
          window_months: months,
        }),
      });
      const d = await r.json();
      if (!r.ok) {
        setError(d.error ?? "could not start");
        return;
      }
      setJob(d);
      follow(d.id);
    } finally {
      setBusy(false);
    }
  }

  async function act(action: "confirm" | "discard") {
    if (!job) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/foresight/discover/${job.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const d = await r.json();
      if (!r.ok) setError(d.error ?? action + " failed");
      else {
        setJob(d);
        if (action === "confirm") follow(d.id);
        else writeStored(null);
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggle(on: boolean) {
    setSwitching(true);
    setError(null);
    try {
      const r = await fetch("/api/foresight/discover/service", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ on }),
      });
      setUnit(await r.json());
      // the copy loads in ~10 s after a start; look again a few times
      for (const ms of [1500, 6000, 15000]) setTimeout(loadHealth, ms);
      if (!on) setHealth(null);
    } finally {
      setSwitching(false);
    }
  }

  async function remove(key: string, name: string) {
    if (!window.confirm(`Delete the domain "${name}" and its pockets?`)) return;
    const r = await fetch(`/api/foresight/discover/domains/${key}`, { method: "DELETE" });
    if (!r.ok) setError((await r.json()).error ?? "delete failed");
    router.refresh();
  }

  const running = job ? isRunning(job.state) : false;
  const pv = job?.preview;
  const tierTotal = pv ? Object.values(pv.by_tier).reduce((a, b) => a + b, 0) : 0;

  const on = unit?.active === "active" || unit?.active === "activating";
  return (
    <div className="space-y-8">
      {/* ---- the switch (Owner 01.10.: the service holds ~4 GB of RAM) ---- */}
      <div className="flex flex-wrap items-center gap-3 border border-border px-5 py-3">
        <span className={label}>Discovery service</span>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          disabled={switching || !unit}
          onClick={() => toggle(!on)}
          className={`relative h-5 w-9 border transition-colors disabled:opacity-40 ${
            on ? "border-accent bg-accent/20" : "border-border bg-ink"
          }`}
          title={on ? "Switch off and free the memory" : "Switch on (loads in about 10 seconds)"}
        >
          <span
            className={`absolute top-0.5 h-3.5 w-3.5 transition-all ${on ? "left-[18px] bg-accent" : "left-0.5 bg-muted"}`}
          />
        </button>
        <span className="font-sans text-sm text-text">
          {!unit
            ? "state unknown"
            : on
              ? health?.ready
                ? "on — holds about 4 GB of memory"
                : "starting — loading the signal copy …"
              : "off — no memory held; switch on to search"}
        </span>
        <span className="font-sans text-xs text-muted">
          {unit && (unit.enabled === "enabled" ? "starts with the machine" : "stays off after a restart")}
        </span>
      </div>

      {/* ---- input ---- */}
      <form onSubmit={start} className="border border-border bg-card/40 p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[2fr_2fr_auto_auto] gap-3 items-end">
          <label className="block">
            <span className={label}>Term</span>
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              maxLength={80}
              placeholder="e.g. precision fermentation"
              className="mt-1 w-full bg-ink border border-border px-3 py-2 font-sans text-paper focus:border-accent outline-none"
            />
          </label>
          <label className="block">
            <span className={label}>Other spellings (optional, comma-separated)</span>
            <input
              value={also}
              onChange={(e) => setAlso(e.target.value)}
              placeholder="e.g. all-solid-state battery, SSB"
              className="mt-1 w-full bg-ink border border-border px-3 py-2 font-sans text-paper focus:border-accent outline-none"
            />
          </label>
          <label className="block">
            <span className={label}>Window</span>
            <select
              value={months}
              onChange={(e) => setMonths(Number(e.target.value))}
              className="mt-1 bg-ink border border-border px-3 py-2 font-sans text-paper"
            >
              <option value={6}>6 months</option>
              <option value={12}>12 months</option>
              <option value={24}>24 months</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || running || !term.trim() || !health?.ready}
            className={`${button} text-accent border-accent hover:bg-accent/10`}
          >
            Select signals
          </button>
        </div>
        <p className="font-sans text-xs text-muted">
          {health
            ? health.ready
              ? `Service ready · ${health.rows.toLocaleString("en-US")} signals in memory` +
                (health.refreshed_at ? ` · updated ${health.refreshed_at.replace("T", " ")}` : "")
              : `Service starting · ${health.loading || "loading the vector copy"}`
            : "Service not reachable."}{" "}
          The selection takes about half a minute, the pockets one to two more.
        </p>
      </form>

      {error && (
        <div className="border border-warn/50 bg-warn/5 p-4 font-sans text-sm text-warn">{error}</div>
      )}

      {/* ---- job ---- */}
      {job && (
        <section className="border border-border p-5 space-y-5">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 className="font-display text-2xl text-paper">{job.term}</h2>
            {job.also.length > 0 && (
              <span className="font-sans text-sm text-muted">also: {job.also.join(", ")}</span>
            )}
            <span className={`${label} ${job.state === "failed" ? "text-warn" : "text-accent"}`}>
              {STATE_LABEL[job.state]}
              {running && " …"}
            </span>
          </div>

          {(running || job.state === "failed") && (
            <ol className="font-mono text-[11px] text-muted space-y-0.5">
              {job.log.map((l, i) => (
                <li key={i}>
                  <span className="text-border mr-2">{l.t.toFixed(0)}s</span>
                  {l.msg}
                </li>
              ))}
            </ol>
          )}

          {pv && job.state !== "discarded" && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className={label}>Selected, last {pv.window_months} months</div>
                  <div className="font-display text-3xl text-paper">
                    {pv.members_window.toLocaleString("en-US")}
                  </div>
                  <div className="font-sans text-xs text-muted">since {pv.window_from}</div>
                </div>
                <div>
                  <div className={label}>In the whole archive</div>
                  <div className="font-display text-3xl text-paper">
                    {pv.members_archive.toLocaleString("en-US")}
                  </div>
                  <div className="font-sans text-xs text-muted">earliest {pv.first_month ?? "—"}</div>
                </div>
                <div>
                  <div className={label}>Carry the term literally</div>
                  <div className="font-display text-3xl text-paper">{Math.round(pv.literal_share * 100)} %</div>
                  <div className="font-sans text-xs text-muted">
                    of {pv.literal_sample} sampled — the rest were chosen by meaning
                  </div>
                </div>
                <div>
                  <div className={label}>By conversation</div>
                  <ul className="mt-1 space-y-1">
                    {Object.entries(pv.by_tier).map(([t, n]) => (
                      <li key={t} className="flex items-center gap-2 font-sans text-xs text-text">
                        <span className="w-16 text-muted">{TIER_LABEL[t] ?? t}</span>
                        <span
                          className="h-1.5 bg-accent/70"
                          style={{ width: `${Math.max(2, (100 * n) / Math.max(tierTotal, 1))}px` }}
                        />
                        <span>{n.toLocaleString("en-US")}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Cards
                  title="Inside the selection"
                  cards={pv.examples}
                  note="A fixed sample of members. If these are off-topic, the term is too broad or means something else — add other spellings or try a narrower term."
                />
                <Cards
                  title="Just outside"
                  cards={pv.just_outside}
                  note="Signals that nearly made it. If these clearly belong, the selection is too strict for this term."
                />
              </div>

              <p className="font-sans text-xs text-muted">
                Seeds: {Object.entries(pv.seeds).filter(([, n]) => n > 0).map(([k, n]) => `${k} ${n.toLocaleString("en-US")}`).join(" · ")}
                {pv.auc != null && ` · probe AUC ${pv.auc.toFixed(3)}`}
                {job.seconds_select != null && ` · selected in ${Math.round(job.seconds_select)} s`}
              </p>

              {job.state === "preview" && (
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    disabled={busy || !pv.enough}
                    onClick={() => act("confirm")}
                    className={`${button} text-accent border-accent hover:bg-accent/10`}
                  >
                    Find pockets
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => act("discard")}
                    className={`${button} text-muted border-border hover:text-paper`}
                  >
                    Discard
                  </button>
                  {!pv.enough && (
                    <span className="font-sans text-sm text-muted">
                      Fewer than {pv.min_signals} signals in the window — too thin for pockets. Try a
                      wider window or a broader term.
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {job.state === "done" && job.result && (
            <div className="space-y-4 border-t border-border pt-5">
              <p className="font-sans text-text">
                {job.result.nests} {job.result.nests === 1 ? "pocket" : "pockets"} in {job.result.groups}{" "}
                {job.result.groups === 1 ? "group" : "groups"}, holding{" "}
                {Math.round(job.result.in_pockets * 100)} % of the selection
                {job.seconds_pockets != null && ` · ${Math.round(job.seconds_pockets)} s`}.{" "}
                <span className="text-muted">
                  {job.result.named} named by the model{job.result.named === 0 ? ` (${job.result.naming})` : ""}.
                </span>
              </p>
              <Link
                href={`/trends/foresight/emerging?domain=${job.key}`}
                className={`${button} inline-block text-accent border-accent hover:bg-accent/10`}
              >
                Open the pockets →
              </Link>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {job.result.outline.map((g) => (
                  <div key={g.group} className="border border-border p-3">
                    <div className={`${label} mb-2`}>
                      {g.nests.length > 1 ? g.label ?? `Group ${g.group}` : "On its own"}
                    </div>
                    <ul className="space-y-1">
                      {g.nests.map((n, i) => (
                        <li key={i} className="font-sans text-sm text-text leading-snug">
                          {n.name}{" "}
                          <span className="font-mono text-[10px] text-muted">
                            {n.size} · since {n.first_month ?? "—"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* ---- saved ---- */}
      <section>
        <div className={`${label} mb-3`}>Discovered domains</div>
        {saved.length === 0 ? (
          <p className="font-sans text-sm text-muted">None yet.</p>
        ) : (
          <ul className="divide-y divide-border border border-border">
            {saved.map((d) => (
              <li key={d.key} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <Link
                  href={`/trends/foresight/emerging?domain=${d.key}`}
                  className="font-sans text-paper hover:text-accent"
                >
                  {d.name}
                </Link>
                <span className="font-mono text-[10px] text-muted">
                  {d.nests != null ? `${d.nests} pockets` : "selection only"}
                  {d.window_days != null && ` · ${Math.round(d.window_days / 30)} months`}
                  {d.computed && ` · ${d.computed}`}
                </span>
                <span className="flex-1" />
                <button
                  type="button"
                  onClick={() => {
                    setTerm(d.name);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper"
                >
                  run again
                </button>
                <button
                  type="button"
                  onClick={() => remove(d.key, d.name)}
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-warn"
                >
                  delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
