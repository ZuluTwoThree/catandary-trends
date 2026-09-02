import { ImageResponse } from "next/og";

/**
 * Site-wide default OG image (#93 owner audit comment, 2026-08-27: "OG-/
 * Social-Bild + Favicon für die Site"). Applies to every route that doesn't
 * define its own `openGraph.images` — in particular `/analysis/[slug]` when
 * the frontmatter `image` file is missing (see `generateMetadata` there).
 *
 * Deliberately schematic, not a screenshot: an ink background, the chartreuse
 * accent rule, wordmark and tagline. No photo, no fabricated chart — the
 * brand rule the launch-honesty pass already applies to page copy applies
 * here too (nothing implying data that isn't shown).
 */

export const alt = "Catandary Trends";
// Route handlers must be `force-static` (literal) for `output: "export"`.
export const dynamic = "force-static";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const TITLE_TEXT = "Catandary Trends";
const TAGLINE_TEXT = "CROSS-INDUSTRY TREND INTELLIGENCE";

interface OgFont {
  data: ArrayBuffer;
  name: string;
  weight: 500;
  style: "normal";
}

/**
 * Best-effort fetch of an IBM Plex weight as a TTF ArrayBuffer for satori
 * (the renderer behind `ImageResponse`). Google's CSS2 endpoint serves
 * WOFF2 to browser user agents that advertise support for it, but falls
 * back to a plain `format('truetype')` `src` for a UA it doesn't recognize
 * — which is exactly what an unadorned `fetch()` (Node's default UA) gets,
 * verified against the live endpoint. No UA spoofing needed.
 *
 * This route has no dynamic segment, so Next renders it once at build time
 * — a failed fetch (offline build, Google Fonts unreachable, response
 * shape changes) falls back to satori's built-in default font rather than
 * failing the build. `Image()` below must never pass an empty `fonts`
 * array to `ImageResponse` — satori throws ("No fonts are loaded") rather
 * than falling back — so callers omit the option entirely when this
 * returns null for both weights.
 */
async function loadGoogleFont(family: string, text: string): Promise<ArrayBuffer | null> {
  try {
    const cssUrl = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(
      family
    )}:wght@500&text=${encodeURIComponent(text)}`;
    const cssRes = await fetch(cssUrl);
    if (!cssRes.ok) return null;
    const css = await cssRes.text();

    const match = /src: url\(([^)]+)\) format\('truetype'\)/.exec(css);
    if (!match) return null;

    const fontRes = await fetch(match[1]);
    if (!fontRes.ok) return null;
    return await fontRes.arrayBuffer();
  } catch {
    return null;
  }
}

export default async function Image() {
  const [serifData, monoData] = await Promise.all([
    loadGoogleFont("IBM Plex Serif", TITLE_TEXT),
    loadGoogleFont("IBM Plex Mono", TAGLINE_TEXT),
  ]);

  const fonts: OgFont[] = [];
  if (serifData) fonts.push({ name: "IBM Plex Serif", data: serifData, weight: 500, style: "normal" });
  if (monoData) fonts.push({ name: "IBM Plex Mono", data: monoData, weight: 500, style: "normal" });

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          backgroundColor: "#0a0c0a",
          padding: "88px",
        }}
      >
        <div
          style={{
            display: "flex",
            width: 72,
            height: 6,
            backgroundColor: "#d4ff3a",
            marginBottom: 44,
          }}
        />
        <div
          style={{
            display: "flex",
            fontSize: 76,
            color: "#f4f1e8",
            fontWeight: 500,
            // Satori chokes on an explicit `fontFamily: undefined` (throws deep
            // inside its style resolver instead of ignoring it like a browser
            // would) — omit the key entirely rather than set it to undefined.
            ...(serifData ? { fontFamily: "IBM Plex Serif" } : {}),
          }}
        >
          {TITLE_TEXT}
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 26,
            color: "#8a8d82",
            marginTop: 28,
            letterSpacing: 6,
            ...(monoData ? { fontFamily: "IBM Plex Mono" } : {}),
          }}
        >
          {TAGLINE_TEXT}
        </div>
      </div>
    ),
    // Same reasoning as the style objects above: an empty `fonts: []` makes
    // satori throw ("No fonts are loaded") instead of using its built-in
    // default, so the key is omitted rather than passed empty.
    fonts.length > 0 ? { ...size, fonts } : size
  );
}
