"use client";

import { useEffect, useRef, useState } from "react";
import { CircleHelp, RefreshCw } from "lucide-react";
import { useApp, type ChatMessage as ChatMessageType } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useLocale, type MessageKey } from "@/lib/i18n";
import { getRagMode, setRagMode } from "@/lib/api";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import Logo from "@/components/shared/Logo";

/** 空态预设问题总数 */
const HINT_COUNT = 30;
/** 每批展示条数 */
const HINT_PAGE_SIZE = 3;

/** 预设问题 i18n key 列表 */
const HINT_KEYS: MessageKey[] = Array.from(
  { length: HINT_COUNT },
  (_, i) => `chat.hint${i + 1}` as MessageKey,
);

interface Props {
  /** 来自记忆页的原话摘录，用于定位到来源用户消息 */
  highlightQuote?: string | null;
  /** 定位处理完成后的回调（匹配成功或失败均调用） */
  onHighlightDone?: () => void;
}

/**
 * 规范化原话摘录，去掉截断省略号以便与完整消息内容匹配。
 *
 * 参数:
 *   quote (string): 记忆中的 source_quote
 *
 * 返回:
 *   string: 可用于匹配的摘录文本
 */
function normalizeQuote(quote: string): string {
  return quote
    .trim()
    .replace(/…\s*$/, "")
    .replace(/\.\.\.\s*$/, "")
    .trim();
}

/**
 * 在消息列表中按原话摘录查找来源用户消息。
 *
 * 参数:
 *   messages (ChatMessageType[]): 当前会话消息
 *   quote (string): 原话摘录
 *
 * 返回:
 *   ChatMessageType | null: 匹配到的用户消息，未找到则 null
 */
function findMessageByQuote(
  messages: ChatMessageType[],
  quote: string,
): ChatMessageType | null {
  const needle = normalizeQuote(quote);
  if (!needle) return null;

  const users = messages.filter((m) => m.role === "user");
  const exact =
    users.find((m) => m.content.trim() === quote.trim()) ||
    users.find((m) => m.content.trim() === needle);
  if (exact) return exact;

  const prefix = users.find((m) => m.content.trim().startsWith(needle));
  if (prefix) return prefix;

  return users.find((m) => m.content.includes(needle)) || null;
}

/**
 * 主聊天面板：消息列表、顶栏（含相关记忆召回开关）与输入框。
 */
