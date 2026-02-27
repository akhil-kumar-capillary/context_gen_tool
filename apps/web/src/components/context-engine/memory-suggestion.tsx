"use client";

import { Lightbulb, Check, Pencil, X } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──

interface Evidence {
  text: string;
  session: string;
}

export interface MemoryData {
  pattern: string;
  evidence: Evidence[];
  confidence: number;
  sessions: number;
  mentions: number;
  node: string;
  preview: string;
}

// ── MemorySuggestion ──

export function MemorySuggestion({
  data,
  onApprove,
  onEdit,
  onDismiss,
}: {
  data: MemoryData;
  onApprove?: () => void;
  onEdit?: () => void;
  onDismiss?: () => void;
}) {
  const confidenceColor =
    data.confidence >= 80
      ? "text-green-700 bg-green-50"
      : data.confidence >= 60
        ? "text-amber-700 bg-amber-50"
        : "text-gray-700 bg-gray-50";

  return (
    <div className="rounded-xl border border-violet-200 bg-violet-50/50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start gap-2">
        <Lightbulb className="h-4 w-4 text-violet-500 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-[13px] font-semibold text-violet-900">
            Memory Suggestion
          </p>
          <p className="text-[13px] text-gray-700 mt-1">{data.pattern}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold",
            confidenceColor
          )}
        >
          {data.confidence}%
        </span>
      </div>

      {/* Evidence */}
      <div className="space-y-1">
        <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">
          Evidence ({data.sessions} sessions, {data.mentions} mentions)
        </p>
        {data.evidence.map((e, i) => (
          <div
            key={i}
            className="flex items-start gap-2 text-[12px] text-gray-600"
          >
            <span className="text-gray-300 shrink-0">&ldquo;</span>
            <span className="flex-1 italic">{e.text}</span>
            <span className="shrink-0 text-[10px] text-gray-400">
              {e.session}
            </span>
          </div>
        ))}
      </div>

      {/* Target node */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-gray-500">Target:</span>
        <span className="text-[11px] font-medium text-violet-700">
          {data.node}
        </span>
      </div>

      {/* Preview */}
      <div className="rounded-lg bg-white border border-gray-200 p-2.5 text-xs text-gray-700">
        {data.preview}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onApprove}
          className="flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 transition-colors"
        >
          <Check className="h-3 w-3" />
          Approve
        </button>
        <button
          onClick={onEdit}
          className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <Pencil className="h-3 w-3" />
          Edit
        </button>
        <button
          onClick={onDismiss}
          className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <X className="h-3 w-3" />
          Dismiss
        </button>
      </div>
    </div>
  );
}
