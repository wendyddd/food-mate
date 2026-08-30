/**
 * FoodMate backend API client.
 * Custom SSE parser that supports POST streaming (native EventSource is GET-only).
 */

import type { MemoryEntry } from "./types";

/**
 * Resolve the backend API root path.
 *
 * Priority:
 * 1. NEXT_PUBLIC_API_BASE (explicit override, e.g. https://foodmates365.com/api)
 * 2. NEXT_PUBLIC_FOODMATE_API_PORT (local start.sh: cross-port access)
 * 3. Relative path /api (production: same-origin Nginx reverse proxy)
 *
 * @returns API root path (no extra trailing slash)
 */
function resolveApiBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }

  const apiPort = process.env.NEXT_PUBLIC_FOODMATE_API_PORT?.trim();
  if (apiPort) {
    if (typeof window !== "undefined") {
      return `http://${window.location.hostname}:${apiPort}/api`;
    }
    return `http://localhost:${apiPort}/api`;
  }

  return "/api";
}

/** Backend API root path */
export const API_BASE = resolveApiBase();

/** Current signed-in user's URL session id (set by AuthProvider) */
let currentUserSession: string | null = null;

export function getUserSession(): string | null {
  return currentUserSession;
}

/**
 * Set or clear the current user's URL session for API auth headers.
 *
 * @param session - Session column from the CSV
 */
export function setUserSession(session: string | null): void {
  currentUserSession = session;
}

/**
 * Return the current signed-in session, or throw if not signed in.
 *
 * @returns User session id
 */
function requireUserSession(): string {
  const session = getUserSession();
  if (!session) {
    throw new Error("Not signed in");
  }
  return session;
}

export interface AuthInfo {
  uid: string;
  session: string;
  nickname: string;
  /** Whether to show debug/memory UI: 1 show, 0 hide */
  is_show: number;
}

/**
 * Fetch with the user session auth header attached.
 *
 * @param input - Request URL
 * @param init - fetch options
 * @returns Promise resolving to the Response
 */
async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (currentUserSession) {
    headers.set("X-User-Session", currentUserSession);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers });
}

/**
 * Sign in with uid and password.
 *
 * @param uid - User ID
 * @param pwd - Password
 * @returns Promise resolving to AuthInfo
 */
export async function login(uid: string, pwd: string): Promise<AuthInfo> {
  const resp = await apiFetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uid, pwd }),
  });
  if (!resp.ok) {
    throw new Error("Invalid uid or password");
  }
  return resp.json();
}

/**
 * Verify that a URL session is valid.
 *
 * @param userSession - Session id from the URL
 * @returns Promise resolving to AuthInfo
 */
