import { create } from "zustand";
import { useAuthStore } from "./auth-store";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────── */

export interface AdminUser {
  id: number;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  is_superadmin: boolean;
  is_active: boolean;
  roles: string[];
  direct_permissions: { module: string; operation: string }[];
  last_login_at: string | null;
}

export interface AdminRole {
  id: number;
  name: string;
  description: string | null;
}

export interface AdminPermission {
  id: number;
  module: string;
  operation: string;
  description: string | null;
}

export interface AuditLogEntry {
  id: number;
  user_email: string;
  action: string;
  module: string;
  resource_type: string;
  resource_id: string;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

export interface PlatformVariable {
  id: number;
  key: string;
  value: string | null;
  value_type: "string" | "number" | "boolean" | "json" | "url" | "text";
  group_name: string | null;
  description: string | null;
  default_value: string | null;
  is_required: boolean;
  validation_rule: string | null;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlatformVariableGroup {
  name: string;
  count: number;
}

export interface PlatformVariableHistory {
  id: number;
  user_email: string;
  action: string;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

/* ── State ─────────────────────────────────────────────────────────── */

interface AdminState {
  // Users
  users: AdminUser[];
  usersLoading: boolean;
  usersError: string | null;

  // Roles
  roles: AdminRole[];
  rolesLoading: boolean;
  rolesError: string | null;

  // Permissions
  permissions: AdminPermission[];
  permissionsLoading: boolean;
  permissionsError: string | null;

  // Audit Logs
  auditLogs: AuditLogEntry[];
  auditLoading: boolean;
  auditError: string | null;

  // Platform Variables
  platformVariables: PlatformVariable[];
  platformVariableGroups: PlatformVariableGroup[];
  platformVarsLoading: boolean;
  platformVarsError: string | null;

  // Action feedback
  actionLoading: boolean;
  actionMessage: string | null;
  actionError: string | null;

  // Actions
  fetchUsers: () => Promise<void>;
  fetchRoles: () => Promise<void>;
  fetchPermissions: () => Promise<void>;
  fetchAuditLogs: (limit?: number, offset?: number) => Promise<void>;

  toggleAdmin: (userEmail: string) => Promise<boolean>;
  grantRole: (userEmail: string, roleName: string) => Promise<boolean>;
  revokeRole: (userEmail: string, roleName: string) => Promise<boolean>;
  grantPermission: (userEmail: string, module: string, operation: string) => Promise<boolean>;
  revokePermission: (userEmail: string, module: string, operation: string) => Promise<boolean>;
  setPermissions: (userEmail: string, permissions: { module: string; operation: string }[]) => Promise<boolean>;

  // Platform Variable Actions
  fetchPlatformVariables: (group?: string, search?: string) => Promise<void>;
  createPlatformVariable: (data: Partial<PlatformVariable> & { key: string }) => Promise<boolean>;
  updatePlatformVariable: (id: number, data: Partial<PlatformVariable> & { change_reason?: string }) => Promise<boolean>;
  deletePlatformVariable: (id: number) => Promise<boolean>;
  fetchPlatformVariableHistory: (id: number) => Promise<PlatformVariableHistory[]>;
  importPlatformVariables: (variables: Partial<PlatformVariable>[], overwrite: boolean) => Promise<{ created: number; updated: number; errors: string[] } | null>;
  exportPlatformVariables: () => Promise<Partial<PlatformVariable>[] | null>;

