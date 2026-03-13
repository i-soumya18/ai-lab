import type { AgentResult, Conversation, RAGChunk, SSEEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Helper ────────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<{ data: T | null; error: string | null }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
    const json = await res.json();
    return json as { data: T | null; error: string | null };
  } catch (err) {
    return { data: null, error: String(err) };
  }
}

// ── Chat ─────────────────────────────────────────────────────────────────────

/** Send a streaming chat message. Calls `onToken` for each token, returns full text. */
export async function sendChatStream(
  message: string,
  sessionId: string | null,
  conversationId: string | null,
  onToken: (token: string) => void,
  onMeta: (sessionId: string, conversationId: string) => void
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v1/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      conversation_id: conversationId,
      stream: true,
    }),
  });

  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let fullText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split("\n");

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event: SSEEvent = JSON.parse(line.slice(6));
        if (event.type === "meta") {
          onMeta(event.session_id, event.conversation_id);
        } else if (event.type === "token") {
          fullText += event.content;
          onToken(event.content);
        } else if (event.type === "done") {
          fullText = event.content;
        }
      } catch {
        // skip malformed SSE lines
      }
    }
  }

  return fullText;
}

export async function listSessions(
  userId = "default",
  limit = 20
): Promise<Conversation[]> {
  const { data } = await apiFetch<Conversation[]>(
    `/api/v1/chat/sessions?user_id=${userId}&limit=${limit}`
  );
  return data ?? [];
}

export async function getSession(conversationId: string): Promise<Conversation | null> {
  const { data } = await apiFetch<Conversation>(
    `/api/v1/chat/sessions/${conversationId}`
  );
  return data;
}

// ── RAG ──────────────────────────────────────────────────────────────────────

export async function ragSearch(
  query: string,
  collection = "default",
  topK = 5
): Promise<RAGChunk[]> {
  const params = new URLSearchParams({ q: query, collection, top_k: String(topK) });
  const { data } = await apiFetch<RAGChunk[]>(`/api/v1/rag/search?${params}`);
  return data ?? [];
}

export async function ingestFile(
  file: File,
  collection = "default"
): Promise<{ chunks: number; documents: number } | null> {
  const form = new FormData();
  form.append("file", file);
  form.append("collection", collection);
  const res = await fetch(`${API_BASE}/api/v1/rag/ingest?collection=${collection}`, {
    method: "POST",
    body: form,
  });
  const json = await res.json();
  return json.data ?? null;
}

export async function listCollections(): Promise<
  { name: string; count: number }[]
> {
  const { data } = await apiFetch<{ name: string; count: number }[]>(
    "/api/v1/rag/collections"
  );
  return data ?? [];
}

// ── Agents ───────────────────────────────────────────────────────────────────

export async function listAgents() {
  const { data } = await apiFetch("/api/v1/agents/");
  return (data as { name: string; task_type: string; model: string }[]) ?? [];
}

export async function runAgent(
  instruction: string,
  taskType?: string,
  workflow = false
): Promise<AgentResult | null> {
  const { data } = await apiFetch<AgentResult>("/api/v1/agents/run", {
    method: "POST",
    body: JSON.stringify({ instruction, task_type: taskType, workflow }),
  });
  return data;
}

// ── Memory ───────────────────────────────────────────────────────────────────

export async function recallMemory(query: string, topK = 5) {
  const params = new URLSearchParams({ q: query, top_k: String(topK) });
  const { data } = await apiFetch<unknown[]>(`/api/v1/memory/recall?${params}`);
  return data ?? [];
}

// ── Health ───────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// ── Goals (v2) ────────────────────────────────────────────────────────────────

import type {
  ApprovalRequest, ActivityEvent, Goal, GoalSummary, SystemStatus, Watcher,
} from "./types";

export async function listGoals(status?: string): Promise<GoalSummary[]> {
  const params = status ? `?status=${status}` : "";
  const { data } = await apiFetch<GoalSummary[]>(`/api/v1/goals/${params}`);
  return data ?? [];
}

export async function createGoal(
  title: string,
  description: string,
  autoRun = false
): Promise<Goal | null> {
  const { data } = await apiFetch<Goal>("/api/v1/goals/", {
    method: "POST",
    body: JSON.stringify({ title, description, auto_run: autoRun }),
  });
  return data;
}

export async function getGoal(goalId: string): Promise<Goal | null> {
  const { data } = await apiFetch<Goal>(`/api/v1/goals/${goalId}`);
  return data;
}

export async function runGoal(goalId: string) {
  return apiFetch(`/api/v1/goals/${goalId}/run`, { method: "POST" });
}

export async function pauseGoal(goalId: string) {
  return apiFetch(`/api/v1/goals/${goalId}/pause`, { method: "POST" });
}

export async function cancelGoal(goalId: string) {
  return apiFetch(`/api/v1/goals/${goalId}/cancel`, { method: "POST" });
}

// ── Approvals (v2) ────────────────────────────────────────────────────────────

export async function listApprovals(status = "pending"): Promise<ApprovalRequest[]> {
  const { data } = await apiFetch<ApprovalRequest[]>(`/api/v1/approvals/?status=${status}`);
  return data ?? [];
}

export async function approveAction(approvalId: string) {
  return apiFetch(`/api/v1/approvals/${approvalId}/approve`, { method: "POST" });
}

export async function denyAction(approvalId: string) {
  return apiFetch(`/api/v1/approvals/${approvalId}/deny`, { method: "POST" });
}

// ── System (v2) ───────────────────────────────────────────────────────────────

export async function getSystemStatus(): Promise<SystemStatus | null> {
  const { data } = await apiFetch<SystemStatus>("/api/v1/system/status");
  return data;
}

export async function killSystem() {
  return apiFetch("/api/v1/system/kill", { method: "POST" });
}

export async function resumeSystem() {
  return apiFetch("/api/v1/system/resume", { method: "POST" });
}

// ── Activity (v2) ─────────────────────────────────────────────────────────────

export async function listActivity(
  entityType?: string,
  entityId?: string,
  limit = 50
): Promise<ActivityEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (entityType) params.set("entity_type", entityType);
  if (entityId) params.set("entity_id", entityId);
  const { data } = await apiFetch<ActivityEvent[]>(`/api/v1/activity/?${params}`);
  return data ?? [];
}

// ── Watchers (v2) ─────────────────────────────────────────────────────────────

export async function listWatchers(): Promise<Watcher[]> {
  const { data } = await apiFetch<Watcher[]>("/api/v1/watchers/");
  return data ?? [];
}

export async function addWatcher(
  path: string,
  recursive = true,
  triggerTemplate?: string
): Promise<{ registered: boolean } | null> {
  const { data } = await apiFetch<{ registered: boolean }>("/api/v1/watchers/", {
    method: "POST",
    body: JSON.stringify({ path, recursive, trigger_goal_template: triggerTemplate }),
  });
  return data;
}

export async function removeWatcher(watcherId: string) {
  return apiFetch(`/api/v1/watchers/${watcherId}`, { method: "DELETE" });
}
