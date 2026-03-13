"use client";

import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/lib/types";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={clsx("flex w-full mb-4", isUser ? "justify-end" : "justify-start")}>
      {/* Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-ailab-accent flex items-center justify-center text-white text-xs font-bold mr-3 mt-1">
          AI
        </div>
      )}

      {/* Bubble */}
      <div
        className={clsx(
          "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed break-words",
          isUser
            ? "bg-ailab-accent text-white rounded-br-sm"
            : "bg-ailab-surface text-ailab-text border border-ailab-border rounded-bl-sm"
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <div
            className={clsx(
              "markdown-body",
              "[&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0",
              "[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2",
              "[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2",
              "[&_li]:my-1",
              "[&_a]:underline [&_a]:text-ailab-accent",
              "[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:bg-ailab-bg [&_pre]:border [&_pre]:border-ailab-border",
              "[&_code]:font-mono [&_code]:text-[0.9em]",
              "[&_table]:w-full [&_table]:text-left [&_table]:border-collapse [&_table]:my-2",
              "[&_th]:border [&_th]:border-ailab-border [&_th]:px-2 [&_th]:py-1",
              "[&_td]:border [&_td]:border-ailab-border [&_td]:px-2 [&_td]:py-1",
              "[&_blockquote]:border-l-2 [&_blockquote]:border-ailab-border [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:my-2"
            )}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" />
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-ailab-user border border-ailab-border flex items-center justify-center text-ailab-muted text-xs font-bold ml-3 mt-1">
          U
        </div>
      )}
    </div>
  );
}
