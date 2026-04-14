"use client";

import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { Loader2, RefreshCw, Key } from "lucide-react";
import { cn } from "@/lib/utils";

export function PermissionsPanel() {
  const { permissions, permissionsLoading, permissionsError, fetchPermissions } =
    useAdminStore();
  const [filterModule, setFilterModule] = useState<string>("all");

  useEffect(() => {
    fetchPermissions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const modules = Array.from(
    new Set(permissions.map((p) => p.module))
  ).sort();

  const filtered =
    filterModule === "all"
      ? permissions
      : permissions.filter((p) => p.module === filterModule);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Permissions control access to specific modules and operations.
        </p>
        <button
          onClick={() => fetchPermissions()}
          disabled={permissionsLoading}
          className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted/50"
        >
          <RefreshCw
            className={cn("h-4 w-4", permissionsLoading && "animate-spin")}
          />
        </button>
      </div>

      {/* Module filter */}
      <div className="flex flex-wrap gap-1">
        <button
          onClick={() => setFilterModule("all")}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
            filterModule === "all"
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground hover:bg-muted"
          )}
        >
          All ({permissions.length})
        </button>
        {modules.map((mod) => (
          <button
            key={mod}
            onClick={() => setFilterModule(mod)}
            className={cn(
              "rounded-md px-3 py-1 text-xs font-medium transition-colors",
              filterModule === mod
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground hover:bg-muted"
            )}
          >
            {mod} (
            {permissions.filter((p) => p.module === mod).length})
          </button>
        ))}
      </div>

      {permissionsError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {permissionsError}
        </div>
      )}

      {permissionsLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!permissionsLoading && filtered.length === 0 && (
        <div className="rounded-xl border border-border bg-background px-5 py-12 text-center">
          <Key className="mx-auto h-8 w-8 text-muted-foreground/50" />
          <p className="mt-2 text-sm text-muted-foreground">
            No permissions found.
          </p>
        </div>
      )}

      {!permissionsLoading && filtered.length > 0 && (
        <div className="rounded-xl border border-border bg-background overflow-hidden">
          <div className="grid grid-cols-12 gap-4 bg-muted/50 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <div className="col-span-3">Module</div>
            <div className="col-span-3">Operation</div>
            <div className="col-span-5">Description</div>
            <div className="col-span-1">ID</div>
          </div>
          {filtered.map((p) => (
            <div
              key={p.id}
              className="grid grid-cols-12 gap-4 border-b border-border px-5 py-2.5 items-center last:border-0 hover:bg-muted/50 transition-colors"
            >
              <div className="col-span-3">
                <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                  {p.module}
                </span>
              </div>
              <div className="col-span-3 text-sm text-foreground font-medium">
                {p.operation}
              </div>
              <div className="col-span-5 text-xs text-muted-foreground">
                {p.description || "—"}
              </div>
              <div className="col-span-1 text-xs text-muted-foreground font-mono">
                {p.id}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
