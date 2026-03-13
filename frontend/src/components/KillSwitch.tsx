"use client";

import { useCallback, useEffect, useState } from "react";
import { getSystemStatus, killSystem, resumeSystem } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

export function KillSwitch() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    const s = await getSystemStatus();
    setStatus(s);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const toggle = async () => {
    setLoading(true);
    try {
      if (status?.kill_switch_active) {
        await resumeSystem();
      } else {
        await killSystem();
      }
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  const isKilled = status?.kill_switch_active ?? false;

  return (
    <div className="flex items-center gap-2">
      {status && (
        <span className="text-xs text-ailab-muted hidden sm:block">
          {status.running_goals} running · {status.pending_approvals} approvals
        </span>
      )}
      <button
        onClick={toggle}
        disabled={loading}
        title={isKilled ? "Kill switch active — click to resume" : "Click to activate kill switch"}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-50 ${
          isKilled
            ? "bg-red-600 text-white animate-pulse hover:bg-red-700"
            : "bg-ailab-surface border border-ailab-border text-ailab-muted hover:border-red-500 hover:text-red-500"
        }`}
      >
        <span>{isKilled ? "■" : "⏹"}</span>
        <span>{isKilled ? "KILL ACTIVE" : "Kill Switch"}</span>
      </button>
    </div>
  );
}
