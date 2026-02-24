"use client";

import { useEffect, useState } from "react";
import { useAdminStore, type AdminUser } from "@/stores/admin-store";
import {
  Loader2, RefreshCw, Shield, ShieldCheck, ShieldAlert, Search,
  ChevronDown, ChevronUp, Plus, Minus, Crown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { GrantRoleDialog } from "./grant-role-dialog";
import { GrantPermissionDialog } from "./grant-permission-dialog";

export function UsersTable() {
  const {
    users, usersLoading, usersError, fetchUsers,
    roles, fetchRoles,
    permissions, fetchPermissions,
    toggleAdmin, revokeRole, revokePermission,
    actionLoading, fetchAuditLogs,
  } = useAdminStore();

  const [searchTerm, setSearchTerm] = useState("");
  const [expandedUser, setExpandedUser] = useState<number | null>(null);
  const [grantRoleFor, setGrantRoleFor] = useState<AdminUser | null>(null);
  const [grantPermFor, setGrantPermFor] = useState<AdminUser | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<{
    type: "role" | "permission";
    email: string;
    value: string;
    module?: string;
    operation?: string;
  } | null>(null);
  const [confirmAdminToggle, setConfirmAdminToggle] = useState<AdminUser | null>(null);

  useEffect(() => {
    fetchUsers();
    fetchRoles();
    fetchPermissions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = users.filter(
    (u) =>
      u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (u.display_name || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleRevokeRole = async (email: string, roleName: string) => {
    const ok = await revokeRole(email, roleName);
    if (ok) {
      await fetchUsers();
      setConfirmRevoke(null);
    }
  };

  const handleRevokePermission = async (
    email: string,
    module: string,
    operation: string
  ) => {
    const ok = await revokePermission(email, module, operation);
    if (ok) {
      await fetchUsers();
      setConfirmRevoke(null);
    }
  };

  const handleToggleAdmin = async (user: AdminUser) => {
    const ok = await toggleAdmin(user.email);
    if (ok) {
      await fetchUsers();
      setConfirmAdminToggle(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search users by email or name..."
            className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
          />
        </div>
        <button
          onClick={() => fetchUsers()}
          disabled={usersLoading}
          className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
        >
          <RefreshCw className={cn("h-4 w-4", usersLoading && "animate-spin")} />
        </button>
      </div>

      {usersError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {usersError}
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-12 gap-4 bg-gray-50 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-gray-500">
          <div className="col-span-4">User</div>
          <div className="col-span-3">Roles</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-2">Last Login</div>
          <div className="col-span-1">Actions</div>
        </div>

        {usersLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        )}

        {!usersLoading && filtered.length === 0 && (
          <div className="px-5 py-12 text-center text-sm text-gray-400">
            {searchTerm ? "No users match your search" : "No users found"}
          </div>
        )}

        {filtered.map((u) => (
          <div key={u.id} className="border-b border-gray-100 last:border-0">
            {/* Main row */}
            <div className="grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-gray-50 transition-colors">
              <div className="col-span-4 min-w-0">
                <div className="flex items-center gap-2">
                  {u.is_superadmin ? (
                    <Crown className="h-4 w-4 shrink-0 text-amber-500" />
                  ) : u.is_admin ? (
                    <ShieldCheck className="h-4 w-4 shrink-0 text-violet-500" />
                  ) : (
                    <Shield className="h-4 w-4 shrink-0 text-gray-300" />
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {u.display_name || u.email}
                    </p>
                    <p className="truncate text-xs text-gray-400">{u.email}</p>
                  </div>
                </div>
              </div>
              <div className="col-span-3 flex flex-wrap gap-1">
                {u.roles.length === 0 && (
                  <span className="text-xs text-gray-400">No roles</span>
                )}
                {u.roles.map((r) => (
                  <span
                    key={r}
                    className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-700"
                  >
                    {r}
                  </span>
                ))}
              </div>
              <div className="col-span-2">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                    u.is_active
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-500"
                  )}
                >
                  {u.is_active ? "Active" : "Inactive"}
                </span>
                {u.is_superadmin && (
                  <span className="ml-1 inline-flex items-center gap-0.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                    <Crown className="h-2.5 w-2.5" /> Superadmin
                  </span>
                )}
                {u.is_admin && !u.is_superadmin && (
                  <span className="ml-1 inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-700">
                    Admin
                  </span>
                )}
              </div>
              <div className="col-span-2 text-xs text-gray-500">
                {u.last_login_at
                  ? new Date(u.last_login_at).toLocaleDateString()
                  : "Never"}
              </div>
              <div className="col-span-1">
                <button
                  onClick={() =>
                    setExpandedUser(expandedUser === u.id ? null : u.id)
                  }
                  className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                >
                  {expandedUser === u.id ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Expanded details */}
            {expandedUser === u.id && (
              <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-4 space-y-3">
                {/* Admin toggle section */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      Admin Access
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {u.is_superadmin
                        ? "Superadmin — cannot be demoted"
                        : u.is_admin
                        ? "This user has admin privileges"
                        : "This user is not an admin"}
                    </p>
                  </div>
                  {!u.is_superadmin && (
                    <>
                      {confirmAdminToggle?.id === u.id ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">
                            {u.is_admin ? "Remove admin?" : "Make admin?"}
                          </span>
                          <button
                            onClick={() => handleToggleAdmin(u)}
                            disabled={actionLoading}
                            className={cn(
                              "rounded-md px-3 py-1 text-xs font-medium text-white disabled:opacity-50",
                              u.is_admin
                                ? "bg-red-600 hover:bg-red-700"
                                : "bg-violet-600 hover:bg-violet-700"
                            )}
                          >
                            {actionLoading ? "..." : "Confirm"}
                          </button>
                          <button
                            onClick={() => setConfirmAdminToggle(null)}
                            className="rounded-md border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmAdminToggle(u)}
                          className={cn(
                            "flex items-center gap-1 rounded-md px-2.5 py-1 text-[10px] font-medium transition-all",
                            u.is_admin
                              ? "border border-red-200 text-red-600 hover:bg-red-50"
                              : "bg-amber-500 text-white hover:bg-amber-600"
                          )}
                        >
                          <ShieldAlert className="h-3 w-3" />
                          {u.is_admin ? "Remove Admin" : "Make Admin"}
                        </button>
                      )}
                    </>
                  )}
                </div>

                {/* Roles section */}
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      Roles
                    </p>
                    <button
                      onClick={() => setGrantRoleFor(u)}
                      className="flex items-center gap-1 rounded-md bg-violet-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-violet-700"
                    >
                      <Plus className="h-3 w-3" /> Grant Role
                    </button>
                  </div>
                  {u.roles.length === 0 && (
                    <p className="text-xs text-gray-400 italic">
                      No roles assigned
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {u.roles.map((r) => (
                      <span
                        key={r}
                        className="group inline-flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-1 text-xs font-medium text-violet-700"
                      >
                        {r}
                        <button
                          onClick={() =>
                            setConfirmRevoke({
                              type: "role",
                              email: u.email,
                              value: r,
                            })
                          }
                          className="ml-0.5 rounded-full p-0.5 opacity-50 hover:bg-violet-200 hover:opacity-100"
                        >
                          <Minus className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Quick grant permission */}
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                      Direct Permissions
                    </p>
                    <button
                      onClick={() => setGrantPermFor(u)}
                      className="flex items-center gap-1 rounded-md bg-blue-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-blue-700"
                    >
                      <Plus className="h-3 w-3" /> Grant Permission
                    </button>
                  </div>
                  <p className="text-xs text-gray-400">
                    Direct permissions are managed in addition to role-based permissions.
                  </p>
                </div>

                {/* Revoke confirm dialog */}
                {confirmRevoke && confirmRevoke.email === u.email && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <p className="text-sm text-amber-800">
                      Revoke{" "}
                      <strong>
                        {confirmRevoke.type === "role"
                          ? `role "${confirmRevoke.value}"`
                          : `permission "${confirmRevoke.module}.${confirmRevoke.operation}"`}
                      </strong>{" "}
                      from <strong>{confirmRevoke.email}</strong>?
                    </p>
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => {
                          if (confirmRevoke.type === "role") {
                            handleRevokeRole(
                              confirmRevoke.email,
                              confirmRevoke.value
                            );
                          } else {
                            handleRevokePermission(
                              confirmRevoke.email,
                              confirmRevoke.module!,
                              confirmRevoke.operation!
                            );
                          }
                        }}
                        disabled={actionLoading}
                        className="rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        {actionLoading ? "Revoking..." : "Confirm Revoke"}
                      </button>
                      <button
                        onClick={() => setConfirmRevoke(null)}
                        className="rounded-md border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Grant Role Dialog */}
      {grantRoleFor && (
        <GrantRoleDialog
          user={grantRoleFor}
          availableRoles={roles}
          onClose={() => setGrantRoleFor(null)}
          onGranted={async () => {
            await fetchUsers();
            setGrantRoleFor(null);
          }}
        />
      )}

      {/* Grant Permission Dialog */}
      {grantPermFor && (
        <GrantPermissionDialog
          user={grantPermFor}
          availablePermissions={permissions}
          onClose={() => setGrantPermFor(null)}
          onGranted={async () => {
            await fetchUsers();
            setGrantPermFor(null);
          }}
        />
      )}
    </div>
  );
}
