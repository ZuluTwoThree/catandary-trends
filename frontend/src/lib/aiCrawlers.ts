/**
 * AI / text-and-data-mining crawlers that are locked out of catandary.de.
 *
 * Owner decision 2026-09-03: the site carries a machine-readable TDM
 * reservation (§44b Abs. 3 UrhG / Art. 4(3) DSM directive — TDMRep header,
 * meta tags, /.well-known/tdmrep.json) AND a hard block for the known AI
 * crawlers. Search engines and link-preview fetchers stay allowed: the site
 * is a lead-gen showcase and must remain indexable.
 *
 * ONE list, three consumers: robots.ts (robots.txt), the .htaccess User-Agent
 * block in public-export/ (403), and a Vitest that keeps the two in sync.
 * Tokens that exist only in robots.txt (Google-Extended, Applebot-Extended)
 * never appear as a User-Agent string; listing them in .htaccess is harmless.
 */
export const AI_CRAWLER_USER_AGENTS: readonly string[] = [
  // OpenAI
  "GPTBot", "ChatGPT-User", "OAI-SearchBot",
  // Anthropic
  "ClaudeBot", "Claude-Web", "Claude-User", "Claude-SearchBot", "anthropic-ai",
  // Google / Apple opt-out tokens (robots.txt only)
  "Google-Extended", "Applebot-Extended",
  // Common Crawl and other corpus builders
  "CCBot", "AI2Bot", "Ai2Bot-Dolma", "Webzio-Extended", "omgili", "omgilibot",
  "Timpibot", "ImagesiftBot", "img2dataset", "Diffbot", "ICC-Crawler",
  // ByteDance, Meta, Amazon, Perplexity, Cohere, Mistral, You.com, Huawei
  "Bytespider", "Meta-ExternalAgent", "Meta-ExternalFetcher", "FacebookBot",
  "Amazonbot", "PerplexityBot", "Perplexity-User", "cohere-ai",
  "cohere-training-data-crawler", "MistralAI-User", "YouBot", "PetalBot",
  "DuckAssistBot", "Kangaroo Bot", "iaskspider",
];

/** Apache RewriteCond regex (case-insensitive use: [NC]). */
export function aiCrawlerRegex(): string {
  return AI_CRAWLER_USER_AGENTS
    .map((ua) => ua.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\ "))
    .join("|");
}
