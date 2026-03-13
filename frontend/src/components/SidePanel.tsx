"use client";

import { useEffect, useState } from "react";
import { listAgents, listCollections, ragSearch } from "@/lib/api";
import type { Collection } from "@/lib/types";
import { ActivityLog } from "./ActivityLog";
import { GoalPanel } from "./GoalPanel";
import { WatcherPanel } from "./WatcherPanel";

type Tab = "knowledge" | "agents" | "goals" | "activity" | "watchers";

const TABS: { key: Tab; label: string }[] = [
  { key: "knowledge", label: "Knowledge" },
  { key: "agents",    label: "Agents" },
  { key: "goals",     label: "Goals" },
  { key: "activity",  label: "Activity" },
  { key: "watchers",  label: "Watch" },
];

interface Props {
  onAgentResult: (result: string) => void;
}

export function SidePanel({ onAgentResult }: Props) {
  const [tab, setTab] = useState<Tab>("knowledge");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [agents, setAgents] = useState<{ name: string; task_type: string }[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{ content: string; score: number }[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    listCollections().then(setCollections).catch(() => {});
    listAgents().then(setAgents).catch(() => {});
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const results = await ragSearch(searchQuery, "default", 5);
      setSearchResults(results);
    } finally {
      setSearching(false);
    }
  };

  return (
    <aside className="w-72 flex-shrink-0 bg-ailab-surface border-l border-ailab-border flex flex-col h-full">
      {/* Tabs — horizontal scroll so all 5 fit at the sidebar width */}
      <div className="flex overflow-x-auto border-b border-ailab-border" style={{ scrollbarWidth: "none" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-shrink-0 px-3 py-3 text-[10px] font-semibold uppercase tracking-wide transition-colors ${
              tab === t.key
                ? "text-ailab-accent border-b-2 border-ailab-accent"
                : "text-ailab-muted hover:text-ailab-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {tab === "knowledge" && (
          <>
            <div>
              <p className="text-xs text-ailab-muted uppercase tracking-wide mb-2">Collections</p>
              {collections.length === 0 ? (
                <p className="text-xs text-ailab-muted">No collections yet. Ingest a document.</p>
              ) : (
                <ul className="space-y-1">
                  {collections.map((c) => (
                    <li
                      key={c.name}
                      className="flex justify-between items-center text-xs px-2 py-1 rounded bg-ailab-bg border border-ailab-border"
                    >
                      <span className="text-ailab-text">{c.name}</span>
                      <span className="text-ailab-muted">{c.count} chunks</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="text-xs text-ailab-muted uppercase tracking-wide mb-2">
                Search Knowledge Base
              </p>
              <div className="flex gap-2">
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  placeholder="Search..."
                  className="flex-1 bg-ailab-bg border border-ailab-border rounded-lg px-3 py-1.5 text-xs text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent"
                />
                <button
                  onClick={handleSearch}
                  disabled={searching}
                  className="px-3 py-1.5 bg-ailab-accent hover:bg-ailab-accent-hover text-white text-xs rounded-lg disabled:opacity-50"
                >
                  {searching ? "..." : "Go"}
                </button>
              </div>

              {searchResults.length > 0 && (
                <ul className="mt-2 space-y-2">
                  {searchResults.map((r, i) => (
                    <li
                      key={i}
                      className="text-xs p-2 bg-ailab-bg rounded border border-ailab-border text-ailab-text line-clamp-3"
                    >
                      {r.content}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}

        {tab === "agents" && (
          <div>
            <p className="text-xs text-ailab-muted uppercase tracking-wide mb-2">
              Available Agents
            </p>
            {agents.length === 0 ? (
              <p className="text-xs text-ailab-muted">Loading agents...</p>
            ) : (
              <ul className="space-y-2">
                {agents.map((a) => (
                  <li
                    key={a.name}
                    className="p-2 rounded-lg bg-ailab-bg border border-ailab-border"
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500" />
                      <span className="text-xs font-semibold text-ailab-text capitalize">
                        {a.name} Agent
                      </span>
                    </div>
                    <p className="text-xs text-ailab-muted mt-0.5 ml-4">
                      {a.task_type} tasks
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {tab === "goals" && <GoalPanel />}
        {tab === "activity" && <ActivityLog />}
        {tab === "watchers" && <WatcherPanel />}
      </div>
    </aside>
  );
}
