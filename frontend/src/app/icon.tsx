import { ImageResponse } from "next/og";

/**
 * Favicon (#64→#93 P0). Generated at request time by Next — no binary asset
 * to track. Ink ground + chartreuse "C" from the Editorial-Intelligence
 * palette (globals.css); replace with a designed icon file (app/icon.png)
 * whenever one exists — a static file takes precedence over this route.
 */
// Route handlers must be `force-static` (literal) for `output: "export"`;
// no input varies here, so the workstation build renders it once as well.
export const dynamic = "force-static";
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0c0a",
          color: "#d4ff3a",
          fontSize: 22,
          fontWeight: 700,
          fontFamily: "Georgia, serif",
        }}
      >
        C
      </div>
    ),
    size
  );
}
