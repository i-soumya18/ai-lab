"use client";

import { useCallback, useEffect, useState } from "react";
import {
  cancelGoal,
  createGoal,
  listGoals,
  pauseGoal,
  runGoal,
} from "@/lib/api";
import type { GoalSummary } from "@/lib/types";
import { GoalDetail } from "./GoalDetail";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/20 text-yellow-400",
  planning: "bg-blue-500/20 text-blue-400",
  running: "bg-green-500/20 text-green-400",
  awaiting_approval: "bg-orange-500/20 text-orange-400",
  paused: "bg-gray-500/20 text-gray-400",
  completed: "bg-emerald-500/20 text-emerald-400",
  failed: "bg-red-500/20 text-red-400",
  cancelled: "bg-gray-500/20 text-gray-400",
};

export function GoalPanel() {
  const [goals, setGoals] = useState<GoalSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await listGoals();
    setGoals(data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const handleCreate = async () => {
    if (!title.trim()) return;
    setCreating(true);
    try {
      await createGoal(title.trim(), description.trim());
      setTitle("");
      setDescription("");
      setShowForm(false);
      await refresh();
    } finally {
      setCreating(false);
    }
  };

  const handleRun = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setLoading(true);
    try { await runGoal(id); await refresh(); }
    finally { setLoading(false); }
  };

  const handlePause = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await pauseGoal(id);
    await refresh();
  };

  const handleCancel = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Cancel this goal?")) return;
    await cancelGoal(id);
    await refresh();
  };

  if (selectedGoalId) {
    return (
      <GoalDetail
        goalId={selectedGoalId}
        onBack={() => { setSelectedGoalId(null); refresh(); }}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ailab-muted uppercase tracking-wide">Goals</p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-xs text-ailab-accent hover:underline"
        >
          {showForm ? "Cancel" : "+ New"}
        </button>
      </div>

      {showForm && (
        <div className="space-y-2 p-3 bg-ailab-bg border border-ailab-border rounded-lg">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Goal title..."
            className="w-full bg-transparent border border-ailab-border rounded px-2 py-1.5 text-xs text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what should happen in detail..."
            rows={3}
            className="w-full bg-transparent border border-ailab-border rounded px-2 py-1.5 text-xs text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent resize-none"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !title.trim()}
            className="w-full py-1.5 bg-ailab-accent hover:bg-ailab-accent-hover text-white text-xs rounded-lg disabled:opacity-50"
          >
            {creating ? "Planning..." : "Create & Plan"}
          </button>
        </div>
      )}

      {goals.length === 0 ? (
        <p className="text-xs text-ailab-muted">No goals yet. Create one above.</p>
      ) : (
        <ul className="space-y-2">
          {goals.map((g) => (
            <li
              key={g.id}
              onClick={() => setSelectedGoalId(g.id)}
              className="p-2.5 rounded-lg bg-ailab-bg border border-ailab-border cursor-pointer hover:border-ailab-accent transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-semibold text-ailab-text leading-snug flex-1">
                  {g.title}
                </span>
                <span
                  className={`flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    STATUS_COLORS[g.status] ?? "bg-gray-500/20 text-gray-400"
                  }`}
                >
                  {g.status}
                </span>
              </div>
              {g.task_count > 0 && (
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="flex-1 bg-ailab-border rounded-full h-1">
                    <div
                      className="bg-ailab-accent h-1 rounded-full transition-all"
                      style={{ width: `${(g.completed_tasks / g.task_count) * 100}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-ailab-muted">
                    {g.completed_tasks}/{g.task_count}
                  </span>
                </div>
              )}
              <div className="flex gap-1.5 mt-2">
                {["pending", "paused", "failed"].includes(g.status) && (
                  <button
                    onClick={(e) => handleRun(g.id, e)}
                    disabled={loading}
                    className="px-2 py-0.5 text-[10px] bg-green-600/20 text-green-400 rounded hover:bg-green-600/30"
                  >
                    Run
                  </button>
                )}
                {g.status === "running" && (
                  <button
                    onClick={(e) => handlePause(g.id, e)}
                    className="px-2 py-0.5 text-[10px] bg-yellow-600/20 text-yellow-400 rounded hover:bg-yellow-600/30"
                  >
                    Pause
                  </button>
                )}
                {!["completed", "cancelled"].includes(g.status) && (
                  <button
                    onClick={(e) => handleCancel(g.id, e)}
                    className="px-2 py-0.5 text-[10px] bg-red-600/20 text-red-400 rounded hover:bg-red-600/30"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
