/**
 * Serialise a JSON-LD object for inline `<script type="application/ld+json">`
 * embedding (security review 2026-09-02, F-2).
 *
 * `JSON.stringify` alone is not safe inside a script element: the HTML parser
 * ends the block at the first `</script>` regardless of JSON string quoting,
 * so a feed title (or an LLM echo of it) containing `</script><script>…`
 * breaks out and runs. With a static export that would be baked into the
 * HTML permanently. Escaping the three HTML-significant characters as JSON
 * `\uXXXX` sequences keeps the payload valid JSON (parsers decode them back)
 * while the raw bytes `<`, `>` and `&` never appear in the markup. U+2028/9
 * are escaped too — they are legal in JSON but line terminators in JS.
 */
export function serializeJsonLd(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
