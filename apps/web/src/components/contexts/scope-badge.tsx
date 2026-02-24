"use client";

import { cn } from "@/lib/utils";

interface ScopeBadgeProps {
  scope: "org" | "private";
  onClick?: () => void;
}

export function ScopeBadge({ scope, onClick }: ScopeBadgeProps) {
  const isOrg = scope === "org";

  return (
    <span
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wide",
        isOrg
          ? "bg-blue-50 text-blue-700"
          : "bg-purple-50 text-purple-700",
        onClick && "cursor-pointer hover:opacity-80 transition-opacity"
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          isOrg ? "bg-blue-500" : "bg-purple-500"
        )}
      />
      {isOrg ? "ORG" : "PRIVATE"}
    </span>
  );
}
