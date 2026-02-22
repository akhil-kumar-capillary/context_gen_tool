"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/stores/chat-store";
import { ChatMessage, StreamingMessage } from "./chat-message";

export function ChatMessageList() {
  const { messages, isStreaming, streamingText, activeToolCalls } =
    useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, activeToolCalls]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-100 to-purple-100">
          <svg
            className="h-8 w-8 text-violet-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
        </div>
        <h3 className="mb-2 text-lg font-semibold text-gray-800">
          Start a conversation
        </h3>
        <p className="max-w-sm text-sm text-gray-500">
          Ask me about your context documents, or tell me to list, create,
          update, or refactor them. I can also answer general questions.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {[
            "List my contexts",
            "Create a new context",
            "Refactor all contexts",
            "What contexts do I have?",
          ].map((suggestion) => (
            <button
              key={suggestion}
              className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700"
              onClick={() => {
                // Find the chat input and set its value
                const input = document.querySelector(
                  '[data-chat-input]'
                ) as HTMLTextAreaElement;
                if (input) {
                  input.value = suggestion;
                  input.focus();
                  // Trigger a React-compatible change event
                  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype,
                    'value'
                  )?.set;
                  nativeInputValueSetter?.call(input, suggestion);
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                }
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto divide-y divide-gray-100"
    >
      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}

      {isStreaming && (
        <StreamingMessage text={streamingText} toolCalls={activeToolCalls} />
      )}

      <div ref={bottomRef} />
    </div>
  );
}
