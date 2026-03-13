"use client";

import { useCallback, useEffect, useState } from "react";
import { addWatcher, listWatchers, removeWatcher } from "@/lib/api";
import type { Watcher } from "@/lib/types";

export function WatcherPanel() {
  const [watchers, setWatchers] = useState<Watcher[]>([]);
  const [path, setPath] = useState("");
  const [template, setTemplate] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const refresh = useCallback(async () => {
    const data = await listWatchers();
    setWatchers(data);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleAdd = async () => {
    if (!path.trim()) return;
    setAdding(true);
    try {
      await addWatcher(path.trim(), recursive, template.trim() || undefined);
      setPath("");
      setTemplate("");
      setShowForm(false);
      await refresh();
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (id: string) => {
    if (!confirm("Remove this watcher?")) return;
    await removeWatcher(id);
    await refresh();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ailab-muted uppercase tracking-wide">Watched Paths</p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-xs text-ailab-accent hover:underline"
        >
          {showForm ? "Cancel" : "+ Add"}
        </button>
      </div>

      {showForm && (
        <div className="space-y-2 p-3 bg-ailab-bg border border-ailab-border rounded-lg">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/app/watched/my-folder"
            className="w-full bg-transparent border border-ailab-border rounded px-2 py-1.5 text-xs text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent"
          />
          <input
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            placeholder="Goal template: Summarize {{path}} ({{event}})"
            className="w-full bg-transparent border border-ailab-border rounded px-2 py-1.5 text-xs text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent"
          />
          <label className="flex items-center gap-2 text-xs text-ailab-muted cursor-pointer">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              className="accent-ailab-accent"
            />
            Recursive
          </label>
          <button
            onClick={handleAdd}
            disabled={adding || !path.trim()}
            className="w-full py-1.5 bg-ailab-accent hover:bg-ailab-accent-hover text-white text-xs rounded-lg disabled:opacity-50"
          >
            {adding ? "Adding..." : "Add Watcher"}
          </button>
        </div>
      )}

      {watchers.length === 0 ? (
        <p className="text-xs text-ailab-muted">No watched paths. Add one to trigger goals on file changes.</p>
      ) : (
        <ul className="space-y-2">
          {watchers.map((w) => (
            <li
              key={w.id}
              className={`p-2.5 rounded-lg bg-ailab-bg border text-xs ${
                w.enabled ? "border-ailab-border" : "border-ailab-border opacity-50"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-ailab-text font-mono truncate">{w.path}</p>
                  <p className="text-ailab-muted mt-0.5">
                    {w.recursive ? "recursive" : "top-level only"}
                    {w.trigger_goal_template && ` · auto-goal`}
                  </p>
                </div>
                <button
                  onClick={() => handleRemove(w.id)}
                  className="text-red-400 hover:text-red-300 text-lg leading-none"
                  title="Remove watcher"
                >
                  ×
                </button>
              </div>
              {w.trigger_goal_template && (
                <p className="text-[10px] text-ailab-muted mt-1 italic truncate">
                  {w.trigger_goal_template}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
