/**
 * 记忆分类与来源的图标、主题色映射，供总览、卡片、引用统一复用。
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

/** 记忆来源类型（与后端 MemorySourceType 对齐） */
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

/** 面向用户的来源分组：手动添加 / 来自对话 */
export type UserSourceGroup = "manual" | "chat";

export const USER_SOURCE_GROUPS: UserSourceGroup[] = ["manual", "chat"];

export interface VisualStyle {
  icon: LucideIcon;
  /** CSS 颜色值，用于图标与徽标 */
  color: string;
  /** 浅色背景 */
  bg: string;
}

/** 五个固定分类的视觉样式 */
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

/** 用户可见的两类来源样式 */
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
 * 按分类名获取视觉样式；未知分类回退到 Other。
 *
 * 参数:
 *   category - 分类 id
 *
 * 返回:
 *   VisualStyle
 */
export function getCategoryVisual(category: string): VisualStyle {
  return CATEGORY_VISUALS[category as MemoryCategory] || CATEGORY_VISUALS.Other;
}

/**
 * 将后端来源类型映射为用户可见分组。
 *
 * 参数:
 *   sourceType - 原始来源（可为 undefined）
 *
 * 返回:
 *   UserSourceGroup — manual 或 chat
 */
export function toUserSourceGroup(
  sourceType?: string | null,
): UserSourceGroup {
  const normalized = normalizeSourceType(sourceType);
  return normalized === "manual" ? "manual" : "chat";
}

/**
 * 按来源类型获取用户可见的视觉样式与文案 key。
 *
 * 参数:
 *   sourceType - 来源类型字符串（可为 undefined）
 *
 * 返回:
 *   带来源文案 key 的视觉样式
 */
export function getSourceVisual(
  sourceType?: string | null,
): VisualStyle & { labelKey: MessageKey } {
  return USER_SOURCE_VISUALS[toUserSourceGroup(sourceType)];
}

/**
 * 规范化来源类型；空值视为 manual。
 *
 * 参数:
 *   sourceType - 原始来源
 *
 * 返回:
 *   MemorySourceType | "unknown"
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
