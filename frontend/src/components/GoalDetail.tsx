"use client";

import { useCallback, useEffect, useState } from "react";
import { cancelGoal, getGoal, pauseGoal, runGoal } from "@/lib/api";
import type { Goal, GoalTask } from "@/lib/types";

interface Props {
  goalId: string;
  onBack: () => void;
}

const STEP_ICON: Record<string, string> = {
  pending: "○",
  running: "◉",
  awaiting_approval: "⏸",
  completed: "✓",
  failed: "✗",
  skipped: "—",
};

const STEP_COLOR: Record<string, string> = {
  pending: "text-ailab-muted",
  running: "text-blue-400 animate-pulse",
  awaiting_approval: "text-orange-400",
  completed: "text-green-400",
  failed: "text-red-400",
  skipped: "text-ailab-muted",
};

export function GoalDetail({ goalId, onBack }: Props) {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    const g = await getGoal(goalId);
    setGoal(g);
  }, [goalId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  if (!goal) {
    return (
      <div className="space-y-3">
        <button onClick={onBack} className="text-xs text-ailab-accent hover:underline">← Back</button>
        <p className="text-xs text-ailab-muted">Loading...</p>
      </div>
    );
  }

  const handleRun = async () => {
    setLoading(true);
    try { await runGoal(goalId); await refresh(); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-3">
      <button onClick={onBack} className="text-xs text-ailab-accent hover:underline">← All Goals</button>

      <div>
        <h3 className="text-sm font-semibold text-ailab-text">{goal.title}</h3>
        {goal.description && (
          <p className="text-xs text-ailab-muted mt-0.5 line-clamp-2">{goal.description}</p>
        )}
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-ailab-surface border border-ailab-border text-ailab-muted">
            {goal.status}
          </span>
          {["pending", "paused", "failed"].includes(goal.status) && (
            <button
              onClick={handleRun}
              disabled={loading}
              className="text-[10px] px-2 py-0.5 bg-green-600/20 text-green-400 rounded"
            >
              {loading ? "Starting..." : "Run"}
            </button>
          )}
          {goal.status === "running" && (
            <button
              onClick={() => pauseGoal(goalId).then(refresh)}
              className="text-[10px] px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded"
            >
              Pause
            </button>
          )}
        </div>
      </div>

      <div>
        <p className="text-[10px] text-ailab-muted uppercase tracking-wide mb-2">Task Steps</p>
        {goal.tasks.length === 0 ? (
          <p className="text-xs text-ailab-muted">No tasks planned yet.</p>
        ) : (
          <ol className="space-y-2">
            {goal.tasks.map((t: GoalTask) => (
              <li key={t.step_number} className="flex gap-2">
                <span className={`text-sm font-mono flex-shrink-0 ${STEP_COLOR[t.status] ?? "text-ailab-muted"}`}>
                  {STEP_ICON[t.status] ?? "○"}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] px-1.5 bg-ailab-surface border border-ailab-border rounded text-ailab-muted">
                      {t.task_type}
                    </span>
                    {t.requires_approval && (
                      <span className="text-[10px] text-orange-400">requires approval</span>
                    )}
                  </div>
                  <p className="text-xs text-ailab-text mt-0.5 line-clamp-2">{t.instruction}</p>
                  {t.status === "completed" && (t.result as any)?.output && (
                    <p className="text-[10px] text-ailab-muted mt-1 line-clamp-2 italic">
                      {String((t.result as any).output).slice(0, 120)}...
                    </p>
                  )}
                  {t.error && (
                    <p className="text-[10px] text-red-400 mt-1">{t.error}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