  clearActionFeedback: () => void;
}

/* ── Helpers ────────────────────────────────────────────────────────── */

function authHeaders() {
  const token = useAuthStore.getState().token;
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/* ── Store ──────────────────────────────────────────────────────────── */

export const useAdminStore = create<AdminState>()((set) => ({
  users: [],
  usersLoading: false,
  usersError: null,

  roles: [],
  rolesLoading: false,
  rolesError: null,

  permissions: [],
  permissionsLoading: false,
  permissionsError: null,

  auditLogs: [],
  auditLoading: false,
  auditError: null,

  platformVariables: [],
  platformVariableGroups: [],
  platformVarsLoading: false,
  platformVarsError: null,

  actionLoading: false,
  actionMessage: null,
  actionError: null,

  /* ── Fetch ──────────────────────────────────────────────────────── */

  fetchUsers: async () => {
    set({ usersLoading: true, usersError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users`, { headers: authHeaders() });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ users: data.users || [], usersLoading: false });
    } catch (e) {
      set({ usersError: e instanceof Error ? e.message : "Failed to load users", usersLoading: false });
    }
  },

  fetchRoles: async () => {
    set({ rolesLoading: true, rolesError: null });
    try {
      const resp = await fetch(`${API}/api/admin/roles`, { headers: authHeaders() });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ roles: data.roles || [], rolesLoading: false });
    } catch (e) {
      set({ rolesError: e instanceof Error ? e.message : "Failed to load roles", rolesLoading: false });
    }
  },

  fetchPermissions: async () => {
    set({ permissionsLoading: true, permissionsError: null });
    try {
      const resp = await fetch(`${API}/api/admin/permissions`, { headers: authHeaders() });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ permissions: data.permissions || [], permissionsLoading: false });
    } catch (e) {
      set({ permissionsError: e instanceof Error ? e.message : "Failed to load permissions", permissionsLoading: false });
    }
  },

  fetchAuditLogs: async (limit = 100, offset = 0) => {
    set({ auditLoading: true, auditError: null });
    try {
      const resp = await fetch(
        `${API}/api/admin/audit-logs?limit=${limit}&offset=${offset}`,
        { headers: authHeaders() }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ auditLogs: data.logs || [], auditLoading: false });
    } catch (e) {
      set({ auditError: e instanceof Error ? e.message : "Failed to load audit logs", auditLoading: false });
    }
  },

  /* ── Mutations ──────────────────────────────────────────────────── */

  toggleAdmin: async (userEmail) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/toggle-admin`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  grantRole: async (userEmail, roleName) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/grant-role`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail, role_name: roleName }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  revokeRole: async (userEmail, roleName) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/revoke-role`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail, role_name: roleName }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  grantPermission: async (userEmail, module, operation) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/grant-permission`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail, module, operation }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  revokePermission: async (userEmail, module, operation) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/revoke-permission`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail, module, operation }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  setPermissions: async (userEmail, permissions) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/users/set-permissions`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_email: userEmail, permissions }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      set({ actionMessage: data.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  /* ── Platform Variables ──────────────────────────────────────────── */

  fetchPlatformVariables: async (group?, search?) => {
    set({ platformVarsLoading: true, platformVarsError: null });
    try {
      const params = new URLSearchParams();
      if (group) params.set("group", group);
      if (search) params.set("search", search);
      const qs = params.toString();
      const resp = await fetch(
        `${API}/api/admin/platform-variables${qs ? `?${qs}` : ""}`,
        { headers: authHeaders() },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({
        platformVariables: data.variables || [],
        platformVariableGroups: data.groups || [],
        platformVarsLoading: false,
      });
    } catch (e) {
      set({ platformVarsError: e instanceof Error ? e.message : "Failed to load variables", platformVarsLoading: false });
    }
  },

  createPlatformVariable: async (data) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/platform-variables`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || `HTTP ${resp.status}`);
      set({ actionMessage: result.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  updatePlatformVariable: async (id, data) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/platform-variables/${id}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || `HTTP ${resp.status}`);
      set({ actionMessage: result.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  deletePlatformVariable: async (id) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/platform-variables/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || `HTTP ${resp.status}`);
      set({ actionMessage: result.message, actionLoading: false });
      return true;
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return false;
    }
  },

  fetchPlatformVariableHistory: async (id) => {
    try {
      const resp = await fetch(
        `${API}/api/admin/platform-variables/${id}/history`,
        { headers: authHeaders() },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return data.history || [];
    } catch {
      return [];
    }
  },

  importPlatformVariables: async (variables, overwrite) => {
    set({ actionLoading: true, actionMessage: null, actionError: null });
    try {
      const resp = await fetch(`${API}/api/admin/platform-variables/import`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ variables, overwrite }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || `HTTP ${resp.status}`);
      set({ actionMessage: result.message, actionLoading: false });
      return { created: result.created, updated: result.updated, errors: result.errors };
    } catch (e) {
      set({ actionError: e instanceof Error ? e.message : "Failed", actionLoading: false });
      return null;
    }
  },

  exportPlatformVariables: async () => {
    try {
      const resp = await fetch(`${API}/api/admin/platform-variables/export`, {
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return data.variables || [];
    } catch {
      return null;
    }
  },

  clearActionFeedback: () => set({ actionMessage: null, actionError: null }),
}));
