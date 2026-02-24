"use client";

import { useState, useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useAdminStore } from "@/stores/admin-store";
import { useRouter } from "next/navigation";
import { UsersTable } from "@/components/admin/users-table";
import { RolesPanel } from "@/components/admin/roles-panel";
import { PermissionsPanel } from "@/components/admin/permissions-panel";
import { AuditLogViewer } from "@/components/admin/audit-log-viewer";
import { cn } from "@/lib/utils";
import {
  Users, Shield, Key, ScrollText, Check, AlertCircle, X,
} from "lucide-react";

type AdminTab = "users" | "roles" | "permissions" | "audit";

const tabs: { id: AdminTab; label: string; icon: typeof Users }[] = [
  { id: "users", label: "Users", icon: Users },
  { id: "roles", label: "Roles", icon: Shield },
  { id: "permissions", label: "Permissions", icon: Key },
  { id: "audit", label: "Audit Logs", icon: ScrollText },
];

export default function AdminPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const { actionMessage, actionError, clearActionFeedback } = useAdminStore();
  const [activeTab, setActiveTab] = useState<AdminTab>("users");

  useEffect(() => {
    if (user && !user.isAdmin) {
      router.replace("/dashboard/contexts");
    }
  }, [user, router]);

  // Auto-clear feedback after 4s
  useEffect(() => {
    if (actionMessage || actionError) {
      const timer = setTimeout(clearActionFeedback, 4000);
      return () => clearTimeout(timer);
    }
  }, [actionMessage, actionError, clearActionFeedback]);

  if (!user?.isAdmin) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
        <p className="text-sm text-gray-500">
          Manage users, roles, permissions, and view audit logs.
        </p>
      </div>

      {/* Action feedback toast */}
      {(actionMessage || actionError) && (
        <div
          className={cn(
            "flex items-center justify-between rounded-lg px-4 py-2.5 text-sm",
            actionMessage
              ? "border border-green-200 bg-green-50 text-green-700"
              : "border border-red-200 bg-red-50 text-red-700"
          )}
        >
          <div className="flex items-center gap-2">
            {actionMessage ? (
              <Check className="h-4 w-4" />
            ) : (
              <AlertCircle className="h-4 w-4" />
            )}
            <span>{actionMessage || actionError}</span>
          </div>
          <button
            onClick={clearActionFeedback}
            className="rounded-md p-1 hover:bg-black/5"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            )}
          >
            <tab.icon className="h-3.5 w-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "users" && <UsersTable />}
      {activeTab === "roles" && <RolesPanel />}
      {activeTab === "permissions" && <PermissionsPanel />}
      {activeTab === "audit" && <AuditLogViewer />}
    </div>
  );
}
