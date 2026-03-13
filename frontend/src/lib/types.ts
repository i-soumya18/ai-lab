import { z } from "zod";

// ── Chat ─────────────────────────────────────────────────────────────────────

export const MessageSchema = z.object({
  id: z.string().optional(),
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
  timestamp: z.string().optional(),
});
export type Message = z.infer<typeof MessageSchema>;

export const ConversationSchema = z.object({
  id: z.string(),
  title: z.string().nullable(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  messages: z.array(MessageSchema).optional(),
});
export type Conversation = z.infer<typeof ConversationSchema>;

export const ChatResponseSchema = z.object({
  data: z
    .object({
      response: z.string(),
      session_id: z.string(),
      conversation_id: z.string(),
      model: z.string(),
    })
    .nullable(),
  error: z.string().nullable(),
});

// ── RAG ──────────────────────────────────────────────────────────────────────

export const RAGChunkSchema = z.object({
  id: z.string().nullable(),
  content: z.string(),
  metadata: z.record(z.unknown()).default({}),
  score: z.number().default(0),
});
export type RAGChunk = z.infer<typeof RAGChunkSchema>;

export const RAGSearchResponseSchema = z.object({
  data: z.array(RAGChunkSchema).nullable(),
  error: z.string().nullable(),
});

export const CollectionSchema = z.object({
  name: z.string(),
  count: z.number(),
});
export type Collection = z.infer<typeof CollectionSchema>;

// ── Agents ───────────────────────────────────────────────────────────────────

export const AgentInfoSchema = z.object({
  name: z.string(),
  task_type: z.string(),
  model: z.string(),
});
export type AgentInfo = z.infer<typeof AgentInfoSchema>;

export const AgentResultSchema = z.object({
  task_id: z.string(),
  agent_name: z.string(),
  success: z.boolean(),
  output: z.string(),
  artifacts: z.array(z.record(z.unknown())).default([]),
  sources: z.array(z.string()).default([]),
  steps_taken: z.number(),
  duration_ms: z.number(),
  model_used: z.string(),
  error: z.string().nullable(),
});
export type AgentResult = z.infer<typeof AgentResultSchema>;

// ── SSE streaming token ───────────────────────────────────────────────────────

export type SSEEvent =
  | { type: "meta"; session_id: string; conversation_id: string }
  | { type: "token"; content: string }
  | { type: "done"; content: string }
  | { type: "error"; content: string };

// ── Goal OS (v2) ──────────────────────────────────────────────────────────────

export const GoalTaskStatusValues = [
  "pending", "running", "awaiting_approval", "completed", "failed", "skipped",
] as const;
export type GoalTaskStatus = typeof GoalTaskStatusValues[number];

export const GoalStatusValues = [
  "pending", "planning", "running", "awaiting_approval", "paused",
  "completed", "failed", "cancelled",
] as const;
export type GoalStatus = typeof GoalStatusValues[number];

export const GoalTaskSchema = z.object({
  step_number: z.number(),
  task_type: z.string(),
  instruction: z.string(),
  depends_on: z.array(z.number()).default([]),
  requires_approval: z.boolean().default(false),
  status: z.string().default("pending"),
  result: z.record(z.unknown()).default({}),
  error: z.string().nullable().optional(),
  approval_id: z.string().nullable().optional(),
});
export type GoalTask = z.infer<typeof GoalTaskSchema>;

export const GoalSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().default(""),
  status: z.string(),
  tasks: z.array(GoalTaskSchema).default([]),
  context: z.record(z.unknown()).default({}),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type Goal = z.infer<typeof GoalSchema>;

export const GoalSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  status: z.string(),
  task_count: z.number(),
  completed_tasks: z.number(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type GoalSummary = z.infer<typeof GoalSummarySchema>;

export const ApprovalRequestSchema = z.object({
  id: z.string(),
  goal_id: z.string().nullable().optional(),
  task_step: z.number().nullable().optional(),
  action_type: z.string(),
  action_description: z.string(),
  action_payload: z.record(z.unknown()).default({}),
  status: z.string(),
  requested_at: z.string().nullable().optional(),
  resolved_at: z.string().nullable().optional(),
  resolved_by: z.string().nullable().optional(),
});
export type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

export const ActivityEventSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  entity_type: z.string().nullable().optional(),
  entity_id: z.string().nullable().optional(),
  description: z.string(),
  payload: z.record(z.unknown()).default({}),
  created_at: z.string().nullable().optional(),
});
export type ActivityEvent = z.infer<typeof ActivityEventSchema>;

export const WatcherSchema = z.object({
  id: z.string(),
  path: z.string(),
  recursive: z.boolean(),
  trigger_goal_template: z.string().nullable().optional(),
  enabled: z.boolean(),
  created_at: z.string().nullable().optional(),
});
export type Watcher = z.infer<typeof WatcherSchema>;

export const SystemStatusSchema = z.object({
  kill_switch_active: z.boolean(),
  running_goals: z.number(),
  pending_approvals: z.number(),
  goal_counts: z.record(z.number()).default({}),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;
