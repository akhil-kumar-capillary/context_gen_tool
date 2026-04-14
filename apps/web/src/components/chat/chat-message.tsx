"use client";

import { User, Bot, AlertCircle, Copy, Check } from "lucide-react";
import { useState } from "react";
import { cn, formatDate } from "@/lib/utils";
import { MarkdownRenderer } from "./markdown-renderer";
import { ToolCallIndicator } from "./tool-call-indicator";
import type { ChatMessage as ChatMessageType, ToolCallStatus } from "@/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (non-HTTPS or permission denied)
    }
  };

  return (
    <div
      className={cn(
        "group flex gap-3 px-4 py-4",
        isUser ? "bg-background" : "bg-muted/30",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary/10 text-primary" : "bg-primary text-primary-foreground",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground">
            {isUser ? "You" : "aiRA"}
          </p>
          <div className="flex items-center gap-2">
            {isAssistant && message.content && (
              <button
                onClick={handleCopy}
                className="rounded p-1 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground hover:bg-muted"
                aria-label="Copy message"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            )}
            <span className="text-xs text-muted-foreground/40 group-hover:text-muted-foreground transition-colors">
              {formatDate(message.createdAt)}
            </span>
          </div>
        </div>

        {/* Tool call indicators (before content for assistant) */}
        {isAssistant && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {message.toolCalls.map((tc) => (
              <ToolCallIndicator key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Error display */}
        {isAssistant && message.error && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
            <div>
              <p className="font-medium">Something went wrong</p>
              <p className="mt-0.5 text-xs text-red-600">{message.error}</p>
            </div>
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm text-foreground">
            {message.content}
          </p>
        ) : message.content ? (
          <MarkdownRenderer
            content={message.content}
            className="prose-sm max-w-none text-foreground"
          />
        ) : !message.error ? (
          <p className="text-sm italic text-muted-foreground">No response</p>
        ) : null}

        {/* Token usage */}
        {isAssistant && message.tokenUsage && (
          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            <span>
              {message.tokenUsage.input_tokens?.toLocaleString()} in /{" "}
              {message.tokenUsage.output_tokens?.toLocaleString()} out
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Streaming message — renders the in-progress assistant response.
 */
interface StreamingMessageProps {
  text: string;
  toolCalls: ToolCallStatus[];
}

export function StreamingMessage({ text, toolCalls }: StreamingMessageProps) {
  return (
    <div className="flex gap-3 bg-muted/50 px-4 py-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-xs font-medium text-muted-foreground">aiRA</p>

        {/* Active tool calls */}
        {toolCalls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {toolCalls.map((tc) => (
              <ToolCallIndicator key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Streaming text or thinking indicator */}
        {text ? (
          <MarkdownRenderer
            content={text}
            className="prose-sm max-w-none text-foreground"
          />
        ) : (
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-primary" />
          </div>
        )}
      </div>
    </div>
  );
}
