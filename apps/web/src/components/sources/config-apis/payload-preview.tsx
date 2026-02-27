"use client";

import { useConfigApisStore } from "@/stores/config-apis-store";
import { cn } from "@/lib/utils";
import { FileJson, AlertTriangle } from "lucide-react";

interface PayloadPreviewProps {
  docKey: string;
}

export function PayloadPreview({ docKey }: PayloadPreviewProps) {
  const { payloadPreviews, tokenBudgets, isLoadingPayloads } =
    useConfigApisStore();

  const preview = payloadPreviews?.[docKey];
  const budget = tokenBudgets[docKey] || 12000;

  if (isLoadingPayloads) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        <div className="animate-pulse">Building payload preview...</div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-sm text-gray-400 gap-2">
        <FileJson className="h-8 w-8" />
        <span>No payload generated for this doc type</span>
      </div>
    );
  }

  const overBudget = preview.est_tokens > budget * 1.2;
  const budgetPct = Math.round((preview.est_tokens / budget) * 100);

  return (
    <div className="flex flex-col h-full">
      {/* Size indicator bar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-3 text-xs">
          <span className="text-gray-500">
            {preview.chars.toLocaleString()} chars
          </span>
          <span className="text-gray-300">|</span>
          <span
            className={cn(
              "font-medium",
              overBudget ? "text-red-600" : "text-gray-600"
            )}
          >
            ~{preview.est_tokens.toLocaleString()} tokens
          </span>
          <span className="text-gray-300">|</span>
          <span className="text-gray-500">
            budget: {budget.toLocaleString()}
          </span>
        </div>

        {overBudget && (
          <div className="flex items-center gap-1 text-xs text-red-600">
            <AlertTriangle className="h-3 w-3" />
            <span>{budgetPct}% of budget</span>
          </div>
        )}
      </div>

      {/* Budget bar */}
      <div className="h-1 bg-gray-100">
        <div
          className={cn(
            "h-full transition-all",
            overBudget ? "bg-red-500" : budgetPct > 80 ? "bg-amber-400" : "bg-violet-400"
          )}
          style={{ width: `${Math.min(budgetPct, 100)}%` }}
        />
      </div>

      {/* JSON content */}
      <div className="flex-1 overflow-auto">
        <pre className="p-3 text-xs text-gray-700 font-mono whitespace-pre-wrap break-all leading-relaxed">
          {preview.payload}
        </pre>
      </div>
    </div>
  );
}
