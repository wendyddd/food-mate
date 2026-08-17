/**
 * food-mate-web memory module type definitions.
 */

/**
 * Memory categories (must match backend MEMORY_CATEGORIES English storage ids).
 */
export const MEMORY_CATEGORIES = [
  "Health & Dietary Restrictions",
  "Taste & Habits",
  "Household & Context",
  "Kitchen & Budget",
  "Other",
] as const;

export type MemoryCategory = (typeof MEMORY_CATEGORIES)[number];

/**
 * 分类展示文案（存储仍用英文 MEMORY_CATEGORIES）。
 */
export const MEMORY_CATEGORY_LABELS: Record<
  MemoryCategory,
  { en: string; zh: string }
> = {
  "Health & Dietary Restrictions": {
    en: "Health & Dietary Restrictions",
    zh: "健康与饮食限制",
  },
  "Taste & Habits": {
    en: "Taste & Habits",
    zh: "口味与习惯",
  },
  "Household & Context": {
    en: "Household & Context",
    zh: "家人与场景",
  },
  "Kitchen & Budget": {
    en: "Kitchen & Budget",
    zh: "厨房设备与预算",
  },
  Other: {
    en: "Other",
    zh: "其他",
  },
};

/**
 * 读取当前界面语言。界面固定为英文。
 *
 * 返回:
 *   "zh" | "en"
 */
export function getUiLocale(): "zh" | "en" {
  return "en";
}

/**
 * 按当前 UI 语言返回分类展示名。
 *
 * 参数:
 *   category - 存储用英文分类名
 *
 * 返回:
 *   展示用标签
 */
export function getCategoryLabel(category: string): string {
  const locale = getUiLocale();
  const labels = MEMORY_CATEGORY_LABELS[category as MemoryCategory];
  if (!labels) return category;
  return labels[locale] || labels.en;
}

/**
 * 单条记忆的一次修改记录。
 */
export interface MemoryRevision {
  content: string;
  category: string;
  changed_at: number;
  new_content: string;
  new_category: string;
  source_type?: string;
  source_session_id?: string;
  source_quote?: string;
}

/**
 * Structured memory entry.
 */
export interface MemoryEntry {
  id: string;
  category: string;
  content: string;
  created_at: number;
  updated_at: number;
  source_type?: string;
  source_session_id?: string;
  source_quote?: string;
  revisions?: MemoryRevision[];
}

/**
 * Memory citation in a chat reply.
 */
export interface MemoryRef {
  id: string;
  category: string;
  content: string;
  source_type?: string;
}

/**
 * memory_updated SSE event payload.
 */
export interface MemoryUpdateEvent {
  changed: boolean;
  added_ids: string[];
  updated_ids: string[];
  deleted_ids: string[];
  entries: MemoryEntry[];
}