export async function verifySession(userSession: string): Promise<AuthInfo> {
  const resp = await apiFetch(
    `${API_BASE}/auth/session/${encodeURIComponent(userSession)}`,
  );
  if (!resp.ok) {
    throw new Error("Invalid user session");
  }
  return resp.json();
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * Stream chat messages via POST SSE.
 * Yields parsed SSE events as they arrive.
 */
export async function* streamChat(
  message: string,
  sessionId: string,
): AsyncGenerator<SSEEvent> {
  requireUserSession();

  const response = await apiFetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // Split complete SSE events on blank lines so a single event is not parsed twice across chunks
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || "";

    for (const block of parts) {
      if (!block.trim()) continue;
      let eventName = "message";
      const dataLines: string[] = [];
      for (const rawLine of block.split(/\r?\n/)) {
        const line = rawLine.replace(/\r$/, "");
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (dataLines.length === 0) continue;
      try {
        const data = JSON.parse(dataLines.join("\n"));
        yield { event: eventName, data };
      } catch {
        // Skip malformed JSON
      }
    }
  }
}

/**
 * Read a file from the backend.
 */
export async function readFile(path: string): Promise<string> {
  requireUserSession();
  const resp = await apiFetch(
    `${API_BASE}/files?path=${encodeURIComponent(path)}`,
  );
  if (!resp.ok) throw new Error(`Failed to read file: ${resp.status}`);
  const data = await resp.json();
  return data.content;
}

/**
 * Save a file to the backend.
 */
export async function saveFile(path: string, content: string): Promise<void> {
  requireUserSession();
  const resp = await apiFetch(`${API_BASE}/files`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!resp.ok) throw new Error(`Failed to save file: ${resp.status}`);
}

/**
 * List all structured memory entries.
 */
export async function listMemoryEntries(): Promise<MemoryEntry[]> {
  requireUserSession();
  const resp = await apiFetch(`${API_BASE}/memory/entries`);
  if (!resp.ok)
    throw new Error(`Failed to list memory entries: ${resp.status}`);
  const data = await resp.json();
  return data.entries;
}

/**
 * Create a memory entry.
 */
export async function createMemoryEntry(
  category: string,
  content: string,
): Promise<MemoryEntry> {
  requireUserSession();
  const resp = await apiFetch(`${API_BASE}/memory/entries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, content }),
  });
  if (!resp.ok)
    throw new Error(`Failed to create memory entry: ${resp.status}`);
  const data = await resp.json();
  return data.entry;
}

/**
 * Update a memory entry (category may be changed at the same time).
 *
 * @param entryId - Entry ID
 * @param content - New body text
 * @param category - Optional new category
 * @returns Promise resolving to the updated MemoryEntry
 */
export async function updateMemoryEntry(
  entryId: string,
  content: string,
  category?: string,
): Promise<MemoryEntry> {
  requireUserSession();
  const body: { content: string; category?: string } = { content };
  if (category) body.category = category;
  const resp = await apiFetch(
    `${API_BASE}/memory/entries/${encodeURIComponent(entryId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok)
    throw new Error(`Failed to update memory entry: ${resp.status}`);
  const data = await resp.json();
  return data.entry;
}

/**
 * Delete a memory entry.
 */
export async function deleteMemoryEntry(entryId: string): Promise<void> {
  requireUserSession();
  const resp = await apiFetch(
    `${API_BASE}/memory/entries/${encodeURIComponent(entryId)}`,
    { method: "DELETE" },
  );
  if (!resp.ok)
    throw new Error(`Failed to delete memory entry: ${resp.status}`);
}

/**
 * Export the user profile as Markdown.
 */
export async function getUserMemoryMarkdown(): Promise<string> {
  requireUserSession();
  const resp = await apiFetch(`${API_BASE}/memory/user`);
  if (!resp.ok) throw new Error(`Failed to get user memory: ${resp.status}`);
  const data = await resp.json();
  return data.content;
}

/**
 * List all sessions.
 */
export async function listSessions(): Promise<
  Array<{ id: string; title: string; updated_at: number }>
> {
  const resp = await apiFetch(`${API_BASE}/sessions`);
  if (!resp.ok) throw new Error(`Failed to list sessions: ${resp.status}`);
  const data = await resp.json();
  return data.sessions;
}

/**
 * Create a new session.
 */
export async function createSession(): Promise<{ id: string; title: string }> {
  const resp = await apiFetch(`${API_BASE}/sessions`, { method: "POST" });
  if (!resp.ok) throw new Error(`Failed to create session: ${resp.status}`);
  return resp.json();
}

/**
 * Rename a session.
 */
export async function renameSession(id: string, title: string): Promise<void> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
  );
  if (!resp.ok) throw new Error(`Failed to rename session: ${resp.status}`);
}

/**
 * Delete a session.
 */
export async function deleteSession(id: string): Promise<void> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(id)}`,
    {
      method: "DELETE",
    },
  );
  if (!resp.ok) throw new Error(`Failed to delete session: ${resp.status}`);
}

/**
 * Get raw messages for a session (including system prompt).
 */
export async function getRawMessages(sessionId: string): Promise<{
  session_id: string;
  title: string;
  messages: Array<{
    role: string;
    content: string;
    tool_calls?: Array<{ tool: string; input?: string; output?: string }>;
  }>;
}> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`,
  );
  if (!resp.ok) throw new Error(`Failed to get raw messages: ${resp.status}`);
  return resp.json();
}

/**
 * Get session conversation history (no system prompt, includes tool_calls).
 */
