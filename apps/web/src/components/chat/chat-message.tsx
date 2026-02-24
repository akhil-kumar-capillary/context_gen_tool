"use client";

import { User, Bot, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "./markdown-renderer";
import { ToolCallIndicator } from "./tool-call-indicator";
import type { ChatMessage as ChatMessageType, ToolCallStatus } from "@/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-4",
        isUser ? "bg-white" : "bg-gray-50/50"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-blue-600 text-white"
            : "bg-gradient-to-br from-violet-500 to-purple-600 text-white"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-xs font-medium text-gray-500">
          {isUser ? "You" : "aiRA"}
        </p>

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
          <p className="whitespace-pre-wrap text-sm text-gray-800">
            {message.content}
          </p>
        ) : message.content ? (
          <MarkdownRenderer
            content={message.content}
            className="prose-sm max-w-none text-gray-800"
          />
        ) : !message.error ? (
          <p className="text-sm italic text-gray-400">No response</p>
        ) : null}

        {/* Token usage */}
        {isAssistant && message.tokenUsage && (
          <div className="mt-2 flex items-center gap-3 text-[10px] text-gray-400">
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
    <div className="flex gap-3 bg-gray-50/50 px-4 py-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600 text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-xs font-medium text-gray-500">aiRA</p>

        {/* Active tool calls */}
        {toolCalls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {toolCalls.map((tc) => (
              <ToolCallIndicator key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Streaming text */}
        {text ? (
          <MarkdownRenderer
            content={text}
            className="prose-sm max-w-none text-gray-800"
          />
        ) : toolCalls.length === 0 ? (
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-violet-400" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
