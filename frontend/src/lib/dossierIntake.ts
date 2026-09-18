/**
 * Deterministic question check for the dossier order form — TypeScript mirror
 * of pipeline/dossier_brief.deterministic_question_check (stage 1 of the
 * dossier-agent plan, 2026-09-19). Same rule on both sides: an empty field is
 * fine (the standard foresight question applies); otherwise the text must
 * contain a "?" or open with an interrogative. A purpose or reader description
 * ("The purpose of the dossier is …", datacenter v1) is rejected — the client
 * form refuses to submit it, the server action refuses to store it, and the
 * worker refuses to research it. The Python rule is the source of truth; keep
 * the word list in sync.
 */

const INTERROGATIVE = new Set([
  "which", "what", "how", "when", "where", "who", "whom", "whose", "why",
  "should", "is", "are", "does", "do", "can", "could", "will", "would",
  "may", "might", "must", "has", "have", "did", "was", "were", "whether",
  "welche", "welcher", "welches", "welchen", "was", "wie", "wann", "wo",
  "wer", "wem", "wen", "wessen", "warum", "wieso", "weshalb", "soll",
  "sollte", "sollten", "ist", "sind", "kann", "können", "wird", "werden",
  "gibt", "lohnt", "ob",
]);

export interface QuestionCheck {
  ok: boolean;
  reason: string;
}

export function questionCheck(question: string | null | undefined): QuestionCheck {
  const q = (question ?? "").split(/\s+/).filter(Boolean).join(" ");
  if (!q) return { ok: true, reason: "" };
  if (q.includes("?")) return { ok: true, reason: "" };
  const first = q
    .replace(/^["'„“(\[]+/, "")
    .split(" ", 1)[0]
    .toLowerCase()
    .replace(/[,.:;]+$/, "");
  if (INTERROGATIVE.has(first)) return { ok: true, reason: "" };
  return {
    ok: false,
    reason:
      "The question field does not ask anything (no '?' and no interrogative opening): " +
      "it reads as a purpose or reader description. Write the question first; put context " +
      "about the reader in a second sentence after it.",
  };
}
