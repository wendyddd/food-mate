/**
 * Icon and theme-color maps for memory categories and sources, reused by overview, cards, and citations.
 */

import type { LucideIcon } from "lucide-react";
import {
  HeartPulse,
  Utensils,
  Users,
  ChefHat,
  MoreHorizontal,
  PenLine,
  MessageSquare,
} from "lucide-react";
import type { MemoryCategory } from "./types";
import type { MessageKey } from "./i18n";

/** Memory source type (aligned with backend MemorySourceType) */
export type MemorySourceType =
  | "judge"
  | "manual"
  | "extract"
  | "tool"
  | "migrate";

export const MEMORY_SOURCE_TYPES: MemorySourceType[] = [
  "judge",
  "manual",
  "extract",
  "tool",
  "migrate",
];

/** User-facing source groups: manually added / from chat */
export type UserSourceGroup = "manual" | "chat";

export const USER_SOURCE_GROUPS: UserSourceGroup[] = ["manual", "chat"];

export interface VisualStyle {
  icon: LucideIcon;
  /** CSS color for icons and badges */
  color: string;
  /** Light background */
  bg: string;
}

/** Visual styles for the five fixed categories */
export const CATEGORY_VISUALS: Record<MemoryCategory, VisualStyle> = {
  "Health & Dietary Restrictions": {
    icon: HeartPulse,
    color: "#e11d48",
    bg: "rgba(225, 29, 72, 0.1)",
  },
  "Taste & Habits": {
    icon: Utensils,
    color: "#ea580c",
    bg: "rgba(234, 88, 12, 0.1)",
  },
  "Household & Context": {
    icon: Users,
    color: "#2563eb",
    bg: "rgba(37, 99, 235, 0.1)",
  },
  "Kitchen & Budget": {
    icon: ChefHat,
    color: "#16a34a",
    bg: "rgba(22, 163, 74, 0.1)",
  },
  Other: {
    icon: MoreHorizontal,
    color: "#6b7280",
    bg: "rgba(107, 114, 128, 0.1)",
  },
};

/** Visual styles for the two user-visible source groups */
export const USER_SOURCE_VISUALS: Record<
  UserSourceGroup,
  VisualStyle & { labelKey: MessageKey }
> = {
  manual: {
    icon: PenLine,
    color: "#0891b2",
    bg: "rgba(8, 145, 178, 0.1)",
    labelKey: "memory.source.manual",
  },
  chat: {
    icon: MessageSquare,
    color: "#7c3aed",
    bg: "rgba(124, 58, 237, 0.1)",
    labelKey: "memory.source.chat",
  },
};

/**
 * Get visual style by category name; unknown categories fall back to Other.
 *
 * @param category - Category id
 * @returns VisualStyle
 */
export function getCategoryVisual(category: string): VisualStyle {
  return CATEGORY_VISUALS[category as MemoryCategory] || CATEGORY_VISUALS.Other;
}

/**
 * Map a backend source type to a user-visible group.
 *
 * @param sourceType - Raw source (may be undefined)
 * @returns UserSourceGroup — manual or chat
 */
export function toUserSourceGroup(
  sourceType?: string | null,
): UserSourceGroup {
  const normalized = normalizeSourceType(sourceType);
  return normalized === "manual" ? "manual" : "chat";
}

/**
 * Get user-visible visual style and copy key by source type.
 *
 * @param sourceType - Source type string (may be undefined)
 * @returns Visual style including the source label key
 */
export function getSourceVisual(
  sourceType?: string | null,
): VisualStyle & { labelKey: MessageKey } {
  return USER_SOURCE_VISUALS[toUserSourceGroup(sourceType)];
}

/**
 * Normalize a source type; empty values are treated as manual.
 *
 * @param sourceType - Raw source
 * @returns MemorySourceType | "unknown"
 */
export function normalizeSourceType(
  sourceType?: string | null,
): MemorySourceType | "unknown" {
  if (
    sourceType &&
    MEMORY_SOURCE_TYPES.includes(sourceType as MemorySourceType)
  ) {
    return sourceType as MemorySourceType;
  }
  if (!sourceType) return "manual";
  return "unknown";
}
