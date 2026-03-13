"use client";

import { useState } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { SidePanel } from "@/components/SidePanel";
import { ApprovalModal } from "@/components/ApprovalModal";
import { KillSwitch } from "@/components/KillSwitch";

export default function Home() {
  const [agentOutput, setAgentOutput] = useState("");

  return (
    <main className="flex h-screen w-full overflow-hidden">
      {/* ApprovalModal renders at root level, overlays everything when approvals are pending */}
      <ApprovalModal />

      {/* Main content */}
      <div className="flex flex-col flex-1 overflow-hidden">
        <header className="flex items-center justify-between px-6 py-3 bg-ailab-surface border-b border-ailab-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-ailab-accent flex items-center justify-center text-white font-bold text-sm">
              AI
            </div>
            <div>
              <h1 className="text-sm font-semibold text-ailab-text">AI Lab</h1>
              <p className="text-xs text-ailab-muted">Local AI OS · Fully offline</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-xs text-ailab-muted">Ollama connected</span>
            </div>
            {/* Kill switch — always visible in header */}
            <KillSwitch />
          </div>
        </header>

        {/* Main chat */}
        <ChatWindow />
      </div>

      {/* Side panel */}
      <SidePanel onAgentResult={setAgentOutput} />
    </main>
  );
}
