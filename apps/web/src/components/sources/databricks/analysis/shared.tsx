"use client";

import React from "react";

// ---------------------------------------------------------------------------
// Badge – reusable across all analysis tabs
// ---------------------------------------------------------------------------

export type BadgeVariant =
  | "default"
  | "blue"
  | "green"
  | "amber"
  | "red"
  | "purple"
  | "cyan";

const BADGE_COLORS: Record<BadgeVariant, string> = {
  default: "bg-gray-100 text-gray-500 border-gray-200",
  blue: "bg-blue-50 text-blue-600 border-blue-200",
  green: "bg-emerald-50 text-emerald-600 border-emerald-200",
  amber: "bg-amber-50 text-amber-600 border-amber-200",
  red: "bg-red-50 text-red-600 border-red-200",
  purple: "bg-purple-50 text-purple-600 border-purple-200",
  cyan: "bg-cyan-50 text-cyan-600 border-cyan-200",
};

export const Badge = React.memo(function Badge({
  children,
  variant = "default",
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
}) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${BADGE_COLORS[variant]}`}
    >
      {children}
    </span>
  );
});

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

/** Format an ISO date string for short display (e.g. "Jan 15, 2025"). */
export function formatShortDate(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

/** Abbreviate a long path to show the last 2 segments. */
export function abbreviatePath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return ".../" + parts.slice(-2).join("/");
}

// ---------------------------------------------------------------------------
// Nivo chart theme constants
// ---------------------------------------------------------------------------

/** Standard tooltip styling for all Nivo charts in the analysis dashboard. */
export const NIVO_TOOLTIP_THEME = {
  tooltip: {
    container: {
      background: "#fff",
      color: "#111",
      borderRadius: "8px",
      border: "1px solid #e5e7eb",
      boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
      padding: "8px 12px",
      fontSize: "12px",
    },
  },
} as const;

/** Axis + grid styling for Nivo bar charts. */
export const NIVO_BAR_THEME = {
  axis: {
    ticks: {
      text: { fontSize: 11, fontFamily: "monospace" },
    },
  },
  grid: {
    line: { stroke: "#e5e7eb", strokeDasharray: "4 4" },
  },
  ...NIVO_TOOLTIP_THEME,
} as const;
