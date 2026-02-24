"use client";

import { useState } from "react";
import { useAdminStore, type AdminUser, type AdminRole } from "@/stores/admin-store";
import { X, Loader2 } from "lucide-react";

interface Props {
  user: AdminUser;
  availableRoles: AdminRole[];
  onClose: () => void;
  onGranted: () => void;
}

export function GrantRoleDialog({ user, availableRoles, onClose, onGranted }: Props) {
  const { grantRole, actionLoading } = useAdminStore();
  const [selectedRole, setSelectedRole] = useState("");

  // Exclude roles the user already has
  const grantableRoles = availableRoles.filter(
    (r) => !user.roles.includes(r.name)
  );

  const handleGrant = async () => {
    if (!selectedRole) return;
    const ok = await grantRole(user.email, selectedRole);
    if (ok) onGranted();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <h3 className="text-sm font-semibold text-gray-900">Grant Role</h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-gray-100">
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
              Select Role
            </label>
            {grantableRoles.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                User already has all available roles
              </p>
            ) : (
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
              >
                <option value="">Choose a role...</option>
                {grantableRoles.map((r) => (
                  <option key={r.id} value={r.name}>
                    {r.name} {r.description ? `— ${r.description}` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
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
            disabled={!selectedRole || actionLoading}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Grant Role
          </button>
        </div>
      </div>
    </div>
  );
}
