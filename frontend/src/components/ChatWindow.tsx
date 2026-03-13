"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ingestFile, sendChatStream } from "@/lib/api";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";
import { VoiceButton } from "./VoiceButton";

export function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [uploading, setUploading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, streamingContent]);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;

      const userMsg: Message = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setStreaming(true);
      setStreamingContent("");

      try {
        // sendChatStream returns the full accumulated text — avoid stale closure
        const fullText = await sendChatStream(
          text,
          sessionId,
          conversationId,
          (token) => setStreamingContent((prev) => prev + token),
          (sid, cid) => {
            setSessionId(sid);
            setConversationId(cid);
          }
        );

        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: fullText },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${String(err)}` },
        ]);
      } finally {
        setStreaming(false);
        setStreamingContent("");
      }
    },
    [streaming, sessionId, conversationId]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await ingestFile(file, "default");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result
            ? `✅ Ingested **${file.name}** — ${result.chunks} chunks from ${result.documents} document(s) added to knowledge base.`
            : `❌ Failed to ingest ${file.name}.`,
        },
      ]);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col flex-1 h-full bg-ailab-bg overflow-hidden">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-ailab-accent flex items-center justify-center mb-4">
              <span className="text-2xl">🧠</span>
            </div>
            <h2 className="text-ailab-text text-xl font-semibold mb-2">AI Lab</h2>
            <p className="text-ailab-muted text-sm max-w-sm">
              Your fully local, privacy-first AI assistant. Ask anything, upload
              documents, or run agents from the side panel.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Live streaming bubble */}
        {streaming && streamingContent && (
          <MessageBubble
            message={{ role: "assistant", content: streamingContent + "▋" }}
          />
        )}

        {streaming && !streamingContent && (
          <div className="flex items-center gap-2 text-ailab-muted text-sm mb-4">
            <div className="w-6 h-6 rounded-full bg-ailab-accent flex items-center justify-center text-white text-xs font-bold">
              AI
            </div>
            <span className="animate-pulse">Thinking…</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="border-t border-ailab-border bg-ailab-surface px-4 py-3">
        <div className="flex items-end gap-2 max-w-4xl mx-auto">
          {/* File upload */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            title="Upload document to knowledge base"
            className="flex-shrink-0 w-10 h-10 rounded-full bg-ailab-bg border border-ailab-border hover:bg-ailab-border flex items-center justify-center text-ailab-muted transition-colors disabled:opacity-50"
          >
            {uploading ? (
              <span className="text-xs animate-spin">⟳</span>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m-8-8h16"
                />
              </svg>
            )}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.md,.txt,.py,.ts,.tsx,.js,.go,.rs,.csv,.json"
            onChange={handleFileUpload}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            placeholder="Message AI Lab… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 resize-none bg-ailab-bg border border-ailab-border rounded-2xl px-4 py-2.5 text-sm text-ailab-text placeholder-ailab-muted focus:outline-none focus:border-ailab-accent transition-colors disabled:opacity-50 max-h-40 overflow-y-auto"
            style={{ minHeight: "42px" }}
          />

          {/* Voice */}
          <VoiceButton onTranscript={(t) => setInput((prev) => prev + t)} />

          {/* Send */}
          <button
            type="button"
            onClick={() => send(input)}
            disabled={!input.trim() || streaming}
            className="flex-shrink-0 w-10 h-10 rounded-full bg-ailab-accent hover:bg-ailab-accent-hover disabled:opacity-40 flex items-center justify-center transition-colors"
          >
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
