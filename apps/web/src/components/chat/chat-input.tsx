"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";
import { useSettingsStore, ANTHROPIC_MODELS, OPENAI_MODELS } from "@/stores/settings-store";

interface ChatInputProps {
  onSend: (content: string) => void;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isStreaming } = useChatStore();
  const { provider, model, setProvider, setModel } = useSettingsStore();

  const models = provider === "anthropic" ? ANTHROPIC_MODELS : OPENAI_MODELS;

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      {/* Model selector */}
      <div className="mb-2 flex items-center gap-2">
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as "anthropic" | "openai")}
          className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs text-gray-600 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
        >
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
        </select>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs text-gray-600 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {/* Input area */}
      <div className="flex items-end gap-2">
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            data-chat-input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onInput={(e) => setInput((e.target as HTMLTextAreaElement).value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your contexts, or chat with aiRA..."
            disabled={isStreaming}
            rows={1}
            className={cn(
              "w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 pr-12 text-sm",
              "placeholder:text-gray-400",
              "focus:border-violet-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-violet-100",
              "disabled:opacity-50",
              "transition-all"
            )}
          />
        </div>
        <button
          onClick={handleSend}
          disabled={!input.trim() || isStreaming}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all",
            input.trim() && !isStreaming
              ? "bg-violet-600 text-white hover:bg-violet-700 shadow-sm"
              : "bg-gray-100 text-gray-400"
          )}
        >
          {isStreaming ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>

      <p className="mt-1.5 text-center text-[10px] text-gray-400">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
