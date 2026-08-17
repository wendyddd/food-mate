/**
 * 记忆正文 → 卡片展示用关键词。
 */

const STRONG_SPLIT = /[;；|/\n]+|(?<=[.。！？!?])\s+|\s*[—–]\s+/;

/**
 * 去掉括号说明与冗长修饰，得到更短的展示短语。
 *
 * 参数:
 * segment (string): 原始分句
 *
 * 返回:
 * string: 精简后的关键词；无效则为空串
 */
function toKeywordPhrase(segment: string): string {
  let s = segment
    .replace(/\([^)]*\)/g, "")
    .replace(/（[^）]*）/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();

  // 去掉句末多余标点
  s = s.replace(/[,，.。;；:：!！?？]+$/g, "").trim();

  if (!s) return "";

  // 过长时优先保留冒号前主题，否则截断
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
 * 将记忆正文拆成关键词列表，供卡片 chip 展示。
 * 完整原文仍保存在 entry.content，编辑时不受影响。
 *
 * 参数:
 * content (string): 记忆正文
 * maxItems (number): 最多展示条数
 *
 * 返回:
 * string[]: 关键词列表；无法拆分时返回单元素原文精简版
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

  // 单段过长时尝试按逗号再拆
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
