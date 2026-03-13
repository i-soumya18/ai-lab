"use client";

import { useCallback, useEffect, useState } from "react";
import { listActivity } from "@/lib/api";
import type { ActivityEvent } from "@/lib/types";

const EVENT_ICONS: Record<string, string> = {
  "goal.": "🎯",
  "approval.": "🔐",
  "agent.": "🤖",
  "file.": "📄",
  "system.": "⚙",
};

function eventIcon(eventType: string): string {
  for (const [prefix, icon] of Object.entries(EVENT_ICONS)) {
    if (eventType.startsWith(prefix)) return icon;
  }
  return "•";
}

function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(isoString).toLocaleDateString();
}

export function ActivityLog() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);

  const refresh = useCallback(async () => {
    const data = await listActivity(undefined, undefined, 40);
    setEvents(data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ailab-muted uppercase tracking-wide">Activity</p>
        <button onClick={refresh} className="text-[10px] text-ailab-muted hover:text-ailab-text">
          Refresh
        </button>
      </div>

      {events.length === 0 ? (
        <p className="text-xs text-ailab-muted">No activity yet.</p>
      ) : (
        <ul className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
          {events.map((e) => (
            <li key={e.id} className="flex gap-2 items-start">
              <span className="text-sm flex-shrink-0 mt-0.5">{eventIcon(e.event_type)}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-ailab-text line-clamp-2">{e.description}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-ailab-muted">{e.event_type}</span>
                  {e.created_at && (
                    <span className="text-[10px] text-ailab-muted">{relativeTime(e.created_at)}</span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