export default function ChatPanel({ highlightQuote, onHighlightDone }: Props) {
  const { messages, sessions, sessionId, isStreaming, suggestedQuestions } =
    useApp();
  const { isShow } = useAuth();
  const { t, locale } = useLocale();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [ragMode, setRagModeState] = useState(true);
  const [ragBusy, setRagBusy] = useState(false);
  /** 空态预设问题当前批次下标 */
  const [hintPage, setHintPage] = useState(0);
  /** 待处理的定位 quote */
  const pendingQuoteRef = useRef<string | null>(null);
  /** 定位流程中抑制默认滚底，避免与 scrollIntoView 目标消息冲突 */
  const suppressBottomScrollRef = useRef(false);

  useEffect(() => {
    if (highlightQuote) {
      pendingQuoteRef.current = highlightQuote;
      suppressBottomScrollRef.current = true;
    }
  }, [highlightQuote]);

  // 有待定位原话时：匹配消息 → 滚动到目标；匹配失败则滚到底
  useEffect(() => {
    const quote = pendingQuoteRef.current;
    if (!quote || messages.length === 0) return;

    const matched = findMessageByQuote(messages, quote);
    pendingQuoteRef.current = null;

    if (matched) {
      requestAnimationFrame(() => {
        const el = document.getElementById(`msg-${matched.id}`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      onHighlightDone?.();
      // 同 session 仅换 quote 时 messages 不变，滚底 effect 不会消费 suppress，需异步解除
      queueMicrotask(() => {
        suppressBottomScrollRef.current = false;
      });
      return;
    }

    suppressBottomScrollRef.current = false;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    onHighlightDone?.();
  }, [messages, highlightQuote, onHighlightDone]);

  // 无定位目标时保持跟到底部（流式输出 / 普通切换会话）
  useEffect(() => {
    if (pendingQuoteRef.current) return;
    // 本轮由原话定位触发的 messages 更新：跳过一次滚底，并解除抑制
    if (suppressBottomScrollRef.current) {
      suppressBottomScrollRef.current = false;
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, suggestedQuestions, isStreaming]);

  useEffect(() => {
    let cancelled = false;
    /**
     * 挂载时拉取 RAG 开关状态。
     */
    async function loadRagMode() {
      try {
        const data = await getRagMode();
        if (!cancelled) setRagModeState(Boolean(data.rag_mode));
      } catch {
        // 拉取失败时保持默认关闭
      }
    }
    loadRagMode();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * 切换相关记忆召回开关并同步到后端。
   *
   * 参数:
   *   enabled (boolean): 是否开启
   */
  async function handleToggleRag(enabled: boolean) {
    if (ragBusy) return;
    setRagBusy(true);
    const prev = ragMode;
    setRagModeState(enabled);
    try {
      const data = await setRagMode(enabled);
      setRagModeState(Boolean(data.rag_mode));
    } catch {
      setRagModeState(prev);
    } finally {
      setRagBusy(false);
    }
  }

  const sessionTitle = sessions.find((s) => s.id === sessionId)?.title?.trim();
  const currentTitle =
    sessionTitle && sessionTitle !== "New Chat" && sessionTitle !== sessionId
      ? sessionTitle
      : t("nav.newChat");

  const hintPageCount = Math.ceil(HINT_COUNT / HINT_PAGE_SIZE);
  const hints = HINT_KEYS.slice(
    hintPage * HINT_PAGE_SIZE,
    hintPage * HINT_PAGE_SIZE + HINT_PAGE_SIZE,
  ).map((key) => t(key));

  // 切换语言时回到第一批，避免文案与页码错位观感
  useEffect(() => {
    setHintPage(0);
  }, [locale]);

  /**
   * 切换到下一批预设问题（循环）。
   */
  function refreshHints() {
    setHintPage((page) => (page + 1) % hintPageCount);
  }

  return (
    <div className="relative flex flex-col h-full">
      <div
        className="h-14 flex items-center justify-between px-6 shrink-0 gap-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-[14px] font-semibold truncate"
            style={{ color: "var(--text-primary)" }}
          >
            {currentTitle}
          </span>
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isShow && (
            <div className="flex items-center gap-1.5">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <span
                  className="text-[11px] hidden sm:inline"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t("chat.ragRecall")}
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={ragMode}
                  aria-label={t("chat.ragRecall")}
                  disabled={ragBusy}
                  onClick={() => handleToggleRag(!ragMode)}
                  className="relative w-9 h-5 rounded-full transition-colors disabled:opacity-60"
                  style={{
                    background: ragMode ? "var(--accent)" : "var(--border)",
                  }}
                >
                  <span
                    className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                    style={{
                      transform: ragMode ? "translateX(16px)" : "translateX(0)",
                    }}
                  />
                </button>
              </label>
              <span className="group relative inline-flex">
                <button
                  type="button"
                  className="p-0.5 rounded-full transition-opacity hover:opacity-80"
                  style={{ color: "var(--text-muted)" }}
                  aria-label={t("chat.ragRecallHint")}
                >
                  <CircleHelp className="w-3.5 h-3.5" />
                </button>
                <span
                  role="tooltip"
                  className="pointer-events-none absolute right-0 top-full z-20 mt-2 hidden w-max max-w-[260px] whitespace-pre-line rounded-lg px-3 py-2 text-[11px] leading-relaxed shadow-md group-hover:block"
                  style={{
                    background: "var(--text-primary)",
                    color: "var(--bg-page)",
                  }}
                >
                  {t("chat.ragRecallHint")}
                </span>
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-6">
            <Logo size={56} className="mb-4 rounded-2xl shadow-lg" />
            <h2
              className="text-lg font-semibold mb-1"
              style={{ color: "var(--text-primary)" }}
            >
              {t("chat.greeting")}
            </h2>
            <p
              className="text-[13px] max-w-xs text-center leading-relaxed"
              style={{ color: "var(--text-muted)" }}
            >
              {t("chat.intro")}{" "}
              <span className="font-medium" style={{ color: "var(--accent)" }}>
                &quot;{t("chat.introHint")}&quot;
              </span>
            </p>
            <div className="w-full max-w-2xl mt-8">
              <ChatInput />
            </div>
            <div className="flex flex-col items-center gap-3 mt-5 max-w-md">
              <div className="flex flex-wrap gap-2 justify-center">
                {hints.map((hint) => (
                  <QuickHint key={hint} text={hint} />
                ))}
              </div>
              <button
                type="button"
                onClick={refreshHints}
                className="flex items-center gap-1.5 text-[12px] transition-opacity hover:opacity-80"
                style={{ color: "var(--text-muted)" }}
                aria-label={t("chat.refreshHints")}
              >
                <RefreshCw className="w-3.5 h-3.5" />
                {t("chat.refreshHints")}
              </button>
            </div>
          </div>
        ) : (
          <div className="py-4 px-6 space-y-6">
            {messages.map((msg, index) => {
              const isLastAssistant =
                !isStreaming &&
                msg.role === "assistant" &&
                index === messages.length - 1;
              return (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  isActiveStreaming={
                    isStreaming &&
                    index === messages.length - 1 &&
                    msg.role === "assistant"
                  }
                  suggestedQuestions={
                    isLastAssistant ? suggestedQuestions : undefined
                  }
                />
              );
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {messages.length > 0 && (
        <div className="relative shrink-0">
          <ChatInput />
        </div>
      )}
    </div>
  );
}

/**
 * 空态快捷提示按钮，点击后直接发送该文案。
 *
 * 参数:
 *   text (string): 提示文案
 */
function QuickHint({ text }: { text: string }) {
  const { sendMessage, isStreaming } = useApp();
  return (
    <button
      onClick={() => !isStreaming && sendMessage(text)}
      className="px-3 py-1.5 rounded-full text-[12px] transition-all shadow-sm hover:shadow-md"
      style={{
        color: "var(--text-secondary)",
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
      }}
    >
      {text}
    </button>
  );
}
