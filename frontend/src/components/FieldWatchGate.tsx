import {
  CONTACT_EMAIL,
  FIELD_WATCH_GATE_CTA,
  FIELD_WATCH_GATE_LABEL,
  FIELD_WATCH_GATE_TEXT,
  FIELD_WATCH_MAILTO,
} from "@/lib/fieldWatchGate";

/**
 * Blurs its children on the public site and explains, on hover, that this
 * part of the page belongs to Field Watch clients (lib/fieldWatchGate.ts).
 *
 * No JavaScript: the hover is CSS (`group-hover`), the panel is also shown
 * when the pointer cannot hover (`.fw-gate-panel` rule in globals.css) and
 * when the mail link receives keyboard focus. `active` is decided on the
 * server (page.tsx: isPublicMode()) — the owner instance renders the
 * children untouched.
 */
export default function FieldWatchGate({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  if (!active) return <>{children}</>;
  return (
    <div className="group relative mt-6" data-testid="field-watch-gate">
      <div
        aria-hidden="true"
        className="pointer-events-none select-none blur-[6px] opacity-50 saturate-50 transition-[filter,opacity] duration-300 group-hover:blur-[9px] group-hover:opacity-35"
      >
        {children}
      </div>
      <div className="absolute inset-0 flex items-start justify-center px-4 pt-12">
        <div
          role="note"
          aria-label={FIELD_WATCH_GATE_LABEL}
          className="fw-gate-panel max-w-md border border-border bg-card p-5 opacity-0 shadow-[0_0_0_1px_var(--color-background)] transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100"
        >
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            {FIELD_WATCH_GATE_LABEL}
          </p>
          <p className="font-sans text-[14px] leading-[1.6] text-text">{FIELD_WATCH_GATE_TEXT}</p>
          <p className="mt-3 font-sans text-[14px] leading-[1.6] text-muted">
            {FIELD_WATCH_GATE_CTA}{" "}
            <a href={FIELD_WATCH_MAILTO} className="text-accent hover:underline">
              {CONTACT_EMAIL}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
