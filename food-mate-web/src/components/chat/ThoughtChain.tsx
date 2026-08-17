"use client";

import {
  Terminal,
  Code,
  Globe,
  FileText,
  Search,
  Loader2,
  CheckCircle2,
  Wrench,
} from "lucide-react";
import type { ToolCall } from "@/lib/store";
import { useT } from "@/lib/i18n";

const TOOL_META: Record<string, { icon: React.ElementType; label: string }> = {
  terminal: { icon: Terminal, label: "Terminal" },
  python_repl: { icon: Code, label: "Python REPL" },
  fetch_url: { icon: Globe, label: "Fetch URL" },
  read_file: { icon: FileText, label: "Read File" },
  search_knowledge_base: { icon: Search, label: "Search KB" },
};

interface Props {
  toolCalls: ToolCall[];
}

export default function ThoughtChain({ toolCalls }: Props) {
  const t = useT();
  if (toolCalls.length === 0) return null;

  return (
    <div className="mb-2 space-y-1">
      {toolCalls.map((tc, idx) => {
        const meta = TOOL_META[tc.tool] || { icon: Wrench, label: tc.tool };
        const Icon = meta.icon;

        return (
          <details
            key={idx}
            className="rounded-xl overflow-hidden animate-fade-in-scale group"
            style={{
              border: "1px solid var(--border)",
              background: "var(--bg-surface)",
            }}
          >
            <summary className="flex items-center gap-2 px-3 py-1.5 text-[12px] cursor-pointer select-none list-none hover:opacity-80 transition-colors">
              <div
                className="w-5 h-5 rounded flex items-center justify-center"
                style={{ background: "var(--accent-bg)" }}
              >
                <Icon className="w-3 h-3" style={{ color: "var(--accent)" }} />
              </div>
              <span
                className="font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                {tc.tool}
              </span>
              <span className="ml-auto">
                {tc.status === "running" ? (
                  <Loader2
                    className="w-3.5 h-3.5 animate-spin"
                    style={{ color: "var(--accent)" }}
                  />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                )}
              </span>
            </summary>
            <div
              className="px-3 pb-2 text-[11px] space-y-1.5 pt-1.5"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              {tc.input && (
                <div>
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("trace.input")}
                  </span>
                  <pre
                    className="mt-0.5 p-2 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed"
                    style={{
                      background: "var(--accent-bg)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {tc.input}
                  </pre>
                </div>
              )}
              {tc.output && (
                <div>
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("trace.output")}
                  </span>
                  <pre
                    className="mt-0.5 p-2 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono max-h-36 overflow-y-auto leading-relaxed"
                    style={{
                      background: "var(--accent-bg)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {tc.output}
                  </pre>
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
