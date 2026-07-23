"use client";

/**
 * Root error boundary — rendered when the layout itself fails, so it must
 * bring its own <html>/<body> and inline styling (globals.css may not load).
 */
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          background: "#0a0c0a",
          color: "#d8d5c8",
          fontFamily: "system-ui, sans-serif",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "2rem",
        }}
      >
        <div>
          <h1 style={{ color: "#f4f1e8", fontSize: "1.6rem", marginBottom: "0.8rem" }}>
            Catandary Trends is briefly unavailable.
          </h1>
          <p style={{ color: "#8a8d82", maxWidth: "28rem", margin: "0 auto 1.5rem" }}>
            An unexpected error stopped the page from loading. Please try
            again — if it keeps happening, come back in a few minutes.
          </p>
          <button
            onClick={reset}
            style={{
              background: "#d4ff3a",
              color: "#0a0c0a",
              border: "none",
              padding: "0.7rem 1.4rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
