/**
 * Licence notices that some primary sources require when their data is
 * re-published (docs/compliance/attribution_matrix.md, 2026-09-03). Matched
 * on `trends.source_name`; everything else needs only name + backlink.
 */
export type SourceLicenseNotice = {
  text: string;        // rendered verbatim under the source line
  licenseUrl: string;  // linked licence text
  licenseName: string; // link label
};

const NOTICES: Array<{ pattern: RegExp; notice: SourceLicenseNotice }> = [
  {
    pattern: /openaire/i,
    notice: {
      text: "Contains data from the OpenAIRE Graph (© OpenAIRE), processed by Catandary.",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      licenseName: "CC BY 4.0",
    },
  },
  {
    pattern: /cordis/i,
    notice: {
      text: "Contains data from the European Union's CORDIS database (© European Union), processed by Catandary.",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      licenseName: "CC BY 4.0",
    },
  },
  {
    pattern: /ukri|gateway to research/i,
    notice: {
      text: "Contains public sector information from UKRI Gateway to Research.",
      licenseUrl: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      licenseName: "Open Government Licence v3.0",
    },
  },
];

export function sourceLicenseNotice(sourceName: string | null | undefined): SourceLicenseNotice | null {
  if (!sourceName) return null;
  for (const { pattern, notice } of NOTICES) {
    if (pattern.test(sourceName)) return notice;
  }
  return null;
}