export async function getSessionHistory(sessionId: string): Promise<{
  session_id: string;
  messages: Array<{
    role: string;
    content: string;
    tool_calls?: Array<{ tool: string; input?: string; output?: string }>;
    memory_refs?: Array<{
      id: string;
      category: string;
      content: string;
      source_type?: string;
    }>;
  }>;
}> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/history`,
  );
  if (!resp.ok)
    throw new Error(`Failed to get session history: ${resp.status}`);
  return resp.json();
}
/**
 * Generate a title for a session using AI.
 */
export async function generateTitle(
  sessionId: string,
): Promise<{ title: string }> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/generate-title`,
    { method: "POST" },
  );
  if (!resp.ok) throw new Error(`Failed to generate title: ${resp.status}`);
  return resp.json();
}

/**
 * Get token count for a session (system + messages).
 */
export async function getSessionTokenCount(sessionId: string): Promise<{
  system_tokens: number;
  message_tokens: number;
  total_tokens: number;
}> {
  const resp = await apiFetch(
    `${API_BASE}/tokens/session/${encodeURIComponent(sessionId)}`,
  );
  if (!resp.ok) throw new Error(`Failed to get token count: ${resp.status}`);
  return resp.json();
}

/**
 * Get token counts for a list of files.
 */
export async function getFileTokenCounts(
  paths: string[],
): Promise<{ files: Array<{ path: string; tokens: number }> }> {
  const resp = await apiFetch(`${API_BASE}/tokens/files`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
  });
  if (!resp.ok)
    throw new Error(`Failed to get file token counts: ${resp.status}`);
  return resp.json();
}

/**
 * Compress a session's conversation history.
 */
export async function compressSession(
  sessionId: string,
): Promise<{ archived_count: number; remaining_count: number }> {
  const resp = await apiFetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/compress`,
    { method: "POST" },
  );
  if (!resp.ok) throw new Error(`Failed to compress session: ${resp.status}`);
  return resp.json();
}

/**
 * Get current RAG mode status.
 */
export async function getRagMode(): Promise<{ rag_mode: boolean }> {
  const resp = await apiFetch(`${API_BASE}/config/rag-mode`);
  if (!resp.ok) throw new Error(`Failed to get RAG mode: ${resp.status}`);
  return resp.json();
}

/**
 * Set RAG mode enabled/disabled.
 */
export async function setRagMode(
  enabled: boolean,
): Promise<{ rag_mode: boolean }> {
  const resp = await apiFetch(`${API_BASE}/config/rag-mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!resp.ok) throw new Error(`Failed to set RAG mode: ${resp.status}`);
  return resp.json();
}

/**
 * Get masked API keys from backend.
 */
export async function getApiKeys(): Promise<Record<string, string>> {
  const resp = await apiFetch(`${API_BASE}/config/api-keys`);
  if (!resp.ok) throw new Error(`Failed to get API keys: ${resp.status}`);
  return resp.json();
}

/**
 * Update API keys on backend.
 */
export async function setApiKeys(
  keys: Record<string, string>,
): Promise<Record<string, string>> {
  const resp = await apiFetch(`${API_BASE}/config/api-keys`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keys }),
  });
  if (!resp.ok) throw new Error(`Failed to set API keys: ${resp.status}`);
  return resp.json();
}

/**
 * Stream chat and collect full response text.
 * Calls onToken for each streamed token, onToolStart/onToolEnd for tool events.
 * Returns the full accumulated text when done.
 */
export async function streamChatCollect(
  message: string,
  sessionId: string,
  callbacks?: {
    onToken?: (text: string) => void;
    onToolStart?: (tool: string, input: string) => void;
    onToolEnd?: (tool: string, output: string) => void;
    onError?: (error: string) => void;
  },
): Promise<string> {
  let fullText = "";
  for await (const event of streamChat(message, sessionId)) {
    if (event.event === "token") {
      const content = (event.data.content as string) || "";
      fullText += content;
      callbacks?.onToken?.(content);
    } else if (event.event === "tool_start") {
      callbacks?.onToolStart?.(
        event.data.tool as string,
        event.data.input as string,
      );
    } else if (event.event === "tool_end") {
      callbacks?.onToolEnd?.(
        event.data.tool as string,
        event.data.output as string,
      );
    } else if (event.event === "error") {
      callbacks?.onError?.((event.data.error as string) || "Unknown error");
      break;
    } else if (event.event === "done") {
      break;
    }
  }
  return fullText;
}
