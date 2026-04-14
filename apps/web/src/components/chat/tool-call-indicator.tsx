"use client";

import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCallStatus } from "@/types";

interface ToolCallIndicatorProps {
  toolCall: ToolCallStatus;
}

const TOOL_LABELS: Record<string, string> = {
  // Context Management
  list_contexts: "Listing contexts",
  get_context_content: "Reading context",
  create_context: "Creating context",
  update_context: "Updating context",
  delete_context: "Deleting context",
  refactor_all_contexts: "Refactoring contexts",
  // Context Engine
  read_context_tree: "Reading tree structure",
  modify_context_tree: "Modifying context tree",
  remove_from_context_tree: "Removing from tree",
  save_tree_checkpoint: "Saving version",
  sync_tree_to_capillary: "Syncing to Capillary",
  generate_context_tree: "Generating context tree",
  restructure_tree: "Restructuring tree",
  grep_context_tree: "Searching tree content",
  read_tree_node_content: "Reading node content",
};

const TOOL_PREPARING_LABELS: Record<string, string> = {
  // Context Management
  list_contexts: "Preparing to list contexts...",
  get_context_content: "Preparing to read context...",
  create_context: "Generating context document...",
  update_context: "Preparing context update...",
  delete_context: "Preparing to delete context...",
  refactor_all_contexts: "Preparing to refactor contexts...",
  // Context Engine
  read_context_tree: "Loading tree structure...",
  modify_context_tree: "Analyzing tree for modification...",
  remove_from_context_tree: "Preparing removal...",
  save_tree_checkpoint: "Saving tree version...",
  sync_tree_to_capillary: "Preparing sync to Capillary...",
  generate_context_tree: "Starting tree generation...",
  restructure_tree: "Planning restructure...",
  grep_context_tree: "Searching tree content...",
  read_tree_node_content: "Loading node content...",
};

export function ToolCallIndicator({ toolCall }: ToolCallIndicatorProps) {
  const isPreparing = toolCall.status === "preparing";
  const isRunning = toolCall.status === "running";
  const isDone = toolCall.status === "done";
  const isError = toolCall.status === "error";

  const label = isPreparing
    ? toolCall.display || TOOL_PREPARING_LABELS[toolCall.name] || `Preparing ${toolCall.name}...`
    : toolCall.display || TOOL_LABELS[toolCall.name] || `Running ${toolCall.name}`;

  return (
    <div
      className={cn(
        "my-2 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all",
        isPreparing && "bg-primary/5 text-primary border border-primary/20 animate-pulse",
        isRunning && "bg-blue-50 text-blue-700 border border-blue-200",
        isDone && "bg-green-50 text-green-700 border border-green-200",
        isError && "bg-red-50 text-red-700 border border-red-200"
      )}
    >
      {isPreparing && <Loader2 className="h-3 w-3 animate-spin" />}
      {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
      {isDone && <CheckCircle2 className="h-3 w-3" />}
      {isError && <AlertCircle className="h-3 w-3" />}
      <span>{isDone ? (toolCall.summary || label) : label}</span>
    </div>
  );
}
