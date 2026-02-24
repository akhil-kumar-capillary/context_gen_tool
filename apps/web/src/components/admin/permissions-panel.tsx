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
        <p className="text-sm text-gray-500">
          Permissions control access to specific modules and operations.
        </p>
        <button
          onClick={() => fetchPermissions()}
          disabled={permissionsLoading}
          className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
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
              ? "bg-violet-100 text-violet-700"
              : "bg-gray-100 text-gray-500 hover:bg-gray-200"
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
                ? "bg-violet-100 text-violet-700"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200"
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
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}

      {!permissionsLoading && filtered.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-12 text-center">
          <Key className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-400">
            No permissions found.
          </p>
        </div>
      )}

      {!permissionsLoading && filtered.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="grid grid-cols-12 gap-4 bg-gray-50 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            <div className="col-span-3">Module</div>
            <div className="col-span-3">Operation</div>
            <div className="col-span-5">Description</div>
            <div className="col-span-1">ID</div>
          </div>
          {filtered.map((p) => (
            <div
              key={p.id}
              className="grid grid-cols-12 gap-4 border-b border-gray-100 px-5 py-2.5 items-center last:border-0 hover:bg-gray-50 transition-colors"
            >
              <div className="col-span-3">
                <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                  {p.module}
                </span>
              </div>
              <div className="col-span-3 text-sm text-gray-900 font-medium">
                {p.operation}
              </div>
              <div className="col-span-5 text-xs text-gray-500">
                {p.description || "—"}
              </div>
              <div className="col-span-1 text-[10px] text-gray-400 font-mono">
                {p.id}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
