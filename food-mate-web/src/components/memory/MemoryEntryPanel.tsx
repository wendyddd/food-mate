"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Brain,
  Loader2,
  Download,
  Search,
} from "lucide-react";
import {
  listMemoryEntries,
  createMemoryEntry,
  updateMemoryEntry,
  deleteMemoryEntry,
  getUserMemoryMarkdown,
} from "@/lib/api";
import { MEMORY_CATEGORIES, type MemoryEntry } from "@/lib/types";
import { useT } from "@/lib/i18n";
import {
  USER_SOURCE_GROUPS,
  getSourceVisual,
  toUserSourceGroup,
} from "@/lib/memoryVisuals";
import MemoryCategorySection from "./MemoryCategorySection";
import MemoryOverview from "./MemoryOverview";

/**
 * 结构化记忆编辑器主面板（总览 + 筛选 + 按类目 CRUD）。
 * 支持 ?entry=mem_xxx 从聊天引用定位到对应条目。
 */
export default function MemoryEntryPanel() {
  const t = useT();
  const searchParams = useSearchParams();
  const focusEntryId = searchParams.get("entry");

  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightEntryId, setHighlightEntryId] = useState<string | null>(null);
  /** 已完成定位的 entry id，避免 entries 更新时重复滚动 */
  const scrolledEntryRef = useRef<string | null>(null);

  const loadEntries = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listMemoryEntries();
      setEntries(data);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  /**
   * 根据 URL ?entry= 定位并短暂高亮目标记忆卡片。
   * 使用重试滚动，避免分类尚未展开时 DOM 不存在；
   * 仅在滚动成功后标记已处理，避免 Strict Mode 清理定时器后二次跳过。
   */
  useEffect(() => {
    if (loading || !focusEntryId) return;
    if (scrolledEntryRef.current === focusEntryId) return;

    const target = entries.find((e) => e.id === focusEntryId);
    if (!target) return;

    // 清除筛选，确保目标条目可见
    setSourceFilter("all");
    setSearchQuery("");
    setHighlightEntryId(focusEntryId);

    let cancelled = false;
    let attempts = 0;
    let retryTimer = 0;
    let clearHighlightTimer = 0;

    /**
     * 尝试滚动到目标卡片；若尚未挂载则短间隔重试。
     */
    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(focusEntryId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        scrolledEntryRef.current = focusEntryId;
        clearHighlightTimer = window.setTimeout(() => {
          if (!cancelled) setHighlightEntryId(null);
        }, 3200);
        return;
      }
      attempts += 1;
      if (attempts < 25) {
        retryTimer = window.setTimeout(tryScroll, 80);
      }
    };

    const startTimer = window.setTimeout(tryScroll, 80);

    return () => {
      cancelled = true;
      window.clearTimeout(startTimer);
      window.clearTimeout(retryTimer);
      window.clearTimeout(clearHighlightTimer);
    };
  }, [loading, focusEntryId, entries]);

  const handleAdd = async (category: string, content: string) => {
    const entry = await createMemoryEntry(category, content);
    setEntries((prev) => [...prev, entry]);
  };

  const handleUpdate = async (
    id: string,
    content: string,
    category: string,
  ) => {
    const entry = await updateMemoryEntry(id, content, category);
    setEntries((prev) => prev.map((e) => (e.id === id ? entry : e)));
  };

  const handleDelete = async (id: string) => {
    await deleteMemoryEntry(id);
    setEntries((prev) => prev.filter((e) => e.id !== id));
  };

  const handleExportMarkdown = async () => {
    try {
      const md = await getUserMemoryMarkdown();
      const blob = new Blob([md], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "user.md";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    }
  };

  /** 按来源与关键字过滤后的条目 */
  const filteredEntries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return entries.filter((e) => {
      if (sourceFilter !== "all") {
        if (toUserSourceGroup(e.source_type) !== sourceFilter) return false;
      }
      if (
        q &&
        !e.content.toLowerCase().includes(q) &&
        !e.id.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [entries, sourceFilter, searchQuery]);

  const entriesByCategory = MEMORY_CATEGORIES.reduce(
    (acc, cat) => {
      acc[cat] = filteredEntries.filter((e) => e.category === cat);
      return acc;
    },
    {} as Record<string, MemoryEntry[]>,
  );

  const isFiltering = sourceFilter !== "all" || searchQuery.trim().length > 0;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: "var(--accent-bg)" }}
          >
            <Brain className="w-5 h-5" style={{ color: "var(--accent)" }} />
          </div>
          <div>
            <h1
              className="text-[16px] font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {t("memory.title")}
            </h1>
            <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>
              {t("memory.count", { count: entries.length })}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] transition-all hover:opacity-80"
            style={{
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
            }}
            title={t("memory.exportTitle")}
          >
            <Download className="w-3.5 h-3.5" />
            {t("memory.export")}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {loading ? (
          <div
            className="flex items-center justify-center py-20"
            style={{ color: "var(--text-muted)" }}
          >
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            {t("memory.loading")}
          </div>
        ) : (
          <>
            <MemoryOverview entries={entries} />

            {/* 筛选栏 */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative flex-1 min-w-[160px]">
                <Search
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("memory.searchPlaceholder")}
                  className="w-full pl-8 pr-3 py-1.5 rounded-lg text-[12px] outline-none"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    color: "var(--text-primary)",
                  }}
                />
              </div>
              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                className="text-[12px] px-2.5 py-1.5 rounded-lg outline-none"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-secondary)",
                }}
              >
                <option value="all">{t("memory.filterAll")}</option>
                {USER_SOURCE_GROUPS.map((group) => {
                  const visual = getSourceVisual(group);
                  return (
                    <option key={group} value={group}>
                      {t(visual.labelKey)}
                    </option>
                  );
                })}
              </select>
            </div>

            {isFiltering && filteredEntries.length === 0 ? (
              <p
                className="text-[13px] text-center py-8"
                style={{ color: "var(--text-muted)" }}
              >
                {t("memory.noMatch")}
              </p>
            ) : (
              MEMORY_CATEGORIES.map((category) => {
                const catEntries = entriesByCategory[category] || [];
                // 筛选时隐藏空分类，未筛选时保留全部以便新增
                if (isFiltering && catEntries.length === 0) return null;
                return (
                  <MemoryCategorySection
                    key={category}
                    category={category}
                    entries={catEntries}
                    highlightEntryId={highlightEntryId}
                    focusEntryId={focusEntryId}
                    onAdd={handleAdd}
                    onUpdate={handleUpdate}
                    onDelete={handleDelete}
                  />
                );
              })
            )}
          </>
        )}
      </div>
    </div>
  );
}
