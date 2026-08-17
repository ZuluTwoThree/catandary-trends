import Link from "next/link";
import { splitAuthors } from "@/lib/research-authors";

/** Autoren-Zeile mit sichtbarer Klick-Affordanz (#83).
 *
 *  Vorher trugen die Namen nur ein `hover:text-accent` — im Ruhezustand war
 *  nicht erkennbar, dass sie Links sind (Owner-Befund 2026-08-17). Jetzt:
 *  mono-Micro-Label „by" wie in der Meta-Zeile darüber, Namen eine Stufe
 *  heller als der umgebende Fließtext (text statt muted) und mit gepunkteter
 *  Unterstreichung in border-strong (~3:1 auf Ink, sichtbar ohne zu schreien).
 *  Beim Hover/Fokus wird daraus durchgezogenes Chartreuse. Der „+N more"-
 *  Zähler bleibt muted und ohne Unterstreichung — er ist kein Link.
 */
export default function AuthorLine({
  authors, limit = 3, className = "",
}: {
  authors: string | null;
  limit?: number;
  className?: string;
}) {
  const { shown, more } = splitAuthors(authors, limit);
  if (!shown.length) return null;
  return (
    <div className={`font-sans text-[12px] leading-relaxed text-muted ${className}`}>
      <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted/80 mr-1.5">
        by
      </span>
      {shown.map((a, i) => (
        <span key={a + i}>
          {i > 0 && <span className="text-muted/60">, </span>}
          <Link
            href={`/trends/foresight/research?q=${encodeURIComponent(`author:"${a}"`)}`}
            title={`All papers by ${a}`}
            className="text-text underline decoration-dotted decoration-border-strong underline-offset-[3px]
                       hover:text-accent hover:decoration-solid hover:decoration-accent
                       focus-visible:text-accent focus-visible:decoration-solid focus-visible:decoration-accent
                       transition-colors"
          >
            {a}
          </Link>
        </span>
      ))}
      {more > 0 && <span className="text-muted/70"> +{more} more</span>}
    </div>
  );
}
