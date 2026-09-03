import Link from "next/link";
import { notFound } from "next/navigation";
import { canManageDossiers } from "@/lib/dossier-access";
import { workerStatus } from "@/lib/dossierWorker";
import {
  dossierTablesReady,
  listDossierOrders,
  listDossierSeries,
  type DossierOrder,
} from "@/lib/dossiers";
import {
  approveAction,
  cancelAction,
  createOrderAction,
  rerunSeriesAction,
  runOrderAction,
  runQueuedAction,
} from "./actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dossier desk",
  robots: { index: false, follow: false },
};

/**
 * Owner dossier desk (#95): place order slips for scouting dossiers, start
 * the worker for them, read the finished runs. Runs start only from the
 * buttons here (radar rule: on demand, never a cron); every finished run
 * waits in 'review' for the owner's final read.
 */

const STATUS_CLASS: Record<DossierOrder["status"], string> = {
  queued: "text-muted",
  running: "text-accent",
  review: "text-warn",
  done: "text-paper",
  failed: "text-warn",
  cancelled: "text-muted line-through",
};

const BTN = "border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]";
const BTN_ACCENT = `${BTN} border-accent text-accent hover:bg-accent hover:text-ink`;
const BTN_QUIET = `${BTN} border-border-strong text-muted hover:text-paper hover:border-paper`;
const BTN_DISABLED = `${BTN} border-border text-muted/60 cursor-not-allowed`;

const NOTICE: Record<string, { text: string; warn: boolean }> = {
  started: { text: "Worker started — the run takes 10–20 minutes; reload to follow.", warn: false },
  busy: { text: "A worker is already running; the order stays queued and can be started afterwards.", warn: true },
  missing: { text: "Worker not found: .venv/bin/python or scripts/dossier_worker.py missing next to this frontend.", warn: true },
  spawn: { text: "The worker could not be started (see server log).", warn: true },
  noseries: { text: "No such series to recompute.", warn: true },
};

/** Lock timestamps are UTC ISO strings — show them in the workstation's
 *  local time (the log file names stay UTC). */
function fmt(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(0, 16).replace("T", " ");
  return d.toLocaleString("en-GB", { hour12: false, dateStyle: "short", timeStyle: "short" });
}

function CheckSummary({ order }: { order: DossierOrder }) {
  const c = order.check;
  if (!c) return null;
  return (
    <span className="font-mono text-[11px]">
      {c.ok ? (
        <span className="text-accent">end-control clean</span>
      ) : (
        <span className="text-warn">{c.findings.length} finding(s)</span>
      )}
      <span className="text-muted">
        {" "}
        · {c.cited}/{c.sources} cited · {c.words} words
        {c.quant_ok === false && " · no quant block"}
      </span>
    </span>
  );
}

function OrderRow({ order, workerBusy }: { order: DossierOrder; workerBusy: boolean }) {
  const runLabel = order.status === "failed" ? "Run again" : "Run now";
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border px-1 py-3">
      <span className="font-mono text-[11px] text-muted">#{order.id}</span>
      <span
        className={`font-mono text-[10px] uppercase tracking-[0.14em] ${STATUS_CLASS[order.status]}`}
      >
        {order.status}
      </span>
      <span className="text-[14px] text-paper">{order.topic}</span>
      {order.dossierVersion != null && (
        <Link
          href={`/trends/dossiers/${order.slug}?v=${order.dossierVersion}`}
          className="font-mono text-[11px] text-accent hover:underline"
        >
          {order.slug} v{order.dossierVersion} →
        </Link>
      )}
      <span className="ml-auto flex items-center gap-3">
        <CheckSummary order={order} />
        {order.status === "review" && (
          <form action={approveAction}>
            <input type="hidden" name="id" value={order.id} />
            <input type="hidden" name="slug" value={order.slug} />
            <button className={BTN_ACCENT}>Sign off</button>
          </form>
        )}
        {(order.status === "queued" || order.status === "failed") && (
          <form action={runOrderAction}>
            <input type="hidden" name="id" value={order.id} />
            {workerBusy ? (
              <button disabled className={BTN_DISABLED} title="a worker is running">
                {runLabel}
              </button>
            ) : (
              <button className={BTN_ACCENT}>{runLabel}</button>
            )}
          </form>
        )}
        {order.status === "queued" && (
          <form action={cancelAction}>
            <input type="hidden" name="id" value={order.id} />
            <button className={BTN_QUIET}>Cancel</button>
          </form>
        )}
      </span>
      {order.error && (
        <p className="w-full font-mono text-[11px] text-warn">{order.error}</p>
      )}
    </li>
  );
}

