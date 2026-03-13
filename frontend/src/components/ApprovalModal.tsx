"use client";

import { useCallback, useEffect, useState } from "react";
import { approveAction, denyAction, listApprovals } from "@/lib/api";
import type { ApprovalRequest } from "@/lib/types";

/**
 * ApprovalModal — renders as a full-screen overlay when there are pending approvals.
 * Polls every 3 seconds. Cannot be dismissed — the user must approve or deny each action.
 */
export function ApprovalModal() {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [resolving, setResolving] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await listApprovals("pending");
    setApprovals(data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  if (approvals.length === 0) return null;

  const current = approvals[0];

  const handle = async (approve: boolean) => {
    setResolving(current.id);
    try {
      if (approve) {
        await approveAction(current.id);
      } else {
        await denyAction(current.id);
      }
      await refresh();
    } finally {
      setResolving(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 bg-ailab-surface border border-orange-500/50 rounded-2xl shadow-2xl p-6 space-y-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-orange-500/20 flex items-center justify-center text-orange-400 text-xl">
            ⚠
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ailab-text">Approval Required</h2>
            <p className="text-xs text-ailab-muted">
              {approvals.length > 1 ? `${approvals.length} pending — showing first` : "1 pending request"}
            </p>
          </div>
        </div>

        {/* Action details */}
        <div className="bg-ailab-bg rounded-lg p-3 space-y-2 border border-ailab-border">
          <div className="flex items-center gap-2">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400 font-medium">
              {current.action_type}
            </span>
            {current.goal_id && (
              <span className="text-[10px] text-ailab-muted">Goal step {current.task_step ?? "-"}</span>
            )}
          </div>
          <p className="text-sm text-ailab-text">{current.action_description}</p>
          {Object.keys(current.action_payload ?? {}).length > 0 && (
            <pre className="text-[10px] text-ailab-muted bg-ailab-surface rounded p-2 overflow-x-auto max-h-32">
              {JSON.stringify(current.action_payload, null, 2)}
            </pre>
          )}
          {current.requested_at && (
            <p className="text-[10px] text-ailab-muted">
              Requested at {new Date(current.requested_at).toLocaleTimeString()}
            </p>
          )}
        </div>

        {/* Buttons */}
        <div className="flex gap-3">
          <button
            onClick={() => handle(true)}
            disabled={resolving !== null}
            className="flex-1 py-2.5 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
          >
            {resolving === current.id ? "..." : "Approve"}
          </button>
          <button
            onClick={() => handle(false)}
            disabled={resolving !== null}
            className="flex-1 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
          >
            Deny
          </button>
        </div>
      </div>
    </div>
  );
}
