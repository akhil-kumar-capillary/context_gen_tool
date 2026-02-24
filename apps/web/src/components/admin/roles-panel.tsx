"use client";

import { useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { Loader2, RefreshCw, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

export function RolesPanel() {
  const { roles, rolesLoading, rolesError, fetchRoles } = useAdminStore();

  useEffect(() => {
    fetchRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Roles define groups of permissions. Users are assigned roles to get access.
        </p>
        <button
          onClick={() => fetchRoles()}
          disabled={rolesLoading}
          className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
        >
          <RefreshCw className={cn("h-4 w-4", rolesLoading && "animate-spin")} />
        </button>
      </div>

      {rolesError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {rolesError}
        </div>
      )}

      {rolesLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}

      {!rolesLoading && roles.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-12 text-center">
          <Shield className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-400">
            No roles defined yet. Create roles via the API or seed script.
          </p>
        </div>
      )}

      {!rolesLoading && roles.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {roles.map((r) => (
            <div
              key={r.id}
              className="rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-sm"
            >
              <div className="flex items-center gap-2 mb-2">
                <Shield className="h-4 w-4 text-violet-500" />
                <h4 className="text-sm font-semibold text-gray-900">
                  {r.name}
                </h4>
              </div>
              <p className="text-xs text-gray-500">
                {r.description || "No description"}
              </p>
              <p className="mt-2 text-[10px] text-gray-400">ID: {r.id}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
