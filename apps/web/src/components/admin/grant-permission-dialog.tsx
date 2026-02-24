"use client";

import { useState } from "react";
import { useAdminStore, type AdminUser, type AdminPermission } from "@/stores/admin-store";
import { X, Loader2 } from "lucide-react";

interface Props {
  user: AdminUser;
  availablePermissions: AdminPermission[];
  onClose: () => void;
  onGranted: () => void;
}

export function GrantPermissionDialog({
  user,
  availablePermissions,
  onClose,
  onGranted,
}: Props) {
  const { grantPermission, actionLoading } = useAdminStore();
  const [selectedPermId, setSelectedPermId] = useState("");

  // Group permissions by module
  const modules = Array.from(
    new Set(availablePermissions.map((p) => p.module))
  ).sort();

  const selectedPerm = availablePermissions.find(
    (p) => String(p.id) === selectedPermId
  );

  const handleGrant = async () => {
    if (!selectedPerm) return;
    const ok = await grantPermission(
      user.email,
      selectedPerm.module,
      selectedPerm.operation
    );
    if (ok) onGranted();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <h3 className="text-sm font-semibold text-gray-900">
            Grant Permission
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 hover:bg-gray-100"
          >
            <X className="h-4 w-4 text-gray-400" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <div>
            <p className="text-xs text-gray-500">User</p>
            <p className="text-sm font-medium text-gray-900">
              {user.display_name || user.email}
            </p>
            <p className="text-xs text-gray-400">{user.email}</p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Select Permission
            </label>
            <select
              value={selectedPermId}
              onChange={(e) => setSelectedPermId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
            >
              <option value="">Choose a permission...</option>
              {modules.map((mod) => (
                <optgroup key={mod} label={mod}>
                  {availablePermissions
                    .filter((p) => p.module === mod)
                    .map((p) => (
                      <option key={p.id} value={String(p.id)}>
                        {p.module}.{p.operation}
                        {p.description ? ` — ${p.description}` : ""}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </div>

          {selectedPerm && (
            <div className="rounded-lg bg-blue-50 p-3">
              <p className="text-xs font-medium text-blue-700">
                {selectedPerm.module}.{selectedPerm.operation}
              </p>
              {selectedPerm.description && (
                <p className="mt-0.5 text-xs text-blue-600">
                  {selectedPerm.description}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-gray-200 px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleGrant}
            disabled={!selectedPerm || actionLoading}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {actionLoading && (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            )}
            Grant Permission
          </button>
        </div>
      </div>
    </div>
  );
}
