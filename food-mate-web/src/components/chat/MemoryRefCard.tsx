"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, BookOpen, ArrowUpRight } from "lucide-react";
import type { MemoryRef } from "@/lib/types";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { splitMemoryKeywords } from "@/lib/memoryKeywords";

interface Props {
  refs: MemoryRef[];
}

/**
 * Memory citations in a chat reply: capsule chips; click jumps to the matching entry on the memory page.
 */
export default function MemoryRefCard({ refs }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { userSession } = useAuth();
  const t = useT();

  if (refs.length === 0) return null;

  return (
    <div
      className="mt-1.5 mb-2 rounded-xl overflow-hidden animate-fade-in-scale"
      style={{
        border: "1px solid var(--border-accent)",
        background: "var(--accent-bg)",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] hover:opacity-80 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="w-3 h-3" style={{ color: "var(--accent)" }} />
        ) : (
          <ChevronRight
            className="w-3 h-3"
            style={{ color: "var(--accent)" }}
          />
        )}
        <div
          className="w-5 h-5 rounded flex items-center justify-center"
          style={{ background: "var(--accent-bg)" }}
        >
          <BookOpen className="w-3 h-3" style={{ color: "var(--accent)" }} />
        </div>
        <span className="font-medium" style={{ color: "var(--accent)" }}>
          {t("memory.referenced")}
        </span>
        <span
          className="text-[10px] ml-1"
          style={{ color: "var(--text-muted)" }}
        >
          {refs.length}
        </span>
      </button>
      {expanded && (
        <div
          className="px-3 pb-2.5 pt-2 flex flex-wrap gap-2"
          style={{ borderTop: "1px solid var(--border-accent)" }}
        >
          {refs.map((r) => {
            const href = userSession
              ? `/${userSession}/memory?entry=${encodeURIComponent(r.id)}`
              : undefined;
            const keywords = splitMemoryKeywords(r.content, 1);
            const label = keywords[0] || r.content;
            const className =
              "inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-[12px] transition-all shadow-sm hover:shadow-md max-w-full text-left";
            const style = {
              color: "var(--text-secondary)",
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
            } as const;

            if (href) {
              return (
                <Link
                  key={r.id}
                  href={href}
                  className={className}
                  style={style}
                  title={r.content}
                >
                  <span className="line-clamp-2 min-w-0">{label}</span>
                  <ArrowUpRight
                    className="w-3 h-3 shrink-0 opacity-80"
                    strokeWidth={2.25}
                  />
                </Link>
              );
            }

            return (
              <span
                key={r.id}
                className={className}
                style={style}
                title={r.content}
              >
                <span className="line-clamp-2 min-w-0">{label}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
