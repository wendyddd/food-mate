/**
 * Memory body text → keywords for card display.
 */

const STRONG_SPLIT = /[;；|/\n]+|(?<=[.。！？!?])\s+|\s*[—–]\s+/;

/**
 * Strip parenthetical notes and long modifiers to get a shorter display phrase.
 *
 * @param segment - Original clause
 * @returns Shortened keyword, or empty string if invalid
 */
function toKeywordPhrase(segment: string): string {
  let s = segment
    .replace(/\([^)]*\)/g, "")
    .replace(/（[^）]*）/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();

  // Strip extra trailing punctuation
  s = s.replace(/[,，.。;；:：!！?？]+$/g, "").trim();

  if (!s) return "";

  // If too long, keep the topic before the colon; otherwise truncate
  if (s.length > 40) {
    const colonIdx = s.search(/[:：]/);
    if (colonIdx > 0 && colonIdx <= 36) {
      s = s.slice(0, colonIdx).trim();
    } else {
      s = `${s.slice(0, 36).trimEnd()}…`;
    }
  }

  return s;
}

/**
 * Split memory body text into keywords for card chips.
 * The full original text stays in entry.content and is unchanged when editing.
 *
 * @param content - Memory body text
 * @param maxItems - Maximum number of keywords to show
 * @returns Keyword list; if splitting fails, a single shortened original
 */
export function splitMemoryKeywords(
  content: string,
  maxItems = 8,
): string[] {
  const raw = (content || "").trim();
  if (!raw) return [];

  let parts = raw
    .split(STRONG_SPLIT)
    .map((p) => p.trim())
    .filter(Boolean);

  // If a single segment is too long, try splitting on commas
  if (parts.length === 1 && parts[0].length > 48) {
    const byComma = parts[0]
      .split(/[,，]/)
      .map((p) => p.trim())
      .filter(Boolean);
    if (byComma.length >= 2) parts = byComma;
  }

  const seen = new Set<string>();
  const keywords: string[] = [];

  for (const part of parts) {
    const kw = toKeywordPhrase(part);
    if (!kw) continue;
    const key = kw.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    keywords.push(kw);
    if (keywords.length >= maxItems) break;
  }

  return keywords.length > 0 ? keywords : [toKeywordPhrase(raw) || raw];
}
