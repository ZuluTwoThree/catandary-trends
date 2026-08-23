/**
 * Attributionssätze für den Startup Explorer — verbindliche Launch-Bedingung
 * (Owner 2026-08-21, docs/startup_explorer_plan.md): OGL v3 (Companies House)
 * und CC BY 4.0 (CORDIS) verlangen sichtbare Nennung, wo die Daten erscheinen.
 * CC0-/Public-Domain-Quellen werden aus Transparenzgründen mitgenannt.
 */
export default function VentureAttribution() {
  return (
    <footer className="mt-10 border-t border-border pt-4">
      <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted leading-relaxed">
        Data sources: SEC EDGAR Form D &amp; SBIR.gov (public domain) · Contains
        data from the European Union&apos;s CORDIS database (© European Union),
        licensed under{" "}
        <a href="https://creativecommons.org/licenses/by/4.0/" className="underline hover:text-paper" rel="noopener noreferrer" target="_blank">
          CC BY 4.0
        </a>
        ; data has been processed (filtered, classified, linked) by Catandary ·
        Contains Companies House data © Crown copyright and database right ·
        GLEIF &amp; Wikidata (CC0) · Hacker News · ClinicalTrials.gov · openFDA
        (not validated for clinical use). Every event links to its primary
        source.
      </p>
    </footer>
  );
}
