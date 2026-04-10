"use client";

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

/**
 * Animated shimmer skeleton placeholder for loading states.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-gray-200",
        className,
      )}
    />
  );
}

/**
 * Pre-built skeleton layouts for common page patterns.
 */

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-8 w-32" />
        <div className="flex-1" />
        <Skeleton className="h-8 w-24" />
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 rounded-lg border border-gray-100 p-4">
          <Skeleton className="h-5 w-5 rounded" />
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-24" />
          <div className="flex-1" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-lg border border-gray-200 p-6 space-y-4">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <div className="flex gap-3 pt-2">
        <Skeleton className="h-9 w-24 rounded-lg" />
        <Skeleton className="h-9 w-24 rounded-lg" />
      </div>
    </div>
  );
}

export function TreeSkeleton() {
  return (
    <div className="space-y-2 p-4">
      <Skeleton className="h-6 w-56" />
      <div className="ml-6 space-y-2">
        <Skeleton className="h-5 w-44" />
        <div className="ml-6 space-y-2">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-5 w-48" />
        <div className="ml-6 space-y-2">
          <Skeleton className="h-4 w-38" />
          <Skeleton className="h-4 w-34" />
        </div>
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* Title bar */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-7 w-48" />
        <div className="flex gap-2">
          <Skeleton className="h-9 w-28 rounded-lg" />
          <Skeleton className="h-9 w-28 rounded-lg" />
        </div>
      </div>
      {/* Content area */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TableSkeleton rows={4} />
        </div>
        <CardSkeleton />
      </div>
    </div>
  );
}

export function SidebarSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2">
          <Skeleton className="h-4 w-4 rounded" />
          <Skeleton className="h-4 w-24" />
        </div>
      ))}
    </div>
  );
}
