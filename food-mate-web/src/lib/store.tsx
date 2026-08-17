"use client";

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
} from "react";
import {
  API_BASE,
  streamChat,
  getUserSession,
  listSessions as apiListSessions,
  createSession as apiCreateSession,
  renameSession as apiRenameSession,
  deleteSession as apiDeleteSession,
  getSessionHistory as apiGetSessionHistory,
  getRawMessages as apiGetRawMessages,
} from "./api";
import { tGlobal } from "./i18n";
import { useAuth } from "./auth";
import MemoryToast from "@/components/chat/MemoryToast";

// ── Types ──────────────────────────────────────────────────

export interface ToolCall {
  tool: string;
  input?: string;
  output?: string;
  status: "running" | "done";
}

export interface MemoryRef {
  id: string;
  category: string;
  content: string;
  source_type?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  memoryRefs?: MemoryRef[];
  timestamp: number;
}

export interface SessionMeta {
  id: string;
  title: string;
  updated_at: number;
}

export interface RawMessage {
  role: string;
  content: string;
  tool_calls?: Array<{ tool: string; input?: string; output?: string }>;
}

interface AppState {
  // Chat
  messages: ChatMessage[];
  isStreaming: boolean;
  suggestedQuestions: string[];
  sendMessage: (text: string) => Promise<void>;

  // Sessions
  sessionId: string;
  setSessionId: (id: string) => void;
  sessions: SessionMeta[];
  loadSessions: () => void;
  createSession: () => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;

  // Sidebar
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Trace
  rawMessages: RawMessage[] | null;
  loadRawMessages: () => void;

