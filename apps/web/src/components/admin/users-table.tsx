"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useAdminStore, type AdminUser } from "@/stores/admin-store";
import {
  Loader2, RefreshCw, Shield, ShieldCheck, ShieldAlert, Search,
  ChevronDown, ChevronUp, Plus, Minus, Crown, Save,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { GrantRoleDialog } from "./grant-role-dialog";

/* ── Module definitions (matches seed_data.py) ─────────────────────── */

const MODULES: Record<
  string,
  { label: string; operations: { key: string; label: string }[] }
> = {
  databricks: {
    label: "Databricks",
    operations: [
      { key: "view", label: "View" },
      { key: "extract", label: "Extract" },
      { key: "analyze", label: "Analyze" },
      { key: "generate", label: "Generate Docs" },
    ],
  },
  confluence: {
    label: "Confluence",
    operations: [
      { key: "view", label: "View" },
      { key: "connect", label: "Connect" },
      { key: "extract", label: "Extract" },
      { key: "generate", label: "Generate Docs" },
    ],
  },
  config_apis: {
    label: "Config APIs",
    operations: [
      { key: "view", label: "View" },
      { key: "fetch", label: "Fetch Data" },
      { key: "analyze", label: "Analyze" },
      { key: "generate", label: "Generate Docs" },
    ],
  },
  context_management: {
    label: "Context Management",
    operations: [
      { key: "view", label: "View" },
      { key: "create", label: "Create" },
      { key: "edit", label: "Edit" },
      { key: "delete", label: "Delete" },
      { key: "refactor", label: "Refactor" },
    ],
  },
  context_engine: {
    label: "Context Engine",
    operations: [
      { key: "view", label: "View" },
      { key: "edit", label: "Edit" },
      { key: "generate", label: "Generate" },
      { key: "sync", label: "Sync" },
    ],
  },
  admin: {
    label: "Admin",
    operations: [
      { key: "view", label: "View" },
      { key: "manage_users", label: "Manage Users" },
      { key: "manage_secrets", label: "Manage Secrets" },
    ],
  },
};

const MODULE_KEYS = Object.keys(MODULES);

/* ── Module color map for badges ───────────────────────────────────── */

const MODULE_COLORS: Record<string, string> = {
  databricks: "bg-blue-100 text-blue-700",
  confluence: "bg-emerald-100 text-emerald-700",
  config_apis: "bg-orange-100 text-orange-700",
  context_management: "bg-cyan-100 text-cyan-700",
  context_engine: "bg-pink-100 text-pink-700",
  admin: "bg-amber-100 text-amber-700",
};

/* ── ModuleAccessTree component ────────────────────────────────────── */

type PermSet = Set<string>; // "module:operation"

function permKey(module: string, op: string) {
  return `${module}:${op}`;
}

function ModuleAccessTree({
  user,
  onSaved,
}: {
  user: AdminUser;
  onSaved: () => void;
}) {
  const { setPermissions, actionLoading } = useAdminStore();

  // Initialize local state from user's current permissions
  const serverPerms = useMemo(() => {
    const s = new Set<string>();
    for (const p of user.direct_permissions) {
      s.add(permKey(p.module, p.operation));
    }
    return s;
  }, [user.direct_permissions]);

  const [localPerms, setLocalPerms] = useState<PermSet>(new Set(serverPerms));

  // Reset when server state changes
  useEffect(() => {
    setLocalPerms(new Set(serverPerms));
  }, [serverPerms]);

  const isDirty = useMemo(() => {
    if (localPerms.size !== serverPerms.size) return true;
    for (const k of localPerms) {
      if (!serverPerms.has(k)) return true;
    }
    return false;
  }, [localPerms, serverPerms]);

  const togglePerm = useCallback((module: string, op: string) => {
    setLocalPerms((prev) => {
      const next = new Set(prev);
      const key = permKey(module, op);

      if (op === "view") {
        // Toggling view: if turning OFF, remove ALL ops for this module
        if (next.has(key)) {
          for (const o of MODULES[module].operations) {
            next.delete(permKey(module, o.key));
          }
        } else {
          // Turning ON view
          next.add(key);
        }
      } else {
        // Non-view operation
        if (next.has(key)) {
          next.delete(key);
        } else {
          // Turning on a non-view op also ensures "view" is on
          next.add(key);
          next.add(permKey(module, "view"));
        }
      }
      return next;
    });
  }, []);

  const toggleModule = useCallback((module: string) => {
    setLocalPerms((prev) => {
      const next = new Set(prev);
      const ops = MODULES[module].operations;
      const hasAny = ops.some((o) => next.has(permKey(module, o.key)));

      if (hasAny) {
        // Uncheck all
        for (const o of ops) {
          next.delete(permKey(module, o.key));
        }
      } else {
        // Check module → auto-check "view" (minimum access)
        next.add(permKey(module, "view"));
      }
      return next;
    });
  }, []);

  const handleSave = async () => {
    const perms: { module: string; operation: string }[] = [];
    for (const k of localPerms) {
      const [mod, op] = k.split(":");
      perms.push({ module: mod, operation: op });
    }
    const ok = await setPermissions(user.email, perms);
    if (ok) onSaved();
  };

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
        Module Access
      </p>

      <div className="rounded-lg border border-gray-200 bg-white divide-y divide-gray-100">
        {MODULE_KEYS.map((mod) => {
          const modDef = MODULES[mod];
          const ops = modDef.operations;
          const checkedOps = ops.filter((o) =>
            localPerms.has(permKey(mod, o.key))
          );
          const isActive = checkedOps.length > 0;
          const allChecked = checkedOps.length === ops.length;
          const indeterminate = isActive && !allChecked;

          return (
            <div key={mod} className="px-3 py-2">
              {/* Module parent checkbox */}
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={isActive}
                  ref={(el) => {
                    if (el) el.indeterminate = indeterminate;
                  }}
                  onChange={() => toggleModule(mod)}
                  className="h-3.5 w-3.5 rounded border-gray-300 text-violet-600 focus:ring-violet-500"
                />
                <span className="text-sm font-medium text-gray-800 group-hover:text-gray-900">
                  {modDef.label}
                </span>
                {isActive && (
                  <span className="text-[10px] text-gray-400 ml-1">
                    {checkedOps.length}/{ops.length}
                  </span>
                )}
              </label>

              {/* Child operation checkboxes — only shown when module is active */}
              {isActive && (
                <div className="mt-1.5 ml-5 flex flex-wrap gap-x-4 gap-y-1">
                  {ops.map((op) => {
                    const checked = localPerms.has(permKey(mod, op.key));
                    const isView = op.key === "view";
                    // View cannot be unchecked while other ops are checked
                    const viewLocked =
                      isView &&
                      checkedOps.some((o) => o.key !== "view");

                    return (
                      <label
                        key={op.key}
                        className={cn(
                          "flex items-center gap-1.5 cursor-pointer",
                          viewLocked && "opacity-60 cursor-not-allowed"
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={viewLocked}
                          onChange={() => togglePerm(mod, op.key)}
                          className="h-3 w-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                        />
                        <span className="text-xs text-gray-600">
                          {op.label}
                          {isView && (
                            <span className="text-[10px] text-gray-400 ml-0.5">
                              (required)
                            </span>
                          )}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Save button — only when dirty */}
      {isDirty && (
        <div className="flex justify-end pt-1">
          <button
            onClick={handleSave}
            disabled={actionLoading}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {actionLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Save className="h-3 w-3" />
            )}
            Save Changes
          </button>
        </div>
      )}
    </div>
  );
}

/* ── UsersTable component ──────────────────────────────────────────── */

export function UsersTable() {
  const {
    users, usersLoading, usersError, fetchUsers,
    roles, fetchRoles,
    fetchPermissions,
    toggleAdmin, revokeRole,
    actionLoading,
  } = useAdminStore();

  const [searchTerm, setSearchTerm] = useState("");
  const [expandedUser, setExpandedUser] = useState<number | null>(null);
  const [grantRoleFor, setGrantRoleFor] = useState<AdminUser | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<{
    type: "role";
    email: string;
    value: string;
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

  const handleToggleAdmin = async (user: AdminUser) => {
    const ok = await toggleAdmin(user.email);
    if (ok) {
      await fetchUsers();
      setConfirmAdminToggle(null);
    }
  };

  /** Get unique module names from user's direct permissions */
  const getUserModules = (u: AdminUser) =>
    Array.from(new Set(u.direct_permissions.map((p) => p.module)));

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
          <div className="col-span-3">User</div>
          <div className="col-span-2">Roles</div>
          <div className="col-span-3">Modules</div>
          <div className="col-span-1">Status</div>
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

        {filtered.map((u) => {
          const userModules = getUserModules(u);

          return (
            <div key={u.id} className="border-b border-gray-100 last:border-0">
              {/* Main row */}
              <div className="grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-gray-50 transition-colors">
                <div className="col-span-3 min-w-0">
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
                <div className="col-span-2 flex flex-wrap gap-1">
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
                {/* Module tags */}
                <div className="col-span-3 flex flex-wrap gap-1">
                  {userModules.length === 0 && (
                    <span className="text-xs text-gray-400">No modules</span>
                  )}
                  {userModules.map((mod) => (
                    <span
                      key={mod}
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
                        MODULE_COLORS[mod] || "bg-gray-100 text-gray-600"
                      )}
                    >
                      {MODULES[mod]?.label || mod}
                    </span>
                  ))}
                </div>
                <div className="col-span-1">
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
                      <Crown className="h-2.5 w-2.5" /> Super
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
                <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-4 space-y-4">
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

                  {/* Module Access Tree — replaces old "Direct Permissions" */}
                  <ModuleAccessTree
                    user={u}
                    onSaved={async () => {
                      await fetchUsers();
                    }}
                  />

                  {/* Revoke confirm dialog */}
                  {confirmRevoke && confirmRevoke.email === u.email && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <p className="text-sm text-amber-800">
                        Revoke{" "}
                        <strong>role &quot;{confirmRevoke.value}&quot;</strong>{" "}
                        from <strong>{confirmRevoke.email}</strong>?
                      </p>
                      <div className="mt-2 flex gap-2">
                        <button
                          onClick={() =>
                            handleRevokeRole(
                              confirmRevoke.email,
                              confirmRevoke.value
                            )
                          }
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
          );
        })}
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
    </div>
  );
}
