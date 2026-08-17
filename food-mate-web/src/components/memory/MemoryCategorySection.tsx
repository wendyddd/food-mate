"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { MemoryEntry, MemoryCategory } from "@/lib/types";
import { useT, type MessageKey } from "@/lib/i18n";
import { getCategoryVisual } from "@/lib/memoryVisuals";
import MemoryEntryCard from "./MemoryEntryCard";
import MemoryEntryForm from "./MemoryEntryForm";

interface Props {
  category: string;
  entries: MemoryEntry[];
  onAdd: (category: string, content: string) => Promise<void>;
  onUpdate: (id: string, content: string, category: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  defaultOpen?: boolean;
  /** 需要视觉高亮的记忆条目 id */
  highlightEntryId?: string | null;
  /** URL 中的目标条目 id（用于首次展开所在分类） */
  focusEntryId?: string | null;
}

/**
 * 按分区展示记忆条目；展开后以普通卡片网格呈现。
 */
export default function MemoryCategorySection({
  category,
  entries,
  onAdd,
  onUpdate,
  onDelete,
  defaultOpen = true,
  highlightEntryId = null,
  focusEntryId = null,
}: Props) {
  const t = useT();
  const locateEntryId = highlightEntryId || focusEntryId;
  const containsTarget = Boolean(
    locateEntryId && entries.some((e) => e.id === locateEntryId),
  );
  const [open, setOpen] = useState(
    containsTarget ? true : category === "Other" ? false : defaultOpen,
  );
  const label = t(`category.${category as MemoryCategory}` as MessageKey);
  const description = t(
    `category.${category as MemoryCategory}.desc` as MessageKey,
  );
  const entryWord =
    entries.length === 1 ? t("common.entry") : t("common.entries");
  const visual = getCategoryVisual(category);
  const CatIcon = visual.icon;

  /**
   * 从聊天引用跳转时，展开目标条目所在分类。
   */
  useEffect(() => {
    if (containsTarget) setOpen(true);
  }, [containsTarget]);

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: "1px solid var(--border)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:opacity-90 transition-opacity"
        style={{ background: "var(--bg-surface)" }}
      >
        {open ? (
          <ChevronDown
            className="w-4 h-4 shrink-0"
            style={{ color: "var(--accent)" }}
          />
        ) : (
          <ChevronRight
            className="w-4 h-4 shrink-0"
            style={{ color: "var(--accent)" }}
          />
        )}
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
          style={{ background: visual.bg }}
        >
          <CatIcon className="w-3.5 h-3.5" style={{ color: visual.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="text-[14px] font-semibold truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {label}
            </span>
            <span
              className="text-[11px] px-2 py-0.5 rounded-full shrink-0"
              style={{
                background: "var(--accent-bg)",
                color: "var(--accent)",
              }}
            >
              {entries.length} {entryWord}
            </span>
          </div>
          <span
            className="block text-[11px] mt-0.5 leading-snug"
            style={{ color: "var(--text-muted)" }}
          >
            {description}
          </span>
        </div>
      </button>

      {open && (
        <div
          className="px-4 pb-4 pt-3"
          style={{ background: "var(--bg-page)" }}
        >
          <div className="memory-entry-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {entries.map((entry, index) => (
              <MemoryEntryCard
                key={entry.id}
                entry={entry}
                index={index}
                highlighted={entry.id === highlightEntryId}
                onUpdate={onUpdate}
                onDelete={onDelete}
              />
            ))}
            <MemoryEntryForm
              category={category}
              onSubmit={onAdd}
              index={entries.length}
            />
          </div>
        </div>
      )}
    </div>
  );
}