export default async function DossierDeskPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // 404 rather than 403: an unauthorised visitor learns nothing about the route.
  if (!canManageDossiers()) notFound();

  const sp = await searchParams;
  const notice = typeof sp.worker === "string" ? NOTICE[sp.worker] : undefined;

  const ready = await dossierTablesReady();
  const [orders, series] = ready
    ? await Promise.all([listDossierOrders(), listDossierSeries()])
    : [[], []];
  const queued = orders.filter((o) => o.status === "queued").length;
  const inReview = orders.filter((o) => o.status === "review").length;
  const runningInDb = orders.filter((o) => o.status === "running").length;
  const worker = workerStatus();
  const workerBusy = worker.running || runningInDb > 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="border-b border-border pb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Owner desk
        </p>
        <h1 className="mt-3 font-display text-[34px] leading-[1.1] text-paper">
          Scouting dossiers
        </h1>
        <p className="mt-3 max-w-2xl text-[14px] leading-[1.65] text-muted">
          Place an order slip and start the worker: the agentic researcher
          runs fully on the local model, measures the innovation chain first,
          audits its own report and parks the result here as <em>review</em>{" "}
          until you sign it off. Nothing runs on a schedule — a dossier is a
          dated document, recomputed only on your click — and nothing leaves
          the machine.
        </p>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.14em]">
          <span className="text-paper">{queued} queued</span>
          <span className={inReview ? "text-warn" : "text-muted"}>
            {inReview} awaiting your review
          </span>
          <span className="text-muted">{series.length} series</span>
        </div>
      </header>

      {notice && (
        <p
          className={`mt-6 border px-4 py-3 font-mono text-[12px] ${
            notice.warn ? "border-warn/40 bg-warn/5 text-warn" : "border-accent/40 bg-accent/5 text-accent"
          }`}
        >
          {notice.text}
        </p>
      )}

      {!ready && (
        <p className="mt-6 border border-warn/40 bg-warn/5 px-4 py-3 font-mono text-[12px] text-warn">
          The dossier tables do not exist on this database yet. Run once, by
          hand: <code>.venv/bin/python scripts/migrate_dossier_orders.py</code>
        </p>
      )}

      <section className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 border border-border px-5 py-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
          Worker
        </span>
        {worker.running ? (
          <span className="font-mono text-[11px] text-accent">
            running · pid {worker.pid} · since {fmt(worker.startedAt)}
          </span>
        ) : runningInDb > 0 ? (
          <span className="font-mono text-[11px] text-accent">
            an order is running (started from the terminal)
          </span>
        ) : (
          <span className="font-mono text-[11px] text-muted">
            idle{worker.stale && worker.startedAt ? ` · last run ${fmt(worker.startedAt)}` : ""}
          </span>
        )}
        {worker.log && (
          <span className="font-mono text-[10px] text-muted break-all">log {worker.log}</span>
        )}
        <form action={runQueuedAction} className="ml-auto">
          {workerBusy || queued === 0 ? (
            <button disabled className={BTN_DISABLED}>
              Run {queued} queued
            </button>
          ) : (
            <button className={BTN_ACCENT}>Run {queued} queued</button>
          )}
        </form>
      </section>

      <section className="mt-8 border border-border p-5">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
          New order slip
        </h2>
        <form action={createOrderAction} className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Technology field *
            </span>
            <input
              name="topic"
              required
              maxLength={500}
              placeholder="e.g. perovskite tandem photovoltaics"
              className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[14px] text-paper placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Series slug (optional — same slug = next version)
            </span>
            <input
              name="slug"
              maxLength={80}
              placeholder="derived from the field if empty"
              className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[14px] text-paper placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Custom question (optional — default: the standard foresight
              framing on the field)
            </span>
            <textarea
              name="question"
              rows={2}
              maxLength={2000}
              className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[14px] text-paper focus:border-accent focus:outline-none"
            />
          </label>
          <div className="flex flex-col gap-2 font-mono text-[11px] text-muted">
            <label className="flex items-center gap-2">
              <input type="checkbox" name="quant" defaultChecked className="accent-current" />
              measure the innovation chain first (TIR, lead-time, hub patents)
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" name="run" defaultChecked={!workerBusy} className="accent-current" />
              start the worker right away
            </label>
          </div>
          <div className="flex items-end justify-end">
            <button className="border border-accent px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
              Place order
            </button>
          </div>
        </form>
      </section>

      <section className="mt-10">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
          Orders
        </h2>
        {orders.length === 0 ? (
          <p className="mt-4 text-[14px] text-muted">No orders yet.</p>
        ) : (
          <ul className="mt-2">
            {orders.map((o) => (
              <OrderRow key={o.id} order={o} workerBusy={workerBusy} />
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
          Dossier series
        </h2>
        {series.length === 0 ? (
          <p className="mt-4 text-[14px] text-muted">No dossiers written yet.</p>
        ) : (
          <ul className="mt-2 grid gap-px bg-border md:grid-cols-2">
            {series.map((s) => (
              <li key={s.slug} className="flex flex-col gap-3 bg-ink p-4">
                <div>
                  <Link
                    href={`/trends/dossiers/${s.slug}`}
                    className="font-display text-[18px] leading-[1.3] text-paper hover:text-accent"
                  >
                    {s.topic || s.slug}
                  </Link>
                  <p className="mt-1 font-mono text-[11px] text-muted">
                    {s.versions} version(s) · latest v{s.latestVersion}
                    {s.latestAt ? ` · ${s.latestAt.slice(0, 10)}` : ""}
                  </p>
                </div>
                <form action={rerunSeriesAction} className="mt-auto">
                  <input type="hidden" name="slug" value={s.slug} />
                  {workerBusy ? (
                    <button disabled className={BTN_DISABLED} title="a worker is running">
                      Recompute · v{s.latestVersion + 1}
                    </button>
                  ) : (
                    <button className={BTN_QUIET}>Recompute · v{s.latestVersion + 1}</button>
                  )}
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
