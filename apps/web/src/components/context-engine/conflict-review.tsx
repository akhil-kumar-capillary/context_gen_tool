"use client";

import { useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface Conflict {
  id: string;
  doc_a_name: string;
  doc_a_key: string;
  doc_a_excerpt: string;
  doc_b_name: string;
  doc_b_key: string;
  doc_b_excerpt: string;
  description: string;
  severity: "high" | "medium" | "low";
  suggested_resolution: string;
}

type Resolution = "keep_a" | "keep_b" | "keep_both";

interface ConflictReviewProps {
  conflicts: Conflict[];
  onResolveAll: (resolutions: Record<string, Resolution>) => void;
  onDismiss: () => void;
}

const SEVERITY_COLORS = {
  high: "bg-red-50 border-red-200 text-red-800",
  medium: "bg-amber-50 border-amber-200 text-amber-800",
  low: "bg-blue-50 border-blue-200 text-blue-700",
};

const SEVERITY_BADGES = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-blue-100 text-blue-700",
};

/**
 * Git-conflict-style review panel for contradictions between contexts.
 * Shows side-by-side comparison with resolution options per conflict.
 */
export function ConflictReview({
  conflicts,
  onResolveAll,
  onDismiss,
}: ConflictReviewProps) {
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [expandedId, setExpandedId] = useState<string | null>(
    conflicts[0]?.id || null,
  );

  const allResolved = conflicts.every((c) => resolutions[c.id]);

  const setResolution = (conflictId: string, resolution: Resolution) => {
    setResolutions((prev) => ({ ...prev, [conflictId]: resolution }));
  };

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-5">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-full bg-amber-100 p-2">
          <AlertTriangle className="h-5 w-5 text-amber-600" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {conflicts.length} Contradiction{conflicts.length > 1 ? "s" : ""}{" "}
            Detected
          </h3>
          <p className="text-xs text-muted-foreground">
            Review and resolve before building the tree. Unresolved conflicts
            will be kept as-is.
          </p>
        </div>
      </div>

      {/* Conflict list */}
      <div className="space-y-3">
        {conflicts.map((conflict) => {
          const isExpanded = expandedId === conflict.id;
          const resolution = resolutions[conflict.id];

          return (
            <div
              key={conflict.id}
              className={cn(
                "rounded-lg border bg-background transition-all",
                resolution
                  ? "border-green-200 bg-green-50/30"
                  : SEVERITY_COLORS[conflict.severity],
              )}
            >
              {/* Conflict header */}
              <button
                onClick={() =>
                  setExpandedId(isExpanded ? null : conflict.id)
                }
                className="flex w-full items-center gap-3 p-3 text-left"
              >
                {resolution ? (
                  <Check className="h-4 w-4 shrink-0 text-green-600" />
                ) : (
                  <AlertTriangle
                    className={cn(
                      "h-4 w-4 shrink-0",
                      conflict.severity === "high"
                        ? "text-red-500"
                        : conflict.severity === "medium"
                          ? "text-amber-500"
                          : "text-blue-500",
                    )}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-medium text-foreground truncate block">
                    {conflict.doc_a_name} vs {conflict.doc_b_name}
                  </span>
                  <span className="text-xs text-muted-foreground truncate block">
                    {conflict.description}
                  </span>
                </div>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs font-medium",
                    SEVERITY_BADGES[conflict.severity],
                  )}
                >
                  {conflict.severity}
                </span>
                {isExpanded ? (
                  <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="border-t border-border p-4 space-y-4">
                  {/* Side-by-side excerpts */}
                  <div className="grid grid-cols-2 gap-3">
                    <div
                      className={cn(
                        "rounded-lg border p-3",
                        resolution === "keep_a"
                          ? "border-green-300 bg-green-50"
                          : resolution === "keep_b"
                            ? "border-red-200 bg-red-50/30 opacity-60"
                            : "border-border",
                      )}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs font-semibold text-foreground">
                          {conflict.doc_a_name}
                        </span>
                        {resolution === "keep_a" && (
                          <span className="text-xs font-medium text-green-600">
                            KEPT
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                        {conflict.doc_a_excerpt || "(no specific excerpt)"}
                      </p>
                    </div>

                    <div
                      className={cn(
                        "rounded-lg border p-3",
                        resolution === "keep_b"
                          ? "border-green-300 bg-green-50"
                          : resolution === "keep_a"
                            ? "border-red-200 bg-red-50/30 opacity-60"
                            : "border-border",
                      )}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs font-semibold text-foreground">
                          {conflict.doc_b_name}
                        </span>
                        {resolution === "keep_b" && (
                          <span className="text-xs font-medium text-green-600">
                            KEPT
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                        {conflict.doc_b_excerpt || "(no specific excerpt)"}
                      </p>
                    </div>
                  </div>

                  {/* AI suggestion */}
                  {conflict.suggested_resolution && (
                    <div className="rounded-md bg-blue-50 px-3 py-2">
                      <p className="text-xs text-blue-700">
                        <span className="font-semibold">AI suggestion:</span>{" "}
                        {conflict.suggested_resolution}
                      </p>
                    </div>
                  )}

                  {/* Resolution buttons */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => setResolution(conflict.id, "keep_a")}
                      className={cn(
                        "flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                        resolution === "keep_a"
                          ? "border-green-500 bg-green-50 text-green-700"
                          : "border-border text-muted-foreground hover:bg-muted/50",
                      )}
                    >
                      Keep &ldquo;{conflict.doc_a_name}&rdquo;
                    </button>
                    <button
                      onClick={() => setResolution(conflict.id, "keep_b")}
                      className={cn(
                        "flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                        resolution === "keep_b"
                          ? "border-green-500 bg-green-50 text-green-700"
                          : "border-border text-muted-foreground hover:bg-muted/50",
                      )}
                    >
                      Keep &ldquo;{conflict.doc_b_name}&rdquo;
                    </button>
                    <button
                      onClick={() => setResolution(conflict.id, "keep_both")}
                      className={cn(
                        "flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                        resolution === "keep_both"
                          ? "border-blue-500 bg-blue-50 text-blue-700"
                          : "border-border text-muted-foreground hover:bg-muted/50",
                      )}
                    >
                      Keep Both
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={onDismiss}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Skip review (keep all as-is)
        </button>
        <button
          onClick={() => onResolveAll(resolutions)}
          disabled={!allResolved}
          className={cn(
            "rounded-lg px-4 py-2 text-xs font-medium transition-colors",
            allResolved
              ? "bg-green-600 text-white hover:bg-green-700"
              : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          {allResolved
            ? `Apply ${conflicts.length} Resolution${conflicts.length > 1 ? "s" : ""}`
            : `Resolve All (${Object.keys(resolutions).length}/${conflicts.length})`}
        </button>
      </div>
    </div>
  );
}
