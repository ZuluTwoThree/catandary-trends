import Link from "next/link";
import { notFound } from "next/navigation";
import { canManageDossiers } from "@/lib/dossier-access";
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
  requeueAction,
} from "./actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dossier desk",
  robots: { index: false, follow: false },
};

/**
 * Owner-only dossier desk: place order slips for scouting dossiers and read
 * the finished runs. Orders are processed ONLY when the owner starts the
 * worker on the workstation — this page never triggers GPU work itself, and
 * every finished run waits here in 'review' for the owner's final read.
 */

const STATUS_CLASS: Record<DossierOrder["status"], string> = {
  queued: "text-muted",
  running: "text-accent",
  review: "text-warn",
  done: "text-paper",
  failed: "text-warn",
  cancelled: "text-muted line-through",
};

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

function OrderRow({ order }: { order: DossierOrder }) {
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
            <button className="border border-accent px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:bg-accent hover:text-ink">
              Sign off
            </button>
          </form>
        )}
        {order.status === "queued" && (
          <form action={cancelAction}>
            <input type="hidden" name="id" value={order.id} />
            <button className="border border-border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper">
              Cancel
            </button>
          </form>
        )}
        {order.status === "failed" && (
          <form action={requeueAction}>
            <input type="hidden" name="id" value={order.id} />
            <button className="border border-border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper">
              Requeue
            </button>
          </form>
        )}
      </span>
      {order.error && (
        <p className="w-full font-mono text-[11px] text-warn">{order.error}</p>
      )}
    </li>
  );
}

export default async function DossierDeskPage() {
  // 404 rather than 403: an unauthorised visitor learns nothing about the route.
  if (!canManageDossiers()) notFound();

  const ready = await dossierTablesReady();
  const [orders, series] = ready
    ? await Promise.all([listDossierOrders(), listDossierSeries()])
    : [[], []];
  const queued = orders.filter((o) => o.status === "queued").length;
  const inReview = orders.filter((o) => o.status === "review").length;

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
          Place an order slip; the agentic researcher runs it fully on the
          local model when you start the worker on the workstation —{" "}
          <code className="font-mono text-[12px] text-paper">
            python -m scripts.dossier_worker
          </code>
          . Every finished run waits here as <em>review</em> with the
          agent&rsquo;s own end-control until you sign it off. Nothing runs on
          a schedule, and nothing leaves the machine.
        </p>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.14em]">
          <span className="text-paper">{queued} queued</span>
          <span className={inReview ? "text-warn" : "text-muted"}>
            {inReview} awaiting your review
          </span>
          <span className="text-muted">{series.length} series</span>
        </div>
      </header>

      {!ready && (
        <p className="mt-8 border border-warn/40 bg-warn/5 px-4 py-3 font-mono text-[12px] text-warn">
          The dossier tables do not exist on this database yet. Run once, by
          hand: <code>.venv/bin/python scripts/migrate_dossier_orders.py</code>
        </p>
      )}

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
              placeholder="e.g. solid-state batteries"
              className="mt-1 w-full border border-border bg-transparent px-3 py-2 text-[14px] text-paper placeholder:text-muted focus:border-accent focus:outline-none"
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
              className="mt-1 w-full border border-border bg-transparent px-3 py-2 text-[14px] text-paper placeholder:text-muted focus:border-accent focus:outline-none"
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
              className="mt-1 w-full border border-border bg-transparent px-3 py-2 text-[14px] text-paper focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 font-mono text-[11px] text-muted">
            <input type="checkbox" name="quant" defaultChecked className="accent-current" />
            measure the innovation chain first (TIR, lead-time, hub patents)
          </label>
          <div className="flex justify-end">
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
              <OrderRow key={o.id} order={o} />
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
              <li key={s.slug} className="bg-ink p-4">
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
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
