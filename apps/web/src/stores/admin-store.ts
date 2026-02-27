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

  clearActionFeedback: () => set({ actionMessage: null, actionError: null }),
}));
