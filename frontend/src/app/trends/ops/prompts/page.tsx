import Link from "next/link";
import { notFound } from "next/navigation";
import { canOps } from "@/lib/ops-access";
import { groupEntries, loadPromptCatalog, type PromptEntry } from "@/lib/promptCatalog";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Prompts — Ops — Catandary",
  robots: { index: false, follow: false },
};

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{children}</div>;
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[92px_1fr] gap-2 text-[13px]">
      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted pt-[3px]">{k}</span>
      <span className="text-text">{v}</span>
    </div>
  );
}

function PromptBlock({ title, text, open }: { title: string; text: string; open?: boolean }) {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return (
    <details className="group border border-border bg-ink/40" open={open}>
      <summary className="cursor-pointer select-none px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper flex items-center justify-between">
        <span>{title}</span>
        <span>{text.length.toLocaleString("en-US")} chars · {words.toLocaleString("en-US")} words</span>
      </summary>
      <pre className="px-3 pb-3 pt-1 whitespace-pre-wrap break-words font-mono text-[12px] leading-[1.55] text-paper/90 max-h-[70vh] overflow-y-auto">{text}</pre>
    </details>
  );
}

function Entry({ e }: { e: PromptEntry }) {
  return (
    <article id={e.key} className={`border p-4 bg-card space-y-3 scroll-mt-6 ${e.error ? "border-warn" : "border-border"}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display text-[20px] leading-tight text-paper">{e.title}</h3>
        <a href={`#${e.key}`} className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent">#{e.key}</a>
      </header>
      <p className="font-sans text-sm leading-relaxed text-text">{e.function}</p>
      <div className="space-y-1">
        <Meta k="Model" v={e.model} />
        <Meta k="Runs" v={e.trigger} />
        <Meta k="Source" v={e.file ? `${e.file}:${e.line} — ${e.symbol}` : e.symbol} />
      </div>
      {e.notes.length > 0 && (
        <ul className="list-disc pl-5 text-[13px] text-muted space-y-0.5">
          {e.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      {e.error ? (
        <p className="border border-warn bg-warn/10 p-3 font-mono text-[12px] text-warn">Could not load: {e.error}</p>
      ) : (
        <div className="space-y-2">
          <PromptBlock title="System instruction" text={e.system} />
          {e.user_template && (
            <PromptBlock
              title={e.user_template_kind === "source" ? "User prompt · builder source" : "User prompt · template"}
              text={e.user_template}
            />
          )}
        </div>
      )}
    </article>
  );
}

export default async function PromptsPage() {
  if (!canOps()) notFound();
  const { data, error, cachedAt } = loadPromptCatalog();
  const groups = data ? groupEntries(data) : [];
  const total = data?.entries.length ?? 0;
  const broken = data?.entries.filter((e) => e.error).length ?? 0;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/trends/ops" className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent">← Ops</Link>
          <Label>Owner · not public</Label>
        </div>
        <h1 className="font-display text-3xl text-paper">Prompts</h1>
        <p className="text-muted text-sm max-w-3xl">
          Every system instruction a language model receives in this system, read live from the code — with what the
          surrounding function does, when it runs and which model answers. {total} entries
          {broken > 0 ? `, ${broken} could not be loaded` : ""}
          {cachedAt ? ` · read ${cachedAt.toLocaleTimeString("en-GB")}` : ""}.
        </p>
        {error && (
          <p className="border border-warn bg-warn/10 p-3 font-mono text-[12px] text-warn">
            Catalogue could not be refreshed: {error}{data ? " — showing the last successful read." : ""}
          </p>
        )}
      </header>

      {data && (
        <nav className="border border-border bg-card p-4">
          <Label>Index</Label>
          <div className="mt-2 grid gap-x-8 gap-y-1 sm:grid-cols-2 text-[13px]">
            {groups.map((g) => (
              <div key={g.key} className="space-y-0.5">
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-accent mt-2">{g.title}</div>
                {g.entries.map((e) => (
                  <div key={e.key}>
                    <a href={`#${e.key}`} className="text-text hover:text-accent">{e.title}</a>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </nav>
      )}

      {groups.map((g) => (
        <section key={g.key} className="space-y-3">
          <Label>{g.title}</Label>
          <div className="space-y-4">
            {g.entries.map((e) => <Entry key={e.key} e={e} />)}
          </div>
        </section>
      ))}

      <footer className="text-muted text-xs">
        Source of this page: <code className="font-mono">pipeline/prompt_catalog.py</code> (<code className="font-mono">python -m pipeline.prompt_catalog --list</code>).
        Not in the catalogue: embedding calls (no instruction), the distilled classification heads (no model), and the A/B, benchmark and eval scripts under <code className="font-mono">scripts/</code>.
      </footer>
    </main>
  );
}