  // Memory toast
  memoryToast: string | null;
  dismissMemoryToast: () => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { isShow } = useAuth();
  const isShowRef = useRef(isShow);
  isShowRef.current = isShow;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [sessionId, setSessionIdRaw] = useState("default");
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rawMessages, setRawMessages] = useState<RawMessage[] | null>(null);
  const [memoryToast, setMemoryToast] = useState<string | null>(null);
  const abortRef = useRef(false);
  /** 同步锁，避免连点导致同一轮发出两次请求、弹两次 Toast */
  const streamingRef = useRef(false);
  /** 同一轮对话只展示一次记忆更新提示 */
  const memoryToastShownRef = useRef(false);
  /** 本轮记忆更新 Toast 文案，待回复完全结束后再展示 */
  const pendingMemoryToastRef = useRef<string | null>(null);

  const dismissMemoryToast = useCallback(() => setMemoryToast(null), []);

  // ── Ghost session management ──────────────────────────
  // A "ghost" is a session created on the backend but not shown in the sidebar.
  // It becomes visible only when the backend sends a `title` event (first response).
  const ghostSessionRef = useRef<string | null>(null);
  const titleAnimTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Silently delete the current ghost session from the backend. */
  const cleanupGhost = useCallback(() => {
    const ghostId = ghostSessionRef.current;
    if (ghostId) {
      ghostSessionRef.current = null;
      apiDeleteSession(ghostId).catch(() => {});
    }
  }, []);

  /** Create a new ghost session: active but invisible in sidebar. */
  const spawnGhost = useCallback(() => {
    apiCreateSession()
      .then((meta) => {
        ghostSessionRef.current = meta.id;
        setSessionIdRaw(meta.id);
        setMessages([]);
        setSuggestedQuestions([]);
      })
      .catch(() => {});
  }, []);

  const toggleSidebar = useCallback(() => setSidebarOpen((v) => !v), []);

  // ── Session management ─────────────────────────────

  const loadSessions = useCallback(() => {
    apiListSessions()
      .then((list) => {
        const ghostId = ghostSessionRef.current;
        // Filter out: 1) the current ghost session  2) any "New Chat" titled sessions (orphans)
        setSessions(
          list.filter((s) => s.id !== ghostId && s.title !== "New Chat"),
        );
      })
      .catch(() => {});
  }, []);

  // On mount: purge orphan "New Chat" sessions left by previous page loads, then spawn ghost
  useEffect(() => {
    apiListSessions()
      .then((list) => {
        const orphans = list.filter((s) => s.title === "New Chat");
        // Delete orphans from backend silently
        for (const o of orphans) {
          apiDeleteSession(o.id).catch(() => {});
        }
        // Show only real sessions
        setSessions(list.filter((s) => s.title !== "New Chat"));
      })
      .catch(() => {});
    spawnGhost();
  }, [spawnGhost]);

  // Cleanup ghost on page close / refresh
  useEffect(() => {
    const handler = () => {
      const ghostId = ghostSessionRef.current;
      const userSession = getUserSession();
      if (ghostId && userSession) {
        const url = `${API_BASE}/sessions/${encodeURIComponent(ghostId)}`;
        fetch(url, {
          method: "DELETE",
          keepalive: true,
          headers: { "X-User-Session": userSession },
        }).catch(() => {});
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

  const setSessionId = useCallback(
    (id: string) => {
      // Switching away from ghost → delete it
      if (ghostSessionRef.current && ghostSessionRef.current !== id) {
        cleanupGhost();
      }
      setSessionIdRaw(id);
      setMessages([]);
      setSuggestedQuestions([]);
      setRawMessages(null);

      apiGetSessionHistory(id)
        .then((data) => {
          if (data.messages && data.messages.length > 0) {
            const loaded: ChatMessage[] = [];
            let msgIndex = 0;
            for (const msg of data.messages) {
              if (msg.role === "user") {
                loaded.push({
                  id: `hist-user-${msgIndex++}`,
                  role: "user",
                  content: msg.content,
                  timestamp:
                    Date.now() - (data.messages.length - msgIndex) * 1000,
                });
              } else if (msg.role === "assistant") {
                const toolCalls: ToolCall[] = (msg.tool_calls || []).map(
                  (tc: { tool: string; input?: string; output?: string }) => ({
                    tool: tc.tool,
                    input: tc.input || "",
                    output: tc.output || "",
                    status: "done" as const,
                  }),
                );
                loaded.push({
                  id: `hist-asst-${msgIndex++}`,
                  role: "assistant",
                  content: msg.content,
                  toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                  memoryRefs: msg.memory_refs?.length
                    ? msg.memory_refs
                    : undefined,
                  timestamp:
                    Date.now() - (data.messages.length - msgIndex) * 1000,
                });
              }
            }
            setMessages(loaded);
          }
        })
        .catch(() => {});
    },
    [cleanupGhost],
  );

  const createSession = useCallback(async () => {
    // Clicking "New Chat" — delete old ghost, spawn a new one
    cleanupGhost();
    spawnGhost();
  }, [cleanupGhost, spawnGhost]);

  const renameSessionFn = useCallback(async (id: string, title: string) => {
    try {
      await apiRenameSession(id, title);
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title } : s)),
      );
    } catch {
      // ignore
    }
  }, []);

  const deleteSessionFn = useCallback(
    async (id: string) => {
      try {
        await apiDeleteSession(id);
      } catch {
        // 后端删除失败时保留侧边栏条目，避免 UI 与磁盘状态不一致
        return;
      }
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (sessionId === id) {
        // Deleted the active session → spawn a fresh ghost
        spawnGhost();
      }
    },
    [sessionId, spawnGhost],
  );

  const loadRawMessages = useCallback(() => {
    if (!sessionId) return;
    apiGetRawMessages(sessionId)
      .then((data) => setRawMessages(data.messages))
      .catch(() => setRawMessages(null));
  }, [sessionId]);

  // ── Title typing animation helper ─────────────────

  /** Add a session to the list with a character-by-character typing animation. */
  const materializeSession = useCallback((id: string, fullTitle: string) => {
    // Clear any ongoing animation
    if (titleAnimTimerRef.current) {
      clearInterval(titleAnimTimerRef.current);
      titleAnimTimerRef.current = null;
    }

    // Ghost has materialized — it's no longer a ghost
    if (ghostSessionRef.current === id) {
      ghostSessionRef.current = null;
    }

    // Insert the session at the top with empty title, then animate
    const entry: SessionMeta = { id, title: "", updated_at: Date.now() / 1000 };
    setSessions((prev) => {
      if (prev.some((s) => s.id === id)) {
        // Already exists (shouldn't normally happen, but handle gracefully)
        return prev.map((s) => (s.id === id ? { ...s, title: "" } : s));
      }
      return [entry, ...prev];
    });

    // Animate title character by character
    let idx = 0;
    titleAnimTimerRef.current = setInterval(() => {
      idx++;
      const partial = fullTitle.slice(0, idx);
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title: partial } : s)),
      );
      if (idx >= fullTitle.length) {
        if (titleAnimTimerRef.current) {
          clearInterval(titleAnimTimerRef.current);
          titleAnimTimerRef.current = null;
        }
      }
    }, 40);
  }, []);

  // Cleanup animation timer on unmount
  useEffect(() => {
    return () => {
      if (titleAnimTimerRef.current) clearInterval(titleAnimTimerRef.current);
    };
  }, []);

  // ── Send message ───────────────────────────────────

  const currentAssistantIdRef = useRef("");
  /** 每条 assistant 消息待显示的文本缓冲（打字机效果） */
  const pendingTextRef = useRef<Map<string, string>>(new Map());
  const typewriterRafRef = useRef<number | null>(null);
  /** SSE 是否已结束；结束后继续冲刷缓冲直至清空 */
  const sseFinishedRef = useRef(false);
  const typewriterResolveRef = useRef<(() => void) | null>(null);

  /**
   * 计算本帧应从缓冲区吐出的字符数（积压越多吐得越快）。
   *
   * 参数:
   *   pendingLen (number): 当前缓冲字符数
   *
   * 返回:
   *   number: 本帧吐出字符数
   */
  const charsPerFrame = useCallback((pendingLen: number): number => {
    if (pendingLen <= 0) return 0;
    if (pendingLen > 800) return Math.ceil(pendingLen / 4);
    if (pendingLen > 300) return Math.ceil(pendingLen / 8);
    if (pendingLen > 80) return Math.max(6, Math.ceil(pendingLen / 12));
    return 3;
  }, []);

  /**
   * 将指定消息缓冲中的全部剩余文本立即写入 UI。
   *
   * 参数:
   *   msgId (string | null): 消息 ID；为 null 时冲刷全部
   */
  const flushPendingText = useCallback((msgId: string | null = null) => {
    const pending = pendingTextRef.current;
    if (pending.size === 0) return;

    const ids =
      msgId === null
        ? Array.from(pending.keys())
        : pending.has(msgId)
          ? [msgId]
          : [];
    if (ids.length === 0) return;

    setMessages((prev) => {
      const updated = [...prev];
      let changed = false;
      for (const id of ids) {
        const text = pending.get(id);
        if (!text) continue;
        const idx = updated.findIndex((m) => m.id === id);
        if (idx === -1) continue;
        updated[idx] = {
          ...updated[idx],
          content: updated[idx].content + text,
        };
        pending.delete(id);
        changed = true;
      }
      return changed ? updated : prev;
    });
  }, []);

  /**
   * 停止打字机 RAF 循环。
   */
  const stopTypewriter = useCallback(() => {
    if (typewriterRafRef.current !== null) {
      cancelAnimationFrame(typewriterRafRef.current);
      typewriterRafRef.current = null;
    }
  }, []);

  /**
   * 启动或继续打字机 RAF；缓冲清空且 SSE 结束后 resolve 等待方。
   */
  const ensureTypewriter = useCallback(() => {
    if (typewriterRafRef.current !== null) return;

    const tick = () => {
      const pending = pendingTextRef.current;
      let drained = 0;

      if (pending.size > 0) {
        const patches: Array<{ id: string; chunk: string }> = [];
        for (const [id, text] of pending) {
          if (!text) {
            pending.delete(id);
            continue;
          }
          const n = charsPerFrame(text.length);
          const chunk = text.slice(0, n);
          const rest = text.slice(n);
          if (rest) pending.set(id, rest);
          else pending.delete(id);
          patches.push({ id, chunk });
          drained += chunk.length;
        }

        if (patches.length > 0) {
          setMessages((prev) => {
            const updated = [...prev];
            let changed = false;
            for (const { id, chunk } of patches) {
              const idx = updated.findIndex((m) => m.id === id);
              if (idx === -1) continue;
              updated[idx] = {
                ...updated[idx],
                content: updated[idx].content + chunk,
              };
              changed = true;
            }
            return changed ? updated : prev;
          });
        }
      }

      const stillPending = pendingTextRef.current.size > 0;
      if (stillPending || !sseFinishedRef.current) {
        typewriterRafRef.current = requestAnimationFrame(tick);
      } else {
        typewriterRafRef.current = null;
        const resolve = typewriterResolveRef.current;
        typewriterResolveRef.current = null;
        resolve?.();
      }

      // drained 仅用于避免 unused 告警时保留可读性
      void drained;
    };

    typewriterRafRef.current = requestAnimationFrame(tick);
  }, [charsPerFrame]);

  /**
   * 向指定消息追加待显示文本并启动打字机。
   *
   * 参数:
   *   msgId (string): 助手消息 ID
   *   text (string): 新增文本片段
   */
  const enqueueTypewriter = useCallback(
    (msgId: string, text: string) => {
      if (!text) return;
      const pending = pendingTextRef.current;
      pending.set(msgId, (pending.get(msgId) || "") + text);
      ensureTypewriter();
    },
    [ensureTypewriter],
  );

  /**
   * 等待打字机缓冲全部冲刷完成（SSE 已结束后调用）。
   *
   * 返回:
   *   Promise<void>
   */
  const waitTypewriterDrain = useCallback((): Promise<void> => {
    if (pendingTextRef.current.size === 0) {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      typewriterResolveRef.current = resolve;
      ensureTypewriter();
    });
  }, [ensureTypewriter]);

  // 组件卸载时清理打字机 RAF
  useEffect(() => {
    return () => {
      stopTypewriter();
      typewriterResolveRef.current = null;
    };
  }, [stopTypewriter]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming || streamingRef.current) return;
      if (!getUserSession()) {
        console.error("Not signed in — cannot send message");
        return;
      }
      streamingRef.current = true;

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      const firstAssistantId = `assistant-${Date.now()}`;
      const assistantMsg: ChatMessage = {
        id: firstAssistantId,
        role: "assistant",
        content: "",
        toolCalls: [],
        timestamp: Date.now(),
      };

      currentAssistantIdRef.current = firstAssistantId;
      pendingTextRef.current.clear();
      sseFinishedRef.current = false;
      memoryToastShownRef.current = false;
      pendingMemoryToastRef.current = null;
      setMemoryToast(null);
      stopTypewriter();
      setSuggestedQuestions([]);
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);
      abortRef.current = false;

      try {
        for await (const event of streamChat(text, sessionId)) {
          if (abortRef.current) break;

          if (event.event === "suggested_questions") {
            const suggestData = event.data as { questions?: string[] };
            const questions = (suggestData.questions || [])
              .map((q) => (typeof q === "string" ? q.trim() : ""))
              .filter(Boolean)
              .slice(0, 3);
            if (questions.length > 0) {
              setSuggestedQuestions(questions);
            }
            continue;
          }

          if (event.event === "memory_ref") {
            const targetId = currentAssistantIdRef.current;
            const refData = event.data as {
              refs: Array<{
                id: string;
                category: string;
                content: string;
                source_type?: string;
              }>;
            };
            setMessages((prev) => {
              const updated = [...prev];
              const idx = updated.findIndex((m) => m.id === targetId);
              if (idx === -1) return prev;
              updated[idx] = {
                ...updated[idx],
                memoryRefs: refData.refs,
              };
              return updated;
            });
            continue;
          }

          if (event.event === "memory_updated") {
            const updateData = event.data as {
              changed?: boolean;
              added_ids?: string[];
              updated_ids?: string[];
            };
            // 先缓存提示文案，等本轮回复完全结束后再展示 Toast
            if (
              isShowRef.current &&
              updateData.changed &&
              !memoryToastShownRef.current
            ) {
              memoryToastShownRef.current = true;
              const added = updateData.added_ids?.length ?? 0;
              const updated = updateData.updated_ids?.length ?? 0;
              const parts: string[] = [];
              if (added > 0)
                parts.push(tGlobal("memory.toastAdded", { n: added }));
              if (updated > 0)
                parts.push(tGlobal("memory.toastUpdatedCount", { n: updated }));
              pendingMemoryToastRef.current =
                parts.length > 0
                  ? tGlobal("memory.toastCombined", {
                      parts: parts.join(", "),
                    })
                  : tGlobal("memory.toastUpdated");
            }
            continue;
          }

          if (event.event === "title") {
            const titleData = event.data as {
              session_id: string;
              title: string;
            };
            // Materialize the ghost into the sidebar with typing animation
            materializeSession(titleData.session_id, titleData.title);
            continue;
          }

          if (event.event === "new_response") {
            // 切换到下一段前，冲刷当前段缓冲，避免文字落到错误气泡
            flushPendingText(currentAssistantIdRef.current);
            const newId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            currentAssistantIdRef.current = newId;
            setMessages((prev) => [
              ...prev,
              {
                id: newId,
                role: "assistant",
                content: "",
                toolCalls: [],
                timestamp: Date.now(),
              },
            ]);
            continue;
          }

          const targetId = currentAssistantIdRef.current;

          if (event.event === "token") {
            const tokenText = (event.data.content as string) || "";
            enqueueTypewriter(targetId, tokenText);
            continue;
          }

          if (event.event === "done") {
            continue;
          }

          setMessages((prev) => {
            const updated = [...prev];
            const idx = updated.findIndex((m) => m.id === targetId);
            if (idx === -1) return prev;
            const msg = { ...updated[idx] };

            switch (event.event) {
              case "tool_start":
                msg.toolCalls = [
                  ...(msg.toolCalls || []),
                  {
                    tool: event.data.tool as string,
                    input: event.data.input as string,
                    status: "running",
                  },
                ];
                break;

              case "tool_end": {
                const calls = [...(msg.toolCalls || [])];
                for (let i = calls.length - 1; i >= 0; i--) {
                  if (
                    calls[i].tool === event.data.tool &&
                    calls[i].status === "running"
                  ) {
                    calls[i] = {
                      ...calls[i],
                      output: event.data.output as string,
                      status: "done",
                    };
                    break;
                  }
                }
                msg.toolCalls = calls;
                break;
              }

              case "error":
                msg.content += `\n\n**${tGlobal("chat.errorPrefix")}:** ${event.data.error || tGlobal("chat.unknownError")}`;
                break;
            }

            updated[idx] = msg;
            return updated;
          });
        }
      } catch (err) {
        flushPendingText(null);
        const targetId = currentAssistantIdRef.current;
        setMessages((prev) => {
          const updated = [...prev];
          const idx = updated.findIndex((m) => m.id === targetId);
          if (idx !== -1) {
            updated[idx] = {
              ...updated[idx],
              content:
                updated[idx].content +
                `\n\n**Connection error:** ${err instanceof Error ? err.message : "Unknown"}`,
            };
          }
          return updated;
        });
      } finally {
        sseFinishedRef.current = true;
        if (abortRef.current) {
          flushPendingText(null);
          stopTypewriter();
          pendingMemoryToastRef.current = null;
        } else {
          await waitTypewriterDrain();
          if (pendingMemoryToastRef.current) {
            setMemoryToast(pendingMemoryToastRef.current);
            pendingMemoryToastRef.current = null;
          }
        }
        streamingRef.current = false;
        setIsStreaming(false);
        loadSessions();
      }
    },
    [
      isStreaming,
      sessionId,
      loadSessions,
      materializeSession,
      enqueueTypewriter,
      flushPendingText,
      stopTypewriter,
      waitTypewriterDrain,
    ],
  );

  return (
    <AppContext.Provider
      value={{
        messages,
        isStreaming,
        suggestedQuestions,
        sendMessage,
        sessionId,
        setSessionId,
        sessions,
        loadSessions,
        createSession,
        renameSession: renameSessionFn,
        deleteSession: deleteSessionFn,
        sidebarOpen,
        setSidebarOpen,
        toggleSidebar,
        rawMessages,
        loadRawMessages,
        memoryToast,
        dismissMemoryToast,
      }}
    >
      {children}
      {isShow && (
        <MemoryToast message={memoryToast} onClose={dismissMemoryToast} />
      )}
    </AppContext.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
